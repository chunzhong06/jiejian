# =============================================================================
# Business Boundary Proposal 应用事务
#
# 职责
#   形成 discovery 预览与不可变 Proposal，并在单一 UoW 原子批准 Actor/Action/Permission。
#
# 边界
#   只有本服务能写正式 Boundary；Candidate 仅校验来源快照和生成 ImplementationBinding。
# =============================================================================

from __future__ import annotations

from product.backend.core.assurance import compile_action_assurance
from product.backend.core.permission_intent import permission_relation_consistent

import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from product.backend.core.approval import HumanApproval, HumanApprovalChannel
from product.backend.core.application_understanding import (
    ApplicationUnderstanding,
    CandidateDecision,
)
from product.backend.core.boundary_proposal import (
    BoundaryDecisionKind,
    BoundaryProposalBundle,
    BoundaryProposalDecision,
    BoundarySourceSnapshot,
    CandidateSourceSnapshot,
    ProposalCandidateKind,
    ProposalWriteMode,
    ProposedActionItem,
    ProposedActorItem,
    ProposedEffectItem,
    ProposedPermissionItem,
)
from product.backend.core.business_boundary import (
    ActionImplementationBinding,
    ActorImplementationBinding,
    BusinessAction,
    BusinessActionRevision,
    BusinessActor,
    BusinessActorRevision,
    BusinessEffectDefinition,
    BusinessRevisionState,
    ImplementationCandidateSnapshot,
    boundary_sha256,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState,
    PermissionIntentRevision,
    PermissionIntentSemantic,
    ProjectPolicyState,
    permission_intent_sha256,
)
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.business_boundaries.fingerprints import (
    candidate_source_snapshot,
    implementation_candidate_snapshot,
    legacy_candidate_source_snapshot,
)
from product.backend.workflows.business_boundaries.inspection import (
    ActionImplementationInspection,
    ActorImplementationInspection,
    inspect_action_binding,
    inspect_actor_binding,
)
from product.backend.workflows.business_boundaries.maintenance import (
    build_maintenance_draft,
    maintenance_to_proposal_command,
    proposal_change_summary,
)
from product.backend.workflows.business_boundaries.models import (
    BoundaryDraftCandidate,
    BoundaryDraftView,
    BoundaryMaintenanceCommand,
    BoundaryMaintenanceDraftView,
    BoundaryProposalCommand,
    BoundaryProposalListView,
    BoundaryProposalView,
    BusinessBoundaryView,
    PermissionBoundaryStatus,
)


@dataclass(frozen=True)
class _ActorPlan:
    item: ProposedActorItem
    root: BusinessActor
    revision: BusinessActorRevision
    binding: ActorImplementationBinding | None
    write_revision: bool
    write_binding: bool
    create_root: bool


@dataclass(frozen=True)
class _ActionPlan:
    item: ProposedActionItem
    root: BusinessAction
    revision: BusinessActionRevision
    effect_ids: dict[str, str]
    binding: ActionImplementationBinding | None
    write_revision: bool
    write_binding: bool
    create_root: bool


@dataclass(frozen=True)
class _PermissionPlan:
    item: ProposedPermissionItem
    semantic: PermissionIntentSemantic
    intent_id: str
    revision: int
    write_revision: bool


@dataclass(frozen=True)
class _MaintenanceFacts:
    actor_roots: tuple[BusinessActor, ...]
    action_roots: tuple[BusinessAction, ...]
    actors: tuple[BusinessActorRevision, ...]
    actions: tuple[BusinessActionRevision, ...]
    permissions: tuple[PermissionIntentRevision, ...]
    actor_bindings: tuple[ActorImplementationBinding, ...]
    action_bindings: tuple[ActionImplementationBinding, ...]
    actor_inspections: tuple[ActorImplementationInspection, ...]
    action_inspections: tuple[ActionImplementationInspection, ...]
    understanding: ApplicationUnderstanding
    policy_epoch: int


class BusinessBoundaryService:
    """把 Proposal/Decision 与全部正式 revision 保持在一个显式事务中。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)

    def preview_from_discovery(self, project_id: str) -> BoundaryDraftView:
        with self._uow_factory() as work:
            understanding = self._understanding(work, project_id)
        candidates = tuple(
            sorted(
                (
                    *(
                        BoundaryDraftCandidate(
                            candidate_kind="ROLE",
                            candidate_id=item.candidate_id,
                            display_name=item.display_name,
                            confidence=item.confidence.value,
                        )
                        for item in understanding.role_candidates
                        if not item.stale and item.decision is not CandidateDecision.REJECTED
                    ),
                    *(
                        BoundaryDraftCandidate(
                            candidate_kind="ACTION",
                            candidate_id=item.candidate_id,
                            display_name=item.display_name,
                            confidence=item.confidence.value,
                        )
                        for item in understanding.action_candidates
                        if not item.stale and item.decision is not CandidateDecision.REJECTED
                    ),
                ),
                key=lambda item: (item.candidate_kind, item.candidate_id),
            )
        )
        return BoundaryDraftView(
            project_id=project_id,
            application_understanding_revision=understanding.revision,
            candidates=candidates,
        )

    def create_proposal(
        self,
        project_id: str,
        command: BoundaryProposalCommand,
    ) -> BoundaryProposalView:
        with self._uow_factory() as work:
            understanding = self._understanding(work, project_id)
            proposal = self._build_proposal(project_id, command, understanding)
            work.business_boundaries.add_proposal(proposal)
            view = self._proposal_view(work, proposal)
            work.commit()
        return view

    def create_initial_proposal(
        self,
        project_id: str,
        command: BoundaryProposalCommand,
    ) -> BoundaryProposalView:
        """HTTP 首次建立入口；已有正式 identity 后必须进入 maintenance。"""

        with self._uow_factory() as work:
            if (
                work.business_boundaries.list_actors(project_id)
                or work.business_boundaries.list_actions(project_id)
            ):
                self._raise(
                    ErrorCode.BOUNDARY_MAINTENANCE_REQUIRED,
                    "项目已有正式业务边界，请使用维护流程",
                )
            understanding = self._understanding(work, project_id)
            proposal = self._build_proposal(project_id, command, understanding)
            work.business_boundaries.add_proposal(proposal)
            view = self._proposal_view(work, proposal)
            work.commit()
        return view

    def maintenance_draft(self, project_id: str) -> BoundaryMaintenanceDraftView:
        with self._uow_factory() as work:
            facts = self._maintenance_facts(work, project_id)
        return build_maintenance_draft(
            project_id,
            facts.actor_roots,
            facts.action_roots,
            facts.actors,
            facts.actions,
            facts.permissions,
            facts.actor_inspections,
            facts.action_inspections,
            facts.understanding,
            facts.policy_epoch,
        )

    def create_maintenance_proposal(
        self,
        project_id: str,
        command: BoundaryMaintenanceCommand,
    ) -> BoundaryProposalView:
        """在同一事务中防 pending、防并发，并把 desired state 冻结为 Proposal。"""

        with self._uow_factory() as work:
            facts = self._maintenance_facts(work, project_id)
            pending = next(
                (
                    item
                    for item in work.business_boundaries.list_proposals(project_id)
                    if work.business_boundaries.decision_for_proposal(item.proposal_id)
                    is None
                ),
                None,
            )
            if pending is not None:
                raise JiejianError(
                    ErrorCode.BOUNDARY_PROPOSAL_PENDING,
                    "项目已有待审业务边界提案",
                    details={"proposal_id": pending.proposal_id},
                )
            proposal_command = maintenance_to_proposal_command(
                project_id,
                command,
                facts.actor_roots,
                facts.action_roots,
                facts.actors,
                facts.actions,
                facts.permissions,
                facts.policy_epoch,
            )
            proposal = self._build_proposal(
                project_id,
                proposal_command,
                facts.understanding,
            )
            work.business_boundaries.add_proposal(proposal)
            view = BoundaryProposalView(
                proposal=proposal,
                change_summary=proposal_change_summary(
                    proposal,
                    facts.permissions,
                    facts.actor_bindings,
                    facts.action_bindings,
                ),
            )
            work.commit()
        return view

    def proposals(
        self,
        project_id: str,
        *,
        pending_only: bool = False,
    ) -> BoundaryProposalListView:
        """读取不可变 Proposal 及追加式 Decision，供页面恢复待审状态。"""

        with self._uow_factory() as work:
            values = tuple(
                self._proposal_view(work, proposal)
                for proposal in work.business_boundaries.list_proposals(project_id)
            )
        if pending_only:
            values = tuple(item for item in values if item.decision is None)
        return BoundaryProposalListView(project_id=project_id, proposals=values)

    def proposal(self, project_id: str, proposal_id: str) -> BoundaryProposalView:
        with self._uow_factory() as work:
            proposal = work.business_boundaries.get_proposal(proposal_id)
            if proposal is None or proposal.project_id != project_id:
                self._raise(ErrorCode.BOUNDARY_PROPOSAL_NOT_FOUND, "业务边界提案不存在")
            view = self._proposal_view(work, proposal)
        return view

    def approve(
        self,
        project_id: str,
        proposal_id: str,
        *,
        expected_fingerprint: str,
        reason: str,
    ) -> BusinessBoundaryView:
        clean_reason = self._reason(reason)
        with self._uow_factory() as work:
            proposal = self._pending_proposal(
                work,
                project_id,
                proposal_id,
                expected_fingerprint,
            )
            if proposal.unresolved_questions:
                self._raise(
                    ErrorCode.BOUNDARY_PROPOSAL_UNRESOLVED,
                    "业务边界提案仍有未解决问题",
                )
            understanding = self._understanding(work, project_id)
            self._validate_source_snapshot(proposal.source_snapshot, understanding)
            now_us = self._clock_us()
            approval = HumanApproval(
                channel=HumanApprovalChannel.LOCAL_GUI,
                approved_by="本机界鉴用户",
                approved_at_us=now_us,
                reason=clean_reason,
            )

            # 先完整构造并交叉校验全部写入对象，随后才按固定顺序触碰 Repository。
            actor_plans = self._plan_actors(
                work,
                proposal,
                approval,
                understanding,
                now_us,
            )
            action_plans = self._plan_actions(
                work,
                proposal,
                approval,
                understanding,
                now_us,
            )
            permission_plans = self._plan_permissions(
                work,
                proposal,
                actor_plans,
                action_plans,
            )
            current_state = work.permission_intents.policy_state(project_id)
            current_epoch = 0 if current_state is None else current_state.policy_epoch
            permission_changed = any(item.write_revision for item in permission_plans)
            next_epoch = current_epoch + 1 if permission_changed else current_epoch

            for plan in actor_plans:
                if not plan.write_revision:
                    continue
                work.business_boundaries.add_actor_revision(plan.revision)
                if plan.create_root:
                    work.business_boundaries.add_actor(plan.root)
                else:
                    work.business_boundaries.replace_actor(plan.root)
            for plan in action_plans:
                if not plan.write_revision:
                    continue
                work.business_boundaries.add_action_revision(plan.revision)
                if plan.create_root:
                    work.business_boundaries.add_action(plan.root)
                else:
                    work.business_boundaries.replace_action(plan.root)
            for plan in permission_plans:
                if plan.write_revision:
                    revision = PermissionIntentRevision(
                        **plan.semantic.model_dump(),
                        intent_id=plan.intent_id,
                        project_id=project_id,
                        revision=plan.revision,
                        intent_hash=permission_intent_sha256(plan.semantic.canonical_payload()),
                        policy_epoch=next_epoch,
                        approval=approval,
                        created_at_us=now_us,
                    )
                    work.permission_intents.add_revision(revision)
            for plan in actor_plans:
                if plan.write_binding:
                    assert plan.binding is not None
                    work.business_boundaries.replace_actor_binding(plan.binding)
            for plan in action_plans:
                if plan.write_binding:
                    assert plan.binding is not None
                    work.business_boundaries.replace_action_binding(plan.binding)
            if permission_changed:
                work.permission_intents.replace_policy_state(
                    ProjectPolicyState(
                        project_id=project_id,
                        policy_epoch=next_epoch,
                        updated_at_us=now_us,
                    )
                )
            decision = BoundaryProposalDecision(
                decision_id=f"bpd_{uuid4().hex}",
                proposal_id=proposal_id,
                proposal_fingerprint=proposal.proposal_fingerprint,
                decision=BoundaryDecisionKind.APPROVED,
                decided_by="本机界鉴用户",
                decided_at_us=now_us,
                reason=clean_reason,
            )
            work.business_boundaries.add_decision(decision)
            work.commit()
        return self.view(project_id)

    def reject(
        self,
        project_id: str,
        proposal_id: str,
        *,
        expected_fingerprint: str,
        reason: str,
    ) -> BoundaryProposalView:
        clean_reason = self._reason(reason)
        with self._uow_factory() as work:
            proposal = self._pending_proposal(
                work,
                project_id,
                proposal_id,
                expected_fingerprint,
            )
            decision = BoundaryProposalDecision(
                decision_id=f"bpd_{uuid4().hex}",
                proposal_id=proposal_id,
                proposal_fingerprint=proposal.proposal_fingerprint,
                decision=BoundaryDecisionKind.REJECTED,
                decided_by="本机界鉴用户",
                decided_at_us=self._clock_us(),
                reason=clean_reason,
            )
            work.business_boundaries.add_decision(decision)
            view = self._proposal_view(work, proposal)
            work.commit()
        return view

    def view(self, project_id: str) -> BusinessBoundaryView:
        with self._uow_factory() as work:
            actor_roots = work.business_boundaries.list_actors(project_id)
            action_roots = work.business_boundaries.list_actions(project_id)
            actors = tuple(
                revision
                for root in actor_roots
                if (
                    revision := work.business_boundaries.actor_revision(
                        root.actor_id, root.current_revision
                    )
                ) is not None
                and revision.effective_state is BusinessRevisionState.ACTIVE
            )
            actions = tuple(
                revision
                for root in action_roots
                if (
                    revision := work.business_boundaries.action_revision(
                        root.action_id, root.current_revision
                    )
                ) is not None
                and revision.effective_state is BusinessRevisionState.ACTIVE
            )
            latest_intents = work.permission_intents.list_latest(project_id)
            state = work.permission_intents.policy_state(project_id)
            understanding = self._understanding(work, project_id)
            actor_bindings = tuple(
                inspect_actor_binding(
                    actor.actor_id,
                    actor.revision,
                    work.business_boundaries.actor_binding(
                        actor.actor_id, actor.revision
                    ),
                    understanding,
                )
                for actor in actors
            )
            action_bindings = tuple(
                inspect_action_binding(
                    action.action_id,
                    action.revision,
                    work.business_boundaries.action_binding(
                        action.action_id, action.revision
                    ),
                    understanding,
                )
                for action in actions
            )
        intents, stale_intents = self._current_permission_intents(
            latest_intents,
            actors,
            actions,
        )
        statuses = tuple(
            self._permission_status(action, intents, stale_intents)
            for action in actions
        )
        return BusinessBoundaryView(
            project_id=project_id,
            policy_epoch=0 if state is None else state.policy_epoch,
            actors=tuple(sorted(actors, key=lambda item: item.actor_id)),
            actions=tuple(sorted(actions, key=lambda item: item.action_id)),
            actor_bindings=tuple(sorted(actor_bindings, key=lambda item: item.actor_id)),
            action_bindings=tuple(sorted(action_bindings, key=lambda item: item.action_id)),
            permission_intents=intents,
            permission_statuses=statuses,
        )

    def _maintenance_facts(
        self,
        work: StorageUnitOfWork,
        project_id: str,
    ) -> _MaintenanceFacts:
        actor_roots = work.business_boundaries.list_actors(project_id)
        action_roots = work.business_boundaries.list_actions(project_id)
        if not actor_roots and not action_roots:
            self._raise(
                ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID,
                "项目尚未建立正式业务边界",
            )
        actors = tuple(
            work.business_boundaries.actor_revision(
                root.actor_id,
                root.current_revision,
            )
            for root in actor_roots
        )
        actions = tuple(
            work.business_boundaries.action_revision(
                root.action_id,
                root.current_revision,
            )
            for root in action_roots
        )
        if any(item is None for item in (*actors, *actions)):
            self._raise(
                ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID,
                "业务边界 root 指向不存在的 revision",
            )
        current_actors = tuple(item for item in actors if item is not None)
        current_actions = tuple(item for item in actions if item is not None)
        permissions = work.permission_intents.list_latest(project_id)
        state = work.permission_intents.policy_state(project_id)
        understanding = self._understanding(work, project_id)
        actor_bindings = tuple(
            binding
            for item in current_actors
            if (
                binding := work.business_boundaries.actor_binding(
                    item.actor_id,
                    item.revision,
                )
            )
            is not None
        )
        action_bindings = tuple(
            binding
            for item in current_actions
            if (
                binding := work.business_boundaries.action_binding(
                    item.action_id,
                    item.revision,
                )
            )
            is not None
        )
        actor_binding_by_key = {
            (item.actor_id, item.actor_revision): item for item in actor_bindings
        }
        action_binding_by_key = {
            (item.action_id, item.action_revision): item for item in action_bindings
        }
        actor_inspections = tuple(
            inspect_actor_binding(
                item.actor_id,
                item.revision,
                actor_binding_by_key.get((item.actor_id, item.revision)),
                understanding,
            )
            for item in current_actors
        )
        action_inspections = tuple(
            inspect_action_binding(
                item.action_id,
                item.revision,
                action_binding_by_key.get((item.action_id, item.revision)),
                understanding,
            )
            for item in current_actions
        )
        return _MaintenanceFacts(
            actor_roots=actor_roots,
            action_roots=action_roots,
            actors=current_actors,
            actions=current_actions,
            permissions=permissions,
            actor_bindings=actor_bindings,
            action_bindings=action_bindings,
            actor_inspections=actor_inspections,
            action_inspections=action_inspections,
            understanding=understanding,
            policy_epoch=0 if state is None else state.policy_epoch,
        )

    @staticmethod
    def _proposal_view(
        work: StorageUnitOfWork,
        proposal: BoundaryProposalBundle,
    ) -> BoundaryProposalView:
        actor_bindings = tuple(
            binding
            for item in proposal.proposed_actors
            if item.actor_id is not None
            and item.expected_current_revision is not None
            and (
                binding := work.business_boundaries.actor_binding(
                    item.actor_id,
                    item.expected_current_revision,
                )
            )
            is not None
        )
        action_bindings = tuple(
            binding
            for item in proposal.proposed_actions
            if item.action_id is not None
            and item.expected_current_revision is not None
            and (
                binding := work.business_boundaries.action_binding(
                    item.action_id,
                    item.expected_current_revision,
                )
            )
            is not None
        )
        return BoundaryProposalView(
            proposal=proposal,
            decision=work.business_boundaries.decision_for_proposal(
                proposal.proposal_id
            ),
            change_summary=proposal_change_summary(
                proposal,
                work.permission_intents.list_latest(proposal.project_id),
                actor_bindings,
                action_bindings,
            ),
        )

    def _build_proposal(
        self,
        project_id: str,
        command: BoundaryProposalCommand,
        understanding: ApplicationUnderstanding,
    ) -> BoundaryProposalBundle:
        # 只在新写入入口校验；已持久 Proposal/revision 仍可原样读取和人工审查。
        actor_items = {item.item_id: item for item in command.proposed_actors}
        for permission in command.proposed_permissions:
            subject = actor_items.get(permission.subject_actor_item_id)
            owner = actor_items.get(permission.resource_owner_actor_item_id)
            if subject is None or owner is None:
                self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "权限引用的业务主体不存在")
            subject_key = (subject.actor_id or subject.item_id, (subject.expected_current_revision or 1)
                           + int(subject.write_mode is ProposalWriteMode.APPEND_REVISION))
            owner_key = (owner.actor_id or owner.item_id, (owner.expected_current_revision or 1)
                         + int(owner.write_mode is ProposalWriteMode.APPEND_REVISION))
            if not permission_relation_consistent(permission.relation, subject_key, owner_key):
                self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "权限资源关系与业务主体不一致")
        source_snapshot = self._source_snapshot(understanding, command)
        proposal_id = f"bpr_{uuid4().hex}"
        created_at_us = self._clock_us()
        fingerprint_payload = {
            "proposal_id": proposal_id,
            "project_id": project_id,
            "source_snapshot": source_snapshot.model_dump(mode="json"),
            "proposed_actors": [
                item.model_dump(mode="json") for item in command.proposed_actors
            ],
            "proposed_actions": [
                item.model_dump(mode="json") for item in command.proposed_actions
            ],
            "proposed_permissions": [
                item.model_dump(mode="json") for item in command.proposed_permissions
            ],
            "unresolved_questions": list(command.unresolved_questions),
            "provenance": command.provenance,
            "created_at_us": created_at_us,
        }
        return BoundaryProposalBundle(
            proposal_id=proposal_id,
            project_id=project_id,
            source_snapshot=source_snapshot,
            proposed_actors=command.proposed_actors,
            proposed_actions=command.proposed_actions,
            proposed_permissions=command.proposed_permissions,
            unresolved_questions=command.unresolved_questions,
            provenance=command.provenance,
            created_at_us=created_at_us,
            proposal_fingerprint=boundary_sha256(fingerprint_payload),
        )

    def actor_revision(
        self,
        project_id: str,
        actor_id: str,
        revision: int,
    ) -> BusinessActorRevision:
        with self._uow_factory() as work:
            value = work.business_boundaries.actor_revision(actor_id, revision)
        if value is None or value.project_id != project_id:
            self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务主体 revision 不存在")
        return value

    def _pending_proposal(
        self,
        work: StorageUnitOfWork,
        project_id: str,
        proposal_id: str,
        expected_fingerprint: str,
    ) -> BoundaryProposalBundle:
        proposal = work.business_boundaries.get_proposal(proposal_id)
        if proposal is None or proposal.project_id != project_id:
            self._raise(ErrorCode.BOUNDARY_PROPOSAL_NOT_FOUND, "业务边界提案不存在")
        if work.business_boundaries.decision_for_proposal(proposal_id) is not None:
            self._raise(ErrorCode.BOUNDARY_PROPOSAL_ALREADY_DECIDED, "业务边界提案已经作出决定")
        actual = boundary_sha256(proposal.fingerprint_payload())
        if actual != proposal.proposal_fingerprint or expected_fingerprint != actual:
            self._raise(
                ErrorCode.BOUNDARY_PROPOSAL_FINGERPRINT_MISMATCH,
                "业务边界提案内容已变化，请重新打开后决定",
            )
        return proposal

    def _plan_actors(
        self,
        work: StorageUnitOfWork,
        proposal: BoundaryProposalBundle,
        approval: HumanApproval,
        understanding: ApplicationUnderstanding,
        now_us: int,
    ) -> tuple[_ActorPlan, ...]:
        plans: list[_ActorPlan] = []
        for item in proposal.proposed_actors:
            if item.write_mode is ProposalWriteMode.CREATE:
                actor_id = f"bar_{uuid4().hex}"
                revision_number = 1
                current = None
            else:
                assert item.actor_id is not None and item.expected_current_revision is not None
                actor_id = item.actor_id
                current = work.business_boundaries.actor(actor_id)
                if (
                    current is None
                    or current.project_id != proposal.project_id
                    or current.current_revision != item.expected_current_revision
                ):
                    self._raise(ErrorCode.BOUNDARY_REVISION_CONFLICT, "业务主体当前 revision 已变化")
                revision_number = (
                    current.current_revision
                    if item.write_mode is ProposalWriteMode.REFERENCE
                    else current.current_revision + 1
                )
            fingerprint = boundary_sha256(
                {
                    "actor_id": actor_id,
                    "project_id": proposal.project_id,
                    "display_name": item.display_name,
                    "description": item.description,
                    "effective_state": item.effective_state.value,
                }
            )
            revision = BusinessActorRevision(
                actor_id=actor_id,
                project_id=proposal.project_id,
                revision=revision_number,
                display_name=item.display_name,
                description=item.description,
                semantic_fingerprint=fingerprint,
                effective_state=item.effective_state,
                approval=approval,
                created_at_us=now_us,
            )
            if item.write_mode is ProposalWriteMode.REFERENCE:
                stored = work.business_boundaries.actor_revision(actor_id, revision_number)
                if stored is None or stored.semantic_fingerprint != fingerprint:
                    self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务主体引用与当前事实不一致")
                revision = stored
                assert current is not None
                root = current
                write_revision = False
                create_root = False
            else:
                if current is not None:
                    previous = work.business_boundaries.actor_revision(actor_id, current.current_revision)
                    if previous is not None and previous.semantic_fingerprint == fingerprint:
                        self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务主体新 revision 没有语义变化")
                    root = BusinessActor(
                        actor_id=actor_id,
                        project_id=proposal.project_id,
                        current_revision=revision_number,
                        created_at_us=current.created_at_us,
                        updated_at_us=now_us,
                    )
                    create_root = False
                else:
                    root = BusinessActor(
                        actor_id=actor_id,
                        project_id=proposal.project_id,
                        current_revision=1,
                        created_at_us=now_us,
                        updated_at_us=now_us,
                    )
                    create_root = True
                write_revision = True
            replacement = self._actor_binding(
                item,
                revision,
                proposal.proposal_id,
                understanding,
                now_us,
            )
            stored_binding = work.business_boundaries.actor_binding(
                revision.actor_id,
                revision.revision,
            )
            write_binding = write_revision or self._binding_changed(
                stored_binding,
                replacement,
            )
            plans.append(
                _ActorPlan(
                    item,
                    root,
                    revision,
                    replacement if write_binding else None,
                    write_revision,
                    write_binding,
                    create_root,
                )
            )
        return tuple(plans)

    def _plan_actions(
        self,
        work: StorageUnitOfWork,
        proposal: BoundaryProposalBundle,
        approval: HumanApproval,
        understanding: ApplicationUnderstanding,
        now_us: int,
    ) -> tuple[_ActionPlan, ...]:
        plans: list[_ActionPlan] = []
        for item in proposal.proposed_actions:
            current_revision: BusinessActionRevision | None = None
            if item.write_mode is ProposalWriteMode.CREATE:
                action_id = f"bac_{uuid4().hex}"
                revision_number = 1
                current = None
            else:
                assert item.action_id is not None and item.expected_current_revision is not None
                action_id = item.action_id
                current = work.business_boundaries.action(action_id)
                if (
                    current is None
                    or current.project_id != proposal.project_id
                    or current.current_revision != item.expected_current_revision
                ):
                    self._raise(ErrorCode.BOUNDARY_REVISION_CONFLICT, "业务动作当前 revision 已变化")
                current_revision = work.business_boundaries.action_revision(action_id, current.current_revision)
                if current_revision is None:
                    self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务动作 revision 不存在")
                revision_number = (
                    current.current_revision
                    if item.write_mode is ProposalWriteMode.REFERENCE
                    else current.current_revision + 1
                )
            effects, effect_ids = self._resolve_effects(item, current_revision)
            semantic_payload = {
                "action_id": action_id,
                "project_id": proposal.project_id,
                "display_name": item.display_name,
                "description": item.description,
                "primary_resource_concept": item.primary_resource_concept,
                "operation_kind": item.operation_kind.value,
                "state_changing": item.state_changing,
                "effect_catalog": [effect.model_dump(mode="json") for effect in effects],
                "effective_state": item.effective_state.value,
            }
            fingerprint = boundary_sha256(semantic_payload)
            revision = BusinessActionRevision(
                action_id=action_id,
                project_id=proposal.project_id,
                revision=revision_number,
                display_name=item.display_name,
                description=item.description,
                primary_resource_concept=item.primary_resource_concept,
                operation_kind=item.operation_kind,
                state_changing=item.state_changing,
                effect_catalog=effects,
                semantic_fingerprint=fingerprint,
                effective_state=item.effective_state,
                approval=approval,
                created_at_us=now_us,
            )
            if item.write_mode is ProposalWriteMode.REFERENCE:
                assert current_revision is not None and current is not None
                if current_revision.semantic_fingerprint != fingerprint:
                    self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务动作引用与当前事实不一致")
                revision = current_revision
                root = current
                write_revision = False
                create_root = False
            else:
                if current is not None:
                    assert current_revision is not None
                    if current_revision.semantic_fingerprint == fingerprint:
                        self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务动作新 revision 没有语义变化")
                    root = BusinessAction(
                        action_id=action_id,
                        project_id=proposal.project_id,
                        current_revision=revision_number,
                        created_at_us=current.created_at_us,
                        updated_at_us=now_us,
                    )
                    create_root = False
                else:
                    root = BusinessAction(
                        action_id=action_id,
                        project_id=proposal.project_id,
                        current_revision=1,
                        created_at_us=now_us,
                        updated_at_us=now_us,
                    )
                    create_root = True
                write_revision = True
            replacement = self._action_binding(
                item,
                revision,
                proposal.proposal_id,
                understanding,
                now_us,
            )
            stored_binding = work.business_boundaries.action_binding(
                revision.action_id,
                revision.revision,
            )
            write_binding = write_revision or self._binding_changed(
                stored_binding,
                replacement,
            )
            plans.append(
                _ActionPlan(
                    item,
                    root,
                    revision,
                    effect_ids,
                    replacement if write_binding else None,
                    write_revision,
                    write_binding,
                    create_root,
                )
            )
        return tuple(plans)

    def _resolve_effects(
        self,
        item: ProposedActionItem,
        current: BusinessActionRevision | None,
    ) -> tuple[tuple[BusinessEffectDefinition, ...], dict[str, str]]:
        existing = {} if current is None else {effect.effect_id: effect for effect in current.effect_catalog}
        effects: list[BusinessEffectDefinition] = []
        local_to_formal: dict[str, str] = {}
        for proposed in item.effect_catalog:
            if item.write_mode is ProposalWriteMode.CREATE and proposed.effect_id is not None:
                self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "新业务动作不能指定正式 Effect ID")
            effect_id = proposed.effect_id or f"bef_{uuid4().hex}"
            effect = self._effect(effect_id, proposed)
            if proposed.effect_id is not None:
                if proposed.effect_id not in existing or existing[proposed.effect_id] != effect:
                    self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "复用 Effect 与冻结定义不一致")
            effects.append(effect)
            local_to_formal[proposed.item_id] = effect_id
        return tuple(effects), local_to_formal

    def _plan_permissions(
        self,
        work: StorageUnitOfWork,
        proposal: BoundaryProposalBundle,
        actors: tuple[_ActorPlan, ...],
        actions: tuple[_ActionPlan, ...],
    ) -> tuple[_PermissionPlan, ...]:
        actor_by_item = {plan.item.item_id: plan.revision for plan in actors}
        action_by_item = {plan.item.item_id: plan for plan in actions}
        plans: list[_PermissionPlan] = []
        for item in proposal.proposed_permissions:
            subject = actor_by_item[item.subject_actor_item_id]
            owner = actor_by_item[item.resource_owner_actor_item_id]
            if not permission_relation_consistent(
                item.relation, (subject.actor_id, subject.revision), (owner.actor_id, owner.revision)
            ):
                self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "权限资源关系与业务主体不一致")
            action_plan = action_by_item[item.business_action_item_id]
            action = action_plan.revision
            protected_ids = tuple(action_plan.effect_ids[value] for value in item.protected_effect_item_ids)
            if item.effective_state is PermissionIntentEffectiveState.ACTIVE and (
                subject.effective_state is not BusinessRevisionState.ACTIVE
                or owner.effective_state is not BusinessRevisionState.ACTIVE
                or action.effective_state is not BusinessRevisionState.ACTIVE
            ):
                self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "ACTIVE 权限必须引用 ACTIVE 业务 revision")
            semantic = PermissionIntentSemantic(
                effective_state=item.effective_state,
                subject_actor_id=subject.actor_id,
                subject_actor_revision=subject.revision,
                business_action_id=action.action_id,
                action_revision=action.revision,
                resource_owner_actor_id=owner.actor_id,
                resource_owner_actor_revision=owner.revision,
                relation=item.relation,
                expectation=item.expectation,
                protected_effect_ids=protected_ids,
            )
            if item.write_mode is ProposalWriteMode.CREATE:
                intent_id = f"pin_{uuid4().hex}"
                revision_number = 1
                write_revision = True
            else:
                assert item.intent_id is not None and item.expected_current_revision is not None
                latest = work.permission_intents.latest(item.intent_id)
                if (
                    latest is None
                    or latest.project_id != proposal.project_id
                    or latest.revision != item.expected_current_revision
                ):
                    self._raise(ErrorCode.BOUNDARY_REVISION_CONFLICT, "权限当前 revision 已变化")
                current_semantic = PermissionIntentSemantic.model_validate(
                    latest.model_dump(include=set(PermissionIntentSemantic.model_fields))
                )
                if item.write_mode is ProposalWriteMode.REFERENCE:
                    if current_semantic != semantic:
                        self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "权限引用与当前事实不一致")
                    revision_number = latest.revision
                    write_revision = False
                else:
                    if current_semantic == semantic:
                        self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "权限新 revision 没有语义变化")
                    revision_number = latest.revision + 1
                    write_revision = True
                intent_id = item.intent_id
            plans.append(_PermissionPlan(item, semantic, intent_id, revision_number, write_revision))
        return tuple(plans)

    def _actor_binding(
        self,
        item: ProposedActorItem,
        revision: BusinessActorRevision,
        source_proposal_id: str,
        understanding: ApplicationUnderstanding,
        now_us: int,
    ) -> ActorImplementationBinding:
        snapshots = self._implementation_snapshots(
            ProposalCandidateKind.ROLE,
            item.source_candidate_ids,
            understanding,
        )
        payload = {
            "actor_id": revision.actor_id,
            "actor_revision": revision.revision,
            "understanding_revision": understanding.revision,
            "source_fingerprint": understanding.source_fingerprint,
            "role_candidate_ids": list(item.source_candidate_ids),
            "basis_version": 2,
            "source_proposal_id": source_proposal_id,
            "confirmed_at_us": now_us,
            "candidate_snapshots": [
                item.model_dump(mode="json") for item in snapshots
            ],
        }
        return ActorImplementationBinding(
            actor_id=revision.actor_id,
            actor_revision=revision.revision,
            understanding_revision=understanding.revision,
            source_fingerprint=understanding.source_fingerprint,
            basis_version=2,
            source_proposal_id=source_proposal_id,
            confirmed_at_us=now_us,
            role_candidate_ids=item.source_candidate_ids,
            candidate_snapshots=snapshots,
            binding_fingerprint=boundary_sha256(payload),
            updated_at_us=now_us,
        )

    def _action_binding(
        self,
        item: ProposedActionItem,
        revision: BusinessActionRevision,
        source_proposal_id: str,
        understanding: ApplicationUnderstanding,
        now_us: int,
    ) -> ActionImplementationBinding:
        snapshots = self._implementation_snapshots(
            ProposalCandidateKind.ACTION,
            item.source_candidate_ids,
            understanding,
        )
        payload = {
            "action_id": revision.action_id,
            "action_revision": revision.revision,
            "understanding_revision": understanding.revision,
            "source_fingerprint": understanding.source_fingerprint,
            "action_candidate_ids": list(item.source_candidate_ids),
            "basis_version": 2,
            "source_proposal_id": source_proposal_id,
            "confirmed_at_us": now_us,
            "candidate_snapshots": [
                item.model_dump(mode="json") for item in snapshots
            ],
        }
        return ActionImplementationBinding(
            action_id=revision.action_id,
            action_revision=revision.revision,
            understanding_revision=understanding.revision,
            source_fingerprint=understanding.source_fingerprint,
            basis_version=2,
            source_proposal_id=source_proposal_id,
            confirmed_at_us=now_us,
            action_candidate_ids=item.source_candidate_ids,
            candidate_snapshots=snapshots,
            binding_fingerprint=boundary_sha256(payload),
            updated_at_us=now_us,
        )

    @staticmethod
    def _implementation_snapshots(
        kind: ProposalCandidateKind,
        candidate_ids: tuple[str, ...],
        understanding: ApplicationUnderstanding,
    ) -> tuple[ImplementationCandidateSnapshot, ...]:
        candidates = (
            understanding.role_candidates
            if kind is ProposalCandidateKind.ROLE
            else understanding.action_candidates
        )
        by_id = {item.candidate_id: item for item in candidates}
        return tuple(
            implementation_candidate_snapshot(
                candidate_source_snapshot(kind, by_id[candidate_id])
            )
            for candidate_id in candidate_ids
        )

    @staticmethod
    def _binding_changed(
        stored: ActorImplementationBinding | ActionImplementationBinding | None,
        replacement: ActorImplementationBinding | ActionImplementationBinding,
    ) -> bool:
        """只比较批准技术来源；新 Proposal/time 本身不制造 rebind。"""

        if stored is None or stored.basis_version != 2:
            return True
        if isinstance(stored, ActorImplementationBinding) and isinstance(
            replacement,
            ActorImplementationBinding,
        ):
            return (
                stored.role_candidate_ids != replacement.role_candidate_ids
                or stored.candidate_snapshots != replacement.candidate_snapshots
            )
        if isinstance(stored, ActionImplementationBinding) and isinstance(
            replacement,
            ActionImplementationBinding,
        ):
            return (
                stored.action_candidate_ids != replacement.action_candidate_ids
                or stored.candidate_snapshots != replacement.candidate_snapshots
            )
        raise TypeError("implementation binding kind changed")

    @staticmethod
    def _current_permission_intents(
        latest: tuple[PermissionIntentRevision, ...],
        actors: tuple[BusinessActorRevision, ...],
        actions: tuple[BusinessActionRevision, ...],
    ) -> tuple[
        tuple[PermissionIntentRevision, ...],
        tuple[PermissionIntentRevision, ...],
    ]:
        """从 latest 历史中投影只精确引用当前 ACTIVE 边界的权限。"""

        actor_revisions = {item.actor_id: item.revision for item in actors}
        action_revisions = {item.action_id: item for item in actions}
        current: list[PermissionIntentRevision] = []
        stale: list[PermissionIntentRevision] = []
        for intent in latest:
            action = action_revisions.get(intent.business_action_id)
            effect_ids = set() if action is None else {
                effect.effect_id for effect in action.effect_catalog
            }
            is_current = (
                intent.effective_state is PermissionIntentEffectiveState.ACTIVE
                and actor_revisions.get(intent.subject_actor_id)
                == intent.subject_actor_revision
                and actor_revisions.get(intent.resource_owner_actor_id)
                == intent.resource_owner_actor_revision
                and action is not None
                and action.revision == intent.action_revision
                and set(intent.protected_effect_ids) <= effect_ids
            )
            (current if is_current else stale).append(intent)
        return tuple(current), tuple(stale)

    @staticmethod
    def _permission_status(
        action: BusinessActionRevision,
        intents: tuple[PermissionIntentRevision, ...],
        stale_intents: tuple[PermissionIntentRevision, ...] = (),
    ) -> PermissionBoundaryStatus:
        active = tuple(
            item
            for item in intents
            if item.effective_state is PermissionIntentEffectiveState.ACTIVE
            and item.business_action_id == action.action_id
            and item.action_revision == action.revision
        )
        contract = compile_action_assurance(action, active)
        related_stale = tuple(
            item for item in stale_intents if item.business_action_id == action.action_id
        )
        allow_control = "ALLOW_CONTROL_REQUIRED" not in contract.reason_codes
        reasons: list[str] = []
        if not active:
            reasons.append(
                "PERMISSION_REVISION_REVIEW_REQUIRED"
                if related_stale
                else "PERMISSION_SEMANTICS_REQUIRED"
            )
        reasons.extend(reason for reason in contract.reason_codes
                       if reason != "PERMISSION_SEMANTICS_REQUIRED" and reason not in reasons)
        return PermissionBoundaryStatus(
            action_id=action.action_id,
            action_revision=action.revision,
            permission_semantics_confirmed=bool(active),
            active_permission_count=len(active),
            stale_permission_count=len(related_stale),
            allow_control_available=allow_control,
            reason_codes=tuple(reasons),
        )

    def _source_snapshot(
        self,
        understanding: ApplicationUnderstanding,
        command: BoundaryProposalCommand,
    ) -> BoundarySourceSnapshot:
        requested_roles = {
            candidate_id
            for item in command.proposed_actors
            for candidate_id in item.source_candidate_ids
        }
        requested_actions = {
            candidate_id
            for item in command.proposed_actions
            for candidate_id in item.source_candidate_ids
        }
        role_by_id = {item.candidate_id: item for item in understanding.role_candidates}
        action_by_id = {item.candidate_id: item for item in understanding.action_candidates}
        snapshots: list[CandidateSourceSnapshot] = []
        for candidate_id in sorted(requested_roles):
            candidate = role_by_id.get(candidate_id)
            if (
                candidate is None
                or candidate.stale
                or candidate.decision is CandidateDecision.REJECTED
            ):
                self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "角色来源候选不存在或已过期")
            snapshots.append(candidate_source_snapshot(ProposalCandidateKind.ROLE, candidate))
        for candidate_id in sorted(requested_actions):
            candidate = action_by_id.get(candidate_id)
            if (
                candidate is None
                or candidate.stale
                or candidate.decision is CandidateDecision.REJECTED
            ):
                self._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "动作来源候选不存在或已过期")
            snapshots.append(candidate_source_snapshot(ProposalCandidateKind.ACTION, candidate))
        return BoundarySourceSnapshot(
            basis_version=2,
            application_understanding_revision=understanding.revision,
            source_fingerprint=self._source_fingerprint(understanding),
            candidates=tuple(snapshots),
        )

    def _validate_source_snapshot(
        self,
        snapshot: BoundarySourceSnapshot,
        understanding: ApplicationUnderstanding,
    ) -> None:
        if snapshot.basis_version == 1 and (
            snapshot.application_understanding_revision != understanding.revision
            or snapshot.source_fingerprint != self._source_fingerprint(understanding)
        ):
            self._raise(ErrorCode.BOUNDARY_PROPOSAL_SOURCE_STALE, "业务边界提案的来源事实已变化")
        roles = {item.candidate_id: item for item in understanding.role_candidates}
        actions = {item.candidate_id: item for item in understanding.action_candidates}
        for expected in snapshot.candidates:
            candidate = (roles if expected.candidate_kind is ProposalCandidateKind.ROLE else actions).get(expected.candidate_id)
            actual = (
                None
                if candidate is None
                else (
                    legacy_candidate_source_snapshot(expected.candidate_kind, candidate)
                    if snapshot.basis_version == 1
                    else candidate_source_snapshot(expected.candidate_kind, candidate)
                )
            )
            if (
                candidate is None
                or candidate.stale
                or candidate.decision is CandidateDecision.REJECTED
                or actual != expected
            ):
                self._raise(ErrorCode.BOUNDARY_PROPOSAL_SOURCE_STALE, "业务边界提案的候选来源已变化")

    @staticmethod
    def _source_fingerprint(understanding: ApplicationUnderstanding) -> str:
        return understanding.source_fingerprint or boundary_sha256({"source_fingerprint": None})

    @staticmethod
    def _effect(effect_id: str, proposed: ProposedEffectItem) -> BusinessEffectDefinition:
        return BusinessEffectDefinition(
            effect_id=effect_id,
            business_label=proposed.business_label,
            effect_kind=proposed.effect_kind,
            resource_concept=proposed.resource_concept,
            expected_state=proposed.expected_state,
            protected_projection=proposed.protected_projection,
            description=proposed.description,
        )

    @staticmethod
    def _understanding(work: StorageUnitOfWork, project_id: str) -> ApplicationUnderstanding:
        understanding = work.application_understanding.get(project_id)
        if understanding is None:
            raise JiejianError(ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND, "应用理解记录不存在")
        return understanding

    @staticmethod
    def _reason(value: str) -> str:
        if not isinstance(value, str):
            raise JiejianError(ErrorCode.INPUT_INVALID, "审批原因无效")
        clean = value.strip()
        if not clean or len(clean) > 512 or any(ord(char) < 32 for char in clean):
            raise JiejianError(ErrorCode.INPUT_INVALID, "审批原因无效")
        return clean

    @staticmethod
    def _raise(code: ErrorCode, message: str) -> None:
        raise JiejianError(code, message)


__all__ = ["BusinessBoundaryService"]
