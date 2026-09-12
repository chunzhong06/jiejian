# 验证独立 v3 快照闭包、严格 canonical 解析与冻结实验关联。
import hashlib
import json
import os
import subprocess
import sys
import pytest
from product.protocols.execution_v3 import PersistedExecutionRequestV3, ExecutionV3Error, canonical_execution_request_v3_bytes, parse_execution_request_v3
from tests.fixtures.check_plan import plan


def request():
    payload = plan().model_dump(mode="json", exclude={"gaps"})
    for action in payload["actions"]:
        action.pop("gaps")
    payload.update(config_fingerprint="c"*64, budget_fingerprint="d"*64)
    return PersistedExecutionRequestV3.model_validate_json(json.dumps(payload), strict=True)


def test_execution_v3_import_closure_has_no_backend():
    result = subprocess.run([sys.executable, "-B", "-c",
        "import sys; import product.protocols.execution_v3; assert not any(n.startswith('product.backend') for n in sys.modules)"],
        env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_canonical_roundtrip_and_sequence_order():
    source = request()
    raw = canonical_execution_request_v3_bytes(source)
    assert parse_execution_request_v3(raw) == source
    reordered = source.model_copy(update={"actions": (source.actions[0].model_copy(update={"cases": tuple(reversed(source.actions[0].cases))}),)})
    assert canonical_execution_request_v3_bytes(reordered) == raw
    changed = source.model_copy(update={"budget_fingerprint": "e"*64})
    assert hashlib.sha256(canonical_execution_request_v3_bytes(changed)).digest() != hashlib.sha256(raw).digest()


@pytest.mark.parametrize("mutation", [
    lambda raw: b"\xef\xbb\xbf"+raw,
    lambda raw: raw+b"\n",
    lambda raw: raw.replace(b'"schema_version":"3"', b'"schema_version":"2"'),
    lambda raw: raw.replace(b'"schema_version":"3"', b'"schema_version":"3","schema_version":"3"'),
    lambda raw: raw.replace(b'"policy_epoch":1', b'"policy_epoch":NaN'),
    lambda raw: raw[:-1]+b',"unknown":true}',
    lambda raw: b" "*1_048_577,
    lambda raw: raw.replace(b'"resource-1"', b'"C:/secret"'),
    lambda raw: raw.replace(b'"policy_epoch":1', b'"policy_epoch":2'),
])
def test_strict_parser_rejects_invalid_raw_without_echo(mutation):
    with pytest.raises(ExecutionV3Error) as caught:
        parse_execution_request_v3(mutation(canonical_execution_request_v3_bytes(request())))
    assert caught.value.code == "RUNNER_PROTOCOL_INVALID"
    assert str(caught.value) == "执行快照格式无效"


@pytest.mark.parametrize("mutation", [
    lambda a: a.update(twins=[]),
    lambda a: a["cases"].append(a["cases"][0]),
    lambda a: a["twins"][0].update(allow_case_id="case_"+"0"*32),
    lambda a: a["cases"][0].update(resource_owner_test_identity_id="tid_"+"f"*32),
    lambda a: a["cases"][0].update(resource_id="different-resource"),
])
def test_wire_rejects_broken_case_and_twin_references(mutation):
    payload = request().model_dump(mode="json")
    mutation(payload["actions"][0])
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ExecutionV3Error):
        parse_execution_request_v3(raw)


def repair_context(reference, regressions=('b' * 64,)):
    from product.protocols.execution_v3 import RepairContext
    case = request().actions[0].cases[0]
    permission = {key: getattr(case.permission, key) for key in ('intent_id', 'revision', 'intent_hash')}
    return RepairContext.model_validate_json(json.dumps(dict(
        repair_reference=reference, source_run_id='run_' + '1' * 32, original_policy_epoch=1,
        original_intents=[permission], selected_allow_permission=permission,
        resource_id=case.resource_id, resource_owner_test_identity_id=case.resource_owner_test_identity_id,
        owner_identity_fingerprint=case.owner_identity_fingerprint,
        must_disappear_effect_ids=list(case.protected_effect_ids),
        original_evidence_standard_fingerprints=['a' * 64], allow_regression_case_fingerprints=list(regressions),
    )), strict=True)


@pytest.mark.parametrize('reference', ['0' * 64, 'a' * 64, 'f' * 64])
def test_complete_repair_hash_roundtrips_without_widening_logical_ids(reference):
    from pydantic import TypeAdapter, ValidationError
    from product.protocols.execution_v3 import LogicalId
    context = repair_context(reference)
    source = request().model_copy(update={'repair_context': context})
    raw = canonical_execution_request_v3_bytes(source)
    assert parse_execution_request_v3(raw).repair_context.repair_reference == reference
    with pytest.raises(ValidationError):
        TypeAdapter(LogicalId).validate_python('repair_' + 'a' * 64, strict=True)


@pytest.mark.parametrize('reference', ['', 'a' * 63, 'a' * 65, 'A' * 64, 'repair_' + 'a' * 64, ' ' + 'a' * 63])
def test_repair_reference_rejects_truncated_prefixed_or_noncanonical_hash(reference):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        repair_context(reference)


def test_block_without_prior_safe_regression_keeps_explicit_control_in_new_request():
    from product.backend.core.lifecycle import CaseVerdict, RunVerdict
    from product.backend.core.verification.checks import aggregate_check_verdict
    assert aggregate_check_verdict((CaseVerdict.INCONCLUSIVE, CaseVerdict.VULNERABLE), planned_case_count=2) is RunVerdict.BLOCK
    context = repair_context('0' * 64, regressions=())
    source = request().model_copy(update={'repair_context': context})
    restored = parse_execution_request_v3(canonical_execution_request_v3_bytes(source)).repair_context
    assert restored.allow_regression_case_fingerprints == ()
    assert restored.selected_allow_permission == context.selected_allow_permission
    assert restored.must_disappear_effect_ids and restored.original_evidence_standard_fingerprints


@pytest.mark.parametrize('field,value', [
    ('original_intents', []), ('must_disappear_effect_ids', []),
    ('original_evidence_standard_fingerprints', []), ('selected_allow_permission', None),
    ('allow_regression_case_fingerprints', None),
])
def test_empty_regression_does_not_relax_other_required_repair_facts(field, value):
    from pydantic import ValidationError
    from product.protocols.execution_v3 import RepairContext
    payload = repair_context('a' * 64, regressions=()).model_dump(mode='json')
    payload[field] = value
    with pytest.raises(ValidationError):
        RepairContext.model_validate_json(json.dumps(payload), strict=True)
