# 验证 Runner codec、Schema 版本、canonical 与严格解析边界。

from __future__ import annotations
import json
from pathlib import Path
import pytest
from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.backend.core.errors import JiejianError
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect, TargetType
from product.protocols import (
    CleanupResult,
    CleanupIssue,
    CleanupIssueCode,
    CleanupStatus,
    Evidence,
    PreparedCookieCredential,
    PreparedCookieSessionIdentityBinding,
    RunnerInput,
    RunnerFailurePhase,
    RunnerResult,
    RunnerResultType,
    WebExecutionIdentity,
    build_evidence,
    canonical_runner_json_bytes,
    canonical_runner_sha256,
    parse_runner_result,
    parse_runner_input,
)
from product.protocols.runner.result import _reject_secret_material
from tests.fixtures.runner import evidence, runner_input
pytestmark = pytest.mark.essential

def test_checked_in_runner_schemas_have_no_drift() -> None:
    schema_root = Path(__file__).parents[3] / "product/protocols/schemas/runner"
    for filename, model in (
        ("runner-input.schema.json", RunnerInput),
        ("evidence.schema.json", Evidence),
        ("runner-result.schema.json", RunnerResult),
    ):
        assert json.loads((schema_root / filename).read_text(encoding="utf-8")) == (
            model.model_json_schema()
        )

def test_runner_result_parser_accepts_only_root_version_five_and_closes_windows() -> None:
    current_evidence = evidence()
    snapshot = runner_input().project_snapshot
    result = RunnerResult(
        run_id=runner_input().run_id,
        job_id="job_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        attempt=1,
        lease_owner="runner-protocol-test",
        fencing_token=1,
        finished_at_us=10,
        result_type=RunnerResultType.SUCCESS,
        run_lifecycle=RunLifecycle.COMPLETED,
        job_state=JobState.SUCCEEDED,
        verdict=RunVerdict.PASS,
        reason_codes=(),
        cleanup=CleanupResult(status=CleanupStatus.SUCCEEDED, finished_at_us=9),
        error=None,
        plan_fingerprint=snapshot.plan.plan_fingerprint,
        coverage_record_count=len(snapshot.plan.coverage),
        coverage_gap_count=0,
        evidence=(current_evidence,),
        artifacts=(),
    )
    raw = canonical_runner_json_bytes(result)
    assert parse_runner_result(raw).schema_version == "1"
    old = json.loads(raw)
    old["schema_version"] = "4"
    with pytest.raises(JiejianError):
        parse_runner_result(json.dumps(old, separators=(",", ":")).encode())
    missing = json.loads(raw)
    missing.pop("schema_version")
    with pytest.raises(JiejianError):
        parse_runner_result(json.dumps(missing, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="observation window"):
        RunnerResult.model_validate({
            **result.model_dump(mode="python"),
            "finished_at_us": 1,
            "cleanup": CleanupResult(status=CleanupStatus.SUCCEEDED, finished_at_us=1),
        })
