# =============================================================================
# ProjectReadiness 只读投影
#
# 定位
#   Project 与应用理解、执行配置、业务流程、权限规则和活动任务之间的控制面读模型
#
# 职责
#   汇总权威事实｜按既有门禁与统一外部 blocker 计算下一项任务｜投影活动 Run/Recording
#
# 边界
#   不持久化 readiness，不生成权限预期，也不修改任何执行或安全结论。
#
# 调用链
#   Workbench / Project API → ProjectReadinessService → Storage / published result reader
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.application_understanding import (
    ApplicationUnderstanding,
    CandidateDecision,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus, RunLifecycle
from product.backend.core.recording import RecordingState
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.projects.preparation import (
    PreparationItemKind,
    PreparationItemStatus,
    ProjectPreparationView,
)


NextRequiredAction = Literal[
    "CONNECT_APPLICATION",
    "CONFIRM_TARGET",
    "AUTHORIZE_SOURCE_ANALYSIS",
    "REVIEW_DISCOVERY",
    "RECORD_FLOW",
    "REVIEW_CHANGE",
    "REVIEW_PERMISSION",
    "RUN_CHECK",
    "OPEN_RESULT",
]


class ReadinessModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class ActiveTaskView(ReadinessModel):
    kind: Literal["RUN", "RECORDING"]
    task_id: str = Field(min_length=1, max_length=128)
    state: str = Field(min_length=1, max_length=64)


class ActionPermissionReadinessView(ReadinessModel):
    """一个业务动作从录制事实到权限意图的当前缺口。"""

    action_candidate_id: str
    action_display_name: str
    compilable: bool
    gaps: tuple[str, ...] = ()
    required_intent_count: int = Field(default=0, ge=0)
    confirmed_intent_count: int = Field(default=0, ge=0)
    executable_intent_count: int = Field(default=0, ge=0)
    representative_gap_count: int = Field(default=0, ge=0)


class ProjectReadinessView(ReadinessModel):
    project_id: str = Field(min_length=1, max_length=64)
    project_status: ProjectStatus
    application_connected: bool
    endpoint_status: Literal["NEEDS_CONNECTION", "NEEDS_CONFIRMATION", "CONFIRMED", "UNAVAILABLE"]
    source_analysis_status: Literal["NOT_AVAILABLE", "NOT_AUTHORIZED", "PENDING", "COMPLETED", "STALE"]
    discovered_role_count: int = Field(ge=0)
    confirmed_role_count: int = Field(ge=0)
    discovered_action_count: int = Field(ge=0)
    confirmed_action_count: int = Field(ge=0)
    execution_profile_available: bool
    completed_flow_available: bool
    active_contract_available: bool
    permission_actions: tuple[ActionPermissionReadinessView, ...] = ()
    permission_requirement_count: int = Field(default=0, ge=0)
    confirmed_permission_requirement_count: int = Field(default=0, ge=0)
    executable_permission_requirement_count: int = Field(default=0, ge=0)
    permission_representative_gap_count: int = Field(default=0, ge=0)
    current_scope_runnable: bool
    remaining_gap_count: int = Field(ge=0)
    active_tasks: tuple[ActiveTaskView, ...] = ()
    latest_verified_run_id: str | None = Field(default=None, max_length=128)
    next_required_action: NextRequiredAction
    preparation: ProjectPreparationView | None = None


class ProjectReadinessService:
    """每次查询都从权威事实重新计算项目准备状态。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        result_reader=None,
        endpoint_status_resolver: Callable[[ApplicationUnderstanding], str] | None = None,
        permission_matrix_resolver: Callable[[str], object] | None = None,
        check_preview_resolver: Callable[[str], object] | None = None,
        preparation_resolver: Callable[[str], ProjectPreparationView] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._result_reader = result_reader
        self._endpoint_status_resolver = endpoint_status_resolver
        self._permission_matrix_resolver = permission_matrix_resolver
        self._check_preview_resolver = check_preview_resolver
        self._preparation_resolver = preparation_resolver

    def get(self, project_id: str) -> ProjectReadinessView:
        with self._uow_factory() as work:
            project = work.projects.get(project_id)
            if project is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            profiles = work.execution_profiles.list_for_project(project_id)
            recordings = work.recordings.list_for_project(project_id)
            runs = work.runs.list_for_project(project_id)
            understanding = work.application_understanding.get(project_id)

        preparation = (
            None
            if self._preparation_resolver is None
            else self._preparation_resolver(project_id)
        )
        execution_profile_available = bool(profiles)
        completed_flow_available = any(
            item.state is RecordingState.COMPLETED for item in recordings
        )
        if preparation is not None:
            profile_items = tuple(
                item
                for item in preparation.items
                if item.kind is PreparationItemKind.PROFILE
            )
            flow_items = tuple(
                item
                for item in preparation.items
                if item.kind is PreparationItemKind.FLOW
            )
            execution_profile_available = bool(profile_items) and all(
                item.status is PreparationItemStatus.READY for item in profile_items
            )
            completed_flow_available = bool(flow_items) and all(
                item.status is PreparationItemStatus.READY for item in flow_items
            )
        active_contract_available = (
            project.governed_contract_id is not None
            and project.governed_contract_version is not None
        )
        active_tasks = tuple(
            [
                ActiveTaskView(kind="RUN", task_id=item.run_id, state=item.lifecycle.value)
                for item in runs
                if item.lifecycle in {RunLifecycle.QUEUED, RunLifecycle.RUNNING}
            ]
            + [
                ActiveTaskView(
                    kind="RECORDING",
                    task_id=item.recording_id,
                    state=item.state.value,
                )
                for item in recordings
                if item.state
                not in {
                    RecordingState.COMPLETED,
                    RecordingState.FAILED,
                    RecordingState.CANCELLED,
                    RecordingState.SAFETY_STOPPED,
                }
            ]
        )
        latest_verified_run_id = self._latest_verified_run_id(runs)
        if understanding is not None:
            permission_actions = self._permission_actions(project_id)
            current_scope_runnable, remaining_gap_count = self._check_state(
                project_id
            )
            endpoint_status = (
                self._endpoint_status_resolver(understanding)
                if self._endpoint_status_resolver is not None
                else (
                    "CONFIRMED"
                    if understanding.confirmed_endpoint is not None
                    and understanding.endpoint_reachable
                    else "NEEDS_CONFIRMATION"
                )
            )
            source_analysis_status = self._source_analysis_status(understanding)
            confirmed_roles = sum(
                item.decision is CandidateDecision.CONFIRMED
                for item in understanding.role_candidates
            )
            confirmed_actions = sum(
                item.decision is CandidateDecision.CONFIRMED
                for item in understanding.action_candidates
            )
            next_action = self._understanding_next_action(
                understanding,
                endpoint_status=endpoint_status,
                source_analysis_status=source_analysis_status,
                confirmed_roles=confirmed_roles,
                confirmed_actions=confirmed_actions,
            )
            preparation_categories = (
                set()
                if preparation is None
                else {item.category for item in preparation.external_blockers}
            )
            # 变化和权限外部 blocker 是统一控制面事实，不能被旧范围仍可运行所遮住。
            if (
                next_action == "RECORD_FLOW"
                and "SOURCE_CHANGE" in preparation_categories
            ):
                next_action = "REVIEW_CHANGE"
            elif next_action == "RECORD_FLOW" and "PERMISSION" in preparation_categories:
                next_action = "REVIEW_PERMISSION"
            # 已有范围仍可运行时也不能遮住新发现候选；持续开发中的新增权限面必须先让人看见。
            elif current_scope_runnable and next_action != "REVIEW_DISCOVERY":
                next_action = (
                    "OPEN_RESULT"
                    if latest_verified_run_id is not None
                    else "RUN_CHECK"
                )
            elif next_action == "RECORD_FLOW" and permission_actions:
                if preparation is not None and not preparation.ready:
                    next_action = "RECORD_FLOW"
                else:
                    next_action = "REVIEW_PERMISSION"
            return ProjectReadinessView(
                project_id=project.project_id,
                project_status=project.status,
                application_connected=True,
                endpoint_status=endpoint_status,
                source_analysis_status=source_analysis_status,
                discovered_role_count=len(understanding.role_candidates),
                confirmed_role_count=confirmed_roles,
                discovered_action_count=len(understanding.action_candidates),
                confirmed_action_count=confirmed_actions,
                execution_profile_available=execution_profile_available,
                completed_flow_available=completed_flow_available,
                active_contract_available=active_contract_available,
                permission_actions=permission_actions,
                permission_requirement_count=sum(
                    item.required_intent_count for item in permission_actions
                ),
                confirmed_permission_requirement_count=sum(
                    item.confirmed_intent_count for item in permission_actions
                ),
                executable_permission_requirement_count=sum(
                    item.executable_intent_count for item in permission_actions
                ),
                permission_representative_gap_count=sum(
                    item.representative_gap_count for item in permission_actions
                ),
                current_scope_runnable=current_scope_runnable,
                remaining_gap_count=remaining_gap_count,
                active_tasks=active_tasks,
                latest_verified_run_id=latest_verified_run_id,
                next_required_action=next_action,
                preparation=preparation,
            )

        return ProjectReadinessView(
            project_id=project.project_id,
            project_status=project.status,
            application_connected=False,
            endpoint_status="NEEDS_CONNECTION",
            source_analysis_status="NOT_AVAILABLE",
            discovered_role_count=0,
            confirmed_role_count=0,
            discovered_action_count=0,
            confirmed_action_count=0,
            execution_profile_available=execution_profile_available,
            completed_flow_available=completed_flow_available,
            active_contract_available=active_contract_available,
            current_scope_runnable=False,
            remaining_gap_count=1,
            active_tasks=active_tasks,
            latest_verified_run_id=latest_verified_run_id,
            next_required_action="CONNECT_APPLICATION",
            preparation=preparation,
        )

    def _permission_actions(
        self,
        project_id: str,
    ) -> tuple[ActionPermissionReadinessView, ...]:
        if self._permission_matrix_resolver is None:
            return ()
        try:
            matrix = self._permission_matrix_resolver(project_id)
        except JiejianError:
            return ()
        return tuple(
            ActionPermissionReadinessView(
                action_candidate_id=action.action_candidate_id,
                action_display_name=action.action_display_name,
                compilable=action.compilable,
                gaps=action.gaps,
                required_intent_count=action.required_intent_count,
                confirmed_intent_count=action.confirmed_intent_count,
                executable_intent_count=action.executable_intent_count,
                representative_gap_count=action.representative_gap_count,
            )
            for action in matrix.actions
        )

    def _check_state(self, project_id: str) -> tuple[bool, int]:
        """直接复用 CheckPreview 真源，避免 readiness 另算一套可执行口径。"""

        if self._check_preview_resolver is None:
            return False, 0
        try:
            preview = self._check_preview_resolver(project_id)
        except JiejianError:
            return False, 0
        return bool(preview.ready), len(preview.gaps)

    def _latest_verified_run_id(self, runs) -> str | None:
        if self._result_reader is None:
            return None
        for run in runs:
            if run.lifecycle not in {RunLifecycle.COMPLETED, RunLifecycle.SAFETY_STOPPED}:
                continue
            try:
                self._result_reader.read(run.run_id)
            except JiejianError:
                continue
            return run.run_id
        return None

    @staticmethod
    def _source_analysis_status(
        understanding: ApplicationUnderstanding,
    ) -> Literal["NOT_AUTHORIZED", "PENDING", "COMPLETED", "STALE"]:
        if not understanding.source_analysis_authorized:
            return "NOT_AUTHORIZED"
        if understanding.source_fingerprint is None:
            return "PENDING"
        if any(
            item.stale or item.decision is CandidateDecision.REVIEW_REQUIRED
            for item in (*understanding.role_candidates, *understanding.action_candidates)
        ):
            return "STALE"
        return "COMPLETED"

    @staticmethod
    def _understanding_next_action(
        understanding: ApplicationUnderstanding,
        *,
        endpoint_status: str,
        source_analysis_status: str,
        confirmed_roles: int,
        confirmed_actions: int,
    ) -> NextRequiredAction:
        if endpoint_status != "CONFIRMED":
            return "CONFIRM_TARGET"
        if not understanding.source_analysis_authorized:
            return "AUTHORIZE_SOURCE_ANALYSIS"
        if source_analysis_status in {"PENDING", "STALE"}:
            return "REVIEW_DISCOVERY"
        has_unreviewed = any(
            item.decision
            in {CandidateDecision.PROPOSED, CandidateDecision.REVIEW_REQUIRED}
            for item in (*understanding.role_candidates, *understanding.action_candidates)
        )
        if has_unreviewed or confirmed_roles == 0 or confirmed_actions == 0:
            return "REVIEW_DISCOVERY"
        return "RECORD_FLOW"

    @staticmethod
    def _next_action(
        project_status: ProjectStatus,
        *,
        execution_profile_available: bool,
        completed_flow_available: bool,
        active_contract_available: bool,
        latest_verified_run_id: str | None,
    ) -> NextRequiredAction:
        if project_status is ProjectStatus.DRAFT:
            return "CONNECT_APPLICATION"
        if not completed_flow_available:
            return "RECORD_FLOW"
        if not active_contract_available or not execution_profile_available:
            return "REVIEW_PERMISSION"
        if latest_verified_run_id is not None:
            return "OPEN_RESULT"
        return "RUN_CHECK"
