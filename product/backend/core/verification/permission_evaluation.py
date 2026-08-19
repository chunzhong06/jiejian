# =============================================================================
# 权限事实判定
#
# 定位
# Verification 的纯领域决策边界，将权限变异 case 与确定性事实归并为安全结论。
#
# 职责
# 校验 case 与事实关联｜聚合必需观察效果｜生成稳定的 CaseVerdict 与原因码
#
# 边界
# 不识别 HTTP、请求路径或具体 Observer，不控制 Run 生命周期或 Gate，也不产生副作用。
#
# 调用链
# Runner 权限 case → 本模块 → Evidence 与 Run verdict 聚合
# =============================================================================

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.facts import ExecutionFact, ExecutionOutcome, ObservationFact, ObservedEffect
from product.backend.core.verification.permission_coverage import PermissionMutationCase
from product.backend.core.verification.permissions import ActionDefinition, BatchAuthorizationMode, PermissionExpectation


# 权限事实判定使用的严格、不可变领域模型基线。
class PermissionEvaluationModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


# 一次 case 判定所需的冻结规则、执行事实与必需观察事实。
class CaseDecisionInput(PermissionEvaluationModel):
    case: PermissionMutationCase
    action: ActionDefinition
    execution: ExecutionFact
    observations: tuple[ObservationFact, ...] = Field(default=(), max_length=19_200)

    @model_validator(mode="after")
    def validate_case_input(self) -> CaseDecisionInput:
        if self.action.action_id != self.case.action_id:
            raise ValueError("action does not match the permission case")
        if self.execution.case_id != self.case.case_id or self.execution.action_id != self.case.action_id:
            raise ValueError("execution fact does not match the permission case")
        required = set(self.case.required_observations)
        keys: set[tuple[str, str]] = set()
        for fact in self.observations:
            key = (fact.requirement_id, fact.resource_id)
            if key in keys:
                raise ValueError("observation facts must have unique requirement/resource keys")
            keys.add(key)
            if fact.requirement_id not in required or fact.resource_id not in self.case.resource_ids:
                raise ValueError("observation fact is outside the permission case")
        return self


class PermissionEvaluationReasonCode(StrEnum):
    REQUIRED_OBSERVATION_INCOMPLETE = "REQUIRED_OBSERVATION_INCOMPLETE"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_UNKNOWN = "EXECUTION_UNKNOWN"
    ALLOW_BASELINE_REJECTED = "ALLOW_BASELINE_REJECTED"
    ALLOW_EFFECT_UNCONFIRMED = "ALLOW_EFFECT_UNCONFIRMED"
    UNAUTHORIZED_EXECUTION_ACCEPTED = "UNAUTHORIZED_EXECUTION_ACCEPTED"
    UNAUTHORIZED_SIDE_EFFECT = "UNAUTHORIZED_SIDE_EFFECT"
    MIXED_BATCH_ATOMIC_ACCEPTED = "MIXED_BATCH_ATOMIC_ACCEPTED"


def _reasons(*values: PermissionEvaluationReasonCode) -> tuple[str, ...]:
    return tuple(sorted({value.value for value in values}))


def _effects(input_data: CaseDecisionInput) -> tuple[dict[str, ObservedEffect], bool]:
    """按资源归并必需观察；任一缺失或不可靠事实都会使完整性失败。"""

    effects = {resource_id: ObservedEffect.ABSENT for resource_id in input_data.case.resource_ids}
    required = set(input_data.case.required_observations)
    facts_by_requirement: dict[str, list[ObservationFact]] = {}
    for fact in input_data.observations:
        facts_by_requirement.setdefault(fact.requirement_id, []).append(fact)
    complete = True
    for requirement in required:
        facts = facts_by_requirement.get(requirement, [])
        if not facts:
            return {resource_id: ObservedEffect.UNKNOWN for resource_id in effects}, False
        for resource_id in input_data.case.resource_ids:
            selected = [fact for fact in facts if fact.resource_id == resource_id]
            if not selected or any(not fact.complete or not fact.reliable or fact.effect is ObservedEffect.UNKNOWN for fact in selected):
                effects[resource_id] = ObservedEffect.UNKNOWN
                complete = False
            elif any(fact.effect is ObservedEffect.CONFIRMED for fact in selected):
                effects[resource_id] = ObservedEffect.CONFIRMED
    return effects, complete


def evaluate_permission_case(input_data: CaseDecisionInput) -> tuple[CaseVerdict, tuple[str, ...]]:
    """确定性判定单个权限 case，并返回稳定排序的原因码。"""

    effects, observations_complete = _effects(input_data)
    if not observations_complete:
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.REQUIRED_OBSERVATION_INCOMPLETE)

    case = input_data.case
    execution = input_data.execution.outcome
    expectations = case.expectations
    if case.batch_mode is None:
        effect = effects[case.resource_ids[0]]
        expected = expectations[0]
        if expected is PermissionExpectation.DENY:
            if effect is ObservedEffect.CONFIRMED:
                return CaseVerdict.VULNERABLE, _reasons(PermissionEvaluationReasonCode.UNAUTHORIZED_SIDE_EFFECT)
            if execution is ExecutionOutcome.ACCEPTED:
                return CaseVerdict.VULNERABLE, _reasons(PermissionEvaluationReasonCode.UNAUTHORIZED_EXECUTION_ACCEPTED)
            if execution is ExecutionOutcome.DENIED:
                return CaseVerdict.SAFE, ()
            return CaseVerdict.INCONCLUSIVE, _reasons(
                PermissionEvaluationReasonCode.EXECUTION_FAILED
                if execution is ExecutionOutcome.FAILED
                else PermissionEvaluationReasonCode.EXECUTION_UNKNOWN
            )
        if execution is not ExecutionOutcome.ACCEPTED:
            return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.ALLOW_BASELINE_REJECTED)
        if input_data.action.side_effect and effect is not ObservedEffect.CONFIRMED:
            return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.ALLOW_EFFECT_UNCONFIRMED)
        return CaseVerdict.SAFE, ()

    deny_effects = [effect for effect, expected in zip(effects.values(), expectations) if expected is PermissionExpectation.DENY]
    allow_effects = [effect for effect, expected in zip(effects.values(), expectations) if expected is PermissionExpectation.ALLOW]
    if case.batch_mode is BatchAuthorizationMode.ALL_DENY:
        if ObservedEffect.CONFIRMED in deny_effects:
            return CaseVerdict.VULNERABLE, _reasons(PermissionEvaluationReasonCode.UNAUTHORIZED_SIDE_EFFECT)
        if execution is ExecutionOutcome.ACCEPTED:
            return CaseVerdict.VULNERABLE, _reasons(PermissionEvaluationReasonCode.UNAUTHORIZED_EXECUTION_ACCEPTED)
        if execution is ExecutionOutcome.DENIED and all(effect is ObservedEffect.ABSENT for effect in deny_effects):
            return CaseVerdict.SAFE, ()
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.EXECUTION_FAILED)
    if case.batch_mode is BatchAuthorizationMode.ALL_ALLOW:
        if execution is not ExecutionOutcome.ACCEPTED:
            return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.ALLOW_BASELINE_REJECTED)
        if input_data.action.side_effect and any(effect is not ObservedEffect.CONFIRMED for effect in allow_effects):
            return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.ALLOW_EFFECT_UNCONFIRMED)
        return CaseVerdict.SAFE, ()
    if case.atomic:
        if execution is ExecutionOutcome.ACCEPTED:
            return CaseVerdict.VULNERABLE, _reasons(PermissionEvaluationReasonCode.MIXED_BATCH_ATOMIC_ACCEPTED)
        if execution is ExecutionOutcome.DENIED:
            if any(effect is ObservedEffect.CONFIRMED for effect in effects.values()):
                return CaseVerdict.VULNERABLE, _reasons(PermissionEvaluationReasonCode.UNAUTHORIZED_SIDE_EFFECT)
            return CaseVerdict.SAFE, ()
        return CaseVerdict.INCONCLUSIVE, _reasons(
            PermissionEvaluationReasonCode.EXECUTION_FAILED
            if execution is ExecutionOutcome.FAILED
            else PermissionEvaluationReasonCode.EXECUTION_UNKNOWN
        )
    if ObservedEffect.CONFIRMED in deny_effects:
        return CaseVerdict.VULNERABLE, _reasons(PermissionEvaluationReasonCode.UNAUTHORIZED_SIDE_EFFECT)
    if execution is not ExecutionOutcome.ACCEPTED:
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.ALLOW_BASELINE_REJECTED)
    if input_data.action.side_effect and any(effect is not ObservedEffect.CONFIRMED for effect in allow_effects):
        return CaseVerdict.INCONCLUSIVE, _reasons(PermissionEvaluationReasonCode.ALLOW_EFFECT_UNCONFIRMED)
    return CaseVerdict.SAFE, ()
