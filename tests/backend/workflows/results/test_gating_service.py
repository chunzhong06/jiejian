from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from product.backend.core.lifecycle import CaseVerdict, JobState, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import CleanupResult, CleanupStatus, ObserverOutcomeStatus, RunnerResultType, RunnerResult
from product.backend.workflows.results.gating import RegressionGate
from product.backend.infra.storage import ProjectRecord, RunRecord, StorageUnitOfWork, create_session_factory, create_sqlite_engine, upgrade_database
from tests.fixtures.runner import evidence as make_evidence, rehash_evidence, runner_input


PROJECT_ID = "project-gating"
FIXED_RUN = "run_" + "1" * 32
VULNERABLE_RUN = "run_" + "2" * 32
INITIAL_VULNERABLE_RUN = "run_" + "0" * 32
EXECUTION_ERROR_RUN = "run_" + "6" * 32
INCONCLUSIVE_RUN = "run_" + "7" * 32
OTHER_PROJECT_RUN = "run_" + "8" * 32
FINDING_ID = "finding_" + "3" * 32
OCCURRENCE_FIXED = "occ_" + "4" * 32
OCCURRENCE_VULNERABLE = "occ_" + "5" * 32


def _result(run_id: str, verdict: CaseVerdict, *, observer_status: ObserverOutcomeStatus | None = None) -> RunnerResult:
    evidence = make_evidence(verdict=verdict)
    if observer_status is not None:
        outcome = evidence.outcomes[0].model_copy(update={"status": observer_status, "reason_codes": (observer_status.value,)})
        evidence = evidence.model_copy(update={"outcomes": (outcome,)})
    evidence = type(evidence)(**rehash_evidence({**evidence.model_dump(mode="python"), "run_id": run_id}))
    snapshot = runner_input().project_snapshot
    run_verdict = RunVerdict.BLOCK if verdict is CaseVerdict.VULNERABLE else RunVerdict.INCONCLUSIVE if verdict is CaseVerdict.INCONCLUSIVE else RunVerdict.PASS
    return RunnerResult(
        schema_version="2",
        run_id=run_id,
        job_id="job_" + run_id[4:],
        attempt=1,
        lease_owner="gate-test",
        fencing_token=1,
        finished_at_us=100 if run_id == FIXED_RUN else 200,
        result_type=RunnerResultType.SUCCESS,
        run_lifecycle=RunLifecycle.COMPLETED,
        job_state=JobState.SUCCEEDED,
        verdict=run_verdict,
        reason_codes=(),
        cleanup=CleanupResult(schema_version="2", status=CleanupStatus.SUCCEEDED),
        error=None,
        plan_fingerprint=snapshot.plan.plan_fingerprint,
        coverage_record_count=len(snapshot.plan.coverage),
        coverage_gap_count=0,
        evidence=(evidence,),
        artifacts=(),
    )


def _finding(run_id: str, occurrence_id: str, evidence_id: str, status: str, verdict: str) -> dict:
    return {
        "schema_version": "2",
        "finding": {"finding_id": FINDING_ID, "project_id": PROJECT_ID},
        "occurrence": {
            "occurrence_id": occurrence_id,
            "finding_id": FINDING_ID,
            "project_id": PROJECT_ID,
            "run_id": run_id,
            "status": status,
            "verdict": verdict,
            "severity": "high",
            "evidence_refs": [evidence_id],
        },
    }


def test_vulnerable_fixed_vulnerable_reappears_and_gate_result_is_immutable(tmp_path: Path) -> None:
    database = tmp_path / "gating.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    try:
        with StorageUnitOfWork(factory) as work:
            work.projects.add(ProjectRecord(project_id=PROJECT_ID, name="Gating", status=ProjectStatus.READY, created_at_us=1, updated_at_us=1))
            work.projects.add(ProjectRecord(project_id="other-project", name="Other", status=ProjectStatus.READY, created_at_us=1, updated_at_us=1))
            for run_id, project_id, verdict, timestamp in (
                (INITIAL_VULNERABLE_RUN, PROJECT_ID, RunVerdict.BLOCK, 50),
                (FIXED_RUN, PROJECT_ID, RunVerdict.PASS, 100),
                (VULNERABLE_RUN, PROJECT_ID, RunVerdict.BLOCK, 200),
                (EXECUTION_ERROR_RUN, PROJECT_ID, RunVerdict.INCONCLUSIVE, 300),
                (INCONCLUSIVE_RUN, PROJECT_ID, RunVerdict.INCONCLUSIVE, 400),
                (OTHER_PROJECT_RUN, "other-project", RunVerdict.PASS, 500),
            ):
                work.runs.add(RunRecord(run_id=run_id, project_id=project_id, contract_id="contract", contract_version=1, engine_version="runner-v2", lifecycle=RunLifecycle.COMPLETED, verdict=verdict, created_at_us=timestamp, updated_at_us=timestamp, finished_at_us=timestamp))
            work.commit()
        snapshot = runner_input().project_snapshot
        results = {
            FIXED_RUN: SimpleNamespace(run_id=FIXED_RUN, publication=SimpleNamespace(result=_result(FIXED_RUN, CaseVerdict.SAFE)), run=SimpleNamespace(project_id=PROJECT_ID, run_id=FIXED_RUN, lifecycle=RunLifecycle.COMPLETED, verdict=RunVerdict.PASS, engine_version="runner-v2")),
            VULNERABLE_RUN: SimpleNamespace(run_id=VULNERABLE_RUN, publication=SimpleNamespace(result=_result(VULNERABLE_RUN, CaseVerdict.VULNERABLE)), run=SimpleNamespace(project_id=PROJECT_ID, run_id=VULNERABLE_RUN, lifecycle=RunLifecycle.COMPLETED, verdict=RunVerdict.BLOCK, engine_version="runner-v2")),
            EXECUTION_ERROR_RUN: SimpleNamespace(run_id=EXECUTION_ERROR_RUN, publication=SimpleNamespace(result=_result(EXECUTION_ERROR_RUN, CaseVerdict.INCONCLUSIVE, observer_status=ObserverOutcomeStatus.EXECUTION_ERROR)), run=SimpleNamespace(project_id=PROJECT_ID, run_id=EXECUTION_ERROR_RUN, lifecycle=RunLifecycle.COMPLETED, verdict=RunVerdict.INCONCLUSIVE, engine_version="runner-v2")),
            INCONCLUSIVE_RUN: SimpleNamespace(run_id=INCONCLUSIVE_RUN, publication=SimpleNamespace(result=_result(INCONCLUSIVE_RUN, CaseVerdict.INCONCLUSIVE, observer_status=ObserverOutcomeStatus.INCONCLUSIVE)), run=SimpleNamespace(project_id=PROJECT_ID, run_id=INCONCLUSIVE_RUN, lifecycle=RunLifecycle.COMPLETED, verdict=RunVerdict.INCONCLUSIVE, engine_version="runner-v2")),
            OTHER_PROJECT_RUN: SimpleNamespace(run_id=OTHER_PROJECT_RUN, publication=SimpleNamespace(result=_result(OTHER_PROJECT_RUN, CaseVerdict.SAFE)), run=SimpleNamespace(project_id="other-project", run_id=OTHER_PROJECT_RUN, lifecycle=RunLifecycle.COMPLETED, verdict=RunVerdict.PASS, engine_version="runner-v2")),
        }
        findings = {
            INITIAL_VULNERABLE_RUN: [_finding(INITIAL_VULNERABLE_RUN, "occ_" + "6" * 32, "ev_" + "9" * 20, "APPEARED", "VULNERABLE")],
            FIXED_RUN: [_finding(FIXED_RUN, OCCURRENCE_FIXED, "ev_" + "a" * 20, "DISAPPEARED", "SAFE")],
            VULNERABLE_RUN: [_finding(VULNERABLE_RUN, OCCURRENCE_VULNERABLE, "ev_" + "b" * 20, "REAPPEARED", "VULNERABLE")],
            EXECUTION_ERROR_RUN: [],
            INCONCLUSIVE_RUN: [],
            OTHER_PROJECT_RUN: [],
        }
        reader = SimpleNamespace(read=lambda run_id: results[run_id], request_snapshot=lambda _view: snapshot)
        finding_service = SimpleNamespace(findings_for_run=lambda run_id: findings[run_id])
        service = RegressionGate(lambda: StorageUnitOfWork(factory), reader, finding_service, clock_us=lambda: 999)
        assert findings[INITIAL_VULNERABLE_RUN][0]["occurrence"]["verdict"] == "VULNERABLE"
        baseline = service.accept_baseline(FIXED_RUN, actor="operator", reason="fixed run")
        assert service.accept_baseline(FIXED_RUN, actor="operator", reason="fixed run") == baseline
        with pytest.raises(JiejianError):
            service.accept_baseline(FIXED_RUN, actor="operator", reason="changed reason")
        first = service.evaluate(baseline["baseline_id"], VULNERABLE_RUN)
        second = service.evaluate(baseline["baseline_id"], VULNERABLE_RUN)
        assert first["decision"] == "BLOCK"
        assert "FINDING_REAPPEARED" in {item["code"] for item in first["reasons"]}
        assert second == first
        execution_error = service.evaluate(baseline["baseline_id"], EXECUTION_ERROR_RUN)
        assert execution_error["decision"] == "ERROR"
        assert "EXECUTION_ERROR" in {item["code"] for item in execution_error["reasons"]}
        inconclusive = service.evaluate(baseline["baseline_id"], INCONCLUSIVE_RUN)
        assert inconclusive["decision"] == "BLOCK"
        assert "REQUIRED_OBSERVER_INCOMPLETE" in {item["code"] for item in inconclusive["reasons"]}
        with pytest.raises(JiejianError) as mismatch:
            service.evaluate(baseline["baseline_id"], OTHER_PROJECT_RUN)
        assert mismatch.value.code == ErrorCode.GATE_INPUT_INVALID.value
        with StorageUnitOfWork(factory) as work:
            assert work.gating.latest_gate_result(baseline["baseline_id"], OTHER_PROJECT_RUN) is None
    finally:
        engine.dispose()
