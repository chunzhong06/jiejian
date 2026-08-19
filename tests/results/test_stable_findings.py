from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from jiejian.domain.lifecycle import CaseVerdict, JobState, ProjectStatus, RunLifecycle, RunVerdict
from jiejian.protocols import (
    CleanupResultV2,
    CleanupStatusV2,
    RunnerResultTypeV2,
    RunnerResultV2,
)
from jiejian.results.stable_findings import FindingApplicationService, finding_inputs
from jiejian.storage import (
    ProjectRecord,
    RunRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)
from tests.execution.protocol.test_runner_v2 import _evidence, _input, _rehash_evidence


PROJECT_ID = "runner-project"
RUN_ONE = "run_11111111111111111111111111111111"
RUN_TWO = "run_22222222222222222222222222222222"


def _view(run_id: str, result: RunnerResultV2):
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
    return RunnerResultV2(
        schema_version="2",
        run_id=run_id,
        job_id="job_" + run_id[4:],
        attempt=1,
        lease_owner="finding-test",
        fencing_token=1,
        finished_at_us=100 if run_id == RUN_ONE else 200,
        result_type=RunnerResultTypeV2.SUCCESS,
        run_lifecycle=RunLifecycle.COMPLETED,
        job_state=JobState.SUCCEEDED,
        verdict=RunVerdict.BLOCK if evidence.verdict.value == "VULNERABLE" else RunVerdict.PASS,
        reason_codes=(),
        cleanup=CleanupResultV2(schema_version="2", status=CleanupStatusV2.SUCCEEDED),
        error=None,
        plan_fingerprint=snapshot.plan.plan_fingerprint,
        coverage_record_count=len(snapshot.plan.coverage),
        coverage_gap_count=0,
        evidence=(evidence,),
        artifacts=(),
    )


def test_v1_v2_finding_input_dispatch_uses_published_result_version() -> None:
    v2_evidence = _evidence()
    v2_result = _result("run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", v2_evidence)
    v2_view = _view(v2_result.run_id, v2_result)
    v2_reader = SimpleNamespace(request_snapshot=lambda _view: _input().project_snapshot)
    v2_inputs = finding_inputs(v2_reader, v2_view)
    assert len(v2_inputs) == 1
    assert v2_inputs[0].evidence_id == v2_evidence.evidence_id
    assert v2_inputs[0].verdict.value == "SAFE"

    v1_reader = SimpleNamespace()
    v1_view = SimpleNamespace(
        publication=SimpleNamespace(result=SimpleNamespace()),
    )
    # The V1 branch is selected by the concrete published result type; the
    # V1 artifact reader remains the only source of its Evidence body.
    from tests.execution.protocol.test_runner_v1 import _runner_result
    from jiejian.protocols import RunnerResultV1

    v1_result = _runner_result()
    assert isinstance(v1_result, RunnerResultV1)
    v1_view.publication.result = v1_result
    v1_view.evidence = ()
    assert finding_inputs(v1_reader, v1_view) == ()


def test_v1_published_evidence_projects_to_a_stable_finding_input(
    stage1_project_factory,
    stage23_request_factory,
) -> None:
    from jiejian.verification.planning import build_mutation_plan
    from tests.execution.protocol.test_runner_v1 import _runner_result

    project_path = stage1_project_factory(8765)
    request = stage23_request_factory(project_path)
    snapshot = request.project_snapshot
    plan = build_mutation_plan(
        snapshot.identities,
        snapshot.resources,
        snapshot.flow,
        snapshot.contract,
        seed=snapshot.mutation_seed,
    )
    case = plan.cases[0]
    result = _runner_result()
    evidence_id = "ev_" + "a" * 20
    view = SimpleNamespace(
        run=SimpleNamespace(project_id=snapshot.project_id, run_id=result.run_id),
        publication=SimpleNamespace(result=result),
        evidence=(SimpleNamespace(evidence_id=evidence_id, case_id=case.case_id),),
    )
    reader = SimpleNamespace(
        request_snapshot=lambda _view: snapshot,
        document=lambda _view, _path: {"cases": [case.model_dump(mode="json")]},
        evidence_document=lambda _view, _evidence_id: {"verdict": "VULNERABLE"},
    )

    inputs = finding_inputs(reader, view)
    assert len(inputs) == 1
    assert inputs[0].evidence_id == evidence_id
    assert inputs[0].identity.finding_id().startswith("finding_")


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
        service = FindingApplicationService(lambda: StorageUnitOfWork(factory), reader)

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
