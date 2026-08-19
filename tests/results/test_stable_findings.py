from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from product.backend.core.lifecycle import CaseVerdict, JobState, ProjectStatus, RunLifecycle, RunVerdict
from product.protocols import (
    CleanupResult,
    CleanupStatus,
    RunnerResultType,
    RunnerResult,
)
from product.backend.workflows.results.findings import FindingProjection, finding_inputs
from product.backend.infra.storage import (
    ProjectRecord,
    RunRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)
from tests.execution.protocol.test_runner import _evidence, _input, _rehash_evidence


PROJECT_ID = "runner-project"
RUN_ONE = "run_11111111111111111111111111111111"
RUN_TWO = "run_22222222222222222222222222222222"


def _view(run_id: str, result: RunnerResult):
    return SimpleNamespace(
        run=SimpleNamespace(
            project_id=PROJECT_ID,
            run_id=run_id,
            finished_at_us=100 if run_id == RUN_ONE else 200,
            updated_at_us=100 if run_id == RUN_ONE else 200,
        ),
        publication=SimpleNamespace(result=result),
        evidence=(),
    )


def _result(run_id: str, evidence):
    snapshot = _input().project_snapshot
    return RunnerResult(
        schema_version="2",
        run_id=run_id,
        job_id="job_" + run_id[4:],
        attempt=1,
        lease_owner="finding-test",
        fencing_token=1,
        finished_at_us=100 if run_id == RUN_ONE else 200,
        result_type=RunnerResultType.SUCCESS,
        run_lifecycle=RunLifecycle.COMPLETED,
        job_state=JobState.SUCCEEDED,
        verdict=RunVerdict.BLOCK if evidence.verdict.value == "VULNERABLE" else RunVerdict.PASS,
        reason_codes=(),
        cleanup=CleanupResult(schema_version="2", status=CleanupStatus.SUCCEEDED),
        error=None,
        plan_fingerprint=snapshot.plan.plan_fingerprint,
        coverage_record_count=len(snapshot.plan.coverage),
        coverage_gap_count=0,
        evidence=(evidence,),
        artifacts=(),
    )


def test_published_current_result_projects_to_a_stable_finding_input() -> None:
    evidence = _evidence()
    result = _result("run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", evidence)
    view = _view(result.run_id, result)
    reader = SimpleNamespace(request_snapshot=lambda _view: _input().project_snapshot)
    inputs = finding_inputs(reader, view)
    assert len(inputs) == 1
    assert inputs[0].evidence_id == evidence.evidence_id
    assert inputs[0].verdict.value == "SAFE"


def test_two_published_runs_materialize_appeared_and_disappeared_occurrences(tmp_path: Path) -> None:
    database = tmp_path / "findings.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    try:
        with StorageUnitOfWork(factory) as work:
            work.projects.add(ProjectRecord(
                project_id=PROJECT_ID,
                name="Finding test",
                status=ProjectStatus.READY,
                created_at_us=1,
                updated_at_us=1,
            ))
            for run_id, verdict, timestamp in (
                (RUN_ONE, RunVerdict.BLOCK, 100),
                (RUN_TWO, RunVerdict.PASS, 200),
            ):
                work.runs.add(RunRecord(
                    run_id=run_id,
                    project_id=PROJECT_ID,
                    contract_id="runner-contract",
                    contract_version=1,
                    engine_version="runner-v2-test",
                    lifecycle=RunLifecycle.COMPLETED,
                    verdict=verdict,
                    created_at_us=timestamp,
                    updated_at_us=timestamp,
                    finished_at_us=timestamp,
                ))
            work.commit()

        first_evidence = _evidence(verdict=CaseVerdict.VULNERABLE)
        first_raw = first_evidence.model_dump(mode="python")
        first_raw["run_id"] = RUN_ONE
        first_evidence = type(first_evidence)(**_rehash_evidence(first_raw))
        second_raw = first_evidence.model_dump(mode="python")
        second_raw["run_id"] = RUN_TWO
        second_raw["verdict"] = CaseVerdict.SAFE
        second_evidence = type(first_evidence)(**_rehash_evidence(second_raw))
        views = {
            RUN_ONE: _view(RUN_ONE, _result(RUN_ONE, first_evidence)),
            RUN_TWO: _view(RUN_TWO, _result(RUN_TWO, second_evidence)),
        }
        reader = SimpleNamespace(
            read=lambda run_id: views[run_id],
            request_snapshot=lambda _view: _input().project_snapshot,
        )
        service = FindingProjection(lambda: StorageUnitOfWork(factory), reader)

        first = service.findings_for_run(RUN_ONE)
        second = service.findings_for_run(RUN_TWO)
        assert first[0]["occurrence"]["status"] == "APPEARED"
        assert first[0]["occurrence"]["evidence_refs"] == [first_evidence.evidence_id]
        assert second[0]["finding"]["finding_id"] == first[0]["finding"]["finding_id"]
        assert second[0]["occurrence"]["status"] == "DISAPPEARED"
        assert second[0]["occurrence"]["evidence_refs"] == [second_evidence.evidence_id]
        repeated = service.findings_for_run(RUN_ONE)
        assert repeated[0]["finding"]["finding_id"] == first[0]["finding"]["finding_id"]
        assert repeated[0]["occurrence"] == first[0]["occurrence"]
    finally:
        engine.dispose()
