# 从已发布结果、修复合同与源码变化实时投影项目修复闭环，不保存第二份修复状态。

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import RunLifecycle, RunVerdict
from product.backend.core.repair import (
    RepairContractReference,
    RepairRequirementView,
    RepairVerification,
    RepairVerificationStatus,
)
from product.backend.workflows.projects.preparation import ProjectPreparationView
from product.backend.workflows.projects.revalidation import (
    ProjectRevalidationService,
    ProjectRevalidationStatus,
)
from product.backend.workflows.results.presentation import PresentedCaseVerdict


RepairNextPath = Literal["/changes", "/permissions", "/preparation", "/validation", "/results"]


class ProjectRepairStatus(StrEnum):
    NONE = "NONE"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    CHANGE_SUBMITTED = "CHANGE_SUBMITTED"
    READY_TO_VERIFY = "READY_TO_VERIFY"
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"
    STALE = "STALE"


class _RepairModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class RepairTaskView(_RepairModel):
    reference: RepairContractReference
    source_run_id: str = Field(min_length=1, max_length=128)
    source_finding_id: str = Field(min_length=1, max_length=128)
    status: ProjectRepairStatus
    must_disappear: str = Field(min_length=1, max_length=320)
    must_remain: str = Field(min_length=1, max_length=320)
    must_not_change: tuple[str, ...] = Field(min_length=2, max_length=8)
    linked_change_id: str | None = Field(default=None, pattern=r"^chg_[0-9a-f]{32}$")
    verification_run_id: str | None = Field(default=None, min_length=1, max_length=128)
    verification_status: RepairVerificationStatus | None = None
    next_path: RepairNextPath
    next_label: str = Field(min_length=1, max_length=80)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)


class ProjectRepairView(_RepairModel):
    project_id: str = Field(min_length=1, max_length=64)
    status: ProjectRepairStatus
    tasks: tuple[RepairTaskView, ...] = Field(default=(), max_length=4096)
    next_path: RepairNextPath | None = None
    next_label: str | None = Field(default=None, min_length=1, max_length=80)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)


class ProjectRepairService:
    """只组合权威修复事实；不批准、完成或自动应用任何修复。"""

    def __init__(
        self,
        uow_factory,
        repair_contracts,
        source_changes,
        project_revalidation: ProjectRevalidationService,
        result_presentation,
    ) -> None:
        self._uow_factory = uow_factory
        self._repair_contracts = repair_contracts
        self._source_changes = source_changes
        self._project_revalidation = project_revalidation
        self._result_presentation = result_presentation

    def evaluate(
        self,
        project_id: str,
        *,
        preparation: ProjectPreparationView | None,
        verified_run_id: str | None,
        verified_change_id: str | None,
    ) -> ProjectRepairView:
        requirements, verifications = self._published_history(project_id)
        if not requirements:
            return ProjectRepairView(project_id=project_id, status=ProjectRepairStatus.NONE)
        tasks = tuple(
            self._task(
                project_id,
                requirement,
                verification=verifications.get(_reference_key(requirement.reference)),
                preparation=preparation,
                verified_run_id=verified_run_id,
                verified_change_id=verified_change_id,
            )
            for requirement in sorted(
                requirements.values(),
                key=lambda item: (
                    item.reference.source_finding_id,
                    item.reference.source_run_id,
                    item.reference.repair_fingerprint,
                ),
            )
        )
        current = next(
            (task for task in tasks if task.status is not ProjectRepairStatus.VERIFIED),
            tasks[0],
        )
        status = (
            ProjectRepairStatus.VERIFIED
            if all(task.status is ProjectRepairStatus.VERIFIED for task in tasks)
            else current.status
        )
        return ProjectRepairView(
            project_id=project_id,
            status=status,
            tasks=tasks,
            next_path=current.next_path,
            next_label=current.next_label,
            reason_codes=current.reason_codes,
        )

    def _published_history(
        self,
        project_id: str,
    ) -> tuple[
        dict[tuple[str, str, str], RepairRequirementView],
        dict[tuple[str, str, str], tuple[RepairVerification, int]],
    ]:
        """按正式完成时间聚合全部可信发布结果，普通后续 Run 不覆盖修复任务。"""

        with self._uow_factory() as work:
            runs = tuple(work.runs.list_for_project(project_id))
        requirements: dict[tuple[str, str, str], RepairRequirementView] = {}
        verifications: dict[
            tuple[str, str, str], tuple[RepairVerification, int]
        ] = {}
        ordered_runs = sorted(
            (
                run
                for run in runs
                if run.lifecycle in {RunLifecycle.COMPLETED, RunLifecycle.SAFETY_STOPPED}
                and run.finished_at_us is not None
            ),
            key=lambda run: (run.finished_at_us, run.created_at_us, run.run_id),
        )
        for run in ordered_runs:
            try:
                presentation = self._result_presentation.build(run.run_id)
            except JiejianError:
                continue
            if presentation.verdict is RunVerdict.BLOCK:
                for issue in presentation.issues:
                    if (
                        issue.verdict is PresentedCaseVerdict.VULNERABLE
                        and issue.repair_requirement is not None
                    ):
                        requirement = issue.repair_requirement
                        requirements[_reference_key(requirement.reference)] = requirement
            verification = presentation.repair_verification
            if verification is None:
                continue
            key = _reference_key(verification.reference)
            existing = verifications.get(key)
            # VERIFIED 是同一修复任务的终态，之后的普通 Run 或重复复验都不能重新打开。
            if existing is None or existing[0].status is not RepairVerificationStatus.VERIFIED:
                verifications[key] = (verification, run.finished_at_us)

        for key, (verification, _) in verifications.items():
            if key in requirements:
                continue
            reference = verification.reference
            requirements[key] = self._repair_contracts.requirement(
                reference.source_run_id,
                reference.source_finding_id,
            )
        return requirements, verifications

    def _task(
        self,
        project_id: str,
        requirement: RepairRequirementView,
        *,
        verification: tuple[RepairVerification, int] | None,
        preparation: ProjectPreparationView | None,
        verified_run_id: str | None,
        verified_change_id: str | None,
    ) -> RepairTaskView:
        reference = requirement.reference
        common = {
            "reference": reference,
            "source_run_id": reference.source_run_id,
            "source_finding_id": reference.source_finding_id,
            "must_disappear": requirement.must_disappear,
            "must_remain": requirement.must_remain,
            "must_not_change": requirement.must_not_change,
        }
        if (
            verification is not None
            and verification[0].status is RepairVerificationStatus.VERIFIED
        ):
            return self._verified_task(common, verification[0])
        try:
            linked = self._source_changes.latest_for_repair(project_id, reference)
        except JiejianError as exc:
            return RepairTaskView(
                **common,
                status=ProjectRepairStatus.STALE,
                next_path="/results",
                next_label="重新读取修复要求",
                reason_codes=(exc.code,),
            )
        if verification is not None and (
            linked is None or linked[0].created_at_us <= verification[1]
        ):
            return self._verified_task(common, verification[0])
        if linked is None:
            return RepairTaskView(
                **common,
                status=ProjectRepairStatus.REPAIR_REQUIRED,
                next_path="/results",
                next_label="等待 Coding Agent 提交修复",
                reason_codes=("REPAIR_CHANGE_REQUIRED",),
            )
        change_id = linked[0].change_id
        revalidation = self._project_revalidation.evaluate_change(
            project_id,
            change_id,
            preparation=preparation,
            verified_run_id=verified_run_id,
            verified_change_id=verified_change_id,
        )
        if revalidation.status in {
            ProjectRevalidationStatus.REVIEW_REQUIRED,
            ProjectRevalidationStatus.PREPARATION_REQUIRED,
        }:
            return RepairTaskView(
                **common,
                status=ProjectRepairStatus.CHANGE_SUBMITTED,
                linked_change_id=change_id,
                next_path=revalidation.next_path or "/preparation",
                next_label=revalidation.next_label or "继续修复准备",
                reason_codes=revalidation.reason_codes,
            )
        if revalidation.status is ProjectRevalidationStatus.STALE:
            return RepairTaskView(
                **common,
                status=ProjectRepairStatus.STALE,
                linked_change_id=change_id,
                next_path=revalidation.next_path or "/changes",
                next_label=revalidation.next_label or "重新说明代码变化",
                reason_codes=revalidation.reason_codes,
            )
        return RepairTaskView(
            **common,
            status=ProjectRepairStatus.READY_TO_VERIFY,
            linked_change_id=change_id,
            next_path="/validation",
            next_label="复验这次修复",
            reason_codes=("REPAIR_VERIFICATION_REQUIRED",),
        )

    @staticmethod
    def _verified_task(common: dict[str, object], verification) -> RepairTaskView:
        presentation = {
            RepairVerificationStatus.VERIFIED: (
                ProjectRepairStatus.VERIFIED,
                "/results",
                "查看修复结果",
            ),
            RepairVerificationStatus.NOT_VERIFIED: (
                ProjectRepairStatus.NOT_VERIFIED,
                "/results",
                "继续修复",
            ),
            RepairVerificationStatus.INCONCLUSIVE: (
                ProjectRepairStatus.INCONCLUSIVE,
                "/preparation",
                "恢复复验条件",
            ),
        }
        status, next_path, next_label = presentation[verification.status]
        return RepairTaskView(
            **common,
            status=status,
            verification_run_id=verification.verification_run_id,
            verification_status=verification.status,
            next_path=next_path,
            next_label=next_label,
            reason_codes=verification.reason_codes,
        )


def _reference_key(reference: RepairContractReference) -> tuple[str, str, str]:
    return (
        reference.source_run_id,
        reference.source_finding_id,
        reference.repair_fingerprint,
    )


__all__ = [
    "ProjectRepairService",
    "ProjectRepairStatus",
    "ProjectRepairView",
    "RepairTaskView",
]
