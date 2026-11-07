"""从已核验主体和独立资源快照投影关系；原始关系集合只存在于 Runner 内。"""
import json

from product.backend.infrastructure.observers.records.record_facts import record_value
from product.protocols.checks.relationships import RelationshipSnapshot, observe_relationship


def collect_relationship_conditions(*, requirements, mapping, identity, resource, subject_id,
                                    owner_id, resource_id, observed_at_us,sql_values=False):
    if mapping is None or not requirements:
        return ()
    output = []
    for requirement in requirements:
        if not mapping.supports(requirement):
            continue
        values = dict(subject_id=subject_id, owner_id=owner_id, resource_id=resource_id,
            action=mapping.application_action, observed_at_us=observed_at_us,
            clock_uncertainty_us=mapping.clock_uncertainty_us,
            scope_complete=record_value(resource,mapping.scope_complete_path))
        if requirement.kind in {'SHARING','DELEGATION'}:
            values['source_time_us']=record_value(resource,mapping.source_time_path)
            if type(values['source_time_us']) is not int:
                raise ValueError('relationship grants require their independent sample time')
            if mapping.subject_groups_path is not None:
                values['subject_groups']=record_value(identity,mapping.subject_groups_path)
        fields = ({'subject_organizations': (identity, mapping.subject_organizations_path),
            'resource_organization': (resource, mapping.resource_organization_path)} if requirement.kind == 'ORGANIZATION'
            else {'subject_roles': (identity, mapping.subject_roles_path),
                'role_inheritance': (resource, mapping.role_inheritance_path)} if requirement.kind == 'ROLE_INHERITANCE'
            else {'grants': (resource, mapping.grants_path)})
        if requirement.kind == 'ORGANIZATION' and requirement.organization_scope != 'SAME':
            fields['organization_parents'] = (resource, mapping.organization_parents_path)
        for name, (document, path) in fields.items():
            values[name] = record_value(document, path)
            if sql_values and name in {'organization_parents','role_inheritance','grants'} and isinstance(values[name],str):
                # SQL 驱动可将 JSON 列作为文本返回；仅解码明确声明的关系数组。
                values[name]=json.loads(values[name])
        if sql_values and type(values['scope_complete']) is int and values['scope_complete'] in (0,1):
            values['scope_complete']=bool(values['scope_complete'])
        snapshot = RelationshipSnapshot.model_validate_json(json.dumps(values, allow_nan=False))
        output.append(observe_relationship(requirement, snapshot))
    return tuple(output)
