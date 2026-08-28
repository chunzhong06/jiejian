# =============================================================================
# Web V1 控制面只读查询
#
# 定位
#   GUI 工作台、CLI status 与 Machine status 共同消费的薄查询边界。
#
# 职责
#   业务流程列表｜结果选择｜组合 ProjectReadiness｜给出六步状态、唯一下一步和最近结果摘要
#
# 边界
#   不保存进度，不调用 AI，不编译或提交检查，也不重新解释 ResultPresentation。
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus, RunVerdict
from product.backend.workflows.projects.readiness import (
    NextRequiredAction,
    ProjectReadinessView,
)
from product.protocols import TargetType


class ProductFlowQuery:
    """只组合既有 Recording/Job 事实，不创建新的流程生命周期。"""

    def __init__(self, projects, uow_factory) -> None:
        self._projects = projects
        self._uow_factory = uow_factory

    def list(self, project_id: str) -> tuple[dict[str, object], ...]:
        self._projects.get(project_id)
        with self._uow_factory() as work:
            recordings = work.recordings.list_for_project(project_id)
            return tuple(
                {
                    **item.model_dump(mode="json"),
                    "job": (
                        job.model_dump(mode="json")
                        if (job := work.jobs.get_by_recording(item.recording_id))
                        else None
                    ),
                }
                for item in recordings
            )


class ProductResultQuery:
    """只负责结果选择；结果内容继续由既有确定性读模型形成。"""

    def __init__(self, status, presentation, history) -> None:
        self._status = status
        self._presentation = presentation
        self._history = history

    def presentation(
        self,
        *,
        run_id: str | None = None,
        project_id: str | None = None,
    ):
        selected_run_id = run_id
        if selected_run_id is None:
            status = self._status.get(project_id)
            selected_run_id = (
                status.readiness.latest_verified_run_id
                if status.readiness is not None
                else None
            )
        if selected_run_id is None:
            raise JiejianError(
                ErrorCode.REPORT_NOT_FOUND,
                "当前应用还没有可信检查结果",
            )
        return self._presentation.build(selected_run_id)

    def history(self, project_id: str | None = None):
        status = self._status.get(project_id)
        if status.project is None:
            raise JiejianError(
                ErrorCode.PROJECT_NOT_FOUND,
                "当前还没有已接入应用",
            )
        return self._history.build(status.project.project_id)


class _ControlModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class ProductProjectSummary(_ControlModel):
    project_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    status: ProjectStatus
    target_type: TargetType


class ProductStepView(_ControlModel):
    key: Literal["application", "account", "flow", "check", "result", "history"]
    label: str = Field(min_length=1, max_length=32)
    route: Literal[
        "/application",
        "/identities",
        "/flows",
        "/check",
        "/results",
        "/history",
    ]
    status: Literal["COMPLETE", "CURRENT", "UPCOMING", "AVAILABLE", "EMPTY"]
    status_label: str = Field(min_length=1, max_length=32)


class ProductNextAction(_ControlModel):
    action: NextRequiredAction
    label: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=240)
    route: Literal["/application", "/identities", "/flows", "/check", "/results"]
    cli_command: str = Field(min_length=1, max_length=160)


class ProductResultSummary(_ControlModel):
    run_id: str = Field(min_length=1, max_length=128)
    verdict: RunVerdict | None
    headline: str = Field(min_length=1, max_length=160)
    scope_statement: str = Field(min_length=1, max_length=320)


class ProductStatusView(_ControlModel):
    project: ProductProjectSummary | None = None
    readiness: ProjectReadinessView | None = None
    steps: tuple[ProductStepView, ...]
    next_action: ProductNextAction
    latest_result: ProductResultSummary | None = None


_STEP_DEFINITIONS = (
    ("application", "应用接入", "/application"),
    ("account", "测试账号", "/identities"),
    ("flow", "业务流程", "/flows"),
    ("check", "权限与检查", "/check"),
    ("result", "检查结果", "/results"),
    ("history", "历史变化", "/history"),
)


class ProductStatusService:
    """只组合现有权威 View；每次调用都重新读取当前事实。"""

    def __init__(
        self,
        projects,
        readiness: Callable[[str], ProjectReadinessView],
        result_presentation,
    ) -> None:
        self._projects = projects
        self._readiness = readiness
        self._result_presentation = result_presentation

    def get(self, project_id: str | None = None) -> ProductStatusView:
        project = self._select_project(project_id)
        if project is None:
            next_action = _next_action(None)
            return ProductStatusView(
                steps=_steps(None, next_action.route),
                next_action=next_action,
            )
        readiness = self._readiness(project.project_id)
        next_action = _next_action(readiness)
        latest_result = None
        if readiness.latest_verified_run_id is not None:
            presentation = self._result_presentation.build(
                readiness.latest_verified_run_id
            )
            latest_result = ProductResultSummary(
                run_id=presentation.run_id,
                verdict=presentation.verdict,
                headline=presentation.headline,
                scope_statement=presentation.scope_statement,
            )
        return ProductStatusView(
            project=ProductProjectSummary(
                project_id=project.project_id,
                name=project.name,
                status=project.status,
                target_type=project.target_type,
            ),
            readiness=readiness,
            steps=_steps(readiness, next_action.route),
            next_action=next_action,
            latest_result=latest_result,
        )

    def _select_project(self, project_id: str | None):
        if project_id is not None:
            return self._projects.get(project_id)
        projects = self._projects.list()
        if not projects:
            return None
        if len(projects) > 1:
            raise JiejianError(
                ErrorCode.INPUT_INVALID,
                "当前有多个应用，请使用 --project 明确选择",
                details={"project_count": len(projects)},
            )
        return projects[0]


def _readiness_route(readiness: ProjectReadinessView | None) -> str:
    if (
        readiness is None
        or readiness.endpoint_status == "LEGACY_PROFILE"
        or readiness.source_analysis_status == "LEGACY_PROFILE"
    ):
        return "/application"
    if readiness.next_required_action in {
        "CONNECT_APPLICATION",
        "CONFIRM_TARGET",
        "AUTHORIZE_SOURCE_ANALYSIS",
        "REVIEW_DISCOVERY",
    }:
        return "/application"
    if readiness.next_required_action == "RECORD_FLOW":
        identity_gap_codes = {
            "TEST_IDENTITY_MISSING",
            "TEST_IDENTITY_NOT_PREPARED",
            "MISSING_SUBJECT",
        }
        has_identity_gap = any(
            gap in identity_gap_codes
            for action in readiness.permission_actions
            for gap in action.gaps
        )
        return (
            "/identities"
            if not readiness.permission_actions or has_identity_gap
            else "/flows"
        )
    if readiness.next_required_action in {"REVIEW_PERMISSION", "RUN_CHECK"}:
        return "/check"
    return "/results"


def _next_action(readiness: ProjectReadinessView | None) -> ProductNextAction:
    action: NextRequiredAction = (
        "CONNECT_APPLICATION" if readiness is None else readiness.next_required_action
    )
    route = _readiness_route(readiness)
    values: dict[NextRequiredAction, tuple[str, str, str]] = {
        "CONNECT_APPLICATION": (
            "接入应用",
            "选择本地应用目录，让界鉴建立正式应用记录。",
            "jiejian app connect <应用目录>",
        ),
        "CONFIRM_TARGET": (
            "确认应用地址",
            "确认真正要检查的本地 Web 应用地址。",
            "jiejian app confirm-endpoint --help",
        ),
        "AUTHORIZE_SOURCE_ANALYSIS": (
            "授权只读分析",
            "明确授权后，界鉴才会只读分析应用源码。",
            "jiejian app authorize-source --help",
        ),
        "REVIEW_DISCOVERY": (
            "确认权限组与业务动作",
            "审阅系统发现的候选，不把候选当作权限结论。",
            "jiejian app show --help",
        ),
        "RECORD_FLOW": (
            (
                "准备测试账号"
                if route == "/identities"
                else "录制业务流程"
            ),
            (
                "先为已确认权限组准备安全登录状态。"
                if route == "/identities"
                else "用真实浏览器录制关键业务操作，并确认观察与恢复方式。"
            ),
            (
                "jiejian account --help"
                if route == "/identities"
                else "jiejian flow --help"
            ),
        ),
        "REVIEW_PERMISSION": (
            "确认权限规则",
            "明确谁应该允许或拒绝执行关键业务动作。",
            "jiejian check permissions --help",
        ),
        "RUN_CHECK": (
            "开始权限检查",
            "核对受控检查范围后，明确开始本次安全验证。",
            "jiejian check run --help",
        ),
        "OPEN_RESULT": (
            "查看检查结果",
            "查看真实副作用、可信证据和已经发布的安全结论。",
            "jiejian result show --help",
        ),
    }
    label, description, command = values[action]
    return ProductNextAction(
        action=action,
        label=label,
        description=description,
        route=route,
        cli_command=command,
    )


def _steps(
    readiness: ProjectReadinessView | None,
    current_route: str,
) -> tuple[ProductStepView, ...]:
    current_index = next(
        index
        for index, (_, _, route) in enumerate(_STEP_DEFINITIONS)
        if route == current_route
    )
    rows: list[ProductStepView] = []
    for index, (key, label, route) in enumerate(_STEP_DEFINITIONS):
        if index < current_index:
            status, status_label = "COMPLETE", "已完成"
        elif index == current_index:
            status, status_label = "CURRENT", "当前步骤"
        elif route in {"/results", "/history"} and readiness is not None and readiness.latest_verified_run_id:
            status, status_label = "AVAILABLE", "可查看"
        elif route == "/history":
            status, status_label = "EMPTY", "暂无历史"
        else:
            status, status_label = "UPCOMING", "尚未开始"
        rows.append(
            ProductStepView(
                key=key,
                label=label,
                route=route,
                status=status,
                status_label=status_label,
            )
        )
    return tuple(rows)


__all__ = [
    "ProductFlowQuery",
    "ProductNextAction",
    "ProductProjectSummary",
    "ProductResultQuery",
    "ProductResultSummary",
    "ProductStatusService",
    "ProductStatusView",
    "ProductStepView",
]
