# 1.1.0 工作台状态投影：只组合接入、源码理解与稳定业务边界事实。

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from product.backend.core.application_understanding import CandidateDecision
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.protocols import TargetType


class _StatusModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class CurrentProjectSummary(_StatusModel):
    project_id: str
    name: str
    status: ProjectStatus
    target_type: TargetType


class CurrentReadinessView(_StatusModel):
    project_id: str
    project_status: ProjectStatus
    application_connected: bool
    endpoint_status: Literal[
        "NEEDS_CONNECTION", "NEEDS_CONFIRMATION", "CONFIRMED", "UNAVAILABLE"
    ]
    source_analysis_status: Literal[
        "NOT_AVAILABLE", "NOT_AUTHORIZED", "PENDING", "COMPLETED", "STALE"
    ]
    discovered_role_count: int
    confirmed_role_count: int
    discovered_action_count: int
    confirmed_action_count: int
    execution_profile_available: bool
    completed_flow_available: bool
    active_contract_available: bool
    permission_actions: tuple[object, ...] = ()
    permission_requirement_count: int
    confirmed_permission_requirement_count: int
    executable_permission_requirement_count: int
    permission_representative_gap_count: int
    current_scope_runnable: bool
    remaining_gap_count: int
    active_tasks: tuple[object, ...] = ()
    latest_verified_run_id: None = None
    next_required_action: Literal[
        "CONNECT_APPLICATION", "CONFIRM_TARGET", "AUTHORIZE_SOURCE_ANALYSIS",
        "REVIEW_DISCOVERY", "RECORD_FLOW", "REVIEW_CHANGE", "REVIEW_PERMISSION",
        "RUN_CHECK", "OPEN_RESULT",
    ]
    preparation: None = None


class CurrentAreaView(_StatusModel):
    key: Literal["overview", "changes", "permissions", "tests"]
    label: str
    description: str
    route: Literal["/workspace", "/changes", "/permissions", "/tests"]
    status: Literal[
        "READY", "NEEDS_ATTENTION", "RUNNING", "AVAILABLE", "BLOCKED", "EMPTY"
    ]
    status_label: str


class CurrentAttentionView(_StatusModel):
    key: str
    label: str
    description: str
    route: Literal["/application", "/permissions"]
    tone: Literal["ACTION", "WARNING", "INFO"] = "ACTION"


class BoundaryWorkspaceStatusView(_StatusModel):
    project: CurrentProjectSummary
    readiness: CurrentReadinessView
    revalidation: None = None
    repair: None = None
    areas: tuple[CurrentAreaView, ...]
    primary_attention_key: str | None
    attention_items: tuple[CurrentAttentionView, ...]
    latest_change: None = None
    latest_result: None = None
    inconclusive_recovery: None = None


class BoundaryWorkspaceStatusService:
    """沿用既有 Workbench DTO 形状，但不恢复旧准备、Run 或 Permission writer。"""

    def __init__(self, uow_factory, business_boundaries) -> None:
        self._uow_factory = uow_factory
        self._business_boundaries = business_boundaries

    def get(self, project_id: str) -> BoundaryWorkspaceStatusView:
        with self._uow_factory() as work:
            project = work.projects.get(project_id)
            understanding = work.application_understanding.get(project_id)
        if project is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
        if understanding is None:
            raise JiejianError(
                ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                "应用理解记录不存在",
            )

        boundary = self._business_boundaries.view(project_id)
        pending = self._business_boundaries.proposals(
            project_id,
            pending_only=True,
        ).proposals
        has_boundary = bool(
            boundary.actors
            and boundary.actions
            and all(
                item.permission_semantics_confirmed
                for item in boundary.permission_statuses
            )
        )
        attention = self._attention(understanding, pending=bool(pending), has_boundary=has_boundary)
        source_status = self._source_status(understanding)
        readiness = CurrentReadinessView(
            project_id=project_id,
            project_status=project.status,
            application_connected=True,
            endpoint_status=self._endpoint_status(understanding),
            source_analysis_status=source_status,
            discovered_role_count=len(understanding.role_candidates),
            confirmed_role_count=sum(
                item.decision is CandidateDecision.CONFIRMED and not item.stale
                for item in understanding.role_candidates
            ),
            discovered_action_count=len(understanding.action_candidates),
            confirmed_action_count=sum(
                item.decision is CandidateDecision.CONFIRMED and not item.stale
                for item in understanding.action_candidates
            ),
            execution_profile_available=False,
            completed_flow_available=False,
            active_contract_available=False,
            permission_actions=(),
            permission_requirement_count=len(boundary.permission_intents),
            confirmed_permission_requirement_count=len(boundary.permission_intents),
            executable_permission_requirement_count=0,
            permission_representative_gap_count=len(boundary.permission_intents),
            current_scope_runnable=False,
            remaining_gap_count=0 if has_boundary else 1,
            active_tasks=(),
            latest_verified_run_id=None,
            next_required_action=self._next_required_action(understanding, has_boundary),
            preparation=None,
        )
        return BoundaryWorkspaceStatusView(
            project=CurrentProjectSummary(
                project_id=project.project_id,
                name=project.name,
                status=project.status,
                target_type=project.target_type,
            ),
            readiness=readiness,
            areas=self._areas(has_boundary=has_boundary, pending=bool(pending)),
            primary_attention_key=attention.key if attention is not None else None,
            attention_items=() if attention is None else (attention,),
        )

    @staticmethod
    def _endpoint_status(understanding) -> str:
        if understanding.confirmed_endpoint is None:
            return "NEEDS_CONFIRMATION"
        if understanding.endpoint_reachable is False:
            return "UNAVAILABLE"
        return "CONFIRMED"

    @staticmethod
    def _source_status(understanding) -> str:
        if not understanding.source_analysis_authorized:
            return "NOT_AUTHORIZED"
        if understanding.analysis_completed_at_us is not None:
            return "COMPLETED"
        return "PENDING"

    @classmethod
    def _next_required_action(cls, understanding, has_boundary: bool) -> str:
        if cls._endpoint_status(understanding) != "CONFIRMED":
            return "CONFIRM_TARGET"
        if cls._source_status(understanding) != "COMPLETED":
            return "AUTHORIZE_SOURCE_ANALYSIS"
        return "RECORD_FLOW" if has_boundary else "REVIEW_PERMISSION"

    @classmethod
    def _attention(cls, understanding, *, pending: bool, has_boundary: bool):
        if cls._endpoint_status(understanding) != "CONFIRMED":
            return CurrentAttentionView(
                key="connect-application",
                label="确认应用连接",
                description="确认当前本地 Web 应用的访问地址。",
                route="/application",
            )
        if cls._source_status(understanding) != "COMPLETED":
            return CurrentAttentionView(
                key="authorize-source-analysis",
                label="授权只读源码分析",
                description="授权界鉴从当前源码整理业务主体和动作候选。",
                route="/application",
            )
        if pending:
            return CurrentAttentionView(
                key="review-business-boundary",
                label="审阅业务边界",
                description="已有不可变业务边界提案等待你的明确决定。",
                route="/permissions",
            )
        if not has_boundary:
            return CurrentAttentionView(
                key="create-business-boundary",
                label="建立业务边界",
                description="从源码候选或手工输入建立稳定业务权限。",
                route="/permissions",
            )
        return None

    @staticmethod
    def _areas(*, has_boundary: bool, pending: bool) -> tuple[CurrentAreaView, ...]:
        permission_status = "NEEDS_ATTENTION" if pending or not has_boundary else "READY"
        permission_label = (
            "待审阅提案" if pending else "业务边界已确认" if has_boundary else "需要建立"
        )
        return (
            CurrentAreaView(
                key="overview",
                label="工作台",
                description="查看当前应用与业务边界状态。",
                route="/workspace",
                status="READY",
                status_label="持续更新",
            ),
            CurrentAreaView(
                key="changes",
                label="变化",
                description="完整变化主链将在后续版本重新接入。",
                route="/changes",
                status="BLOCKED",
                status_label="当前暂不可用",
            ),
            CurrentAreaView(
                key="permissions",
                label="权限",
                description="建立并审阅稳定业务边界。",
                route="/permissions",
                status=permission_status,
                status_label=permission_label,
            ),
            CurrentAreaView(
                key="tests",
                label="测试",
                description="新检查主链尚未重新接入。",
                route="/tests",
                status="BLOCKED",
                status_label="当前不可检查",
            ),
        )


__all__ = ["BoundaryWorkspaceStatusService"]
