# 定义权限关系、业务效果和规则条目，集中维护字段约束与字面量校验。
# 这里只接受有限、可序列化的意图事实；不包含 URL、秘密或可执行载荷。

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.domain.boundaries.semantics import BusinessEffectKind as SecurityEffectKind, PermissionExpectation

INTENT_ID_PATTERN = r"^[a-z][a-z0-9_-]{0,63}$"
INTENT_TEXT_PATTERN = r"^[a-z][a-z0-9_.:-]{0,127}$"
WORKFLOW_STATE_PATTERN = r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
_SECRET_OR_URL = re.compile(
    r"(?:https?://|javascript:|data:|bearer\s|authorization\s*[:=]|"
    r"(?:password|passwd|secret|token|api[_-]?key)\s*[:=])",
    re.IGNORECASE,
)


class PermissionModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class RelationType(StrEnum):
    OWNS = "OWNS"
    MEMBER_OF = "MEMBER_OF"
    SAME_TENANT = "SAME_TENANT"
    SAME_DEPARTMENT = "SAME_DEPARTMENT"
    MANAGES = "MANAGES"
    PARENT_OF = "PARENT_OF"
    INHERITS = "INHERITS"


# Contract 中的安全效果只表达业务意图，不携带 Observer 或传输实现细节。
class SecurityEffectDefinition(PermissionModel):
    effect_id: str = Field(pattern=INTENT_ID_PATTERN)
    kind: SecurityEffectKind
    resource_type: str = Field(pattern=INTENT_TEXT_PATTERN)
    expected_state: str | None = Field(default=None, pattern=WORKFLOW_STATE_PATTERN)
    protected_fields: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("effect_id", "resource_type", "expected_state")
    @classmethod
    def reject_forbidden_effect_text(cls, value: str | None, info: Any) -> str | None:
        return None if value is None else validate_intent_text(value, info.field_name)

    @field_validator("protected_fields")
    @classmethod
    def normalize_protected_fields(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(re.fullmatch(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$", value) is None for value in values):
            raise ValueError("protected_fields must contain bounded projection paths")
        return sorted_unique_values(values, "protected_fields")

    @model_validator(mode="after")
    def validate_effect(self) -> SecurityEffectDefinition:
        if self.kind is SecurityEffectKind.DATA_DISCLOSURE and not self.protected_fields:
            raise ValueError("DATA_DISCLOSURE requires protected_fields")
        if self.kind is not SecurityEffectKind.DATA_DISCLOSURE and self.protected_fields:
            raise ValueError("protected_fields are only valid for DATA_DISCLOSURE")
        return self


class CoverageDimension(StrEnum):
    ROLE = "ROLE"
    TENANT = "TENANT"
    DEPARTMENT = "DEPARTMENT"
    RELATION = "RELATION"
    WORKFLOW = "WORKFLOW"
    BULK = "BULK"


class BatchAuthorizationMode(StrEnum):
    ALL_ALLOW = "ALL_ALLOW"
    ALL_DENY = "ALL_DENY"
    MIXED_AUTHORIZATION = "MIXED_AUTHORIZATION"


class WorkflowTransition(PermissionModel):
    allowed_from_states: tuple[str, ...] = Field(min_length=1, max_length=32)
    target_state: str = Field(pattern=WORKFLOW_STATE_PATTERN)

    @field_validator("allowed_from_states")
    @classmethod
    def normalize_allowed_from_states(
        cls, values: tuple[str, ...]
    ) -> tuple[str, ...]:
        if any(not re.fullmatch(WORKFLOW_STATE_PATTERN, value) for value in values):
            raise ValueError("allowed_from_states must contain bounded IDs")
        return sorted_unique_values(values, "allowed_from_states")


def sorted_unique_values(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must be unique")
    return tuple(sorted(values))


def validate_intent_text(value: str, field_name: str) -> str:
    """拒绝权限格式禁止的字面量；不作为通用秘密检测器。"""
    if _SECRET_OR_URL.search(value):
        raise ValueError(f"{field_name} contains a forbidden secret, URL, or script")
    return value


class SubjectDefinition(PermissionModel):
    subject_id: str = Field(pattern=INTENT_ID_PATTERN)
    roles: tuple[str, ...] = Field(min_length=1, max_length=64)
    tenant_id: str | None = Field(default=None, pattern=INTENT_ID_PATTERN)
    department_id: str | None = Field(default=None, pattern=INTENT_ID_PATTERN)
    admin_level: int = Field(default=0, ge=0, le=100)
    parent_subject_id: str | None = Field(default=None, pattern=INTENT_ID_PATTERN)

    @field_validator("subject_id", "tenant_id", "department_id", "parent_subject_id")
    @classmethod
    def reject_forbidden_text(cls, value: str | None, info: Any) -> str | None:
        return None if value is None else validate_intent_text(value, info.field_name)

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(INTENT_TEXT_PATTERN, value) for value in values):
            raise ValueError("roles must be bounded slugs")
        return sorted_unique_values(values, "roles")


class ActionDefinition(PermissionModel):
    action_id: str = Field(pattern=INTENT_ID_PATTERN)
    effect_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    is_batch: bool = False
    workflow_transition: WorkflowTransition | None = None

    @field_validator("action_id")
    @classmethod
    def reject_forbidden_action_text(cls, value: str) -> str:
        return validate_intent_text(value, "action_id")

    @field_validator("effect_ids")
    @classmethod
    def normalize_effect_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(re.fullmatch(INTENT_ID_PATTERN, value) is None for value in values):
            raise ValueError("effect_ids must contain bounded IDs")
        return sorted_unique_values(values, "effect_ids")


class ResourceDefinition(PermissionModel):
    resource_id: str = Field(pattern=INTENT_ID_PATTERN)
    resource_type: str = Field(pattern=INTENT_TEXT_PATTERN)
    tenant_id: str | None = Field(default=None, pattern=INTENT_ID_PATTERN)
    department_id: str | None = Field(default=None, pattern=INTENT_ID_PATTERN)
    owner_subject_id: str | None = Field(default=None, pattern=INTENT_ID_PATTERN)
    parent_resource_id: str | None = Field(default=None, pattern=INTENT_ID_PATTERN)
    workflow_state: str = Field(pattern=WORKFLOW_STATE_PATTERN)

    @field_validator(
        "resource_id",
        "resource_type",
        "tenant_id",
        "department_id",
        "owner_subject_id",
        "parent_resource_id",
        "workflow_state",
    )
    @classmethod
    def reject_forbidden_resource_text(cls, value: str | None, info: Any) -> str | None:
        return None if value is None else validate_intent_text(value, info.field_name)


class RelationEndpoint(PermissionModel):
    endpoint_type: Literal["subject", "resource"]
    endpoint_id: str = Field(pattern=INTENT_ID_PATTERN)

    @field_validator("endpoint_id")
    @classmethod
    def reject_forbidden_endpoint_text(cls, value: str) -> str:
        return validate_intent_text(value, "endpoint_id")


class RelationFact(PermissionModel):
    relation_id: str = Field(pattern=INTENT_ID_PATTERN)
    relation: RelationType
    source: RelationEndpoint
    target: RelationEndpoint

    @field_validator("relation_id")
    @classmethod
    def reject_forbidden_relation_text(cls, value: str) -> str:
        return validate_intent_text(value, "relation_id")


class PermissionContext(PermissionModel):
    workflow_states: tuple[str, ...] = Field(default=(), max_length=64)
    tenant_ids: tuple[str, ...] = Field(default=(), max_length=64)
    department_ids: tuple[str, ...] = Field(default=(), max_length=64)
    resource_ids: tuple[str, ...] = Field(default=(), max_length=256)

    @field_validator("workflow_states", "tenant_ids", "department_ids", "resource_ids")
    @classmethod
    def normalize_context_values(
        cls, values: tuple[str, ...], info: Any
    ) -> tuple[str, ...]:
        pattern = WORKFLOW_STATE_PATTERN if info.field_name == "workflow_states" else INTENT_ID_PATTERN
        if any(not re.fullmatch(pattern, value) for value in values):
            raise ValueError(f"{info.field_name} must contain bounded IDs")
        return sorted_unique_values(values, info.field_name)


class PermissionRule(PermissionModel):
    rule_id: str = Field(pattern=INTENT_ID_PATTERN)
    subject_id: str = Field(pattern=INTENT_ID_PATTERN)
    action_id: str = Field(pattern=INTENT_ID_PATTERN)
    resource_id: str = Field(pattern=INTENT_ID_PATTERN)
    relation_path: tuple[str, ...] = Field(min_length=1, max_length=64)
    context: PermissionContext = Field(default_factory=PermissionContext)
    expectation: PermissionExpectation
    required_observations: tuple[str, ...] = Field(min_length=1, max_length=16)
    coverage_dimensions: tuple[CoverageDimension, ...] = Field(
        default=(), max_length=6
    )
    severity: Literal["low", "medium", "high", "critical"] = "high"

    @field_validator("rule_id", "subject_id", "action_id", "resource_id")
    @classmethod
    def reject_forbidden_rule_text(cls, value: str, info: Any) -> str:
        return validate_intent_text(value, info.field_name)

    @field_validator("relation_path")
    @classmethod
    def normalize_relation_path(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(INTENT_ID_PATTERN, value) for value in values):
            raise ValueError("relation_path must contain relation IDs")
        return values

    @field_validator("required_observations")
    @classmethod
    def normalize_observations(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(INTENT_TEXT_PATTERN, value) for value in values):
            raise ValueError("required_observations must contain bounded requirement IDs")
        return sorted_unique_values(values, "required_observations")

    @field_validator("coverage_dimensions")
    @classmethod
    def normalize_coverage_dimensions(
        cls, values: tuple[CoverageDimension, ...]
    ) -> tuple[CoverageDimension, ...]:
        if len(set(values)) != len(values):
            raise ValueError("coverage_dimensions must be unique")
        if CoverageDimension.BULK in values:
            raise ValueError("BULK coverage requires a batch rule")
        return tuple(sorted(values, key=lambda value: value.value))


class BatchResourceExpectation(PermissionModel):
    resource_id: str = Field(pattern=INTENT_ID_PATTERN)
    expectation: PermissionExpectation
    relation_path: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("relation_path")
    @classmethod
    def validate_batch_relation_path(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(INTENT_ID_PATTERN, value) for value in values):
            raise ValueError("batch relation_path must contain relation IDs")
        if len(set(values)) != len(values):
            raise ValueError("batch relation_path must not repeat relations")
        return values


class BatchPermissionRule(PermissionModel):
    rule_id: str = Field(pattern=INTENT_ID_PATTERN)
    subject_id: str = Field(pattern=INTENT_ID_PATTERN)
    action_id: str = Field(pattern=INTENT_ID_PATTERN)
    resource_expectations: tuple[BatchResourceExpectation, ...] = Field(
        min_length=2, max_length=256
    )
    required_observations: tuple[str, ...] = Field(min_length=1, max_length=16)
    context: PermissionContext = Field(default_factory=PermissionContext)
    atomic: bool = True
    coverage_dimensions: tuple[CoverageDimension, ...] = Field(
        min_length=1, max_length=6
    )
    severity: Literal["low", "medium", "high", "critical"] = "high"

    @field_validator("required_observations")
    @classmethod
    def normalize_batch_observations(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(INTENT_TEXT_PATTERN, value) for value in values):
            raise ValueError("required_observations must contain bounded requirement IDs")
        return sorted_unique_values(values, "required_observations")

    @field_validator("coverage_dimensions")
    @classmethod
    def normalize_batch_dimensions(
        cls, values: tuple[CoverageDimension, ...]
    ) -> tuple[CoverageDimension, ...]:
        if len(set(values)) != len(values):
            raise ValueError("coverage_dimensions must be unique")
        return tuple(sorted(values, key=lambda value: value.value))

    @model_validator(mode="after")
    def require_bulk_dimension(self) -> BatchPermissionRule:
        if CoverageDimension.BULK not in self.coverage_dimensions:
            raise ValueError("batch rule coverage_dimensions must include BULK")
        object.__setattr__(
            self,
            "resource_expectations",
            tuple(sorted(self.resource_expectations, key=lambda item: item.resource_id)),
        )
        return self
