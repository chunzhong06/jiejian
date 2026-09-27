# 验证结果工作流中的稳定发现生成。

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from product.backend.core.lifecycle import CaseVerdict, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.workflows.reports.findings import FindingMaterializer, FindingQueries, finding_inputs
from product.backend.infra.artifacts.run_publication import publication_manifest_sha256
from product.backend.infra.storage import (
    ProjectRecord,
    RunRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)
from tests.fixtures.runner import evidence, rehash_evidence, runner_input
from tests.backend.workflows.reports._support_stable_findings import PROJECT_ID, RUN_ONE, _result, _view


RUN_TWO = "run_22222222222222222222222222222222"






def test_published_current_result_projects_to_a_stable_finding_input() -> None:
    current_evidence = evidence()
    result = _result("run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", current_evidence)
    view = _view(result.run_id, result)
    reader = SimpleNamespace(request_snapshot=lambda _view: runner_input().project_snapshot)
    inputs = finding_inputs(reader, view)
    assert len(inputs) == 1
    assert inputs[0].evidence_id == current_evidence.evidence_id
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
                    policy_epoch=0,
                    plan_fingerprint="a" * 64,
                    source_fingerprint="b" * 64,
                    request_hash="c" * 64,
                    engine_version="runner-test",
                    lifecycle=RunLifecycle.COMPLETED,
                    verdict=verdict,
                    created_at_us=timestamp,
                    updated_at_us=timestamp,
                    finished_at_us=timestamp,
                ))
            work.commit()

        first_evidence = evidence(verdict=CaseVerdict.VULNERABLE)
        first_raw = first_evidence.model_dump(mode="python")
        first_raw["run_id"] = RUN_ONE
        first_evidence = type(first_evidence)(**rehash_evidence(first_raw))
        second_raw = first_evidence.model_dump(mode="python")
        second_raw["run_id"] = RUN_TWO
        second_raw["verdict"] = CaseVerdict.SAFE
        second_evidence = type(first_evidence)(**rehash_evidence(second_raw))
        views = {
            RUN_ONE: _view(RUN_ONE, _result(RUN_ONE, first_evidence)),
            RUN_TWO: _view(RUN_TWO, _result(RUN_TWO, second_evidence)),
        }
        reader = SimpleNamespace(
            read=lambda run_id: views[run_id],
            request_snapshot=lambda _view: runner_input().project_snapshot,
        )
        materializer = FindingMaterializer(lambda: StorageUnitOfWork(factory), reader)
        for view in views.values():
            with StorageUnitOfWork(factory) as work:
                materializer_sha = publication_manifest_sha256(view.publication.manifest)
                work.finalizations.ensure_initial(view.run.run_id, materializer_sha, view.run.finished_at_us)
                work.commit()
            materializer.materialize(view)
        queries = FindingQueries(lambda: StorageUnitOfWork(factory))

        first = queries.findings_for_run(RUN_ONE)
        second = queries.findings_for_run(RUN_TWO)
        assert first[0]["occurrence"]["status"] == "APPEARED"
        assert first[0]["occurrence"]["evidence_refs"] == [first_evidence.evidence_id]
        assert second[0]["finding"]["finding_id"] == first[0]["finding"]["finding_id"]
        assert second[0]["occurrence"]["status"] == "DISAPPEARED"
        assert second[0]["occurrence"]["evidence_refs"] == [second_evidence.evidence_id]
        repeated = queries.findings_for_run(RUN_ONE)
        assert repeated[0]["finding"]["finding_id"] == first[0]["finding"]["finding_id"]
        assert repeated[0]["occurrence"] == first[0]["occurrence"]
    finally:
        engine.dispose()
