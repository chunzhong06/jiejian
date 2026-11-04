"""比较独立所有者查询与真实目标响应；仅封存摘要，不推断写入历史。"""
import hashlib
import hmac
import json

from product.backend.infrastructure.observers.checks.models import CheckObservedSource
from product.protocols.checks.check_result import CheckObservation


def selected(value, path):
    for part in path.removeprefix('$').removeprefix('.').split('.') if path != '$' else ():
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def entity_fields(data, paths, key):
    values = {}
    for path in paths:
        value = selected(data, '$.' + path)
        if value is None or value in ('[REDACTED]', '<redacted>'):
            continue
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        values[path] = hmac.new(key, raw, hashlib.sha256).hexdigest()
    return values


def observe_http_entity(owner, *, case, action_id, proof, phase, common, source_identity, cleanup):
    query = proof.entity_query
    key = (case.case_id, proof.binding_fingerprint)
    response = owner.web.request(query.request, case=case, action_id=action_id,
        identity_id=case.resource_owner_test_identity_id, cleanup=cleanup)
    identity = next((item for item in owner.bundle.identities if item.identity_id == case.resource_owner_test_identity_id), None)
    expected_owner = identity.verification.expected_application_subject_id if identity is not None and identity.verification is not None else None
    resource, actual_owner = selected(response.data, query.resource_path), selected(response.data, query.owner_path)
    fields = entity_fields(selected(response.data, query.data_path), proof.protected_projection, owner._disclosure_key)
    valid = (source_identity == 'MATCH' and expected_owner is not None and type(resource) in (str, int)
        and str(resource) == case.resource_id and actual_owner == expected_owner and 200 <= response.status_code < 300
        and len(fields) == len(proof.protected_projection))
    projection = (case.resource_id, expected_owner, tuple(sorted(fields.items()))) if valid else None
    if phase in ('BASELINE', 'BEFORE'):
        owner._http_entities[key] = projection
        observation = CheckObservation(**common, state='CONFIRMED' if valid else 'UNKNOWN',
            closure='CLOSED' if valid else 'OPEN', complete=valid, reliable=source_identity=='MATCH',
            correlated=valid, authoritative=True, window_end_us=owner.clock(),
            correlation_refs=(case.case_id,owner.web.request_marker(case.case_id)), reason_codes=() if valid else ('HTTP_ENTITY_BASELINE_UNAVAILABLE',))
        return CheckObservedSource(observation, projection)
    before = owner._http_entities.get(key)
    stable = valid and before is not None and before == projection
    target = owner.web.target_response(case.case_id)
    matched, state, complete = (), 'UNKNOWN', False
    if target is not None and before is not None:
        target_fields = entity_fields(selected(target.data, query.data_path), proof.protected_projection, owner._disclosure_key)
        baseline = dict(before[2])
        same_resource = (str(selected(target.data, query.resource_path)) == case.resource_id
            and selected(target.data, query.owner_path) == before[1])
        matched = tuple(path for path in proof.protected_projection if path in target_fields
            and hmac.compare_digest(target_fields[path], baseline[path])) if same_resource else ()
        # 已确认披露不被之后的资源变化覆盖；缺席和正常对照则需要完整、稳定的比较。
        if matched and (case.permission.expectation == 'DENY' or len(matched) == len(proof.protected_projection)):
            state, complete = 'CONFIRMED', True
        elif stable and not target_fields and (same_resource or target.status_code in (401,403)
                and isinstance(target.data, dict) and set(target.data) <= {'error','message'}):
            state, complete = 'ABSENT', True
    digest = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest() if before else None
    references = (case.case_id,owner.web.request_marker(case.case_id)) + (('entity-baseline:' + digest,) if digest else ()) + tuple('field:' + path for path in matched)
    observation = CheckObservation(**common, state=state, closure='CLOSED' if complete else 'OPEN',
        complete=complete, reliable=source_identity=='MATCH', correlated=before is not None and target is not None,
        authoritative=True, window_end_us=owner.clock(), correlation_refs=references,
        reason_codes=() if complete else ('HTTP_ENTITY_COMPARISON_INCOMPLETE',))
    return CheckObservedSource(observation, projection)
