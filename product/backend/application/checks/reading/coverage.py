"""从同次已验证包解释实际样本；覆盖说明不修改 Case、Run 或执行门禁。"""
from product.protocols.checks.execution_request import PermissionReference, WireModel
from product.protocols.checks.conditions import ObservedPermissionConditions


class CoverageSample(WireModel):
    case_id: str
    resource_id: str
    subject_identity_id: str | None
    case_verdict: str
    conditions: tuple[ObservedPermissionConditions, ...]
    evidence_refs: tuple[str, ...]


class RequirementCoverage(WireModel):
    permission: PermissionReference
    applicable_states: tuple[str, ...]
    observed_states: tuple[str, ...]
    concluded_states: tuple[str, ...]
    unchecked_states: tuple[str, ...]
    unknown_case_ids: tuple[str, ...]
    samples: tuple[CoverageSample, ...]


def sample_coverage(package):
    """只枚举规则明确声明的状态，不将单维成员出现解释为全部交叉组合覆盖。"""
    results = {item.case_id: item for item in package.result.case_results}
    evidence = {item.evidence_id:item for item in package.evidence}
    groups = {}
    for action in package.request.actions:
        for case in action.cases:
            permission = case.permission
            key = (permission.intent_id, permission.revision, permission.intent_hash)
            group = groups.setdefault(key, dict(permission=PermissionReference(
                intent_id=key[0], revision=key[1], intent_hash=key[2]),
                applicable_states=() if permission.conditions is None else permission.conditions.resource_states,
                samples=[]))
            result = results[case.case_id]
            documents=tuple(evidence[ref] for ref in result.evidence_ids)
            observed_case=documents[0].effective_case if documents else case
            created={fact.data.resource_id for document in documents for fact in document.business_facts
                if fact.data.kind=='OBJECT_CREATION'}
            group['samples'].append(CoverageSample(case_id=case.case_id, resource_id='、'.join(sorted(created)) or observed_case.resource_id,
                subject_identity_id=case.subject_test_identity_id, case_verdict=result.verdict.value,
                conditions=result.outcome.condition_observations, evidence_refs=result.evidence_ids))
    coverage = []
    for group in groups.values():
        samples, expected = group['samples'], group['applicable_states']
        observed = {item.resource_state for sample in samples for item in sample.conditions if item.resource_state is not None}
        concluded = {item.resource_state for sample in samples if sample.case_verdict in {'SAFE', 'VULNERABLE'}
            for item in sample.conditions if item.resource_state is not None}
        coverage.append(RequirementCoverage(permission=group['permission'], applicable_states=expected,
            observed_states=tuple(sorted(observed)), concluded_states=tuple(sorted(concluded)),
            unchecked_states=tuple(state for state in expected if state not in concluded),
            unknown_case_ids=tuple(sample.case_id for sample in samples if expected and
                (not sample.conditions or any(item.resource_state is None for item in sample.conditions))),
            samples=tuple(samples)))
    return tuple(coverage)
