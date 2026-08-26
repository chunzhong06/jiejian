# =============================================================================
# 失败序列中的 SETUP 最小化
#
# 定位
#   在复现谓词保持成立时，删除与安全问题无关的准备步骤。
#
# 职责
#   冻结 Target/Mutation/Baseline/Effect｜仅尝试删除 SETUP｜重建依赖与指纹
#
# 边界
#   不删除或改写 TARGET/CLEANUP，不修改请求、身份、效果或权限 mutation。
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.verification.permissions.coverage import PermissionMutationCase
from product.backend.core.verification.permissions import permission_model_sha256
from product.protocols.web.workflow import (
    HttpWorkflowBinding,
    HttpWorkflowStep,
    WorkflowStepPurpose,
)


class SetupMinimizationModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class SetupMinimizationInvariant(SetupMinimizationModel):
    target_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    permission_mutation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    security_effect_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class SetupMinimizationResult(SetupMinimizationModel):
    original_workflow_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    minimized_workflow: HttpWorkflowBinding
    invariant: SetupMinimizationInvariant
    removed_setup_step_ids: tuple[str, ...] = Field(default=(), max_length=255)
    reproduction_attempts: int = Field(ge=1, le=256)

    @model_validator(mode="after")
    def validate_result(self) -> SetupMinimizationResult:
        remaining_ids = {step.id for step in self.minimized_workflow.steps}
        if any(step_id in remaining_ids for step_id in self.removed_setup_step_ids):
            raise ValueError("removed SETUP steps cannot remain in the minimized workflow")
        if self.minimized_workflow.target_step_id in self.removed_setup_step_ids:
            raise ValueError("setup minimization cannot remove the TARGET")
        if _target_fingerprint(self.minimized_workflow) != self.invariant.target_fingerprint:
            raise ValueError("setup minimization changed the TARGET")
        if permission_model_sha256(self.minimized_workflow.baseline_projections) != self.invariant.baseline_fingerprint:
            raise ValueError("setup minimization changed the baseline")
        return self


def minimize_failure_setup(
    workflow: HttpWorkflowBinding,
    case: PermissionMutationCase,
    *,
    security_effect_fingerprint: str,
    reproduces: Callable[[HttpWorkflowBinding], bool],
) -> SetupMinimizationResult:
    """贪心删除无动态值依赖的 SETUP；每个候选都由调用方重新验证复现。"""

    invariant = SetupMinimizationInvariant(
        target_fingerprint=_target_fingerprint(workflow),
        permission_mutation_fingerprint=case.fingerprint,
        baseline_fingerprint=permission_model_sha256(workflow.baseline_projections),
        security_effect_fingerprint=security_effect_fingerprint,
    )
    attempts = 1
    if not reproduces(workflow):
        raise ValueError("original workflow does not reproduce the target failure")
    current = workflow
    removed: list[str] = []
    for step in reversed(workflow.steps):
        if step.purpose is not WorkflowStepPurpose.SETUP:
            continue
        if any(
            slot.producer_step_id == step.id
            for candidate in current.steps
            for slot in candidate.input_slots
        ):
            continue
        candidate = _without_setup(current, step.id)
        attempts += 1
        if reproduces(candidate):
            current = candidate
            removed.append(step.id)
    return SetupMinimizationResult(
        original_workflow_fingerprint=workflow.workflow_fingerprint or "",
        minimized_workflow=current,
        invariant=invariant,
        removed_setup_step_ids=tuple(sorted(removed)),
        reproduction_attempts=attempts,
    )


def _without_setup(workflow: HttpWorkflowBinding, setup_step_id: str) -> HttpWorkflowBinding:
    steps = tuple(
        HttpWorkflowStep.model_validate(
            {
                **step.model_dump(mode="python"),
                "depends_on_step_ids": tuple(
                    dependency
                    for dependency in step.depends_on_step_ids
                    if dependency != setup_step_id
                ),
            }
        )
        for step in workflow.steps
        if step.id != setup_step_id
    )
    return HttpWorkflowBinding.model_validate(
        {
            **workflow.model_dump(mode="python"),
            "steps": steps,
            "workflow_fingerprint": None,
        }
    )


def _target_fingerprint(workflow: HttpWorkflowBinding) -> str:
    target = next(step for step in workflow.steps if step.id == workflow.target_step_id)
    payload = target.model_dump(mode="json", exclude={"depends_on_step_ids"})
    return permission_model_sha256(payload)
