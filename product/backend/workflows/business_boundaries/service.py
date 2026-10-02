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

from product.backend.core.boundaries.permissions import permission_relation_consistent

import time
from collections.abc import Callable
from contextlib import nullcontext
from uuid import uuid4

from product.backend.core.boundaries.approval import HumanApproval, HumanApprovalChannel
from product.backend.core.applications.models import ApplicationUnderstanding
from product.backend.core.boundaries.proposals import BoundaryDecisionKind, BoundaryProposalBundle, BoundaryProposalDecision, ProposalWriteMode
from product.backend.core.boundaries.entities import BusinessActorRevision, BusinessRevisionState, boundary_sha256
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.boundaries.permissions import PermissionIntentRevision, ProjectPolicyState, permission_intent_sha256
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.business_boundaries.inspection import inspect_action_binding, inspect_actor_binding
from product.backend.workflows.business_boundaries.maintenance import build_maintenance_draft, maintenance_to_proposal_command
from product.backend.workflows.business_boundaries.models import BoundaryDraftView, BoundaryEditorView, BoundaryPendingProposal, BoundaryMaintenanceCommand, BoundaryMaintenanceDraftView, BoundaryProposalCommand, BoundaryProposalListView, BoundaryProposalView, BusinessBoundaryView
from . import planning as boundary_planning
from . import queries as boundary_queries
from . import sources as boundary_sources
from . import validation as boundary_validation










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
            understanding = boundary_validation._understanding(work, project_id)
        return boundary_queries._discovery_preview(project_id, understanding)


    def create_proposal(
        self,
        project_id: str,
        command: BoundaryProposalCommand,
    ) -> BoundaryProposalView:
        with self._uow_factory() as work:
            understanding = boundary_validation._understanding(work, project_id)
            proposal = self._build_proposal(project_id, command, understanding)
            work.business_boundaries.add_proposal(proposal)
            view = boundary_queries._proposal_view(work, proposal)
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
                boundary_validation._raise(
                    ErrorCode.BOUNDARY_MAINTENANCE_REQUIRED,
                    "项目已有正式业务边界，请使用维护流程",
                )
            understanding = boundary_validation._understanding(work, project_id)
            proposal = self._build_proposal(project_id, command, understanding)
            work.business_boundaries.add_proposal(proposal)
            view = boundary_queries._proposal_view(work, proposal)
            work.commit()
        return view

    def maintenance_draft(self, project_id: str, *, work=None, allow_empty: bool = False) -> BoundaryMaintenanceDraftView:
        with (self._uow_factory() if work is None else nullcontext(work)) as work:
            facts = boundary_queries._maintenance_facts(work, project_id, allow_empty=allow_empty)
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
        *,
        work=None,
        allow_initial: bool = False,
    ) -> BoundaryProposalView:
        """在同一事务中防 pending、防并发，并把 desired state 冻结为 Proposal。"""

        owns_transaction = work is None
        with (self._uow_factory() if owns_transaction else nullcontext(work)) as work:
            # 首条对话候选使用空边界作为明确基线；既有维护API仍拒绝无边界项目。
            facts = boundary_queries._maintenance_facts(work, project_id, allow_empty=allow_initial)
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
            view = boundary_queries._proposal_view(work, proposal)
            # 候选转提案由调用者同时保存来源关联与回执，不能提前提交半个事务。
            if owns_transaction:
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
                boundary_queries._proposal_view(work, proposal)
                for proposal in work.business_boundaries.list_proposals(project_id)
            )
        if pending_only:
            values = tuple(item for item in values if item.decision is None)
        return BoundaryProposalListView(project_id=project_id, proposals=values)

    def editor(self, project_id: str) -> BoundaryEditorView:
        """同一UoW读取编辑所需的持久事实；不承诺外部磁盘写入的原子性。"""
        with self._uow_factory() as work:
            boundary = self.view(project_id, work=work)
            preview = boundary_queries._discovery_preview(project_id, boundary_validation._understanding(work, project_id))
            has_objects = bool(work.business_boundaries.list_actors(project_id) or work.business_boundaries.list_actions(project_id))
            draft = self.maintenance_draft(project_id, work=work) if has_objects else None
            pending = tuple(p for p in work.business_boundaries.list_proposals(project_id)
                            if work.business_boundaries.decision_for_proposal(p.proposal_id) is None)
            summaries = tuple(BoundaryPendingProposal(proposal_id=p.proposal_id,
                created_at_us=p.created_at_us, change_summary=boundary_queries._proposal_view(work, p).change_summary)
                for p in pending[:100])
            return BoundaryEditorView(project_id=project_id, boundary=boundary, preview=preview,
                maintenance_draft=draft, pending_proposals=summaries, pending_has_more=len(pending)>100,
                boundary_state_fingerprint=None if draft is None else draft.boundary_state_fingerprint)

    def proposal(self, project_id: str, proposal_id: str) -> BoundaryProposalView:
        with self._uow_factory() as work:
            proposal = work.business_boundaries.get_proposal(proposal_id)
            if proposal is None or proposal.project_id != project_id:
                boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_NOT_FOUND, "业务边界提案不存在")
            view = boundary_queries._proposal_view(work, proposal)
        return view

    def approve(
        self,
        project_id: str,
        proposal_id: str,
        *,
        expected_fingerprint: str,
        reason: str,
    ) -> BusinessBoundaryView:
        clean_reason = boundary_validation._reason(reason)
        with self._uow_factory() as work:
            proposal = boundary_validation._pending_proposal(
                work,
                project_id,
                proposal_id,
                expected_fingerprint,
            )
            if proposal.unresolved_questions:
                boundary_validation._raise(
                    ErrorCode.BOUNDARY_PROPOSAL_UNRESOLVED,
                    "业务边界提案仍有未解决问题",
                )
            understanding = boundary_validation._understanding(work, project_id)
            boundary_sources._validate_source_snapshot(proposal.source_snapshot, understanding)
            now_us = self._clock_us()
            approval = HumanApproval(
                channel=HumanApprovalChannel.LOCAL_GUI,
                approved_by="本机界鉴用户",
                approved_at_us=now_us,
                reason=clean_reason,
            )

            # 先完整构造并交叉校验全部写入对象，随后才按固定顺序触碰 Repository。
            actor_plans = boundary_planning._plan_actors(
                work,
                proposal,
                approval,
                understanding,
                now_us,
            )
            action_plans = boundary_planning._plan_actions(
                work,
                proposal,
                approval,
                understanding,
                now_us,
            )
            permission_plans = boundary_planning._plan_permissions(
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
        clean_reason = boundary_validation._reason(reason)
        with self._uow_factory() as work:
            proposal = boundary_validation._pending_proposal(
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
            view = boundary_queries._proposal_view(work, proposal)
            work.commit()
        return view

    def view(self, project_id: str, *, work=None) -> BusinessBoundaryView:
        from contextlib import nullcontext
        # 技术准备写入者可以在自己的 UoW 中重读正式事实；这里仍不读取技术选择。
        with (self._uow_factory() if work is None else nullcontext(work)) as work:
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
            understanding = boundary_validation._understanding(work, project_id)
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
        intents, stale_intents = boundary_queries.current_permission_intents(
            latest_intents,
            actors,
            actions,
        )
        statuses = tuple(
            boundary_queries._permission_status(action, intents, stale_intents)
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
                boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "权限引用的业务主体不存在")
            subject_key = (subject.actor_id or subject.item_id, (subject.expected_current_revision or 1)
                           + int(subject.write_mode is ProposalWriteMode.APPEND_REVISION))
            owner_key = (owner.actor_id or owner.item_id, (owner.expected_current_revision or 1)
                         + int(owner.write_mode is ProposalWriteMode.APPEND_REVISION))
            if not permission_relation_consistent(permission.relation, subject_key, owner_key):
                boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "权限资源关系与业务主体不一致")
        source_snapshot = boundary_sources._source_snapshot(understanding, command)
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
            boundary_validation._raise(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "业务主体 revision 不存在")
        return value




















__all__ = ["BusinessBoundaryService"]
