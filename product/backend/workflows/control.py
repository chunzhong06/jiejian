# =============================================================================
# 持续验证控制面只读查询
#
# 定位
#   GUI 工作区、CLI status 与 Machine status 共同消费的产品状态投影。
#
# 职责
#   业务流程列表｜结果选择｜组合准备度、ProjectRevalidation、长期工作区与多项待办
#
# 边界
#   不保存进度，不调用 AI，不编译或提交检查，也不重新解释安全结论。
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus, RunVerdict
from product.backend.workflows.projects.revalidation import (
    ProjectRevalidationStatus,
    ProjectRevalidationView,
)
from product.backend.workflows.projects.repair import (
    ProjectRepairStatus,
    ProjectRepairView,
)
from product.backend.workflows.projects.readiness import ProjectReadinessView
from product.backend.workflows.source_changes import SourceChangeView
from product.protocols import TargetType

ProductRoute = Literal[
    "/workspace",
    "/application",
    "/changes",
    "/permissions",
    "/preparation",
    "/identities",
    "/flows",
    "/validation",
    "/results",
    "/verification",
    "/history",
]


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


class ProductAreaView(_ControlModel):
    key: Literal[
        "overview",
        "changes",
        "permissions",
        "preparation",
        "validation",
        "results",
    ]
    label: str = Field(min_length=1, max_length=32)
    description: str = Field(min_length=1, max_length=160)
    route: Literal[
        "/workspace",
        "/changes",
        "/permissions",
        "/preparation",
        "/validation",
        "/results",
    ]
    status: Literal[
        "READY",
        "NEEDS_ATTENTION",
        "RUNNING",
        "AVAILABLE",
        "BLOCKED",
        "EMPTY",
    ]
    status_label: str = Field(min_length=1, max_length=32)


class ProductAttentionView(_ControlModel):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    route: ProductRoute
    tone: Literal["ACTION", "WARNING", "INFO"] = "ACTION"


class ProductResultSummary(_ControlModel):
    run_id: str = Field(min_length=1, max_length=128)
    verdict: RunVerdict | None
    headline: str = Field(min_length=1, max_length=160)
    scope_statement: str = Field(min_length=1, max_length=320)
    verified_change_id: str | None = Field(
        default=None,
        pattern=r"^chg_[0-9a-f]{32}$",
    )


class InconclusiveRecoveryView(_ControlModel):
    source_run_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=320)
    next_path: Literal["/changes", "/permissions", "/preparation", "/validation"]
    next_label: str = Field(min_length=1, max_length=80)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)


class ProductStatusView(_ControlModel):
    project: ProductProjectSummary | None = None
    readiness: ProjectReadinessView | None = None
    revalidation: ProjectRevalidationView | None = None
    repair: ProjectRepairView | None = None
    areas: tuple[ProductAreaView, ...]
    attention_items: tuple[ProductAttentionView, ...]
    latest_change: SourceChangeView | None = None
    latest_result: ProductResultSummary | None = None
    inconclusive_recovery: InconclusiveRecoveryView | None = None


class ProductStatusService:
    """每次从当前事实组合持续验证工作区，不把页面位置保存成产品进度。"""

    def __init__(
        self,
        projects,
        readiness: Callable[[str], ProjectReadinessView],
        result_presentation,
        source_changes=None,
        project_revalidation=None,
        project_repair=None,
        current_permission_intents: Callable[[str], tuple] | None = None,
    ) -> None:
        self._projects = projects
        self._readiness = readiness
        self._result_presentation = result_presentation
        self._source_changes = source_changes
        self._project_revalidation = project_revalidation
        self._project_repair = project_repair
        self._current_permission_intents = current_permission_intents

    def get(self, project_id: str | None = None) -> ProductStatusView:
        project = self._select_project(project_id)
        if project is None:
            return ProductStatusView(
                areas=_areas(None, None, None),
                attention_items=(
                    ProductAttentionView(
                        key="connect-application",
                        label="接入第一个应用",
                        description="选择本地 Web 应用，建立持续验证的初始安全基线。",
                        route="/application",
                    ),
                ),
            )
        readiness = self._readiness(project.project_id)
        latest_change = (
            None
            if self._source_changes is None
            else self._source_changes.latest_view(project.project_id)
        )
        latest_presentation = self._latest_presentation(readiness)
        latest_result = self._result_summary(latest_presentation)
        revalidation = (
            None
            if self._project_revalidation is None
            else self._project_revalidation.evaluate(
                project.project_id,
                preparation=readiness.preparation,
                verified_run_id=(
                    None if latest_result is None else latest_result.run_id
                ),
                verified_change_id=(
                    None
                    if latest_result is None
                    else latest_result.verified_change_id
                ),
            )
        )
        inconclusive_recovery = self._inconclusive_recovery(
            project.project_id,
            readiness,
            revalidation,
            latest_result,
            latest_presentation,
        )
        repair = (
            None
            if self._project_repair is None
            else self._project_repair.evaluate(
                project.project_id,
                preparation=readiness.preparation,
                verified_run_id=None if latest_result is None else latest_result.run_id,
                verified_change_id=(
                    None if latest_result is None else latest_result.verified_change_id
                ),
            )
        )
        repair = _repair_with_inconclusive_recovery(repair, inconclusive_recovery)
        return ProductStatusView(
            project=ProductProjectSummary(
                project_id=project.project_id,
                name=project.name,
                status=project.status,
                target_type=project.target_type,
            ),
            readiness=readiness,
            revalidation=revalidation,
            repair=repair,
            areas=_areas(readiness, latest_change, revalidation),
            attention_items=_attention_items(
                readiness,
                revalidation,
                latest_result,
                inconclusive_recovery,
                repair,
            ),
            latest_change=latest_change,
            latest_result=latest_result,
            inconclusive_recovery=inconclusive_recovery,
        )

    def _latest_presentation(
        self,
        readiness: ProjectReadinessView,
    ):
        if readiness.latest_verified_run_id is None:
            return None
        return self._result_presentation.build(
            readiness.latest_verified_run_id
        )

    @staticmethod
    def _result_summary(presentation) -> ProductResultSummary | None:
        if presentation is None:
            return None
        change_verification = presentation.change_verification
        return ProductResultSummary(
            run_id=presentation.run_id,
            verdict=presentation.verdict,
            headline=presentation.headline,
            scope_statement=presentation.scope_statement,
            verified_change_id=(
                None
                if change_verification is None
                else change_verification.change_id
            ),
        )

    def _inconclusive_recovery(
        self,
        project_id: str,
        readiness: ProjectReadinessView,
        revalidation: ProjectRevalidationView | None,
        latest_result: ProductResultSummary | None,
        latest_presentation,
    ) -> InconclusiveRecoveryView | None:
        if (
            latest_result is None
            or latest_result.verdict is not RunVerdict.INCONCLUSIVE
            or latest_presentation is None
        ):
            return None
        current_intents = (
            ()
            if self._current_permission_intents is None
            else self._current_permission_intents(project_id)
        )
        source_identity = _intent_identity(latest_presentation.relevant_intents)
        current_identity = _intent_identity(current_intents)
        if source_identity != current_identity:
            return InconclusiveRecoveryView(
                source_run_id=latest_result.run_id,
                summary="原权限考题已经变化，当前不能把新的检查称为原题复验。",
                next_path="/permissions",
                next_label="查看当前权限规则",
                reason_codes=("ORIGINAL_PERMISSION_INTENT_CHANGED",),
            )
        if revalidation is not None and revalidation.status in {
            ProjectRevalidationStatus.REVIEW_REQUIRED,
            ProjectRevalidationStatus.STALE,
        }:
            assert revalidation.next_path in {"/changes", "/permissions"}
            return InconclusiveRecoveryView(
                source_run_id=latest_result.run_id,
                summary=(
                    "上次证据不足结果会永久保留；请先完成当前代码变化审阅。"
                ),
                next_path=revalidation.next_path,
                next_label=revalidation.next_label or "处理代码变化",
                reason_codes=tuple(
                    dict.fromkeys(
                        (
                            f"PROJECT_REVALIDATION_{revalidation.status.value}",
                            *revalidation.reason_codes,
                        )
                    )
                ),
            )
        if (
            revalidation is not None
            and revalidation.status is ProjectRevalidationStatus.PREPARATION_REQUIRED
        ) or readiness.preparation is None or not readiness.preparation.ready:
            return InconclusiveRecoveryView(
                source_run_id=latest_result.run_id,
                summary="上次结果仍保留为证据不足；请只修复当前失效的测试条件。",
                next_path="/preparation",
                next_label="修复测试准备",
                reason_codes=("PREPARATION_NOT_READY",),
            )
        return InconclusiveRecoveryView(
            source_run_id=latest_result.run_id,
            summary="当前测试条件已经恢复；旧结果仍保持证据不足，可以开始一次新的独立检查。",
            next_path="/validation",
            next_label="重新检查原权限考题",
            reason_codes=("ORIGINAL_PERMISSION_INTENT_READY",),
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


def _areas(
    readiness: ProjectReadinessView | None,
    latest_change: SourceChangeView | None,
    revalidation: ProjectRevalidationView | None,
) -> tuple[ProductAreaView, ...]:
    if readiness is None:
        states = {
            "overview": ("READY", "可以开始"),
            "changes": ("EMPTY", "尚无应用"),
            "permissions": ("BLOCKED", "尚未建立"),
            "preparation": ("BLOCKED", "尚未建立"),
            "validation": ("BLOCKED", "尚未建立"),
            "results": ("EMPTY", "暂无结果"),
        }
    else:
        discovery_attention = readiness.source_analysis_status != "COMPLETED"
        change_attention = bool(
            revalidation
            and revalidation.status
            in {
                ProjectRevalidationStatus.REVIEW_REQUIRED,
                ProjectRevalidationStatus.STALE,
            }
        )
        permission_attention = any(
            not action.compilable for action in readiness.permission_actions
        ) or bool(
            revalidation
            and revalidation.status is ProjectRevalidationStatus.REVIEW_REQUIRED
        )
        preparation_ready = bool(
            readiness.preparation is not None and readiness.preparation.ready
        )
        # 变化重验不是前端附加标签；非 READY 前置态必须同步关闭工作台验证入口。
        revalidation_allows_validation = bool(
            revalidation is None
            or revalidation.status
            in {
                ProjectRevalidationStatus.NO_CHANGE,
                ProjectRevalidationStatus.READY,
            }
        )
        run_active = any(task.kind == "RUN" for task in readiness.active_tasks)
        states = {
            "overview": ("READY", "当前概览"),
            "changes": (
                "NEEDS_ATTENTION"
                if discovery_attention or change_attention
                else "AVAILABLE"
                if latest_change
                else "EMPTY",
                "需要处理"
                if discovery_attention or change_attention
                else "已有记录"
                if latest_change
                else "等待变化",
            ),
            "permissions": (
                "NEEDS_ATTENTION"
                if permission_attention
                else "READY"
                if readiness.active_contract_available
                else "BLOCKED",
                "需要确认"
                if permission_attention
                else "规则已建立"
                if readiness.active_contract_available
                else "尚未建立",
            ),
            "preparation": (
                "READY" if preparation_ready else "NEEDS_ATTENTION",
                "测试条件可用" if preparation_ready else "需要补充",
            ),
            "validation": (
                "RUNNING"
                if run_active
                else "READY"
                if readiness.current_scope_runnable and revalidation_allows_validation
                else "BLOCKED",
                "正在检查"
                if run_active
                else "可以检查"
                if readiness.current_scope_runnable and revalidation_allows_validation
                else "等待准备",
            ),
            "results": (
                "AVAILABLE" if readiness.latest_verified_run_id else "EMPTY",
                "已有可信结果" if readiness.latest_verified_run_id else "暂无结果",
            ),
        }
    definitions = (
        ("overview", "项目概览", "查看当前安全基线、覆盖范围和待处理事项", "/workspace"),
        ("changes", "变化与待办", "跟踪 Agent 修改、新发现和需要重新确认的内容", "/changes"),
        ("permissions", "权限规则", "维护由人确认且不会被 Agent 改写的权限要求", "/permissions"),
        ("preparation", "测试准备", "补齐测试账号、业务流程、结果确认和现场恢复", "/preparation"),
        ("validation", "验证运行", "核对当前范围并检查真实业务后果", "/validation"),
        ("results", "结果与历史", "查看结论、完整链路、证据和历次变化", "/results"),
    )
    return tuple(
        ProductAreaView(
            key=key,
            label=label,
            description=description,
            route=route,
            status=states[key][0],
            status_label=states[key][1],
        )
        for key, label, description, route in definitions
    )


def _attention_items(
    readiness: ProjectReadinessView,
    revalidation: ProjectRevalidationView | None,
    latest_result: ProductResultSummary | None,
    inconclusive_recovery: InconclusiveRecoveryView | None,
    repair: ProjectRepairView | None,
) -> tuple[ProductAttentionView, ...]:
    items: list[ProductAttentionView] = []
    if readiness.active_tasks:
        run_active = any(task.kind == "RUN" for task in readiness.active_tasks)
        items.append(
            ProductAttentionView(
                key="active-task",
                label=(
                    "查看正在进行的验证"
                    if run_active
                    else "查看正在录制的业务流程"
                ),
                description=(
                    "当前验证仍在运行，可以查看最新进度。"
                    if run_active
                    else "当前业务流程仍在录制，可以返回测试准备继续处理。"
                ),
                route="/validation" if run_active else "/preparation",
                tone="INFO",
            )
        )
    if readiness.endpoint_status != "CONFIRMED":
        items.append(
            ProductAttentionView(
                key="confirm-application",
                label="确认应用连接",
                description="先确认被测应用地址和只读源码分析范围。",
                route="/application",
                tone="WARNING",
            )
        )
    elif readiness.next_required_action == "AUTHORIZE_SOURCE_ANALYSIS":
        items.append(
            ProductAttentionView(
                key="authorize-source-analysis",
                label="授权只读源码分析",
                description="明确授权后，界鉴才会分析源码并发现权限组与业务动作。",
                route="/application",
                tone="WARNING",
            )
        )
    elif readiness.source_analysis_status != "COMPLETED":
        items.append(
            ProductAttentionView(
                key="review-discovery",
                label="确认新发现的权限范围",
                description="代码变化后出现了新的权限组、业务动作或需要复核的候选。",
                route="/application",
                tone="WARNING",
            )
        )
    if any(not action.compilable for action in readiness.permission_actions):
        items.append(
            ProductAttentionView(
                key="review-permissions",
                label="补齐或重新确认权限规则",
                description="新增或变化的业务动作还没有形成完整的允许与拒绝对照。",
                route="/permissions",
            )
        )
    if repair is not None and repair.status not in {
        ProjectRepairStatus.NONE,
        ProjectRepairStatus.VERIFIED,
    }:
        route_already_present = bool(
            repair.next_path
            and any(item.route == repair.next_path and item.tone != "INFO" for item in items)
        )
        if not route_already_present:
            items.append(
                ProductAttentionView(
                    key="continue-project-repair",
                    label=repair.next_label or "继续处理当前修复",
                    description=(
                        repair.tasks[0].must_disappear
                        if repair.tasks
                        else "当前权限问题仍未完成独立修复复验。"
                    ),
                    route=repair.next_path or "/results",
                    tone="WARNING",
                )
            )
    if revalidation is not None and revalidation.status in {
        ProjectRevalidationStatus.REVIEW_REQUIRED,
        ProjectRevalidationStatus.STALE,
    }:
        route = revalidation.next_path or "/changes"
        route_already_present = any(
            item.route == route and item.tone != "INFO" for item in items
        )
        if not route_already_present:
            items.append(
                ProductAttentionView(
                    key="review-change-mapping",
                    label=(
                        "重新确认权限规则与当前实现"
                        if revalidation.status is ProjectRevalidationStatus.REVIEW_REQUIRED
                        else "重新建立代码变化事实"
                    ),
                    description=revalidation.summary,
                    route=route,
                    tone="WARNING",
                )
            )
    if (
        inconclusive_recovery is None
        and readiness.preparation is not None
        and not readiness.preparation.ready
    ):
        items.append(
            ProductAttentionView(
                key="complete-preparation",
                label="补齐新增或失效的测试准备",
                description="只处理当前缺少的测试账号、业务流程、结果确认或现场恢复。",
                route="/preparation",
            )
        )
    recovery_route_already_present = bool(
        inconclusive_recovery is not None
        and any(
            item.route == inconclusive_recovery.next_path
            and item.tone != "INFO"
            for item in items
        )
    )
    if inconclusive_recovery is not None and not recovery_route_already_present:
        items.append(
            ProductAttentionView(
                key="recover-inconclusive",
                label=inconclusive_recovery.next_label,
                description=inconclusive_recovery.summary,
                route=inconclusive_recovery.next_path,
                tone="WARNING",
            )
        )
    if (
        inconclusive_recovery is None
        and readiness.current_scope_runnable
        and revalidation is not None
        and revalidation.status is ProjectRevalidationStatus.READY
    ):
        items.append(
            ProductAttentionView(
                key="verify-latest-change",
                label="检查最近一次代码变化",
                description="按当前完整权限范围运行，并把这次变化冻结到检查记录中。",
                route="/validation",
            )
        )
    elif (
        inconclusive_recovery is None
        and readiness.current_scope_runnable
        and latest_result is None
        and (
            revalidation is None
            or revalidation.status is ProjectRevalidationStatus.NO_CHANGE
        )
    ):
        items.append(
            ProductAttentionView(
                key="run-current-scope",
                label="建立第一份安全基线",
                description="当前已有可运行范围，可以开始真实检查。",
                route="/validation",
            )
        )
    if latest_result is not None:
        items.append(
            ProductAttentionView(
                key="open-result",
                label="查看当前安全基线",
                description=latest_result.headline,
                route="/results",
                tone="INFO",
            )
        )
    return tuple(items)


def _repair_with_inconclusive_recovery(
    repair: ProjectRepairView | None,
    recovery: InconclusiveRecoveryView | None,
) -> ProjectRepairView | None:
    if (
        repair is None
        or recovery is None
        or repair.status is not ProjectRepairStatus.INCONCLUSIVE
    ):
        return repair
    tasks = tuple(
        task.model_copy(
            update={
                "next_path": recovery.next_path,
                "next_label": recovery.next_label,
                "reason_codes": tuple(
                    dict.fromkeys((*task.reason_codes, *recovery.reason_codes))
                ),
            }
        )
        if task.status is ProjectRepairStatus.INCONCLUSIVE
        else task
        for task in repair.tasks
    )
    return repair.model_copy(
        update={
            "tasks": tasks,
            "next_path": recovery.next_path,
            "next_label": recovery.next_label,
            "reason_codes": tuple(
                dict.fromkeys((*repair.reason_codes, *recovery.reason_codes))
            ),
        }
    )


def _intent_identity(items) -> tuple[tuple[str, int, str], ...]:
    return tuple(
        sorted(
            (
                str(item.intent_id),
                int(item.revision),
                str(item.intent_hash),
            )
            for item in items
        )
    )


__all__ = [
    "InconclusiveRecoveryView",
    "ProductAreaView",
    "ProductAttentionView",
    "ProductFlowQuery",
    "ProductProjectSummary",
    "ProductResultQuery",
    "ProductResultSummary",
    "ProductStatusService",
    "ProductStatusView",
]
