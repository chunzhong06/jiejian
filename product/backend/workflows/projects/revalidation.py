# 从 SourceChange inspection 与当前准备/结果事实唯一推导项目变化重验状态。

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.workflows.projects.preparation import ProjectPreparationView
from product.backend.workflows.source_changes import (
    SourceChangeService,
    SourceRevalidationInspectionStatus,
)


class ProjectRevalidationStatus(StrEnum):
    NO_CHANGE = "NO_CHANGE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PREPARATION_REQUIRED = "PREPARATION_REQUIRED"
    READY = "READY"
    VERIFIED = "VERIFIED"
    STALE = "STALE"


class ProjectRevalidationView(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    project_id: str = Field(min_length=1, max_length=64)
    status: ProjectRevalidationStatus
    change_id: str | None = Field(default=None, pattern=r"^chg_[0-9a-f]{32}$")
    summary: str = Field(min_length=1, max_length=240)
    next_path: Literal["/changes", "/permissions", "/preparation", "/validation", "/results"] | None = None
    next_label: str | None = Field(default=None, min_length=1, max_length=80)
    required_intent_count: int = Field(ge=0)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)
    verified_run_id: str | None = Field(default=None, max_length=128)
    verified_change_id: str | None = Field(
        default=None,
        pattern=r"^chg_[0-9a-f]{32}$",
    )


class ProjectRevalidationService:
    """不保存状态，只按冻结顺序组合 inspection、准备度和可信结果。"""

    def __init__(self, source_changes: SourceChangeService) -> None:
        self._source_changes = source_changes

    def evaluate(
        self,
        project_id: str,
        *,
        preparation: ProjectPreparationView | None,
        verified_run_id: str | None,
        verified_change_id: str | None,
    ) -> ProjectRevalidationView:
        latest = self._source_changes.latest(project_id)
        if latest is None:
            return ProjectRevalidationView(
                project_id=project_id,
                status=ProjectRevalidationStatus.NO_CHANGE,
                summary="当前还没有需要重新验证的代码变化。",
                required_intent_count=0,
                reason_codes=("NO_SOURCE_CHANGE",),
                verified_run_id=verified_run_id,
                verified_change_id=verified_change_id,
            )
        return self.evaluate_change(
            project_id,
            latest[0].change_id,
            preparation=preparation,
            verified_run_id=verified_run_id,
            verified_change_id=verified_change_id,
        )

    def evaluate_change(
        self,
        project_id: str,
        change_id: str,
        *,
        preparation: ProjectPreparationView | None,
        verified_run_id: str | None,
        verified_change_id: str | None,
    ) -> ProjectRevalidationView:
        """对指定变化复用唯一状态算法，供项目修复与普通重验共同消费。"""

        inspection = self._source_changes.inspect_revalidation(
            project_id,
            change_id,
        )
        common = {
            "project_id": project_id,
            "change_id": change_id,
            "required_intent_count": len(inspection.required_intent_ids),
            "reason_codes": inspection.reason_codes,
            "verified_run_id": verified_run_id,
            "verified_change_id": verified_change_id,
        }
        if (
            inspection.status
            is SourceRevalidationInspectionStatus.MAPPING_REVIEW_REQUIRED
        ):
            return ProjectRevalidationView(
                **common,
                status=ProjectRevalidationStatus.REVIEW_REQUIRED,
                summary="最近代码变化涉及的实现映射需要先由你确认。",
                next_path="/permissions",
                next_label="确认权限实现",
            )
        if inspection.status in {
            SourceRevalidationInspectionStatus.NO_BASELINE,
            SourceRevalidationInspectionStatus.SOURCE_STALE,
            SourceRevalidationInspectionStatus.POLICY_STALE,
        }:
            return ProjectRevalidationView(
                **common,
                status=ProjectRevalidationStatus.STALE,
                summary="最近代码变化已不再对应当前源码或权限版本，需要重新建立变化事实。",
                next_path="/changes",
                next_label="重新说明代码变化",
            )
        if verified_change_id == change_id and verified_run_id is not None:
            return ProjectRevalidationView(
                **common,
                status=ProjectRevalidationStatus.VERIFIED,
                summary="最近代码变化已经按当前源码和权限范围完成可信验证。",
                next_path="/results",
                next_label="查看验证结果",
            )
        if preparation is None or not preparation.ready:
            return ProjectRevalidationView(
                **common,
                status=ProjectRevalidationStatus.PREPARATION_REQUIRED,
                summary="最近代码变化可以重验，但当前测试条件仍需补齐。",
                next_path="/preparation",
                next_label="补齐测试准备",
            )
        return ProjectRevalidationView(
            **common,
            status=ProjectRevalidationStatus.READY,
            summary="最近代码变化与当前源码和权限范围一致，可以开始重新验证。",
            next_path="/validation",
            next_label="开始重新验证",
        )


__all__ = [
    "ProjectRevalidationService",
    "ProjectRevalidationStatus",
    "ProjectRevalidationView",
]
