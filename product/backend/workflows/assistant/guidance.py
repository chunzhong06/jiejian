# =============================================================================
# 确定性项目引导快照
#
# 定位
#   把 ProjectReadiness 与 CheckPreview 的权威事实收敛为模型可选的有限下一步。
#
# 职责
#   生成稳定选项｜保留当前可运行检查｜计算只含语义事实的指纹
#
# 边界
#   不调用模型、不写数据库、不创建 CheckPlan，也不推导权限预期或安全结论。
#
# 调用链
#   Assistant API / Workbench → build_guidance_snapshot → Readiness / CheckPreview
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from product.backend.core.errors import JiejianError
from product.backend.workflows.projects.readiness import (
    NextRequiredAction,
    ProjectReadinessView,
)
from product.backend.workflows.security_setup.checks import CheckPreview, CheckPreviewGap


GuidanceRoute = Literal[
    "/workspace",
    "/application",
    "/changes",
    "/permissions",
    "/preparation",
    "/validation",
    "/results",
]


class GuidancePhase(StrEnum):
    APPLICATION_CONNECTION = "APPLICATION_CONNECTION"
    APPLICATION_UNDERSTANDING = "APPLICATION_UNDERSTANDING"
    IDENTITY_PREPARATION = "IDENTITY_PREPARATION"
    RECORDING = "RECORDING"
    CHANGE_REVIEW = "CHANGE_REVIEW"
    PERMISSION_REVIEW = "PERMISSION_REVIEW"
    CHECK_READY = "CHECK_READY"
    CHECK_RUNNING = "CHECK_RUNNING"
    RESULT_AVAILABLE = "RESULT_AVAILABLE"


class GuidanceOptionKind(StrEnum):
    CONNECT_APPLICATION = "CONNECT_APPLICATION"
    CONFIRM_TARGET = "CONFIRM_TARGET"
    AUTHORIZE_SOURCE_ANALYSIS = "AUTHORIZE_SOURCE_ANALYSIS"
    REVIEW_DISCOVERY = "REVIEW_DISCOVERY"
    PREPARE_IDENTITY = "PREPARE_IDENTITY"
    RECORD_ACTION = "RECORD_ACTION"
    REVIEW_CHANGE = "REVIEW_CHANGE"
    REVIEW_PERMISSION = "REVIEW_PERMISSION"
    RESOLVE_COVERAGE_GAP = "RESOLVE_COVERAGE_GAP"
    START_CURRENT_CHECK = "START_CURRENT_CHECK"
    OPEN_ACTIVE_TASK = "OPEN_ACTIVE_TASK"
    OPEN_LATEST_RESULT = "OPEN_LATEST_RESULT"
    RECOVER_FROM_ERROR = "RECOVER_FROM_ERROR"


class GuidancePriorityTier(StrEnum):
    PRIMARY = "PRIMARY"
    BLOCKING = "BLOCKING"
    OPTIONAL = "OPTIONAL"


class _GuidanceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class GuidanceOption(_GuidanceModel):
    option_id: str = Field(pattern=r"^opt_[0-9a-f]{24}$")
    kind: GuidanceOptionKind
    title: str = Field(min_length=1, max_length=160)
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=32)
    priority_tier: GuidancePriorityTier
    route: GuidanceRoute

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            re.fullmatch(r"[A-Z][A-Z0-9_]{1,95}", value) is None for value in values
        ):
            raise ValueError("guidance reason codes must be unique stable codes")
        return tuple(sorted(values))


class GuidanceSnapshot(_GuidanceModel):
    project_id: str = Field(min_length=1, max_length=64)
    state_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    phase: GuidancePhase
    current_scope_runnable: bool
    remaining_gap_count: int = Field(ge=0)
    options: tuple[GuidanceOption, ...] = Field(min_length=1, max_length=64)


class GuidanceQueryService:
    """组合现有两个只读真源；准备尚未完成时退回 readiness，而不是制造持久化计划。"""

    def __init__(
        self,
        readiness_resolver: Callable[[str], ProjectReadinessView],
        preview_resolver: Callable[[str], CheckPreview],
    ) -> None:
        self._readiness_resolver = readiness_resolver
        self._preview_resolver = preview_resolver

    def get(self, project_id: str) -> GuidanceSnapshot:
        readiness = self._readiness_resolver(project_id)
        try:
            preview = self._preview_resolver(project_id)
        except JiejianError:
            preview = None
        return build_guidance_snapshot(readiness, preview)


_ROUTE_RANK: dict[str, int] = {
    "/application": 0,
    "/changes": 1,
    "/permissions": 2,
    "/preparation": 3,
    "/validation": 4,
}

_ROUTE_PRESENTATION: dict[str, tuple[GuidanceOptionKind, str]] = {
    "/application": (GuidanceOptionKind.REVIEW_DISCOVERY, "完善应用与权限组信息"),
    "/changes": (GuidanceOptionKind.REVIEW_CHANGE, "审阅最近代码变化"),
    "/permissions": (GuidanceOptionKind.REVIEW_PERMISSION, "确认权限规则与覆盖"),
    "/preparation": (GuidanceOptionKind.RESOLVE_COVERAGE_GAP, "完善测试账号、业务流程与真实结果确认"),
    "/validation": (GuidanceOptionKind.RESOLVE_COVERAGE_GAP, "重新准备本次检查"),
}

_NEXT_ACTION: dict[
    NextRequiredAction,
    tuple[GuidancePhase, GuidanceOptionKind, str, GuidanceRoute],
] = {
    "CONNECT_APPLICATION": (
        GuidancePhase.APPLICATION_CONNECTION,
        GuidanceOptionKind.CONNECT_APPLICATION,
        "接入要验证的本地应用",
        "/application",
    ),
    "CONFIRM_TARGET": (
        GuidancePhase.APPLICATION_CONNECTION,
        GuidanceOptionKind.CONFIRM_TARGET,
        "确认应用地址",
        "/application",
    ),
    "AUTHORIZE_SOURCE_ANALYSIS": (
        GuidancePhase.APPLICATION_UNDERSTANDING,
        GuidanceOptionKind.AUTHORIZE_SOURCE_ANALYSIS,
        "授权只读源码分析",
        "/application",
    ),
    "REVIEW_DISCOVERY": (
        GuidancePhase.APPLICATION_UNDERSTANDING,
        GuidanceOptionKind.REVIEW_DISCOVERY,
        "确认权限组与业务操作",
        "/application",
    ),
    "RECORD_FLOW": (
        GuidancePhase.RECORDING,
        GuidanceOptionKind.RECORD_ACTION,
        "准备测试账号并录制业务操作",
        "/preparation",
    ),
    "REVIEW_CHANGE": (
        GuidancePhase.CHANGE_REVIEW,
        GuidanceOptionKind.REVIEW_CHANGE,
        "审阅最近代码变化",
        "/changes",
    ),
    "REVIEW_PERMISSION": (
        GuidancePhase.PERMISSION_REVIEW,
        GuidanceOptionKind.REVIEW_PERMISSION,
        "确认权限规则",
        "/permissions",
    ),
    "RUN_CHECK": (
        GuidancePhase.CHECK_READY,
        GuidanceOptionKind.START_CURRENT_CHECK,
        "开始检查当前可运行范围",
        "/validation",
    ),
    "OPEN_RESULT": (
        GuidancePhase.RESULT_AVAILABLE,
        GuidanceOptionKind.OPEN_LATEST_RESULT,
        "查看最近一次可信检查结果",
        "/results",
    ),
}


def build_guidance_snapshot(
    readiness: ProjectReadinessView,
    preview: CheckPreview | None = None,
) -> GuidanceSnapshot:
    """从只读控制面事实构造有限选项，模型只能在这些选项中排序。"""

    options: list[GuidanceOption] = []
    if readiness.active_tasks:
        task_kinds = tuple(sorted({item.kind for item in readiness.active_tasks}))
        options.append(
            _option(
                GuidanceOptionKind.OPEN_ACTIVE_TASK,
                "查看正在进行的检查或录制",
                tuple(f"ACTIVE_{kind}" for kind in task_kinds),
                GuidancePriorityTier.PRIMARY,
                "/workspace",
            )
        )

    if readiness.current_scope_runnable:
        options.append(
            _option(
                GuidanceOptionKind.START_CURRENT_CHECK,
                "开始检查当前可运行范围",
                ("CURRENT_SCOPE_RUNNABLE",),
                GuidancePriorityTier.PRIMARY,
                "/validation",
            )
        )
        options.extend(_gap_options(preview, tier=GuidancePriorityTier.OPTIONAL))
        if readiness.latest_verified_run_id is not None:
            options.append(
                _option(
                    GuidanceOptionKind.OPEN_LATEST_RESULT,
                    "查看最近一次可信检查结果",
                    ("LATEST_VERIFIED_RESULT_AVAILABLE",),
                    GuidancePriorityTier.OPTIONAL,
                    "/results",
                )
            )
        phase = GuidancePhase.CHECK_READY
    else:
        options.extend(
            _gap_options(
                preview,
                tier=GuidancePriorityTier.BLOCKING,
                highest_route_only=True,
            )
        )
        phase, kind, title, route = _NEXT_ACTION[readiness.next_required_action]
        if not options:
            options.append(
                _option(
                    kind,
                    title,
                    (readiness.next_required_action,),
                    GuidancePriorityTier.BLOCKING,
                    route,
                )
            )

    if readiness.active_tasks and not readiness.current_scope_runnable:
        phase = GuidancePhase.CHECK_RUNNING
    ordered = tuple(sorted(_unique_options(options), key=_option_order))
    semantic = {
        "project_id": readiness.project_id,
        "phase": phase.value,
        "current_scope_runnable": readiness.current_scope_runnable,
        "remaining_gap_count": readiness.remaining_gap_count,
        "options": [item.model_dump(mode="json") for item in ordered],
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            semantic,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return GuidanceSnapshot(
        project_id=readiness.project_id,
        state_fingerprint=fingerprint,
        phase=phase,
        current_scope_runnable=readiness.current_scope_runnable,
        remaining_gap_count=readiness.remaining_gap_count,
        options=ordered,
    )


def _gap_options(
    preview: CheckPreview | None,
    *,
    tier: GuidancePriorityTier,
    highest_route_only: bool = False,
) -> tuple[GuidanceOption, ...]:
    if preview is None or not preview.gaps:
        return ()
    routes = {gap.next_path for gap in preview.gaps}
    if highest_route_only:
        highest_rank = min(_ROUTE_RANK[route] for route in routes)
        routes = {route for route in routes if _ROUTE_RANK[route] == highest_rank}
    options: list[GuidanceOption] = []
    for action in preview.actions:
        grouped = _group_gaps(action.gaps, routes)
        for route, gaps in grouped.items():
            kind, title = _ROUTE_PRESENTATION[route]
            options.append(
                _option(
                    kind,
                    f"{title}：{_short_name(action.action_display_name)}",
                    tuple(item.code for item in gaps),
                    tier,
                    route,
                    stable_subject=action.action_candidate_id,
                )
            )
    if options:
        return tuple(options)
    for route, gaps in _group_gaps(preview.gaps, routes).items():
        kind, title = _ROUTE_PRESENTATION[route]
        options.append(
            _option(
                kind,
                title,
                tuple(item.code for item in gaps),
                tier,
                route,
            )
        )
    return tuple(options)


def _group_gaps(
    gaps: tuple[CheckPreviewGap, ...],
    routes: set[str],
) -> dict[str, tuple[CheckPreviewGap, ...]]:
    grouped: dict[str, list[CheckPreviewGap]] = {}
    for gap in gaps:
        if gap.next_path in routes:
            grouped.setdefault(gap.next_path, []).append(gap)
    return {
        route: tuple(sorted(items, key=lambda item: item.code))
        for route, items in sorted(grouped.items(), key=lambda item: _ROUTE_RANK[item[0]])
    }


def _option(
    kind: GuidanceOptionKind,
    title: str,
    reason_codes: tuple[str, ...],
    tier: GuidancePriorityTier,
    route: GuidanceRoute,
    *,
    stable_subject: str = "project",
) -> GuidanceOption:
    stable = json.dumps(
        {
            "kind": kind.value,
            "reason_codes": tuple(sorted(set(reason_codes))),
            "route": route,
            "subject": stable_subject,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    option_id = f"opt_{hashlib.sha256(stable.encode('utf-8')).hexdigest()[:24]}"
    return GuidanceOption(
        option_id=option_id,
        kind=kind,
        title=title,
        reason_codes=tuple(sorted(set(reason_codes))),
        priority_tier=tier,
        route=route,
    )


def _unique_options(options: list[GuidanceOption]) -> list[GuidanceOption]:
    return list({item.option_id: item for item in options}.values())


def _option_order(option: GuidanceOption) -> tuple[int, int, str]:
    tier_rank = {
        GuidancePriorityTier.PRIMARY: 0,
        GuidancePriorityTier.BLOCKING: 1,
        GuidancePriorityTier.OPTIONAL: 2,
    }
    return tier_rank[option.priority_tier], _ROUTE_RANK.get(option.route, 9), option.option_id


def _short_name(value: str) -> str:
    # 用户可编辑名称始终是普通 JSON 数据；只做显示边界裁剪，不解释其中任何指令文本。
    normalized = " ".join(value.split())
    return normalized[:80] or "未命名业务操作"


__all__ = [
    "GuidanceOption",
    "GuidanceOptionKind",
    "GuidancePhase",
    "GuidancePriorityTier",
    "GuidanceQueryService",
    "GuidanceSnapshot",
    "build_guidance_snapshot",
]
