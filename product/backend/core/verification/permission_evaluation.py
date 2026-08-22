# =============================================================================
# 关系差分权限事实判定
#
# 定位
#   Verification 的纯领域决策边界，把孪生、执行、基线与安全效果归并为结论。
#
# 职责
#   校验事实关联｜执行不对称 BLOCK/PASS 规则｜生成稳定原因码
#
# 边界
#   不认识 HTTP、Cookie、ObserverType、数据库、队列或 Blob，也不执行副作用。
#
# 调用链
#   Runner PermissionTwin → CaseDecisionInput → Evidence / Run verdict
# =============================================================================

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.differential import TwinExecutionRole
from product.backend.core.verification.facts import ExecutionFact, ExecutionOutcome, ObservedEffect, SecurityEffectFact, TemporalClosure
from product.backend.core.verification.permission_coverage import PermissionMutationCase
from product.backend.core.verification.permissions import ActionDefinition, PermissionExpectation


class PermissionEvaluationModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class CaseDecisionInput(PermissionEvaluationModel):
    case: PermissionMutationCase
    action: ActionDefinition
    execution: ExecutionFact
    effects: tuple[SecurityEffectFact, ...] = Field(min_length=1, max_length=19_200)
    twin_role: TwinExecutionRole | None = None
    allow_control_valid: bool
    baseline_integrity: bool

    @model_validator(mode="after")
    def validate_case_input(self) -> CaseDecisionInput:
        if self.action.action_id != self.case.action_id:
            raise ValueError("action does not match the permission case")
        if self.execution.case_id != self.case.case_id or self.execution.action_id != self.case.action_id:
            raise ValueError("execution fact does not match the permission case")
        expected = {
            (effect_id, resource_id)
            for effect_id in self.action.effect_ids
            for resource_id in self.case.resource_ids
        }
        actual = {(item.effect_id, item.resource_id) for item in self.effects}
        if len(actual) != len(self.effects) or actual != expected:
            raise ValueError("security effect facts must exactly cover action effects and case resources")
        if self.twin_role is TwinExecutionRole.ALLOW_CONTROL and not all(
            item is PermissionExpectation.ALLOW for item in self.case.expectations
        ):
            raise ValueError("ALLOW control role requires an ALLOW case")
        if self.twin_role is TwinExecutionRole.DENY_VARIANT and not all(
            item is PermissionExpectation.DENY for item in self.case.expectations
        ):
            raise ValueError("DENY variant role requires a DENY case")
        return self


class PermissionEvaluationReasonCode(StrEnum):
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_UNKNOWN = "EXECUTION_UNKNOWN"
    ALLOW_CONTROL_INVALID = "ALLOW_CONTROL_INVALID"
    ALLOW_EXECUTION_REJECTED = "ALLOW_EXECUTION_REJECTED"
    ALLOW_EFFECT_UNCONFIRMED = "ALLOW_EFFECT_UNCONFIRMED"
    BASELINE_INTEGRITY_INVALID = "BASELINE_INTEGRITY_INVALID"
    TWIN_CONTEXT_MISSING = "TWIN_CONTEXT_MISSING"
    UNAUTHORIZED_EXECUTION_ACCEPTED = "UNAUTHORIZED_EXECUTION_ACCEPTED"
    UNAUTHORIZED_EFFECT_CONFIRMED = "UNAUTHORIZED_EFFECT_CONFIRMED"
    REQUIRED_EFFECT_UNKNOWN = "REQUIRED_EFFECT_UNKNOWN"
    TEMPORAL_CLOSURE_INCOMPLETE = "TEMPORAL_CLOSURE_INCOMPLETE"


def _reasons(*values: PermissionEvaluationReasonCode) -> tuple[str, ...]:
    return tuple(sorted({value.value for value in values}))


def evaluate_permission_case(input_data: CaseDecisionInput) -> tuple[CaseVerdict, tuple[str, ...]]:
    """先保留强 BLOCK 证据，再对 PASS 要求完整、闭合、可比的孪生证明。"""

    effects = input_data.effects
    execution = input_data.execution.outcome
    has_deny = any(item is PermissionExpectation.DENY for item in input_data.case.expectations)
    confirmed = any(item.state is ObservedEffect.CONFIRMED for item in effects)
    if has_deny and confirmed:
        return CaseVerdict.VULNERABLE, _reasons(PermissionEvaluationReasonCode.UNAUTHORIZED_EFFECT_CONFIRMED)
    if has_deny and execution is ExecutionOutcome.ACCEPTED:
        return CaseVerdict.VULNERABLE, _reasons(PermissionEvaluationReasonCode.UNAUTHORIZED_EXECUTION_ACCEPTED)
    if execution is ExecutionOutcome.FAILED:
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.EXECUTION_FAILED)
    if execution is ExecutionOutcome.UNKNOWN:
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.EXECUTION_UNKNOWN)
    if not input_data.baseline_integrity:
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.BASELINE_INTEGRITY_INVALID)

    is_allow_case = all(
        item is PermissionExpectation.ALLOW for item in input_data.case.expectations
    )
    if input_data.twin_role is TwinExecutionRole.ALLOW_CONTROL or (
        input_data.twin_role is None and is_allow_case
    ):
        if execution is not ExecutionOutcome.ACCEPTED:
            return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.ALLOW_EXECUTION_REJECTED)
        if any(item.state is not ObservedEffect.CONFIRMED for item in effects):
            return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.ALLOW_EFFECT_UNCONFIRMED)
        return CaseVerdict.SAFE, ()

    if input_data.twin_role is not TwinExecutionRole.DENY_VARIANT:
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.TWIN_CONTEXT_MISSING)
    if not input_data.allow_control_valid:
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.ALLOW_CONTROL_INVALID)
    if execution is not ExecutionOutcome.DENIED:
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.EXECUTION_UNKNOWN)
    if any(item.state is ObservedEffect.UNKNOWN for item in effects):
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.REQUIRED_EFFECT_UNKNOWN)
    if any(item.temporal_closure is not TemporalClosure.CLOSED for item in effects):
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.TEMPORAL_CLOSURE_INCOMPLETE)
    if not all(item.state is ObservedEffect.ABSENT for item in effects):
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.REQUIRED_EFFECT_UNKNOWN)
    return CaseVerdict.SAFE, ()
