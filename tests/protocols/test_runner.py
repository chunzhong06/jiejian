from __future__ import annotations

import json

import pytest

from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.backend.core.errors import JiejianError
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect, TargetType
from product.protocols import (
    CleanupResult,
    CleanupStatus,
    RunnerResult,
    RunnerResultType,
    build_evidence,
    canonical_runner_json_bytes,
    canonical_runner_sha256,
    parse_runner_result,
    parse_runner_input,
)
from tests.fixtures.runner import evidence, runner_input


pytestmark = pytest.mark.essential


def test_current_runner_input_round_trips_with_web_target_and_execution_binding() -> None:
    document = runner_input()
    raw = canonical_runner_json_bytes(document)
    assert parse_runner_input(raw) == document
    assert document.project_snapshot.target_type is TargetType.WEB
    assert canonical_runner_sha256(document) == canonical_runner_sha256(parse_runner_input(raw))


def test_current_evidence_carries_execution_and_observation_facts() -> None:
    current_evidence = evidence()
    assert current_evidence.execution_fact.outcome is ExecutionOutcome.ACCEPTED
    assert current_evidence.observation_facts[0].effect is ObservedEffect.CONFIRMED


def test_incomplete_observation_requires_inconclusive_verdict() -> None:
    current_evidence = evidence(available=False, verdict=CaseVerdict.INCONCLUSIVE)
    assert current_evidence.verdict is CaseVerdict.INCONCLUSIVE


def test_evidence_rejects_missing_observation_fact_coverage() -> None:
    raw = evidence().model_dump(mode="python")
    raw.pop("evidence_id")
    raw.pop("evidence_hash")
    raw["observation_facts"] = ()
    with pytest.raises(ValueError, match="exactly cover"):
        build_evidence(**raw)


def test_runner_result_root_and_cleanup_completion_contract_are_current() -> None:
    assert RunnerResult.model_fields["schema_version"].default == "3"
    assert CleanupResult(status=CleanupStatus.NOT_REQUIRED).finished_at_us is None
    assert CleanupResult(status=CleanupStatus.SUCCEEDED, finished_at_us=10).finished_at_us == 10
    assert CleanupResult(
        status=CleanupStatus.FAILED,
        finished_at_us=11,
        reason_codes=("CLEANUP_FAILED",),
    ).reason_codes == ("CLEANUP_FAILED",)
    with pytest.raises(ValueError):
        CleanupResult(status=CleanupStatus.NOT_REQUIRED, finished_at_us=10)
    with pytest.raises(ValueError):
        CleanupResult(status=CleanupStatus.FAILED, finished_at_us=11, reason_codes=("OTHER",))


def test_runner_result_parser_accepts_only_root_version_three_and_closes_windows() -> None:
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
    assert parse_runner_result(raw).schema_version == "3"
    old = json.loads(raw)
    old["schema_version"] = "2"
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
