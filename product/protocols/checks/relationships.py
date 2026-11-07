"""有限关系条件和私有事实归约；只核对实验前提，不计算应用的授权结论。"""
from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RelationshipModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True)


PublicId = Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')]
RelationshipKind = Literal['ORGANIZATION', 'ROLE_INHERITANCE', 'SHARING', 'DELEGATION']
RelationState = Literal['ACTIVE', 'ABSENT', 'EXPIRED', 'REVOKED']


class RelationshipRequirement(RelationshipModel):
    kind: RelationshipKind
    state: RelationState = 'ACTIVE'
    organization_scope: Literal['SAME', 'SUBJECT_ANCESTOR', 'RESOURCE_ANCESTOR'] = 'SAME'
    inherited_role: PublicId | None = None
    max_depth: int = Field(default=1, ge=1, le=8)

    @model_validator(mode='after')
    def finite_shape(self):
        if self.kind != 'ORGANIZATION' and self.organization_scope != 'SAME':
            raise ValueError('organization scope belongs to organization relationships')
        if (self.kind == 'ROLE_INHERITANCE') != (self.inherited_role is not None):
            raise ValueError('role inheritance requires its named business role')
        if self.kind in {'ORGANIZATION', 'ROLE_INHERITANCE'} and self.state not in {'ACTIVE', 'ABSENT'}:
            raise ValueError('membership uses active or absent state')
        if self.kind in {'SHARING', 'DELEGATION'} and self.max_depth != 1:
            raise ValueError('grants support direct, non-redelegable relationships')
        return self

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.model_dump(mode='json'), sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


class RelationshipEdge(RelationshipModel):
    child: PublicId
    parent: PublicId


class RelationshipGrant(RelationshipModel):
    grant_id: PublicId
    kind: Literal['SHARING', 'DELEGATION']
    grantor_id: PublicId
    grantee_id: PublicId
    grantee_kind:Literal['SUBJECT','GROUP']=Field(default='SUBJECT',exclude_if=lambda value:value=='SUBJECT')
    resource_id: PublicId
    actions: tuple[PublicId, ...] = Field(min_length=1, max_length=32)
    valid_from_us: int = Field(ge=0)
    valid_until_us: int | None = Field(default=None, ge=0)
    revoked_at_us: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def bounded_grant(self):
        if (self.grantee_kind=='SUBJECT' and self.grantor_id == self.grantee_id) or len(set(self.actions)) != len(self.actions):
            raise ValueError('grant endpoints and actions must be distinct')
        if self.kind=='DELEGATION' and self.grantee_kind!='SUBJECT':
            raise ValueError('bounded delegation requires one explicit subject')
        if self.valid_until_us is not None and self.valid_until_us <= self.valid_from_us:
            raise ValueError('grant interval must be nonempty')
        if self.revoked_at_us is not None and self.revoked_at_us < self.valid_from_us:
            raise ValueError('revocation cannot precede grant')
        return self


class RelationshipSnapshot(RelationshipModel):
    """独立来源内的临时投影，不将整份组织、角色或共享数据发布到报告。"""
    subject_id: PublicId
    owner_id: PublicId
    resource_id: PublicId
    action: PublicId
    observed_at_us: int = Field(ge=0)
    clock_uncertainty_us: int = Field(default=0, ge=0, le=5_000_000)
    source_time_us: int | None = Field(default=None, ge=0)
    scope_complete: bool = True
    subject_organizations: tuple[PublicId, ...] = Field(default=(), max_length=32)
    subject_groups:tuple[PublicId,...]|None=Field(default=None,max_length=32)
    resource_organization: PublicId | None = None
    organization_parents: tuple[RelationshipEdge, ...] = Field(default=(), max_length=128)
    subject_roles: tuple[PublicId, ...] = Field(default=(), max_length=32)
    role_inheritance: tuple[RelationshipEdge, ...] = Field(default=(), max_length=128)
    grants: tuple[RelationshipGrant, ...] = Field(default=(), max_length=128)

    @model_validator(mode='after')
    def unique_acyclic_graphs(self):
        for values in (self.subject_organizations, self.subject_roles,self.subject_groups or ()):
            if len(set(values)) != len(values):
                raise ValueError('duplicate relationship membership')
        if len({item.grant_id for item in self.grants}) != len(self.grants):
            raise ValueError('duplicate grant identity')
        for edges in (self.organization_parents, self.role_inheritance):
            graph = {}
            for edge in edges:
                if edge.parent in graph.setdefault(edge.child, set()):
                    raise ValueError('duplicate relationship edge')
                graph[edge.child].add(edge.parent)
            visited, active = set(), set()
            def visit(node):
                if node in active:
                    raise ValueError('cyclic relationship graph')
                if node in visited:
                    return
                active.add(node)
                for parent in sorted(graph.get(node, ())):
                    visit(parent)
                active.remove(node)
                visited.add(node)
            for node in sorted(graph):
                visit(node)
        return self


class ObservedRelationship(RelationshipModel):
    requirement_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    kind: RelationshipKind
    status: Literal['MATCH', 'MISMATCH', 'UNKNOWN']
    observed_at_us: int = Field(ge=0)
    path: tuple[PublicId, ...] = Field(default=(), max_length=9)
    reason: Literal['RELATIONSHIP_MATCHED', 'RELATIONSHIP_NOT_MATCHED', 'RELATIONSHIP_TIME_UNCERTAIN',
        'RELATIONSHIP_SCOPE_INCOMPLETE', 'RELATIONSHIP_DEPTH_EXCEEDED']


def _path(edges, starts, target, max_depth):
    graph = {}
    for edge in edges:
        graph.setdefault(edge.child, set()).add(edge.parent)
    pending = deque((item,) for item in sorted(starts))
    seen = set(starts)
    exhausted = False
    while pending:
        path = pending.popleft()
        if path[-1] == target:
            return path, exhausted
        parents = sorted(graph.get(path[-1], set()) - seen)
        if len(path) - 1 == max_depth:
            exhausted |= bool(parents)
        else:
            pending.extend((*path, parent) for parent in parents)
            seen.update(parents)
    return (), exhausted


def observe_relationship(requirement, snapshot):
    """来源字段完整后才可调用；时间边缘、超深路径不能降格成关系不存在。"""
    base = dict(requirement_fingerprint=requirement.fingerprint(), kind=requirement.kind,
        observed_at_us=snapshot.observed_at_us)
    def result(status, reason, path=()):
        return ObservedRelationship(**base, status=status, reason=reason, path=path)
    if not snapshot.scope_complete:
        return result('UNKNOWN', 'RELATIONSHIP_SCOPE_INCOMPLETE')
    path, exhausted, states = (), False, set()
    if requirement.kind == 'ORGANIZATION':
        if snapshot.resource_organization is None:
            return result('UNKNOWN', 'RELATIONSHIP_SCOPE_INCOMPLETE')
        if requirement.organization_scope == 'SAME':
            if snapshot.resource_organization in snapshot.subject_organizations:
                path = (snapshot.resource_organization,)
        elif requirement.organization_scope == 'RESOURCE_ANCESTOR':
            path, exhausted = _path(snapshot.organization_parents, snapshot.subject_organizations,
                snapshot.resource_organization, requirement.max_depth)
        else:
            for organization in snapshot.subject_organizations:
                found, beyond = _path(snapshot.organization_parents, (snapshot.resource_organization,),
                    organization, requirement.max_depth)
                exhausted |= beyond
                if found:
                    path = found
                    break
        states.add('ACTIVE' if path else 'ABSENT')
    elif requirement.kind == 'ROLE_INHERITANCE':
        path, exhausted = _path(snapshot.role_inheritance, snapshot.subject_roles,
            requirement.inherited_role, requirement.max_depth)
        states.add('ACTIVE' if path else 'ABSENT')
    else:
        at = snapshot.observed_at_us if snapshot.source_time_us is None else snapshot.source_time_us
        if abs(at-snapshot.observed_at_us)>5_000_000+snapshot.clock_uncertainty_us:
            return result('UNKNOWN','RELATIONSHIP_TIME_UNCERTAIN')
        # 样本取得与本次观察之间跨过时效边界时，不能沿用较早时刻的有效关系。
        lower = min(at,snapshot.observed_at_us) - snapshot.clock_uncertainty_us
        upper = max(at,snapshot.observed_at_us) + snapshot.clock_uncertainty_us
        for grant in snapshot.grants:
            if (grant.kind != requirement.kind
                    or grant.grantor_id != snapshot.owner_id or grant.resource_id != snapshot.resource_id
                    or snapshot.action not in grant.actions):
                continue
            if grant.grantee_kind=='GROUP':
                if snapshot.subject_groups is None:return result('UNKNOWN','RELATIONSHIP_SCOPE_INCOMPLETE')
                if grant.grantee_id not in snapshot.subject_groups:continue
            elif grant.grantee_id!=snapshot.subject_id:
                continue
            boundaries = (grant.valid_from_us, grant.valid_until_us, grant.revoked_at_us)
            if any(value is not None and lower < value <= upper for value in boundaries):
                return result('UNKNOWN', 'RELATIONSHIP_TIME_UNCERTAIN')
            if lower < grant.valid_from_us:
                continue
            state = ('REVOKED' if grant.revoked_at_us is not None and lower >= grant.revoked_at_us
                else 'EXPIRED' if grant.valid_until_us is not None and lower >= grant.valid_until_us else 'ACTIVE')
            states.add(state)
            if state == requirement.state:
                path = (grant.grantor_id,grant.grantee_id,snapshot.subject_id) if grant.grantee_kind=='GROUP' else (grant.grantor_id, grant.grantee_id)
        if not states:
            states.add('ABSENT')
        # 仍有有效授权时，旧的过期/撤销记录不能证明当前授权已失效。
        if 'ACTIVE' in states and requirement.state in {'REVOKED', 'EXPIRED', 'ABSENT'}:
            states = {'ACTIVE'}
        elif 'ACTIVE' not in states and len(states) > 1:
            return result('UNKNOWN', 'RELATIONSHIP_SCOPE_INCOMPLETE')
    if exhausted and not path:
        return result('UNKNOWN', 'RELATIONSHIP_DEPTH_EXCEEDED')
    matched = requirement.state in states
    return result('MATCH' if matched else 'MISMATCH',
        'RELATIONSHIP_MATCHED' if matched else 'RELATIONSHIP_NOT_MATCHED', path if matched else ())
