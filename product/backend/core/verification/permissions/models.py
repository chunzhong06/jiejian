# =============================================================================
# 权限关系模型与覆盖计划
#
# 定位
#   表达可验证的权限意图，并编译为不执行目标流量的规范化 Verification 用例
#
# 职责
#   定义权限图与规则｜校验跨引用不变量｜编译稳定规范计划
#
# 边界
#   只接受显式、有限、可序列化的关系事实；不包含 URL、秘密、脚本或任意 payload。
#   本模块不依赖适配器，也不执行 Runner。
#
# 调用链
#   Contract governance / ExecutionWorkflow → PermissionContract → normalized plan
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ID_PATTERN = r"^[a-z][a-z0-9_-]{0,63}$"
_TEXT_PATTERN = r"^[a-z][a-z0-9_.:-]{0,127}$"
_STATE_PATTERN = r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
_HEX_PATTERN = r"^[0-9a-f]{64}$"
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


class PermissionExpectation(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class SecurityEffectKind(StrEnum):
    STATE_MUTATION = "STATE_MUTATION"
    DATA_DISCLOSURE = "DATA_DISCLOSURE"
    OBJECT_CREATION = "OBJECT_CREATION"
    EXTERNAL_DISPATCH = "EXTERNAL_DISPATCH"
    RESTRICTED_FUNCTION_INVOCATION = "RESTRICTED_FUNCTION_INVOCATION"
    CREDENTIAL_ACCESS = "CREDENTIAL_ACCESS"


# Contract 中的安全效果只表达业务意图，不携带 Observer 或传输实现细节。
class SecurityEffectDefinition(PermissionModel):
    effect_id: str = Field(pattern=_ID_PATTERN)
    kind: SecurityEffectKind
    resource_type: str = Field(pattern=_TEXT_PATTERN)
    expected_state: str | None = Field(default=None, pattern=_STATE_PATTERN)
    protected_fields: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("effect_id", "resource_type", "expected_state")
    @classmethod
    def reject_forbidden_effect_text(cls, value: str | None, info: Any) -> str | None:
        return None if value is None else _safe_text(value, info.field_name)

    @field_validator("protected_fields")
    @classmethod
    def normalize_protected_fields(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(re.fullmatch(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$", value) is None for value in values):
            raise ValueError("protected_fields must contain bounded projection paths")
        return _ordered_unique(values, "protected_fields")

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
    target_state: str = Field(pattern=_STATE_PATTERN)

    @field_validator("allowed_from_states")
    @classmethod
    def normalize_allowed_from_states(
        cls, values: tuple[str, ...]
    ) -> tuple[str, ...]:
        if any(not re.fullmatch(_STATE_PATTERN, value) for value in values):
            raise ValueError("allowed_from_states must contain bounded IDs")
        return _ordered_unique(values, "allowed_from_states")


def _ordered_unique(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must be unique")
    return tuple(sorted(values))


def _safe_text(value: str, field_name: str) -> str:
    if _SECRET_OR_URL.search(value):
        raise ValueError(f"{field_name} contains a forbidden secret, URL, or script")
    return value


class SubjectDefinition(PermissionModel):
    subject_id: str = Field(pattern=_ID_PATTERN)
    roles: tuple[str, ...] = Field(min_length=1, max_length=64)
    tenant_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    department_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    admin_level: int = Field(default=0, ge=0, le=100)
    parent_subject_id: str | None = Field(default=None, pattern=_ID_PATTERN)

    @field_validator("subject_id", "tenant_id", "department_id", "parent_subject_id")
    @classmethod
    def reject_forbidden_text(cls, value: str | None, info: Any) -> str | None:
        return None if value is None else _safe_text(value, info.field_name)

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(_TEXT_PATTERN, value) for value in values):
            raise ValueError("roles must be bounded slugs")
        return _ordered_unique(values, "roles")


class ActionDefinition(PermissionModel):
    action_id: str = Field(pattern=_ID_PATTERN)
    effect_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    is_batch: bool = False
    workflow_transition: WorkflowTransition | None = None

    @field_validator("action_id")
    @classmethod
    def reject_forbidden_action_text(cls, value: str) -> str:
        return _safe_text(value, "action_id")

    @field_validator("effect_ids")
    @classmethod
    def normalize_effect_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(re.fullmatch(_ID_PATTERN, value) is None for value in values):
            raise ValueError("effect_ids must contain bounded IDs")
        return _ordered_unique(values, "effect_ids")


class ResourceDefinition(PermissionModel):
    resource_id: str = Field(pattern=_ID_PATTERN)
    resource_type: str = Field(pattern=_TEXT_PATTERN)
    tenant_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    department_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    owner_subject_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    parent_resource_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    workflow_state: str = Field(pattern=_STATE_PATTERN)

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
        return None if value is None else _safe_text(value, info.field_name)


class RelationEndpoint(PermissionModel):
    endpoint_type: Literal["subject", "resource"]
    endpoint_id: str = Field(pattern=_ID_PATTERN)

    @field_validator("endpoint_id")
    @classmethod
    def reject_forbidden_endpoint_text(cls, value: str) -> str:
        return _safe_text(value, "endpoint_id")


class RelationFact(PermissionModel):
    relation_id: str = Field(pattern=_ID_PATTERN)
    relation: RelationType
    source: RelationEndpoint
    target: RelationEndpoint

    @field_validator("relation_id")
    @classmethod
    def reject_forbidden_relation_text(cls, value: str) -> str:
        return _safe_text(value, "relation_id")


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
        pattern = _STATE_PATTERN if info.field_name == "workflow_states" else _ID_PATTERN
        if any(not re.fullmatch(pattern, value) for value in values):
            raise ValueError(f"{info.field_name} must contain bounded IDs")
        return _ordered_unique(values, info.field_name)


class PermissionRule(PermissionModel):
    rule_id: str = Field(pattern=_ID_PATTERN)
    subject_id: str = Field(pattern=_ID_PATTERN)
    action_id: str = Field(pattern=_ID_PATTERN)
    resource_id: str = Field(pattern=_ID_PATTERN)
    relation_path: tuple[str, ...] = Field(min_length=1, max_length=64)
    context: PermissionContext = Field(default_factory=PermissionContext)
    expectation: PermissionExpectation
    required_observations: tuple[str, ...] = Field(min_length=1, max_length=16)
    coverage_dimensions: tuple[CoverageDimension, ...] = Field(
        min_length=1, max_length=6
    )
    severity: Literal["low", "medium", "high", "critical"] = "high"

    @field_validator("rule_id", "subject_id", "action_id", "resource_id")
    @classmethod
    def reject_forbidden_rule_text(cls, value: str, info: Any) -> str:
        return _safe_text(value, info.field_name)

    @field_validator("relation_path")
    @classmethod
    def normalize_relation_path(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(_ID_PATTERN, value) for value in values):
            raise ValueError("relation_path must contain relation IDs")
        return values

    @field_validator("required_observations")
    @classmethod
    def normalize_observations(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(_TEXT_PATTERN, value) for value in values):
            raise ValueError("required_observations must contain bounded requirement IDs")
        return _ordered_unique(values, "required_observations")

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
    resource_id: str = Field(pattern=_ID_PATTERN)
    expectation: PermissionExpectation
    relation_path: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("relation_path")
    @classmethod
    def validate_batch_relation_path(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(_ID_PATTERN, value) for value in values):
            raise ValueError("batch relation_path must contain relation IDs")
        if len(set(values)) != len(values):
            raise ValueError("batch relation_path must not repeat relations")
        return values


class BatchPermissionRule(PermissionModel):
    rule_id: str = Field(pattern=_ID_PATTERN)
    subject_id: str = Field(pattern=_ID_PATTERN)
    action_id: str = Field(pattern=_ID_PATTERN)
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
        if any(not re.fullmatch(_TEXT_PATTERN, value) for value in values):
            raise ValueError("required_observations must contain bounded requirement IDs")
        return _ordered_unique(values, "required_observations")

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


# 完整、冻结的权限关系图与规则集合；所有跨引用在构造时一次校验。
