# =============================================================================
# 长期权限意图账本与普通矩阵
#
# 定位
#   Human GUI 权限批准、实现 binding、Agent proposal 与 Compiler 视图的唯一应用服务。
#
# 职责
#   追加不可变 revision｜推进 policy epoch｜投影矩阵｜维护 binding｜冻结运行权限快照。
#
# 边界
#   Proposal、重分析、账号、Recording、compile 和 run 都不能改变人类批准语义或 epoch。
#
# 调用链
#   GUI / Compiler / Run → PermissionIntentService → Ledger repository
# =============================================================================

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.application_understanding import (
    ActionCandidate,
    ApplicationUnderstanding,
    CandidateDecision,
    RoleCandidate,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import (
    HumanApproval,
    HumanApprovalChannel,
    IntentImplementationBinding,
    IntentImplementationBindingStatus,
    IntentProposal,
    IntentProposalKind,
    IntentProposalStatus,
    PermissionIntentEffectiveState,
    PermissionIntentRelation,
    PermissionIntentRevision,
    PermissionIntentSemantic,
    ProjectPolicyState,
    ProposedImplementationBinding,
    ProtectedEffect,
    implementation_binding_sha256,
    permission_intent_sha256,
)
from product.backend.core.test_setup import ActionSafetySetup
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.recording.safety_setup import ActionSafetySetupService
from product.backend.workflows.test_identities import (
    TestIdentityService,
    TestIdentityStatus,
    TestIdentityView,
)
from product.protocols.execution_request import (
    PermissionPolicySnapshot,
    PermissionPolicySnapshotEntry,
    build_permission_policy_snapshot,
)


_LOCAL_GUI_APPROVER = "本机界鉴用户"


class PermissionIntentViewModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class PermissionIntentCellStatus(StrEnum):
    UNCONFIRMED = "UNCONFIRMED"
    CURRENT = "CURRENT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNRESOLVED = "UNRESOLVED"


class PermissionIntentCellView(PermissionIntentViewModel):
    action_candidate_id: str
    subject_role_candidate_id: str
    subject_role_display_name: str
    resource_owner_role_candidate_id: str
    resource_owner_role_display_name: str
    relation: PermissionIntentRelation
    expectation: PermissionExpectation | None = None
    protected_effects: tuple[ProtectedEffect, ...] = Field(default=(), max_length=16)
    status: PermissionIntentCellStatus
    review_reasons: tuple[str, ...] = ()
    intent_id: str | None = None
    intent_revision: int | None = Field(default=None, ge=1)
    intent_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    policy_epoch: int | None = Field(default=None, ge=1)
    binding_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    representative_test_identity_id: str | None = None
    representative_label: str | None = None
    execution_gap: str | None = None


class PermissionIntentActionView(PermissionIntentViewModel):
    action_candidate_id: str
    action_display_name: str
    resource_logical_name: str | None = None
    cells: tuple[PermissionIntentCellView, ...] = ()
    gaps: tuple[str, ...] = ()
    required_intent_count: int = Field(ge=0)
    confirmed_intent_count: int = Field(ge=0)
    executable_intent_count: int = Field(ge=0)
    representative_gap_count: int = Field(ge=0)
    compilable: bool = False


class PermissionIntentMatrixView(PermissionIntentViewModel):
    project_id: str
    policy_epoch: int = Field(ge=0)
    actions: tuple[PermissionIntentActionView, ...]
    confirmed_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    unconfirmed_count: int = Field(ge=0)
    executable_count: int = Field(ge=0)
    representative_gap_count: int = Field(ge=0)
    compilable_action_count: int = Field(ge=0)


class PermissionIntentExecution(PermissionIntentViewModel):
    revision: PermissionIntentRevision
    binding: IntentImplementationBinding
    subject_test_identity_id: str | None = None
    gap: str | None = None


class PermissionIntentHistoryView(PermissionIntentViewModel):
    project_id: str
    intent_id: str
    revisions: tuple[PermissionIntentRevision, ...] = Field(max_length=4096)
    latest_binding: IntentImplementationBinding | None = None


class PermissionIntentProposalListView(PermissionIntentViewModel):
    project_id: str
    proposals: tuple[IntentProposal, ...] = Field(max_length=256)


class PermissionIntentService:
    """只有本机 GUI 语义批准会追加 revision 并推进项目 epoch。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        test_identities: TestIdentityService,
        action_safety_setup: ActionSafetySetupService,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._test_identities = test_identities
        self._action_safety_setup = action_safety_setup
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)

    def matrix(self, project_id: str) -> PermissionIntentMatrixView:
        with self._uow_factory() as work:
            understanding = work.application_understanding.get(project_id)
            if understanding is None:
                raise JiejianError(
                    ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                    "当前项目还没有应用连接记录",
                )
            latest = work.permission_intents.list_latest(project_id)
            bindings = {
                (item.intent_id, item.intent_revision): item
                for item in work.permission_intents.list_bindings(project_id)
            }
            state = work.permission_intents.policy_state(project_id)
            setups = {
                action.candidate_id: work.action_safety_setups.get_for_action(
                    project_id,
                    action.candidate_id,
                )
                for action in understanding.action_candidates
            }
        actions = tuple(
            action
            for action in understanding.action_candidates
            if action.decision is CandidateDecision.CONFIRMED and not action.stale
        )
        roles = {
            role.candidate_id: role
            for role in understanding.role_candidates
            if role.decision is CandidateDecision.CONFIRMED and not role.stale
        }
        identities = tuple(
            sorted(self._test_identities.list(project_id), key=lambda item: item.identity_id)
        )
        latest_by_key: dict[
            tuple[str, str, str, PermissionIntentRelation],
            tuple[PermissionIntentRevision, IntentImplementationBinding],
        ] = {}
        for revision in latest:
            binding = bindings.get((revision.intent_id, revision.revision))
            if binding is None:
                raise JiejianError(ErrorCode.STORAGE_FAILURE, "权限意图缺少实现绑定")
            latest_by_key[_binding_key(binding, revision.relation)] = (revision, binding)
        seen: set[str] = set()
        action_views = [
            self._action_view(
                action,
                setups.get(action.candidate_id),
                roles,
                identities,
                latest_by_key,
                understanding,
                setups,
                seen,
            )
            for action in actions
        ]
        action_views.extend(
            self._orphan_action_views(
                latest,
                bindings,
                understanding,
                setups,
                identities,
                seen,
            )
        )
        cells = tuple(cell for action in action_views for cell in action.cells)
        active_cells = tuple(
            cell
            for cell in cells
            if cell.intent_id is not None and cell.expectation is not None
        )
        return PermissionIntentMatrixView(
            project_id=project_id,
            policy_epoch=0 if state is None else state.policy_epoch,
            actions=tuple(action_views),
            confirmed_count=len({cell.intent_id for cell in active_cells}),
            review_required_count=sum(
                cell.status
                in {PermissionIntentCellStatus.NEEDS_REVIEW, PermissionIntentCellStatus.UNRESOLVED}
                for cell in active_cells
            ),
            unconfirmed_count=sum(
                cell.status is PermissionIntentCellStatus.UNCONFIRMED for cell in cells
            ),
            executable_count=sum(
                cell.status is PermissionIntentCellStatus.CURRENT and cell.execution_gap is None
                for cell in active_cells
            ),
            representative_gap_count=sum(
                cell.status is PermissionIntentCellStatus.CURRENT and cell.execution_gap is not None
                for cell in active_cells
            ),
            compilable_action_count=sum(action.compilable for action in action_views),
        )

    def confirm(
        self,
        project_id: str,
        action_candidate_id: str,
        subject_role_candidate_id: str,
        resource_owner_role_candidate_id: str,
        relation: PermissionIntentRelation,
        *,
        expectation: PermissionExpectation | None,
        reason: str = "本机界面确认权限要求",
    ) -> PermissionIntentMatrixView:
        """执行本机 GUI 语义事务；重复同语义幂等，取消确认写 RETIRED revision。"""

        matrix = self.matrix(project_id)
        cell = next(
            (
                cell
                for action in matrix.actions
                if action.action_candidate_id == action_candidate_id
                for cell in action.cells
                if _view_key(cell)
                == (
                    action_candidate_id,
                    subject_role_candidate_id,
                    resource_owner_role_candidate_id,
                    relation,
                )
            ),
            None,
        )
        if cell is None:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "当前动作尚未形成可批准的权限组与资源关系",
            )
        with self._uow_factory() as work:
            understanding = work.application_understanding.get(project_id)
            setup = work.action_safety_setups.get_for_action(project_id, action_candidate_id)
            latest = work.permission_intents.list_latest(project_id)
            bindings = {
                (item.intent_id, item.intent_revision): item
                for item in work.permission_intents.list_bindings(project_id)
            }
            state = work.permission_intents.policy_state(project_id)
        if understanding is None or setup is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "权限批准所需业务事实不完整")
        existing = next(
            (
                revision
                for revision in latest
                if (binding := bindings.get((revision.intent_id, revision.revision))) is not None
                and _binding_key(binding, revision.relation) == _view_key(cell)
            ),
            None,
        )
        if expectation is None:
            if existing is None or existing.effective_state is PermissionIntentEffectiveState.RETIRED:
                return matrix
            semantic = PermissionIntentSemantic(
                effective_state=PermissionIntentEffectiveState.RETIRED,
                subject_display_name=existing.subject_display_name,
                action_display_name=existing.action_display_name,
                resource_owner_display_name=existing.resource_owner_display_name,
                relation=existing.relation,
                expectation=existing.expectation,
                protected_effects=existing.protected_effects,
            )
        else:
            semantic = PermissionIntentSemantic(
                effective_state=PermissionIntentEffectiveState.ACTIVE,
                subject_display_name=cell.subject_role_display_name,
                action_display_name=next(
                    action.action_display_name
                    for action in matrix.actions
                    if action.action_candidate_id == action_candidate_id
                ),
                resource_owner_display_name=cell.resource_owner_role_display_name,
                relation=relation,
                expectation=expectation,
                protected_effects=_protected_effects(setup),
            )
        semantic_hash = permission_intent_sha256(semantic.canonical_payload())
        if existing is not None and existing.intent_hash == semantic_hash:
            binding = bindings[(existing.intent_id, existing.revision)]
            live_status, _ = _live_binding_status(understanding, {action_candidate_id: setup}, binding)
            if live_status is not IntentImplementationBindingStatus.CURRENT:
                self.rebind(
                    project_id,
                    existing.intent_id,
                    action_candidate_id=action_candidate_id,
                    subject_role_candidate_id=subject_role_candidate_id,
                    resource_owner_role_candidate_id=resource_owner_role_candidate_id,
                )
            return self.matrix(project_id)
        now_us = self._clock_us()
        expected_epoch = 0 if state is None else state.policy_epoch
        next_epoch = expected_epoch + 1
        intent_id = existing.intent_id if existing is not None else f"pin_{uuid4().hex}"
        revision_number = 1 if existing is None else existing.revision + 1
        revision = PermissionIntentRevision(
            **semantic.model_dump(mode="python"),
            intent_id=intent_id,
            project_id=project_id,
            revision=revision_number,
            intent_hash=semantic_hash,
            policy_epoch=next_epoch,
            approval=HumanApproval(
                channel=HumanApprovalChannel.LOCAL_GUI,
                approved_by=_LOCAL_GUI_APPROVER,
                approved_at_us=now_us,
                reason=reason,
            ),
            created_at_us=now_us,
        )
        binding = _current_binding(
            revision,
            understanding,
            setup,
            action_candidate_id=action_candidate_id,
            subject_role_candidate_id=subject_role_candidate_id,
            resource_owner_role_candidate_id=resource_owner_role_candidate_id,
            now_us=now_us,
        )
        with self._uow_factory() as work:
            live_state = work.permission_intents.policy_state(project_id)
            live_epoch = 0 if live_state is None else live_state.policy_epoch
            if live_epoch != expected_epoch:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "权限策略已由另一个审批事务更新，请刷新后重试",
                    details={
                        "expected_policy_epoch": expected_epoch,
                        "current_policy_epoch": live_epoch,
                    },
                )
            work.permission_intents.add_revision(revision)
            work.permission_intents.add_binding(binding)
            work.permission_intents.replace_policy_state(
                ProjectPolicyState(
                    project_id=project_id,
                    policy_epoch=next_epoch,
                    updated_at_us=now_us,
                )
            )
            work.commit()
        return self.matrix(project_id)

    def current_intents(self, project_id: str) -> tuple[PermissionIntentRevision, ...]:
        with self._uow_factory() as work:
            latest = work.permission_intents.list_latest(project_id)
        return tuple(
            item
            for item in latest
            if item.effective_state is PermissionIntentEffectiveState.ACTIVE
        )

    def execution_intents(self, project_id: str) -> tuple[PermissionIntentExecution, ...]:
        """只投影 ACTIVE latest + CURRENT binding；其他 active revision 必须阻断编译。"""

        with self._uow_factory() as work:
            understanding = work.application_understanding.get(project_id)
            latest = work.permission_intents.list_latest(project_id)
            bindings = {
                (item.intent_id, item.intent_revision): item
                for item in work.permission_intents.list_bindings(project_id)
            }
            setups = {
                binding.action_candidate_id: work.action_safety_setups.get_for_action(
                    project_id,
                    binding.action_candidate_id,
                )
                for binding in bindings.values()
            }
        if understanding is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "项目尚未形成应用理解事实")
        identities = tuple(
            sorted(self._test_identities.list(project_id), key=lambda item: item.identity_id)
        )
        output: list[PermissionIntentExecution] = []
        for revision in latest:
            if revision.effective_state is not PermissionIntentEffectiveState.ACTIVE:
                continue
            binding = bindings.get((revision.intent_id, revision.revision))
            if binding is None:
                raise JiejianError(ErrorCode.STORAGE_FAILURE, "权限意图缺少实现绑定")
            status, reasons = _live_binding_status(understanding, setups, binding)
            if binding.status is not IntentImplementationBindingStatus.CURRENT or status is not IntentImplementationBindingStatus.CURRENT:
                continue
            setup = setups[binding.action_candidate_id]
            assert setup is not None
            representative, gap = _representative(
                revision.relation,
                binding.subject_role_candidate_id,
                setup.resource.owner_test_identity_id,
                identities,
            )
            output.append(
                PermissionIntentExecution(
                    revision=revision,
                    binding=binding,
                    subject_test_identity_id=(
                        None if representative is None else representative.identity_id
                    ),
                    gap=gap or (reasons[0] if reasons else None),
                )
            )
        return tuple(sorted(output, key=lambda item: item.revision.intent_id))

    def refresh_bindings(self, project_id: str) -> None:
        """候选失效或安全准备变化才降级 binding，不修改 revision 或 epoch。"""

        with self._uow_factory() as work:
            understanding = work.application_understanding.get(project_id)
            latest = work.permission_intents.list_latest(project_id)
            bindings = {
                (item.intent_id, item.intent_revision): item
                for item in work.permission_intents.list_bindings(project_id)
            }
            setups = {
                binding.action_candidate_id: work.action_safety_setups.get_for_action(
                    project_id,
                    binding.action_candidate_id,
                )
                for binding in bindings.values()
            }
            if understanding is None:
                return
            changed = False
            now_us = self._clock_us()
            for revision in latest:
                if revision.effective_state is not PermissionIntentEffectiveState.ACTIVE:
                    continue
                binding = bindings.get((revision.intent_id, revision.revision))
                if binding is None or binding.status is not IntentImplementationBindingStatus.CURRENT:
                    continue
                status, reasons = _live_binding_status(understanding, setups, binding)
                if status is IntentImplementationBindingStatus.CURRENT:
                    continue
                work.permission_intents.replace_binding(
                    binding.model_copy(
                        update={
                            "status": status,
                            "reason_codes": reasons,
                            "updated_at_us": now_us,
                        }
                    )
                )
                changed = True
            if changed:
                work.commit()

    def rebind(
        self,
        project_id: str,
        intent_id: str,
        *,
        action_candidate_id: str,
        subject_role_candidate_id: str,
        resource_owner_role_candidate_id: str,
    ) -> IntentImplementationBinding:
        """由后续 Human Approval 调用的实现重绑事务；绝不推进 policy epoch。"""

        with self._uow_factory() as work:
            revision = work.permission_intents.latest(intent_id)
            understanding = work.application_understanding.get(project_id)
            setup = work.action_safety_setups.get_for_action(project_id, action_candidate_id)
            previous_binding = (
                None
                if revision is None
                else work.permission_intents.binding(intent_id, revision.revision)
            )
        if (
            revision is None
            or revision.project_id != project_id
            or revision.effective_state is not PermissionIntentEffectiveState.ACTIVE
            or understanding is None
            or setup is None
        ):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前权限意图不能重新绑定")
        now_us = max(
            self._clock_us(),
            0 if previous_binding is None else previous_binding.updated_at_us + 1,
        )
        binding = _current_binding(
            revision,
            understanding,
            setup,
            action_candidate_id=action_candidate_id,
            subject_role_candidate_id=subject_role_candidate_id,
            resource_owner_role_candidate_id=resource_owner_role_candidate_id,
            now_us=now_us,
        )
        status, reasons = _live_binding_status(
            understanding,
            {action_candidate_id: setup},
            binding,
        )
        if status is not IntentImplementationBindingStatus.CURRENT:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "新的实现映射仍不可用",
                details={"reason_codes": reasons},
            )
        with self._uow_factory() as work:
            work.permission_intents.replace_binding(binding)
            work.commit()
        return binding

    def propose_semantic_change(
        self,
        project_id: str,
        semantic: PermissionIntentSemantic,
        *,
        proposed_by: str,
        reason: str,
        intent_id: str | None = None,
    ) -> IntentProposal:
        proposal = IntentProposal(
            proposal_id=f"prp_{uuid4().hex}",
            project_id=project_id,
            kind=IntentProposalKind.SEMANTIC_CHANGE,
            intent_id=intent_id,
            semantic_change=semantic,
            proposed_by=proposed_by,
            reason=reason,
            created_at_us=self._clock_us(),
        )
        with self._uow_factory() as work:
            work.permission_intents.add_proposal(proposal)
            work.commit()
        return proposal

    def propose_rebind(
        self,
        project_id: str,
        intent_id: str,
        binding: ProposedImplementationBinding,
        *,
        proposed_by: str,
        reason: str,
    ) -> IntentProposal:
        proposal = IntentProposal(
            proposal_id=f"prp_{uuid4().hex}",
            project_id=project_id,
            kind=IntentProposalKind.IMPLEMENTATION_REBIND,
            intent_id=intent_id,
            implementation_rebind=binding,
            proposed_by=proposed_by,
            reason=reason,
            created_at_us=self._clock_us(),
        )
        with self._uow_factory() as work:
            work.permission_intents.add_proposal(proposal)
            work.commit()
        return proposal

    def propose_rebind_target(
        self,
        project_id: str,
        intent_id: str,
        *,
        action_candidate_id: str,
        subject_role_candidate_id: str,
        resource_owner_role_candidate_id: str,
        proposed_by: str,
        reason: str,
    ) -> IntentProposal:
        """从当前生产事实冻结 Agent 的实现重绑建议，调用者不能伪造 revision 或 fingerprint。"""

        with self._uow_factory() as work:
            revision = work.permission_intents.latest(intent_id)
            understanding = work.application_understanding.get(project_id)
            setup = work.action_safety_setups.get_for_action(project_id, action_candidate_id)
        if (
            revision is None
            or revision.project_id != project_id
            or revision.effective_state is not PermissionIntentEffectiveState.ACTIVE
            or understanding is None
            or setup is None
        ):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前权限意图不能形成实现重绑建议")
        proposed = ProposedImplementationBinding(
            action_candidate_id=action_candidate_id,
            subject_role_candidate_id=subject_role_candidate_id,
            resource_owner_role_candidate_id=resource_owner_role_candidate_id,
            understanding_revision=understanding.revision,
            action_safety_setup_fingerprint=_setup_fingerprint(setup),
        )
        return self.propose_rebind(
            project_id,
            intent_id,
            proposed,
            proposed_by=proposed_by,
            reason=reason,
        )

    def history(self, project_id: str, intent_id: str) -> PermissionIntentHistoryView:
        with self._uow_factory() as work:
            revisions = tuple(
                item
                for item in work.permission_intents.list_revisions(project_id)
                if item.intent_id == intent_id
            )
            latest_binding = (
                None
                if not revisions
                else work.permission_intents.binding(intent_id, revisions[-1].revision)
            )
        if not revisions:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前应用中不存在该权限意图")
        return PermissionIntentHistoryView(
            project_id=project_id,
            intent_id=intent_id,
            revisions=revisions,
            latest_binding=latest_binding,
        )

    def proposals(self, project_id: str) -> PermissionIntentProposalListView:
        with self._uow_factory() as work:
            pending = tuple(
                item
                for item in work.permission_intents.list_proposals(project_id)
                if item.status is IntentProposalStatus.PENDING
            )
        if len(pending) > 256:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "待审权限建议过多，请先完成审阅")
        return PermissionIntentProposalListView(project_id=project_id, proposals=pending)

    def approve_proposal(
        self,
        project_id: str,
        proposal_id: str,
        *,
        reason: str = "本机界面批准 Agent 权限建议",
    ) -> IntentProposal:
        """把仍与当前事实一致的建议送入正式 human revision 或 rebind transaction。"""

        proposal = self._pending_proposal(project_id, proposal_id)
        if proposal.kind is IntentProposalKind.SEMANTIC_CHANGE:
            target = self._semantic_proposal_target(project_id, proposal)
            semantic = proposal.semantic_change
            assert semantic is not None
            self.confirm(
                project_id,
                target[0],
                target[1],
                target[2],
                target[3],
                expectation=(
                    None
                    if semantic.effective_state is PermissionIntentEffectiveState.RETIRED
                    else semantic.expectation
                ),
                reason=reason,
            )
        else:
            binding = proposal.implementation_rebind
            assert binding is not None and proposal.intent_id is not None
            with self._uow_factory() as work:
                understanding = work.application_understanding.get(project_id)
                setup = work.action_safety_setups.get_for_action(
                    project_id,
                    binding.action_candidate_id,
                )
            if (
                understanding is None
                or setup is None
                or understanding.revision != binding.understanding_revision
                or _setup_fingerprint(setup) != binding.action_safety_setup_fingerprint
            ):
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "Agent 建议的实现映射已经过期，请重新生成建议",
                )
            self.rebind(
                project_id,
                proposal.intent_id,
                action_candidate_id=binding.action_candidate_id,
                subject_role_candidate_id=binding.subject_role_candidate_id,
                resource_owner_role_candidate_id=binding.resource_owner_role_candidate_id,
            )
        return self._decide_proposal(proposal, IntentProposalStatus.APPROVED)

    def reject_proposal(self, project_id: str, proposal_id: str) -> IntentProposal:
        proposal = self._pending_proposal(project_id, proposal_id)
        return self._decide_proposal(proposal, IntentProposalStatus.REJECTED)

    def policy_snapshot(self, project_id: str) -> PermissionPolicySnapshot:
        self.refresh_bindings(project_id)
        executions = {
            item.revision.intent_id: item
            for item in self.execution_intents(project_id)
            if item.gap is None and item.subject_test_identity_id is not None
        }
        with self._uow_factory() as work:
            state = work.permission_intents.policy_state(project_id)
            latest = work.permission_intents.list_latest(project_id)
            bindings = {
                (item.intent_id, item.intent_revision): item
                for item in work.permission_intents.list_bindings(project_id)
            }
        entries: list[PermissionPolicySnapshotEntry] = []
        for revision in latest:
            if revision.effective_state is not PermissionIntentEffectiveState.ACTIVE:
                continue
            binding = bindings.get((revision.intent_id, revision.revision))
            if binding is None or binding.status is not IntentImplementationBindingStatus.CURRENT:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "存在需要重新映射的权限要求，不能冻结执行请求",
                    details={"intent_id": revision.intent_id},
                )
            execution = executions.get(revision.intent_id)
            if execution is None or execution.subject_test_identity_id is None:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "权限要求缺少当前可执行代表，不能冻结执行请求",
                    details={"intent_id": revision.intent_id},
                )
            entries.append(
                PermissionPolicySnapshotEntry(
                    intent_id=revision.intent_id,
                    revision=revision.revision,
                    intent_hash=revision.intent_hash,
                    binding_fingerprint=binding.binding_fingerprint,
                    expectation=revision.expectation,
                    relation=revision.relation,
                    subject_display_name=revision.subject_display_name,
                    action_display_name=revision.action_display_name,
                    resource_owner_display_name=revision.resource_owner_display_name,
                    protected_effects=revision.protected_effects,
                    action_candidate_id=binding.action_candidate_id,
                    subject_test_identity_id=execution.subject_test_identity_id,
                )
            )
        return build_permission_policy_snapshot(
            project_id,
            0 if state is None else state.policy_epoch,
            entries,
        )

    def _pending_proposal(self, project_id: str, proposal_id: str) -> IntentProposal:
        with self._uow_factory() as work:
            proposal = work.permission_intents.proposal(proposal_id)
        if proposal is None or proposal.project_id != project_id:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前应用中不存在该权限建议")
        if proposal.status is not IntentProposalStatus.PENDING:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "该权限建议已经完成审阅")
        return proposal

    def _decide_proposal(
        self,
        proposal: IntentProposal,
        status: IntentProposalStatus,
    ) -> IntentProposal:
        decided = proposal.model_copy(
            update={"status": status, "decided_at_us": self._clock_us()}
        )
        with self._uow_factory() as work:
            current = work.permission_intents.proposal(proposal.proposal_id)
            if current is None or current.status is not IntentProposalStatus.PENDING:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "该权限建议已经完成审阅")
            work.permission_intents.replace_proposal(decided)
            work.commit()
        return decided

    def _semantic_proposal_target(
        self,
        project_id: str,
        proposal: IntentProposal,
    ) -> tuple[str, str, str, PermissionIntentRelation]:
        semantic = proposal.semantic_change
        assert semantic is not None
        matrix = self.matrix(project_id)
        if proposal.intent_id is not None:
            with self._uow_factory() as work:
                revision = work.permission_intents.latest(proposal.intent_id)
                binding = (
                    None
                    if revision is None
                    else work.permission_intents.binding(revision.intent_id, revision.revision)
                )
            if revision is None or revision.project_id != project_id or binding is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "建议引用的权限意图已经不可用")
            target = (
                binding.action_candidate_id,
                binding.subject_role_candidate_id,
                binding.resource_owner_role_candidate_id,
                revision.relation,
            )
        else:
            matches = tuple(
                (
                    action.action_candidate_id,
                    cell.subject_role_candidate_id,
                    cell.resource_owner_role_candidate_id,
                    cell.relation,
                )
                for action in matrix.actions
                for cell in action.cells
                if action.action_display_name == semantic.action_display_name
                and cell.subject_role_display_name == semantic.subject_display_name
                and cell.resource_owner_role_display_name
                == semantic.resource_owner_display_name
                and cell.relation is semantic.relation
            )
            if len(matches) != 1:
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "Agent 建议不能唯一映射到当前权限单元",
                )
            target = matches[0]
        expected = self._semantic_for_target(project_id, target, semantic)
        if permission_intent_sha256(expected.canonical_payload()) != permission_intent_sha256(
            semantic.canonical_payload()
        ):
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "Agent 建议与当前业务事实不一致，请重新生成建议",
            )
        return target

    def _semantic_for_target(
        self,
        project_id: str,
        target: tuple[str, str, str, PermissionIntentRelation],
        proposed: PermissionIntentSemantic,
    ) -> PermissionIntentSemantic:
        action_id, subject_id, owner_id, relation = target
        matrix = self.matrix(project_id)
        action = next(
            (item for item in matrix.actions if item.action_candidate_id == action_id),
            None,
        )
        cell = (
            None
            if action is None
            else next(
                (
                    item
                    for item in action.cells
                    if _view_key(item) == target
                ),
                None,
            )
        )
        with self._uow_factory() as work:
            setup = work.action_safety_setups.get_for_action(project_id, action_id)
            latest_revisions = work.permission_intents.list_latest(project_id)
            bindings = {
                (item.intent_id, item.intent_revision): item
                for item in work.permission_intents.list_bindings(project_id)
            }
        latest = next(
            (
                revision
                for revision in latest_revisions
                if (
                    binding := bindings.get((revision.intent_id, revision.revision))
                )
                is not None
                and _binding_key(binding, revision.relation) == target
            ),
            None,
        )
        if action is None or cell is None or setup is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "建议目标缺少当前业务事实")
        if proposed.effective_state is PermissionIntentEffectiveState.RETIRED:
            if latest is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "尚未确认的权限不能退休")
            return PermissionIntentSemantic(
                effective_state=PermissionIntentEffectiveState.RETIRED,
                subject_display_name=latest.subject_display_name,
                action_display_name=latest.action_display_name,
                resource_owner_display_name=latest.resource_owner_display_name,
                relation=latest.relation,
                expectation=latest.expectation,
                protected_effects=latest.protected_effects,
            )
        return PermissionIntentSemantic(
            effective_state=PermissionIntentEffectiveState.ACTIVE,
            subject_display_name=cell.subject_role_display_name,
            action_display_name=action.action_display_name,
            resource_owner_display_name=cell.resource_owner_role_display_name,
            relation=relation,
            expectation=proposed.expectation,
            protected_effects=_protected_effects(setup),
        )

    def _action_view(
        self,
        action: ActionCandidate,
        setup: ActionSafetySetup | None,
        roles: dict[str, RoleCandidate],
        identities: tuple[TestIdentityView, ...],
        latest_by_key: dict[
            tuple[str, str, str, PermissionIntentRelation],
            tuple[PermissionIntentRevision, IntentImplementationBinding],
        ],
        understanding: ApplicationUnderstanding,
        setups: dict[str, ActionSafetySetup | None],
        seen: set[str],
    ) -> PermissionIntentActionView:
        if setup is None:
            return PermissionIntentActionView(
                action_candidate_id=action.candidate_id,
                action_display_name=action.display_name,
                gaps=("ACTION_FLOW_OR_RESOURCE_MISSING",),
                required_intent_count=0,
                confirmed_intent_count=0,
                executable_intent_count=0,
                representative_gap_count=0,
            )
        owner_role = roles.get(setup.resource.owner_role_candidate_id)
        if owner_role is None:
            return PermissionIntentActionView(
                action_candidate_id=action.candidate_id,
                action_display_name=action.display_name,
                resource_logical_name=setup.resource.logical_name,
                gaps=("RESOURCE_OWNER_ROLE_UNCONFIRMED",),
                required_intent_count=0,
                confirmed_intent_count=0,
                executable_intent_count=0,
                representative_gap_count=0,
            )
        setup_gaps = self._setup_gaps(setup)
        requirements = [
            (owner_role, PermissionIntentRelation.OWNS),
            (owner_role, PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT),
            *(
                (role, PermissionIntentRelation.OTHER_ROLE)
                for role in sorted(roles.values(), key=lambda item: item.candidate_id)
                if role.candidate_id != owner_role.candidate_id
            ),
        ]
        cells: list[PermissionIntentCellView] = []
        for subject_role, relation in requirements:
            ledger = latest_by_key.get(
                (
                    action.candidate_id,
                    subject_role.candidate_id,
                    owner_role.candidate_id,
                    relation,
                )
            )
            if ledger is not None and ledger[0].effective_state is PermissionIntentEffectiveState.ACTIVE:
                seen.add(ledger[0].intent_id)
            cells.append(
                self._cell_view(
                    action,
                    setup,
                    subject_role,
                    owner_role,
                    relation,
                    identities,
                    ledger,
                    understanding,
                    setups,
                )
            )
        confirmed = tuple(cell for cell in cells if cell.expectation is not None)
        executable = tuple(
            cell
            for cell in confirmed
            if cell.status is PermissionIntentCellStatus.CURRENT and cell.execution_gap is None
        )
        executable_expectations = {cell.expectation for cell in executable}
        gaps = list(setup_gaps)
        if PermissionExpectation.ALLOW not in executable_expectations:
            gaps.append("ALLOW_INTENT_MISSING")
        if PermissionExpectation.DENY not in executable_expectations:
            gaps.append("DENY_INTENT_MISSING")
        gaps.extend(cell.execution_gap for cell in confirmed if cell.execution_gap is not None)
        gaps.extend(reason for cell in confirmed for reason in cell.review_reasons)
        return PermissionIntentActionView(
            action_candidate_id=action.candidate_id,
            action_display_name=action.display_name,
            resource_logical_name=setup.resource.logical_name,
            cells=tuple(cells),
            gaps=tuple(dict.fromkeys(gaps)),
            required_intent_count=len(cells),
            confirmed_intent_count=len(confirmed),
            executable_intent_count=len(executable),
            representative_gap_count=sum(cell.execution_gap is not None for cell in executable),
            compilable=(
                not setup_gaps
                and PermissionExpectation.ALLOW in executable_expectations
                and PermissionExpectation.DENY in executable_expectations
            ),
        )

    def _orphan_action_views(
        self,
        latest: tuple[PermissionIntentRevision, ...],
        bindings: dict[tuple[str, int], IntentImplementationBinding],
        understanding: ApplicationUnderstanding,
        setups: dict[str, ActionSafetySetup | None],
        identities: tuple[TestIdentityView, ...],
        seen: set[str],
    ) -> tuple[PermissionIntentActionView, ...]:
        grouped: dict[str, list[PermissionIntentCellView]] = defaultdict(list)
        labels: dict[str, tuple[str, str | None]] = {}
        for revision in latest:
            if (
                revision.effective_state is not PermissionIntentEffectiveState.ACTIVE
                or revision.intent_id in seen
            ):
                continue
            binding = bindings[(revision.intent_id, revision.revision)]
            status, reasons = _live_binding_status(understanding, setups, binding)
            if binding.status is not IntentImplementationBindingStatus.CURRENT:
                status = binding.status
                reasons = binding.reason_codes
            setup = setups.get(binding.action_candidate_id)
            representative, gap = (
                (None, "IMPLEMENTATION_BINDING_UNRESOLVED")
                if setup is None
                else _representative(
                    revision.relation,
                    binding.subject_role_candidate_id,
                    setup.resource.owner_test_identity_id,
                    identities,
                )
            )
            grouped[binding.action_candidate_id].append(
                _ledger_cell(
                    revision,
                    binding,
                    _cell_status(status),
                    reasons,
                    representative,
                    gap,
                )
            )
            labels[binding.action_candidate_id] = (
                revision.action_display_name,
                next(
                    (item.business_label for item in revision.protected_effects),
                    None,
                ),
            )
        return tuple(
            PermissionIntentActionView(
                action_candidate_id=action_id,
                action_display_name=labels[action_id][0],
                resource_logical_name=labels[action_id][1],
                cells=tuple(cells),
                gaps=tuple(dict.fromkeys(reason for cell in cells for reason in cell.review_reasons)),
                required_intent_count=len(cells),
                confirmed_intent_count=len(cells),
                executable_intent_count=0,
                representative_gap_count=len(cells),
                compilable=False,
            )
            for action_id, cells in sorted(grouped.items())
        )

    def _setup_gaps(self, setup: ActionSafetySetup) -> tuple[str, ...]:
        try:
            view = self._action_safety_setup.preview(setup.resource.recording_id)
        except JiejianError as exc:
            if exc.code in {
                ErrorCode.TEST_IDENTITY_NOT_FOUND.value,
                ErrorCode.TEST_IDENTITY_NOT_READY.value,
            }:
                return ()
            return ("ACTION_SAFETY_SETUP_STALE",)
        if view.automatic_execution_allowed and view.confirmed_setup is not None:
            return ()
        return tuple(view.gaps) or ("ACTION_SAFETY_SETUP_STALE",)

    @staticmethod
    def _cell_view(
        action: ActionCandidate,
        setup: ActionSafetySetup,
        subject_role: RoleCandidate,
        owner_role: RoleCandidate,
        relation: PermissionIntentRelation,
        identities: tuple[TestIdentityView, ...],
        ledger: tuple[PermissionIntentRevision, IntentImplementationBinding] | None,
        understanding: ApplicationUnderstanding,
        setups: dict[str, ActionSafetySetup | None],
    ) -> PermissionIntentCellView:
        representative, execution_gap = _representative(
            relation,
            subject_role.candidate_id,
            setup.resource.owner_test_identity_id,
            identities,
        )
        if ledger is None or ledger[0].effective_state is PermissionIntentEffectiveState.RETIRED:
            return PermissionIntentCellView(
                action_candidate_id=action.candidate_id,
                subject_role_candidate_id=subject_role.candidate_id,
                subject_role_display_name=subject_role.display_name,
                resource_owner_role_candidate_id=owner_role.candidate_id,
                resource_owner_role_display_name=owner_role.display_name,
                relation=relation,
                protected_effects=_protected_effects(setup),
                status=PermissionIntentCellStatus.UNCONFIRMED,
                review_reasons=("PERMISSION_INTENT_UNCONFIRMED",),
                representative_test_identity_id=(
                    None if representative is None else representative.identity_id
                ),
                representative_label=None if representative is None else representative.label,
                execution_gap=execution_gap,
            )
        revision, binding = ledger
        status, reasons = _live_binding_status(understanding, setups, binding)
        if binding.status is not IntentImplementationBindingStatus.CURRENT:
            status = binding.status
            reasons = binding.reason_codes
        return _ledger_cell(
            revision,
            binding,
            _cell_status(status),
            reasons,
            representative,
            execution_gap,
        )


def _setup_fingerprint(setup: ActionSafetySetup) -> str:
    return permission_intent_sha256(
        {
            "resource": setup.resource.fingerprint,
            "observation": None if setup.observation is None else setup.observation.fingerprint,
            "recovery": None if setup.recovery is None else setup.recovery.fingerprint,
            "effect": None if setup.effect is None else setup.effect.fingerprint,
        }
    )


def _protected_effects(setup: ActionSafetySetup) -> tuple[ProtectedEffect, ...]:
    if setup.effect is None:
        return ()
    return (
        ProtectedEffect(
            kind=setup.effect.kind,
            resource_type=setup.resource.resource_type,
            business_label=setup.resource.logical_name,
            protected_fields=setup.effect.protected_fields,
        ),
    )


def _current_binding(
    revision: PermissionIntentRevision,
    understanding: ApplicationUnderstanding,
    setup: ActionSafetySetup,
    *,
    action_candidate_id: str,
    subject_role_candidate_id: str,
    resource_owner_role_candidate_id: str,
    now_us: int,
) -> IntentImplementationBinding:
    setup_fingerprint = _setup_fingerprint(setup)
    semantic = {
        "intent_id": revision.intent_id,
        "intent_revision": revision.revision,
        "action_candidate_id": action_candidate_id,
        "subject_role_candidate_id": subject_role_candidate_id,
        "resource_owner_role_candidate_id": resource_owner_role_candidate_id,
        "understanding_revision": understanding.revision,
        "action_safety_setup_fingerprint": setup_fingerprint,
    }
    return IntentImplementationBinding(
        **semantic,
        binding_fingerprint=implementation_binding_sha256(semantic),
        status=IntentImplementationBindingStatus.CURRENT,
        updated_at_us=now_us,
    )


def _live_binding_status(
    understanding: ApplicationUnderstanding,
    setups: dict[str, ActionSafetySetup | None],
    binding: IntentImplementationBinding,
) -> tuple[IntentImplementationBindingStatus, tuple[str, ...]]:
    actions = {item.candidate_id: item for item in understanding.action_candidates}
    roles = {item.candidate_id: item for item in understanding.role_candidates}
    unresolved: list[str] = []
    for candidate, reason in (
        (actions.get(binding.action_candidate_id), "ACTION_CANDIDATE_STALE"),
        (roles.get(binding.subject_role_candidate_id), "SUBJECT_ROLE_CANDIDATE_STALE"),
        (roles.get(binding.resource_owner_role_candidate_id), "OWNER_ROLE_CANDIDATE_STALE"),
    ):
        if candidate is None or candidate.decision is not CandidateDecision.CONFIRMED or candidate.stale:
            unresolved.append(reason)
    setup = setups.get(binding.action_candidate_id)
    if setup is None:
        unresolved.append("ACTION_SAFETY_SETUP_MISSING")
    if unresolved:
        return IntentImplementationBindingStatus.UNRESOLVED, tuple(unresolved)
    review: list[str] = []
    assert setup is not None
    if _setup_fingerprint(setup) != binding.action_safety_setup_fingerprint:
        review.append("ACTION_SAFETY_SETUP_CHANGED")
    if setup.resource.owner_role_candidate_id != binding.resource_owner_role_candidate_id:
        review.append("RESOURCE_OWNER_BINDING_CHANGED")
    if review:
        return IntentImplementationBindingStatus.NEEDS_REVIEW, tuple(review)
    return IntentImplementationBindingStatus.CURRENT, ()


def _representative(
    relation: PermissionIntentRelation,
    subject_role_candidate_id: str,
    owner_test_identity_id: str,
    identities: tuple[TestIdentityView, ...],
) -> tuple[TestIdentityView | None, str | None]:
    if relation is PermissionIntentRelation.OWNS:
        candidates = tuple(item for item in identities if item.identity_id == owner_test_identity_id)
    else:
        candidates = tuple(
            item
            for item in identities
            if item.role_candidate_id == subject_role_candidate_id
            and (
                relation is PermissionIntentRelation.OTHER_ROLE
                or item.identity_id != owner_test_identity_id
            )
        )
    if not candidates:
        return None, "TEST_IDENTITY_MISSING"
    prepared = tuple(item for item in candidates if item.status is TestIdentityStatus.PREPARED)
    if not prepared:
        return None, "TEST_IDENTITY_NOT_PREPARED"
    return prepared[0], None


def _binding_key(
    binding: IntentImplementationBinding,
    relation: PermissionIntentRelation,
) -> tuple[str, str, str, PermissionIntentRelation]:
    return (
        binding.action_candidate_id,
        binding.subject_role_candidate_id,
        binding.resource_owner_role_candidate_id,
        relation,
    )


def _view_key(
    cell: PermissionIntentCellView,
) -> tuple[str, str, str, PermissionIntentRelation]:
    return (
        cell.action_candidate_id,
        cell.subject_role_candidate_id,
        cell.resource_owner_role_candidate_id,
        cell.relation,
    )


def _cell_status(status: IntentImplementationBindingStatus) -> PermissionIntentCellStatus:
    return PermissionIntentCellStatus(status.value)


def _ledger_cell(
    revision: PermissionIntentRevision,
    binding: IntentImplementationBinding,
    status: PermissionIntentCellStatus,
    reasons: tuple[str, ...],
    representative: TestIdentityView | None,
    execution_gap: str | None,
) -> PermissionIntentCellView:
    return PermissionIntentCellView(
        action_candidate_id=binding.action_candidate_id,
        subject_role_candidate_id=binding.subject_role_candidate_id,
        subject_role_display_name=revision.subject_display_name,
        resource_owner_role_candidate_id=binding.resource_owner_role_candidate_id,
        resource_owner_role_display_name=revision.resource_owner_display_name,
        relation=revision.relation,
        expectation=revision.expectation,
        protected_effects=revision.protected_effects,
        status=status,
        review_reasons=reasons,
        intent_id=revision.intent_id,
        intent_revision=revision.revision,
        intent_hash=revision.intent_hash,
        policy_epoch=revision.policy_epoch,
        binding_fingerprint=binding.binding_fingerprint,
        representative_test_identity_id=None if representative is None else representative.identity_id,
        representative_label=None if representative is None else representative.label,
        execution_gap=execution_gap,
    )


__all__ = [
    "PermissionIntentActionView",
    "PermissionIntentCellStatus",
    "PermissionIntentCellView",
    "PermissionIntentExecution",
    "PermissionIntentHistoryView",
    "PermissionIntentMatrixView",
    "PermissionIntentProposalListView",
    "PermissionIntentService",
]
