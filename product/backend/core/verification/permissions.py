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
class PermissionContract(PermissionModel):
    schema_version: Literal["4"] = "4"
    contract_id: str = Field(pattern=_ID_PATTERN)
    version: int = Field(ge=1, le=2_147_483_647)
    role_ids: tuple[str, ...] = Field(min_length=1, max_length=128)
    workflow_states: tuple[str, ...] = Field(min_length=1, max_length=128)
    subjects: tuple[SubjectDefinition, ...] = Field(min_length=1, max_length=4096)
    effects: tuple[SecurityEffectDefinition, ...] = Field(min_length=1, max_length=4096)
    actions: tuple[ActionDefinition, ...] = Field(min_length=1, max_length=4096)
    resources: tuple[ResourceDefinition, ...] = Field(min_length=1, max_length=4096)
    relations: tuple[RelationFact, ...] = Field(default=(), max_length=8192)
    rules: tuple[PermissionRule, ...] = Field(min_length=1, max_length=8192)
    batch_rules: tuple[BatchPermissionRule, ...] = Field(default=(), max_length=2048)

    @field_validator("contract_id")
    @classmethod
    def reject_forbidden_contract_text(cls, value: str) -> str:
        return _safe_text(value, "contract_id")

    @field_validator("role_ids", "workflow_states")
    @classmethod
    def normalize_declared_ids(cls, values: tuple[str, ...], info: Any) -> tuple[str, ...]:
        pattern = _STATE_PATTERN if info.field_name == "workflow_states" else _ID_PATTERN
        if any(not re.fullmatch(pattern, value) for value in values):
            raise ValueError(f"{info.field_name} must contain bounded IDs")
        return _ordered_unique(values, info.field_name)

    @model_validator(mode="after")
    def validate_references(self) -> PermissionContract:
        """校验图、规则、批量语义和跨引用，拒绝悬空或冲突关系。"""

        subjects = {item.subject_id: item for item in self.subjects}
        effects = {item.effect_id: item for item in self.effects}
        actions = {item.action_id: item for item in self.actions}
        resources = {item.resource_id: item for item in self.resources}
        relations = {item.relation_id: item for item in self.relations}
        rules = {item.rule_id: item for item in self.rules}
        batch_rules = {item.rule_id: item for item in self.batch_rules}
        all_ids = (
            tuple(subjects)
            + tuple(effects)
            + tuple(actions)
            + tuple(resources)
            + tuple(relations)
            + tuple(rules)
            + tuple(batch_rules)
            + self.workflow_states
        )
        if len(set(all_ids)) != len(all_ids):
            raise ValueError("all permission definition IDs must be globally unique")
        if len(subjects) != len(self.subjects):
            raise ValueError("subject IDs must be unique")
        if len(effects) != len(self.effects):
            raise ValueError("effect IDs must be unique")
        if len(actions) != len(self.actions):
            raise ValueError("action IDs must be unique")
        if any(effect_id not in effects for action in self.actions for effect_id in action.effect_ids):
            raise ValueError("action effect reference is invalid")
        if len(resources) != len(self.resources):
            raise ValueError("resource IDs must be unique")
        if len(relations) != len(self.relations):
            raise ValueError("relation IDs must be unique")
        if len(rules) != len(self.rules):
            raise ValueError("rule IDs must be unique")
        if len(batch_rules) != len(self.batch_rules):
            raise ValueError("batch rule IDs must be unique")
        if any(role not in self.role_ids for subject in self.subjects for role in subject.roles):
            raise ValueError("subject role must be declared by role_ids")
        if any(
            subject.parent_subject_id not in subjects
            for subject in self.subjects
            if subject.parent_subject_id is not None
        ):
            raise ValueError("parent_subject_id must reference a declared subject")
        if any(
            resource.owner_subject_id not in subjects
            for resource in self.resources
            if resource.owner_subject_id is not None
        ):
            raise ValueError("owner_subject_id must reference a declared subject")
        if any(
            resource.parent_resource_id not in resources
            for resource in self.resources
            if resource.parent_resource_id is not None
        ):
            raise ValueError("parent_resource_id must reference a declared resource")
        if any(state not in self.workflow_states for rule in self.rules for state in rule.context.workflow_states):
            raise ValueError("rule context references an undeclared workflow state")
        if any(resource.workflow_state not in self.workflow_states for resource in self.resources):
            raise ValueError("resource workflow_state must be declared")
        declared_tenants = {
            item.tenant_id for item in (*self.subjects, *self.resources) if item.tenant_id is not None
        }
        declared_departments = {
            item.department_id for item in (*self.subjects, *self.resources) if item.department_id is not None
        }
        if any(tenant_id not in declared_tenants for rule in self.rules for tenant_id in rule.context.tenant_ids):
            raise ValueError("rule context references an undeclared tenant")
        if any(department_id not in declared_departments for rule in self.rules for department_id in rule.context.department_ids):
            raise ValueError("rule context references an undeclared department")
        if any(item not in resources for rule in self.rules for item in rule.context.resource_ids):
            raise ValueError("rule context references an undeclared resource")
        if any(item not in subjects for rule in self.rules for item in (rule.subject_id,)):
            raise ValueError("rule subject reference is invalid")
        if any(rule.action_id not in actions for rule in self.rules):
            raise ValueError("rule action reference is invalid")
        if any(rule.resource_id not in resources for rule in self.rules):
            raise ValueError("rule resource reference is invalid")
        for action in self.actions:
            if action.workflow_transition is not None:
                transition = action.workflow_transition
                if not any(effects[effect_id].kind is SecurityEffectKind.STATE_MUTATION for effect_id in action.effect_ids):
                    raise ValueError("workflow transition requires a STATE_MUTATION effect")
                if any(state not in self.workflow_states for state in transition.allowed_from_states):
                    raise ValueError("workflow transition references an undeclared source state")
                if transition.target_state not in self.workflow_states:
                    raise ValueError("workflow transition references an undeclared target state")
        for relation in self.relations:
            self._validate_relation(relation, subjects, resources)
        for rule in self.rules:
            if any(relation_id not in relations for relation_id in rule.relation_path):
                raise ValueError("rule relation_path reference is invalid")
            resource = resources[rule.resource_id]
            subject = subjects[rule.subject_id]
            action = actions[rule.action_id]
            if CoverageDimension.WORKFLOW in rule.coverage_dimensions:
                transition = action.workflow_transition
                if transition is None:
                    raise ValueError("WORKFLOW coverage requires a workflow transition")
                if (
                    rule.expectation is PermissionExpectation.ALLOW
                    and (
                        resource.workflow_state not in transition.allowed_from_states
                        or any(state not in transition.allowed_from_states for state in rule.context.workflow_states)
                    )
                ):
                    raise ValueError("ALLOW WORKFLOW coverage must use an allowed source state")
            self._validate_relation_path(rule, relations)
            if rule.context.resource_ids and rule.resource_id not in rule.context.resource_ids:
                raise ValueError("rule resource must be included in its resource context")
            if (
                rule.context.workflow_states
                and resource.workflow_state not in rule.context.workflow_states
            ):
                raise ValueError("resource workflow_state must match the rule context")
            for scope_name, context_values in (
                ("tenant", rule.context.tenant_ids),
                ("department", rule.context.department_ids),
            ):
                if not context_values:
                    continue
                subject_scope = getattr(subject, f"{scope_name}_id")
                resource_scope = getattr(resource, f"{scope_name}_id")
                if (
                    subject_scope is None
                    or resource_scope is None
                    or subject_scope not in context_values
                    or resource_scope not in context_values
                ):
                    raise ValueError(f"rule {scope_name} facts must match its context")
            if (
                subject.tenant_id is not None
                and resource.tenant_id is not None
                and subject.tenant_id != resource.tenant_id
            ):
                raise ValueError("rule cannot implicitly cross tenant boundaries")
            if (
                subject.department_id is not None
                and resource.department_id is not None
                and subject.department_id != resource.department_id
            ):
                raise ValueError("rule cannot implicitly cross department boundaries")
        for batch_rule in self.batch_rules:
            action = actions.get(batch_rule.action_id)
            subject = subjects.get(batch_rule.subject_id)
            if subject is None:
                raise ValueError("batch rule subject reference is invalid")
            if action is None or not action.is_batch:
                raise ValueError("batch rule action must be declared as batch")
            resource_ids = [item.resource_id for item in batch_rule.resource_expectations]
            if len(set(resource_ids)) != len(resource_ids):
                raise ValueError("batch resource IDs must be unique")
            if any(resource_id not in resources for resource_id in resource_ids):
                raise ValueError("batch rule resource reference is invalid")
            if batch_rule.context.resource_ids and set(batch_rule.context.resource_ids) != set(resource_ids):
                raise ValueError("batch context resources must match its resource expectations")
            for item in batch_rule.resource_expectations:
                resource = resources[item.resource_id]
                if item.relation_path:
                    self._validate_relation_path_values(
                        batch_rule.subject_id,
                        item.resource_id,
                        item.relation_path,
                        relations,
                    )
                elif item.expectation is PermissionExpectation.ALLOW:
                    raise ValueError("batch ALLOW expectation requires a relation path")
                if batch_rule.context.workflow_states and resource.workflow_state not in batch_rule.context.workflow_states:
                    raise ValueError("batch resource workflow_state must match its context")
                for scope_name, context_values in (
                    ("tenant", batch_rule.context.tenant_ids),
                    ("department", batch_rule.context.department_ids),
                ):
                    if not context_values:
                        continue
                    subject_scope = getattr(subject, f"{scope_name}_id")
                    resource_scope = getattr(resource, f"{scope_name}_id")
                    if (
                        subject_scope is None
                        or resource_scope is None
                        or subject_scope not in context_values
                        or resource_scope not in context_values
                    ):
                        raise ValueError(f"batch rule {scope_name} facts must match its context")
        self._validate_graphs(subjects, resources, relations)
        self._validate_conflicts()
        object.__setattr__(self, "subjects", tuple(sorted(self.subjects, key=lambda item: item.subject_id)))
        object.__setattr__(self, "actions", tuple(sorted(self.actions, key=lambda item: item.action_id)))
        object.__setattr__(self, "resources", tuple(sorted(self.resources, key=lambda item: item.resource_id)))
        object.__setattr__(self, "relations", tuple(sorted(self.relations, key=lambda item: item.relation_id)))
        object.__setattr__(self, "rules", tuple(sorted(self.rules, key=lambda item: item.rule_id)))
        object.__setattr__(self, "batch_rules", tuple(sorted(self.batch_rules, key=lambda item: item.rule_id)))
        return self


    @staticmethod
    def _validate_relation_path(
        rule: PermissionRule,
        relations: dict[str, RelationFact],
    ) -> None:
        PermissionContract._validate_relation_path_values(
            rule.subject_id, rule.resource_id, rule.relation_path, relations
        )

    @staticmethod
    def _validate_relation_path_values(
        subject_id: str,
        resource_id: str,
        relation_path: tuple[str, ...],
        relations: dict[str, RelationFact],
    ) -> None:
        if len(set(relation_path)) != len(relation_path):
            raise ValueError("rule relation_path must not repeat relations")
        current = ("subject", subject_id)
        for relation_id in relation_path:
            relation = relations[relation_id]
            source = (relation.source.endpoint_type, relation.source.endpoint_id)
            if source != current:
                raise ValueError("rule relation_path must be a continuous directed path")
            current = (relation.target.endpoint_type, relation.target.endpoint_id)
        if current != ("resource", resource_id):
            raise ValueError("rule relation_path must end at the rule resource")

    @staticmethod
    def _validate_relation(
        relation: RelationFact,
        subjects: dict[str, SubjectDefinition],
        resources: dict[str, ResourceDefinition],
    ) -> None:
        endpoints = (relation.source, relation.target)
        if relation.source.endpoint_type == "subject" and relation.source.endpoint_id not in subjects:
            raise ValueError("relation source subject reference is invalid")
        if relation.source.endpoint_type == "resource" and relation.source.endpoint_id not in resources:
            raise ValueError("relation source resource reference is invalid")
        if relation.target.endpoint_type == "subject" and relation.target.endpoint_id not in subjects:
            raise ValueError("relation target subject reference is invalid")
        if relation.target.endpoint_type == "resource" and relation.target.endpoint_id not in resources:
            raise ValueError("relation target resource reference is invalid")
        expected_types = {
            RelationType.OWNS: (("subject", "resource"),),
            RelationType.MEMBER_OF: (("subject", "resource"),),
            RelationType.SAME_TENANT: (("subject", "subject"), ("subject", "resource"), ("resource", "subject"), ("resource", "resource")),
            RelationType.SAME_DEPARTMENT: (("subject", "subject"), ("subject", "resource"), ("resource", "subject"), ("resource", "resource")),
            RelationType.MANAGES: (("subject", "subject"),),
            RelationType.PARENT_OF: (("resource", "resource"),),
            RelationType.INHERITS: (("subject", "subject"), ("resource", "resource")),
        }
        if (relation.source.endpoint_type, relation.target.endpoint_type) not in expected_types[relation.relation]:
            raise ValueError("relation endpoint types are invalid")
        attributes = []
        for endpoint in endpoints:
            item = subjects[endpoint.endpoint_id] if endpoint.endpoint_type == "subject" else resources[endpoint.endpoint_id]
            attributes.append((getattr(item, "tenant_id"), getattr(item, "department_id")))
        for index, name in enumerate(("tenant", "department")):
            left, right = attributes[0][index], attributes[1][index]
            if left is not None and right is not None and left != right:
                raise ValueError(f"relation crosses declared {name} boundary")
        if relation.relation is RelationType.SAME_TENANT and (
            attributes[0][0] is None or attributes[0][0] != attributes[1][0]
        ):
            raise ValueError("SAME_TENANT must match declared tenant facts")
        if relation.relation is RelationType.SAME_DEPARTMENT and (
            attributes[0][1] is None or attributes[0][1] != attributes[1][1]
        ):
            raise ValueError("SAME_DEPARTMENT must match declared department facts")
        if relation.relation is RelationType.OWNS:
            resource = resources[relation.target.endpoint_id]
            if resource.owner_subject_id != relation.source.endpoint_id:
                raise ValueError("OWNS must match resource owner_subject_id")

    @staticmethod
    def _validate_graphs(
        subjects: dict[str, SubjectDefinition],
        resources: dict[str, ResourceDefinition],
        relations: dict[str, RelationFact],
    ) -> None:
        def reject_cycles(graph: dict[str, set[str]], label: str) -> None:
            visiting: set[str] = set()
            visited: set[str] = set()

            def visit(node: str) -> None:
                if node in visiting:
                    raise ValueError(f"{label} must be acyclic")
                if node in visited:
                    return
                visiting.add(node)
                for child in graph.get(node, ()):
                    visit(child)
                visiting.remove(node)
                visited.add(node)

            for node in graph:
                visit(node)

        subject_parent = {
            item.subject_id: {item.parent_subject_id}
            for item in subjects.values()
            if item.parent_subject_id is not None
        }
        resource_parent = {
            item.resource_id: {item.parent_resource_id}
            for item in resources.values()
            if item.parent_resource_id is not None
        }
        relation_graphs: dict[RelationType, dict[str, set[str]]] = {}
        for relation in relations.values():
            if relation.source.endpoint_id == relation.target.endpoint_id:
                raise ValueError("relation graph must not contain self loops")
            if relation.relation in {RelationType.MANAGES, RelationType.INHERITS, RelationType.PARENT_OF}:
                graph = relation_graphs.setdefault(relation.relation, {})
                graph.setdefault(relation.source.endpoint_id, set()).add(relation.target.endpoint_id)
        reject_cycles(subject_parent, "subject parent graph")
        reject_cycles(resource_parent, "resource parent graph")
        for relation_type, graph in relation_graphs.items():
            reject_cycles(graph, f"{relation_type.value} graph")

    def _validate_conflicts(self) -> None:
        seen: dict[tuple[Any, ...], PermissionExpectation] = {}
        for rule in self.rules:
            key = (
                rule.subject_id,
                rule.action_id,
                rule.resource_id,
                rule.relation_path,
                canonical_json_bytes(rule.context),
            )
            previous = seen.get(key)
            if previous is not None and previous is not rule.expectation:
                raise ValueError("same permission semantics cannot ALLOW and DENY")
            seen[key] = rule.expectation
        batch_seen: dict[tuple[Any, ...], tuple[PermissionExpectation, ...]] = {}
        for rule in self.batch_rules:
            key = (
                rule.subject_id,
                rule.action_id,
                tuple(item.resource_id for item in rule.resource_expectations),
                canonical_json_bytes(rule.context),
            )
            expectations = tuple(item.expectation for item in rule.resource_expectations)
            previous = batch_seen.get(key)
            if previous is not None and previous != expectations:
                raise ValueError("same batch permission semantics cannot conflict")
            batch_seen[key] = expectations


def parse_permission_contract(raw: bytes | str) -> PermissionContract:
    """严格读取唯一当前版本的权限契约根文档。"""

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value

        return result

    if isinstance(raw, str):
        encoded = raw.encode("utf-8")
    elif isinstance(raw, bytes):
        encoded = raw
    else:
        raise TypeError("permission contract must be UTF-8 JSON bytes or text")
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise ValueError("permission contract does not accept BOM")
    parsed = json.loads(
        encoded.decode("utf-8"),
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    if not isinstance(parsed, dict) or parsed.get("schema_version") != "4":
        raise ValueError("permission contract schema_version is missing or unsupported")
    return PermissionContract.model_validate_json(encoded, strict=True)

class NormalizedPermissionCase(PermissionModel):
    case_id: str = Field(pattern=_ID_PATTERN)
    fingerprint: str = Field(pattern=_HEX_PATTERN)
    source_kind: Literal["permission"]
    source_contract_id: str = Field(pattern=_ID_PATTERN)
    source_rule_id: str = Field(pattern=_ID_PATTERN)
    subject_id: str = Field(pattern=_ID_PATTERN)
    action_id: str = Field(pattern=_ID_PATTERN)
    resource_id: str = Field(pattern=_ID_PATTERN)
    relation_path: tuple[str, ...] = Field(min_length=1, max_length=64)
    context: PermissionContext
    expected: PermissionExpectation
    required_observations: tuple[str, ...] = Field(min_length=1, max_length=16)
    seed: int
    engine_version: str = Field(min_length=1, max_length=128, pattern=_TEXT_PATTERN)
    source_case_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    source_step_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    source_identity_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    source_resource_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    source_owner_identity_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    source_mutation: str | None = Field(default=None, pattern=_TEXT_PATTERN)


class NormalizedPermissionPlan(PermissionModel):
    plan_id: str = Field(pattern=_ID_PATTERN)
    source_contract_id: str = Field(pattern=_ID_PATTERN)
    seed: int
    engine_version: str = Field(min_length=1, max_length=128, pattern=_TEXT_PATTERN)
    cases: tuple[NormalizedPermissionCase, ...] = Field(min_length=1, max_length=8192)

    @model_validator(mode="after")
    def normalize_cases(self) -> NormalizedPermissionPlan:
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("normalized case IDs must be unique")
        object.__setattr__(self, "cases", tuple(sorted(self.cases, key=lambda item: item.fingerprint)))
        return self


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="python"))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def permission_model_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def compile_permission_plan(
    contract: PermissionContract,
    *,
    engine_version: str,
    seed: int = 0,
) -> NormalizedPermissionPlan:
    """把已验证 Contract 投影为稳定排序、带指纹的规范计划。"""

    cases: list[NormalizedPermissionCase] = []
    for rule in contract.rules:
        fingerprint = permission_model_sha256(
            {
                "contract_id": contract.contract_id,
                "rule": rule,
                "engine_version": engine_version,
                "seed": seed,
            }
        )
        cases.append(
            NormalizedPermissionCase(
                case_id=f"case-{fingerprint[:32]}",
                fingerprint=fingerprint,
                source_kind="permission",
                source_contract_id=contract.contract_id,
                source_rule_id=rule.rule_id,
                subject_id=rule.subject_id,
                action_id=rule.action_id,
                resource_id=rule.resource_id,
                relation_path=rule.relation_path,
                context=rule.context,
                expected=rule.expectation,
                required_observations=rule.required_observations,
                seed=seed,
                engine_version=engine_version,
            )
        )
    plan = NormalizedPermissionPlan(
        plan_id=f"plan-{permission_model_sha256(cases)[:32]}",
        source_contract_id=contract.contract_id,
        seed=seed,
        engine_version=engine_version,
        cases=tuple(cases),
    )
    return plan
