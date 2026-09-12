# 验证当前检查独立根的内容地址、fence 身份、严格解析和安全停止语义。
import json

import pytest
from pydantic import ValidationError

from product.backend.core.lifecycle import CaseVerdict, RunLifecycle, RunVerdict
from product.protocols.check_result import (
    CheckAssetReference, CheckCaseOutcome, CheckCaseResult, CheckEvidence, CheckRunnerInput,
    CheckRunnerResult, CheckResultProtocolError, canonical_check_document, parse_check_document, seal_check_evidence,
)
from product.protocols.execution_v3 import ExecutionCase
from tests.fixtures.check_plan import plan


def input_document():
    return CheckRunnerInput(run_id="run_" + "1" * 32, job_id="job_" + "2" * 32, attempt=1,
        lease_owner="worker-1", fencing_token=1, created_at_us=1, request_hash="a" * 64, config_hash="b" * 64,
        assets=(CheckAssetReference(logical_id="request", sha256="a" * 64),
            CheckAssetReference(logical_id="runtime", sha256="b" * 64)))


def evidence_document():
    action = plan().actions[0]
    case = ExecutionCase.model_validate_json(action.cases[0].model_dump_json())
    return seal_check_evidence(run_id="run_" + "1" * 32, job_id="job_" + "2" * 32, attempt=1,
        action_id=action.action_id, action_revision=action.action_revision, request_hash="a" * 64,
        config_hash="b" * 64, case=case, outcome=CheckCaseOutcome(execution_outcome="UNKNOWN",
            actual_identity_status="UNKNOWN", baseline_trusted=False, recovery_verified=False,
            run_correlated=False, resource_correlated=False), observations=())


def result_document():
    evidence = evidence_document()
    return CheckRunnerResult(run_id=evidence.run_id, job_id=evidence.job_id, attempt=1, lease_owner="worker-1",
        fencing_token=1, request_hash=evidence.request_hash, config_hash=evidence.config_hash,
        result_type="SUCCESS", lifecycle=RunLifecycle.COMPLETED, verdict=RunVerdict.INCONCLUSIVE,
        started_at_us=1, completed_at_us=2,
        case_results=(CheckCaseResult(case_id=evidence.case.case_id, action_id=evidence.action_id,
            verdict=CaseVerdict.INCONCLUSIVE, reason_codes=("ACTUAL_IDENTITY_UNKNOWN",),
            evidence_ids=(evidence.evidence_id,), outcome=evidence.outcome),))


@pytest.mark.parametrize("build", [input_document, evidence_document, result_document])
def test_check_root_roundtrip(build):
    document = build()
    assert parse_check_document(canonical_check_document(document), type(document)) == document


@pytest.mark.parametrize("build", [input_document, evidence_document, result_document])
@pytest.mark.parametrize("mutate", [
    lambda raw: raw + b"\n", lambda raw: b"\xef\xbb\xbf" + raw,
    lambda raw: raw.replace(b'"attempt":1', b'"attempt":1,"attempt":1'),
    lambda raw: raw.replace(b'"schema_version":"1"', b'"schema_version":"9"', 1),
    lambda raw: raw.replace(b'"attempt":1', b'"attempt":NaN'),
    lambda raw: raw[:-1] + b',"unknown":true}',
])
def test_check_roots_reject_invalid_bytes(build, mutate):
    document = build()
    with pytest.raises(CheckResultProtocolError):
        parse_check_document(mutate(canonical_check_document(document)), type(document))


def test_evidence_tampering_changes_content_identity():
    document = evidence_document()
    payload = document.model_dump(mode="json")
    payload["outcome"]["actual_identity_status"] = "MATCH"
    with pytest.raises(ValidationError, match="content address"):
        CheckEvidence.model_validate_json(json.dumps(payload))


def test_input_assets_cannot_swap_request_and_configuration():
    document = input_document()
    with pytest.raises(CheckResultProtocolError):
        canonical_check_document(document.model_copy(update={"request_hash": "b" * 64}))


@pytest.mark.parametrize("changes", [
    {"result_type": "SAFETY_STOPPED", "lifecycle": "SAFETY_STOPPED", "verdict": "PASS"},
    {"result_type": "FAILED", "lifecycle": "FAILED", "verdict": "BLOCK"},
    {"result_type": "SUCCESS", "verdict": None},
    {"completed_at_us": 0},
])
def test_result_lifecycle_and_time_are_strict(changes):
    payload = result_document().model_dump(mode="json") | changes
    with pytest.raises(ValidationError):
        CheckRunnerResult.model_validate_json(json.dumps(payload))
