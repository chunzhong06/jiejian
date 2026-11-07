"""有限权限条件与采集事实；缺值保持未知，不从账号名称或请求结果推断。"""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from product.protocols.checks.relationships import RelationshipRequirement, ObservedRelationship


class ConditionModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True)


PublicValue = Annotated[str, Field(min_length=1, max_length=128)]


class PermissionConditions(ConditionModel):
    principal: Literal['AUTHENTICATED', 'ANONYMOUS'] = 'AUTHENTICATED'
    tenant: Literal['SAME', 'DIFFERENT'] | None = None
    resource_states: tuple[PublicValue, ...] = Field(default=(), max_length=8)
    relationships: tuple[RelationshipRequirement, ...] = Field(default=(), max_length=4, exclude_if=lambda value: not value)

    @field_validator('resource_states')
    @classmethod
    def finite_states(cls, values):
        if len(set(values)) != len(values) or any(value != value.strip() or any(ord(char) < 32 for char in value) for value in values):
            raise ValueError('resource states must be unique')
        return tuple(sorted(values))

    @model_validator(mode='after')
    def meaningful_condition(self):
        if len({item.kind for item in self.relationships}) != len(self.relationships):
            raise ValueError('one finite requirement per relationship kind')
        if self.relationships and self.principal == 'ANONYMOUS':
            raise ValueError('relationship conditions require an authenticated subject')
        if self.principal == 'ANONYMOUS' and self.tenant is not None:
            raise ValueError('an anonymous principal has no verified tenant')
        if self.principal == 'AUTHENTICATED' and self.tenant is None and not self.resource_states and not self.relationships:
            raise ValueError('use an absent condition for an unconditional authenticated rule')
        return self


class ObservedPermissionConditions(ConditionModel):
    proof_fingerprint: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    source_id: Annotated[str, Field(pattern=r'^psr_[0-9a-f]{32}$')]
    source_fingerprint: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    principal: Literal['AUTHENTICATED', 'ANONYMOUS']
    subject_tenant: PublicValue | None = None
    owner_tenant: PublicValue | None = None
    resource_tenant: PublicValue | None = None
    resource_state: PublicValue | None = None
    relationships: tuple[ObservedRelationship, ...] = Field(default=(), max_length=4, exclude_if=lambda value: not value)

    @field_validator('subject_tenant', 'owner_tenant', 'resource_tenant', 'resource_state')
    @classmethod
    def public_value(cls, value):
        if value is not None and (value != value.strip() or any(ord(char) < 32 for char in value)):
            raise ValueError('condition values must be public printable identifiers')
        return value


def match_permission_conditions(expected, observed):
    """只比较已采集的公开条件值；租户要求同时约束真实主体、所有者与资源。"""
    if expected is None:
        return 'MATCH'
    if observed is None:
        return 'UNKNOWN'
    checks = [observed.principal == expected.principal]
    if expected.tenant is not None:
        if any(value is None for value in (observed.subject_tenant, observed.owner_tenant, observed.resource_tenant)):
            return 'UNKNOWN'
        checks.append(observed.owner_tenant == observed.resource_tenant)
        same = observed.subject_tenant == observed.resource_tenant
        checks.append(same == (expected.tenant == 'SAME'))
    if expected.resource_states:
        if observed.resource_state is None:
            return 'UNKNOWN'
        checks.append(observed.resource_state in expected.resource_states)
    for requirement in expected.relationships:
        matches = [item for item in observed.relationships if item.requirement_fingerprint == requirement.fingerprint()
            and item.kind == requirement.kind]
        if len(matches) != 1 or matches[0].status == 'UNKNOWN':
            return 'UNKNOWN'
        checks.append(matches[0].status == 'MATCH')
    return 'MATCH' if all(checks) else 'MISMATCH'


def collected_conditions_status(expected, observations):
    if expected is None:
        return 'MATCH'
    states = {match_permission_conditions(expected, item) for item in observations}
    if not states or 'UNKNOWN' in states:
        return 'UNKNOWN'
    return 'MISMATCH' if 'MISMATCH' in states else 'MATCH'


def permission_conditions_overlap(left, right):
    """有限条件的交集；未限定属性覆盖该属性全部值，不假定未声明的状态互斥。"""
    if (left.principal if left else 'AUTHENTICATED') != (right.principal if right else 'AUTHENTICATED'):
        return False
    if left is None or right is None:
        return True
    if left.tenant is not None and right.tenant is not None and left.tenant != right.tenant:
        return False
    for a in left.relationships:
        for b in right.relationships:
            if (a.kind, a.organization_scope, a.inherited_role, a.max_depth) == (b.kind, b.organization_scope, b.inherited_role, b.max_depth) and a.state != b.state:
                return False
    return not (left.resource_states and right.resource_states and set(left.resource_states).isdisjoint(right.resource_states))
