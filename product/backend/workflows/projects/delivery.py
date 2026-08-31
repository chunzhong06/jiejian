# 显式核对 live 源码、当前权限、修复/重验与最新可信结果是否属于同一交付事实。

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.lifecycle import RunVerdict
from product.backend.workflows.projects.repair import ProjectRepairStatus
from product.backend.workflows.projects.revalidation import ProjectRevalidationStatus
from product.backend.workflows.source_changes import SourceWorkspaceInspectionStatus
from product.protocols.execution_request import PersistedExecutionRequest


DeliveryNextPath = Literal["/changes", "/permissions", "/preparation", "/validation", "/results"]


class DeliveryDecision(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class DeliveryCheckView(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    project_id: str = Field(min_length=1, max_length=64)
    decision: DeliveryDecision
    summary: str = Field(min_length=1, max_length=320)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)
    next_path: DeliveryNextPath | None = None
    next_label: str | None = Field(default=None, min_length=1, max_length=80)
    verified_run_id: str | None = Field(default=None, min_length=1, max_length=128)


class DeliveryCheckService:
    """只读形成一次 fail-closed 交付证明，不创建 Run、Gate 或持久状态。"""

    def __init__(
        self,
        *,
        source_changes,
        permission_intents,
        product_status,
        result_presentation,
        published_reader,
    ) -> None:
        self._source_changes = source_changes
        self._permission_intents = permission_intents
        self._product_status = product_status
        self._result_presentation = result_presentation
        self._published_reader = published_reader

    def check(self, project_id: str) -> DeliveryCheckView:
        workspace = self._source_changes.inspect_workspace(project_id)
        if workspace.status is SourceWorkspaceInspectionStatus.UNAVAILABLE:
            return self._view(
                project_id,
                DeliveryDecision.ERROR,
                "当前无法读取源码工作区，不能形成交付证明。",
                workspace.reason_codes or ("SOURCE_WORKSPACE_UNAVAILABLE",),
            )
        if workspace.status is SourceWorkspaceInspectionStatus.DRIFTED:
            return self._view(
                project_id,
                DeliveryDecision.BLOCKED,
                "磁盘源码已不同于登记基线，请先提交并审阅这次变化。",
                workspace.reason_codes or ("SOURCE_WORKSPACE_DRIFTED",),
                next_path="/changes",
                next_label="审阅代码变化",
            )

        status = self._product_status.get(project_id)
        repair = status.repair
        if repair is not None and repair.status not in {
            ProjectRepairStatus.NONE,
            ProjectRepairStatus.VERIFIED,
        }:
            return self._view(
                project_id,
                DeliveryDecision.BLOCKED,
                "当前权限问题的修复闭环尚未完成。",
                (f"PROJECT_REPAIR_{repair.status.value}", *repair.reason_codes),
                next_path=repair.next_path or "/results",
                next_label=repair.next_label or "继续处理修复",
                verified_run_id=(None if status.latest_result is None else status.latest_result.run_id),
            )
        revalidation = status.revalidation
        if revalidation is not None and revalidation.status not in {
            ProjectRevalidationStatus.NO_CHANGE,
            ProjectRevalidationStatus.VERIFIED,
        }:
            return self._view(
                project_id,
                DeliveryDecision.BLOCKED,
                "当前代码变化尚未完成可信重验。",
                (f"PROJECT_REVALIDATION_{revalidation.status.value}", *revalidation.reason_codes),
                next_path=revalidation.next_path or "/validation",
                next_label=revalidation.next_label or "完成代码变化重验",
                verified_run_id=(None if status.latest_result is None else status.latest_result.run_id),
            )
        latest = status.latest_result
        if latest is None:
            return self._view(
                project_id,
                DeliveryDecision.BLOCKED,
                "当前还没有可用于交付的可信检查结果。",
                ("TRUSTED_RESULT_MISSING",),
                next_path="/validation",
                next_label="开始验证运行",
            )

        published = self._published_reader.read(latest.run_id)
        request = self._published_reader.execution_request(published)
        presentation = self._result_presentation.build(latest.run_id)
        if not isinstance(request, PersistedExecutionRequest):
            return self._view(
                project_id,
                DeliveryDecision.BLOCKED,
                "最近结果缺少当前交付所需的项目级源码身份，请重新检查。",
                ("LEGACY_EXECUTION_REQUEST",),
                next_path="/validation",
                next_label="重新检查当前版本",
                verified_run_id=latest.run_id,
            )
        current_identity = _intent_identity(self._permission_intents.current_intents(project_id))
        run_identity = _intent_identity(presentation.relevant_intents)
        if current_identity != run_identity:
            return self._view(
                project_id,
                DeliveryDecision.BLOCKED,
                "当前权限要求已经不同于最近检查时的考题。",
                ("PERMISSION_IDENTITY_CHANGED",),
                next_path="/permissions",
                next_label="查看当前权限规则",
                verified_run_id=latest.run_id,
            )
        if request.source_fingerprint != workspace.live_source_fingerprint:
            return self._view(
                project_id,
                DeliveryDecision.BLOCKED,
                "最近结果验证的不是当前磁盘源码，请重新检查。",
                ("RUN_SOURCE_IDENTITY_CHANGED",),
                next_path="/validation",
                next_label="重新检查当前源码",
                verified_run_id=latest.run_id,
            )
        if presentation.uncovered_count > 0:
            return self._view(
                project_id,
                DeliveryDecision.BLOCKED,
                "最近检查仍有未覆盖的权限范围，不能作为交付证明。",
                ("RESULT_SCOPE_UNCOVERED",),
                next_path="/preparation",
                next_label="补齐测试准备",
                verified_run_id=latest.run_id,
            )
        if presentation.verdict is RunVerdict.INCONCLUSIVE:
            recovery = status.inconclusive_recovery
            return self._view(
                project_id,
                DeliveryDecision.BLOCKED,
                "最近检查证据不足，尚不能证明当前版本可交付。",
                ("RESULT_INCONCLUSIVE",),
                next_path=(recovery.next_path if recovery is not None else "/validation"),
                next_label=(recovery.next_label if recovery is not None else "重新检查当前版本"),
                verified_run_id=latest.run_id,
            )
        if presentation.verdict is RunVerdict.BLOCK:
            return self._view(
                project_id,
                DeliveryDecision.BLOCKED,
                "最近检查确认仍有权限问题，不能交付。",
                ("RESULT_BLOCK",),
                next_path=(repair.next_path if repair is not None else "/results"),
                next_label=(repair.next_label if repair is not None else "查看权限问题"),
                verified_run_id=latest.run_id,
            )
        if presentation.verdict is not RunVerdict.PASS:
            return self._view(
                project_id,
                DeliveryDecision.ERROR,
                "最近可信结果缺少可解释的安全结论。",
                ("RESULT_VERDICT_UNAVAILABLE",),
                verified_run_id=latest.run_id,
            )
        return self._view(
            project_id,
            DeliveryDecision.READY,
            "当前源码、权限要求、修复状态与最近完整 PASS 结果一致，可以交付。",
            ("DELIVERY_PROOF_CURRENT",),
            verified_run_id=latest.run_id,
        )

    @staticmethod
    def _view(
        project_id: str,
        decision: DeliveryDecision,
        summary: str,
        reason_codes: tuple[str, ...],
        *,
        next_path: DeliveryNextPath | None = None,
        next_label: str | None = None,
        verified_run_id: str | None = None,
    ) -> DeliveryCheckView:
        return DeliveryCheckView(
            project_id=project_id,
            decision=decision,
            summary=summary,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            next_path=next_path,
            next_label=next_label,
            verified_run_id=verified_run_id,
        )


def _intent_identity(items) -> tuple[tuple[str, int, str], ...]:
    return tuple(
        sorted(
            (str(item.intent_id), int(item.revision), str(item.intent_hash))
            for item in items
        )
    )


__all__ = ["DeliveryCheckService", "DeliveryCheckView", "DeliveryDecision"]
