# =============================================================================
# 关系差分孪生计划
#
# 定位
#   在 Contract-only Coverage 之后，把允许控制与禁止变体冻结为可解释实验对。
#
# 职责
#   唯一配对 ALLOW/DENY case｜记录唯一变化｜冻结工作流、效果、观察与基线不变量
#
# 边界
#   不理解 HTTP、Cookie 或具体 Observer；调用方只传入已计算的稳定指纹。
#
# 调用链
#   ExecutionWorkflow → Coverage → DifferentialExperimentPlan → Runner / Verification
# =============================================================================

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from typing import Literal

from pydantic import Field, model_validator

from product.backend.core.verification.permissions.coverage import PermissionMutationCase, PermissionMutationPlan
from product.backend.core.verification.permissions import CoverageDimension, PermissionContract, PermissionExpectation, PermissionModel, permission_model_sha256


class TwinPlanGapCode(StrEnum):
    MISSING_ALLOW_CONTROL = "MISSING_ALLOW_CONTROL"
    AMBIGUOUS_ALLOW_CONTROL = "AMBIGUOUS_ALLOW_CONTROL"
    MULTIPLE_VARIATIONS = "MULTIPLE_VARIATIONS"
    MISSING_INVARIANT = "MISSING_INVARIANT"


class TwinExecutionRole(StrEnum):
    ALLOW_CONTROL = "ALLOW_CONTROL"
    DENY_VARIANT = "DENY_VARIANT"


class PermissionMutationDescriptor(PermissionModel):
    dimension: CoverageDimension
    changed_fields: tuple[str, ...] = Field(min_length=1, max_length=16)
    allow_value_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    deny_value_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class TwinInvariantSpecification(PermissionModel):
    action_id: str
    resource_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    workflow_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    effect_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    observer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalization_version: str = Field(min_length=1, max_length=64)


class PermissionTwin(PermissionModel):
    twin_id: str = Field(pattern=r"^twin-[0-9a-f]{32}$")
    source_rule_id: str
    allow_case: PermissionMutationCase
    deny_case: PermissionMutationCase
    varied_dimension: CoverageDimension
    mutation: PermissionMutationDescriptor
    invariant: TwinInvariantSpecification
    twin_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_twin(self) -> PermissionTwin:
        if not all(value is PermissionExpectation.ALLOW for value in self.allow_case.expectations):
            raise ValueError("twin allow case must contain only ALLOW expectations")
        if not all(value is PermissionExpectation.DENY for value in self.deny_case.expectations):
            raise ValueError("twin deny case must contain only DENY expectations")
        if self.varied_dimension is not self.mutation.dimension:
            raise ValueError("twin mutation dimension must match varied_dimension")
        if self.allow_case.action_id != self.deny_case.action_id or self.allow_case.action_id != self.invariant.action_id:
            raise ValueError("twin action invariant is inconsistent")
        if self.allow_case.resource_ids != self.deny_case.resource_ids or self.allow_case.resource_ids != self.invariant.resource_ids:
            raise ValueError("twin resource invariant is inconsistent")
        payload = self.model_dump(mode="json", exclude={"twin_id", "twin_fingerprint"})
        expected = permission_model_sha256(payload)
        if self.twin_id != f"twin-{expected[:32]}" or self.twin_fingerprint != expected:
            raise ValueError("twin fingerprint does not match its semantic payload")
        return self


class TwinPlanGap(PermissionModel):
    deny_case_id: str = Field(pattern=r"^case-[0-9a-f]{32}$")
    code: TwinPlanGapCode
    detail: str = Field(min_length=1, max_length=160)


class DifferentialExperimentPlan(PermissionModel):
    schema_version: Literal["1"] = "1"
    differential_plan_id: str = Field(pattern=r"^dplan-[0-9a-f]{32}$")
    differential_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    coverage_plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    twins: tuple[PermissionTwin, ...] = Field(default=(), max_length=8192)
    gaps: tuple[TwinPlanGap, ...] = Field(default=(), max_length=8192)

    @model_validator(mode="after")
    def validate_plan(self) -> DifferentialExperimentPlan:
        if len({item.twin_id for item in self.twins}) != len(self.twins):
            raise ValueError("differential twin IDs must be unique")
        if len({item.deny_case.case_id for item in self.twins}) != len(self.twins):
            raise ValueError("each DENY case can belong to only one twin")
        if len({item.deny_case_id for item in self.gaps}) != len(self.gaps):
            raise ValueError("differential gaps must be unique per DENY case")
        payload = self.model_dump(
            mode="json",
            exclude={"schema_version", "differential_plan_id", "differential_fingerprint"},
        )
        expected = permission_model_sha256(payload)
        if self.differential_plan_id != f"dplan-{expected[:32]}" or self.differential_fingerprint != expected:
            raise ValueError("differential plan fingerprint does not match its semantic payload")
        return self


def build_differential_experiment_plan(
    contract: PermissionContract,
    coverage: PermissionMutationPlan,
    *,
    workflow_fingerprints: Mapping[str, str],
    effect_fingerprints: Mapping[str, str],
    observer_fingerprint: str,
    baseline_fingerprints: Mapping[str, str],
    normalization_version: str,
) -> DifferentialExperimentPlan:
    """按同动作、同资源和冻结不变量建立唯一 ALLOW/DENY 实验对。"""

    del contract
    allow_cases = tuple(
        item for item in coverage.cases
        if item.batch_mode is None and all(value is PermissionExpectation.ALLOW for value in item.expectations)
    )
    deny_cases = tuple(
        item for item in coverage.cases
        if item.batch_mode is None and all(value is PermissionExpectation.DENY for value in item.expectations)
    )
    twins: list[PermissionTwin] = []
    gaps: list[TwinPlanGap] = []
    for deny in sorted(deny_cases, key=lambda item: item.case_id):
        candidates = tuple(
            item for item in allow_cases
            if item.action_id == deny.action_id
            and item.resource_ids == deny.resource_ids
            and item.required_observations == deny.required_observations
        )
        if not candidates:
            gaps.append(TwinPlanGap(deny_case_id=deny.case_id, code=TwinPlanGapCode.MISSING_ALLOW_CONTROL, detail="没有同动作、同资源和同观察要求的 ALLOW 控制"))
            continue
        ranked = sorted(candidates, key=lambda item: (len(_variation_fields(item, deny)), item.fingerprint))
        allow = ranked[0]
        if len(ranked) > 1 and len(_variation_fields(ranked[0], deny)) == len(_variation_fields(ranked[1], deny)):
            gaps.append(TwinPlanGap(deny_case_id=deny.case_id, code=TwinPlanGapCode.AMBIGUOUS_ALLOW_CONTROL, detail="存在多个同等接近的 ALLOW 控制"))
            continue
        dimension, changed_fields = _variation(allow, deny)
        if dimension is None:
            gaps.append(TwinPlanGap(deny_case_id=deny.case_id, code=TwinPlanGapCode.MULTIPLE_VARIATIONS, detail="ALLOW 与 DENY 之间不是一个可解释的权限变化"))
            continue
        invariant_values = (
            workflow_fingerprints.get(deny.action_id),
            effect_fingerprints.get(deny.action_id),
            baseline_fingerprints.get(deny.action_id),
        )
        if any(value is None for value in invariant_values):
            gaps.append(TwinPlanGap(deny_case_id=deny.case_id, code=TwinPlanGapCode.MISSING_INVARIANT, detail="工作流、效果或基线不变量尚未冻结"))
            continue
        mutation = PermissionMutationDescriptor(
            dimension=dimension,
            changed_fields=changed_fields,
            allow_value_fingerprint=permission_model_sha256(_variation_payload(allow, changed_fields)),
            deny_value_fingerprint=permission_model_sha256(_variation_payload(deny, changed_fields)),
        )
        invariant = TwinInvariantSpecification(
            action_id=deny.action_id,
            resource_ids=deny.resource_ids,
            workflow_fingerprint=invariant_values[0],
            effect_fingerprint=invariant_values[1],
            observer_fingerprint=observer_fingerprint,
            baseline_fingerprint=invariant_values[2],
            normalization_version=normalization_version,
        )
        payload = {
            "source_rule_id": deny.source_rule_ids[0],
            "allow_case": allow,
            "deny_case": deny,
            "varied_dimension": dimension,
            "mutation": mutation,
            "invariant": invariant,
        }
        fingerprint = permission_model_sha256(payload)
        twins.append(PermissionTwin(**payload, twin_id=f"twin-{fingerprint[:32]}", twin_fingerprint=fingerprint))
    body = {
        "coverage_plan_fingerprint": coverage.plan_fingerprint,
        "twins": tuple(sorted(twins, key=lambda item: item.twin_id)),
        "gaps": tuple(sorted(gaps, key=lambda item: item.deny_case_id)),
    }
    fingerprint = permission_model_sha256(body)
    return DifferentialExperimentPlan(
        **body,
        differential_plan_id=f"dplan-{fingerprint[:32]}",
        differential_fingerprint=fingerprint,
    )


def _variation_fields(allow: PermissionMutationCase, deny: PermissionMutationCase) -> tuple[str, ...]:
    changed: list[str] = []
    if allow.subject_id != deny.subject_id:
        changed.append("subject_id")
    if allow.relation_paths != deny.relation_paths:
        changed.append("relation_paths")
    if allow.context != deny.context:
        changed.append("context")
    return tuple(changed)


def _variation(allow: PermissionMutationCase, deny: PermissionMutationCase) -> tuple[CoverageDimension | None, tuple[str, ...]]:
    changed = _variation_fields(allow, deny)
    groups = {
        CoverageDimension.RELATION if "relation_paths" in changed else CoverageDimension.ROLE: {
            field for field in changed if field in {"subject_id", "relation_paths"}
        },
        CoverageDimension.WORKFLOW: {field for field in changed if field == "context" and allow.context.workflow_states != deny.context.workflow_states},
    }
    context_changed = "context" in changed and allow.context.workflow_states == deny.context.workflow_states
    if context_changed:
        context_dimension = next((item for item in (CoverageDimension.TENANT, CoverageDimension.DEPARTMENT) if item in deny.dimensions), CoverageDimension.RELATION)
        groups[context_dimension] = {"context"}
    active = [(dimension, fields) for dimension, fields in groups.items() if fields]
    if len(active) != 1:
        return None, changed
    dimension, fields = active[0]
    return dimension, tuple(sorted(fields))


def _variation_payload(case: PermissionMutationCase, fields: tuple[str, ...]) -> dict[str, object]:
    return {field: getattr(case, field) for field in fields}
