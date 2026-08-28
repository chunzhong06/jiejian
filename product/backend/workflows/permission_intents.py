# =============================================================================
# 普通权限组意图矩阵
#
# 定位
#   ApplicationUnderstanding 与动作资源归属之上的用户权限要求确认边界。
#
# 职责
#   计算权限组矩阵｜保存 ALLOW/DENY｜为编译实时选择可用测试账号代表。
#
# 边界
#   PermissionIntent 不绑定账号、资源实例或登录状态；本服务不生成 Contract/Profile。
#
# 调用链
#   Permission API / GUI → PermissionIntentService → Core fact / Storage
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.application_understanding import (
    ActionCandidate,
    CandidateDecision,
    RoleCandidate,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import (
    PermissionIntent,
    PermissionIntentRelation,
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


class PermissionIntentCellView(PermissionIntentViewModel):
    action_candidate_id: str
    subject_role_candidate_id: str
    subject_role_display_name: str
    resource_owner_role_candidate_id: str
    resource_owner_role_display_name: str
    relation: PermissionIntentRelation
    expectation: PermissionExpectation | None = None
    status: PermissionIntentCellStatus
    review_reasons: tuple[str, ...] = ()
    intent_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
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
    actions: tuple[PermissionIntentActionView, ...]
    confirmed_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    unconfirmed_count: int = Field(ge=0)
    executable_count: int = Field(ge=0)
    representative_gap_count: int = Field(ge=0)
    compilable_action_count: int = Field(ge=0)


# 当前组级要求的临时执行代表；代表和缺口都不回写确认事实或生成 Schema 说明。
class PermissionIntentExecution(PermissionIntentViewModel):
    intent: PermissionIntent
    subject_test_identity_id: str | None = None
    gap: str | None = None


class PermissionIntentService:
    """权限要求只随动作和权限组变化，测试账号仅决定当前可执行覆盖。"""

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
            stored = work.permission_intents.list_for_project(project_id)
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
        stored_cells = {_intent_key(item): item for item in stored}
        action_views = tuple(
            self._action_view(
                action,
                setups.get(action.candidate_id),
                roles,
                identities,
                stored_cells,
            )
            for action in actions
        )
        cells = tuple(cell for action in action_views for cell in action.cells)
        current_fingerprints = {
            cell.intent_fingerprint
            for cell in cells
            if cell.status is PermissionIntentCellStatus.CURRENT
        }
        return PermissionIntentMatrixView(
            project_id=project_id,
            actions=action_views,
            confirmed_count=len(current_fingerprints),
            review_required_count=sum(
                item.fingerprint not in current_fingerprints for item in stored
            ),
            unconfirmed_count=sum(
                cell.status is PermissionIntentCellStatus.UNCONFIRMED for cell in cells
            ),
            executable_count=sum(
                cell.status is PermissionIntentCellStatus.CURRENT
                and cell.execution_gap is None
                for cell in cells
            ),
            representative_gap_count=sum(
                cell.status is PermissionIntentCellStatus.CURRENT
                and cell.execution_gap is not None
                for cell in cells
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
        actor: str,
    ) -> PermissionIntentMatrixView:
        """确认或删除一个权限组关系单元，不要求当下已有可执行账号代表。"""

        actor = actor.strip()
        if not actor or any(ord(char) < 32 for char in actor):
            raise JiejianError(ErrorCode.INPUT_INVALID, "确认人名称无效")
        if expectation is None:
            with self._uow_factory() as work:
                work.permission_intents.delete_cell(
                    project_id,
                    action_candidate_id,
                    subject_role_candidate_id,
                    resource_owner_role_candidate_id,
                    relation,
                )
                work.commit()
            return self.matrix(project_id)

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
                "当前动作尚未形成可确认的权限组与资源关系",
            )
        with self._uow_factory() as work:
            existing = work.permission_intents.get_cell(
                project_id,
                action_candidate_id,
                subject_role_candidate_id,
                resource_owner_role_candidate_id,
                relation,
            )
        now_us = self._clock_us()
        semantic = {
            "project_id": project_id,
            "action_candidate_id": action_candidate_id,
            "subject_role_candidate_id": subject_role_candidate_id,
            "resource_owner_role_candidate_id": resource_owner_role_candidate_id,
            "relation": relation.value,
            "expectation": expectation.value,
            "confirmation_source": "USER",
            "confirmed_by": actor,
        }
        fingerprint = permission_intent_sha256(semantic)
        intent = PermissionIntent(
            intent_id=f"pin_{fingerprint[:32]}",
            fingerprint=fingerprint,
            confirmed_at_us=now_us,
            created_at_us=existing.created_at_us if existing is not None else now_us,
            updated_at_us=now_us,
            **{**semantic, "relation": relation, "expectation": expectation},
        )
        with self._uow_factory() as work:
            work.permission_intents.replace_cell(intent)
            work.commit()
        return self.matrix(project_id)

    def current_intents(self, project_id: str) -> tuple[PermissionIntent, ...]:
        """只返回动作和双方权限组引用仍处于当前确认状态的意图。"""

        matrix = self.matrix(project_id)
        current = {
            cell.intent_fingerprint
            for action in matrix.actions
            for cell in action.cells
            if cell.status is PermissionIntentCellStatus.CURRENT
        }
        with self._uow_factory() as work:
            stored = work.permission_intents.list_for_project(project_id)
        return tuple(item for item in stored if item.fingerprint in current)

    def execution_intents(self, project_id: str) -> tuple[PermissionIntentExecution, ...]:
        """实时投影当前意图的确定性账号代表，供编译器消费而不持久化。"""

        matrix = self.matrix(project_id)
        with self._uow_factory() as work:
            stored = work.permission_intents.list_for_project(project_id)
        by_fingerprint = {item.fingerprint: item for item in stored}
        executions = (
            PermissionIntentExecution(
                intent=by_fingerprint[cell.intent_fingerprint],
                subject_test_identity_id=cell.representative_test_identity_id,
                gap=cell.execution_gap,
            )
            for action in matrix.actions
            for cell in action.cells
            if cell.status is PermissionIntentCellStatus.CURRENT
            and cell.intent_fingerprint in by_fingerprint
        )
        return tuple(sorted(executions, key=lambda item: _intent_key(item.intent)))

    def _action_view(
        self,
        action: ActionCandidate,
        setup: ActionSafetySetup | None,
        roles: dict[str, RoleCandidate],
        identities: tuple[TestIdentityView, ...],
        stored_cells: dict[tuple[str, str, str, PermissionIntentRelation], PermissionIntent],
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
        cells = tuple(
            self._cell_view(
                action,
                setup,
                subject_role,
                owner_role,
                relation,
                identities,
                stored_cells.get(
                    (
                        action.candidate_id,
                        subject_role.candidate_id,
                        owner_role.candidate_id,
                        relation,
                    )
                ),
            )
            for subject_role, relation in requirements
        )
        confirmed = tuple(
            cell for cell in cells if cell.status is PermissionIntentCellStatus.CURRENT
        )
        executable = tuple(cell for cell in confirmed if cell.execution_gap is None)
        executable_expectations = {cell.expectation for cell in executable}
        gaps = list(setup_gaps)
        if PermissionExpectation.ALLOW not in executable_expectations:
            gaps.append("ALLOW_INTENT_MISSING")
        if PermissionExpectation.DENY not in executable_expectations:
            gaps.append("DENY_INTENT_MISSING")
        gaps.extend(
            cell.execution_gap
            for cell in confirmed
            if cell.execution_gap is not None
        )
        return PermissionIntentActionView(
            action_candidate_id=action.candidate_id,
            action_display_name=action.display_name,
            resource_logical_name=setup.resource.logical_name,
            cells=cells,
            gaps=tuple(dict.fromkeys(gaps)),
            required_intent_count=len(cells),
            confirmed_intent_count=len(confirmed),
            executable_intent_count=len(executable),
            representative_gap_count=sum(cell.execution_gap is not None for cell in confirmed),
            compilable=(
                not setup_gaps
                and PermissionExpectation.ALLOW in executable_expectations
                and PermissionExpectation.DENY in executable_expectations
            ),
        )

    def _setup_gaps(self, setup: ActionSafetySetup) -> tuple[str, ...]:
        try:
            view = self._action_safety_setup.preview(setup.resource.recording_id)
        except JiejianError as exc:
            # 登录状态只影响临时执行代表，不让已经确认的动作安全事实或权限要求失效。
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
        intent: PermissionIntent | None,
    ) -> PermissionIntentCellView:
        representative, execution_gap = _representative(
            relation,
            subject_role.candidate_id,
            setup.resource.owner_test_identity_id,
            identities,
        )
        return PermissionIntentCellView(
            action_candidate_id=action.candidate_id,
            subject_role_candidate_id=subject_role.candidate_id,
            subject_role_display_name=subject_role.display_name,
            resource_owner_role_candidate_id=owner_role.candidate_id,
            resource_owner_role_display_name=owner_role.display_name,
            relation=relation,
            expectation=None if intent is None else intent.expectation,
            status=(
                PermissionIntentCellStatus.UNCONFIRMED
                if intent is None
                else PermissionIntentCellStatus.CURRENT
            ),
            review_reasons=("PERMISSION_INTENT_UNCONFIRMED",) if intent is None else (),
            intent_fingerprint=None if intent is None else intent.fingerprint,
            representative_test_identity_id=(
                None if representative is None else representative.identity_id
            ),
            representative_label=None if representative is None else representative.label,
            execution_gap=execution_gap,
        )


def _representative(
    relation: PermissionIntentRelation,
    subject_role_candidate_id: str,
    owner_test_identity_id: str,
    identities: tuple[TestIdentityView, ...],
) -> tuple[TestIdentityView | None, str | None]:
    if relation is PermissionIntentRelation.OWNS:
        candidates = tuple(
            item for item in identities if item.identity_id == owner_test_identity_id
        )
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
    prepared = tuple(
        item for item in candidates if item.status is TestIdentityStatus.PREPARED
    )
    if not prepared:
        return None, "TEST_IDENTITY_NOT_PREPARED"
    return prepared[0], None


def _intent_key(
    intent: PermissionIntent,
) -> tuple[str, str, str, PermissionIntentRelation]:
    return (
        intent.action_candidate_id,
        intent.subject_role_candidate_id,
        intent.resource_owner_role_candidate_id,
        intent.relation,
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


__all__ = [
    "PermissionIntentActionView",
    "PermissionIntentCellStatus",
    "PermissionIntentCellView",
    "PermissionIntentExecution",
    "PermissionIntentMatrixView",
    "PermissionIntentService",
]
