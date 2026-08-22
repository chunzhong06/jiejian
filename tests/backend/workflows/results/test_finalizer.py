from __future__ import annotations

import hashlib
import json
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import CaseVerdict, JobState, ProjectStatus, RunLifecycle, RunVerdict
from product.backend.infra.artifacts.run_packages import PublicationManifest, StagedArtifact, ValidatedPublication
from product.backend.infra.artifacts.run_publication import publication_manifest_sha256
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process_lock import try_lock_stream, unlock_stream
from product.backend.infra.runtime.jobs.verification import VerificationRunJobHandler
from product.backend.infra.storage import (
    BaseReportFinalizationState,
    FindingFinalizationState,
    ProjectRecord,
    RunFinalizationRecord,
    RunRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)
from product.backend.workflows.results.finalizer import ResultFinalizer
from product.backend.workflows.results.findings import FindingMaterializer, FindingQueries
from product.backend.workflows.results.published import PublishedRunView
from product.protocols import CleanupResult, CleanupStatus, RunnerResult, RunnerResultType
from tests.fixtures.runner import evidence as make_evidence, rehash_evidence, runner_input


pytestmark = pytest.mark.database

PROJECT_ID = "result-finalizer-project"
RUN_ONE = "run_" + "1" * 32
RUN_TWO = "run_" + "2" * 32
RUN_THREE = "run_" + "3" * 32
RUN_FOUR = "run_" + "4" * 32


class _Reader:
    def __init__(self, views: dict[str, PublishedRunView]) -> None:
        self.views = views

    def read(self, run_id: str) -> PublishedRunView:
        return self.views[run_id]

    def request_snapshot(self, _view: PublishedRunView):
        return runner_input().project_snapshot


def _result(
    run_id: str,
    finished_at_us: int,
    verdict: CaseVerdict | None,
) -> RunnerResult:
    evidence = ()
    run_verdict = RunVerdict.INCONCLUSIVE
    coverage_gap_count = 1
    if verdict is not None:
        item = make_evidence(verdict=verdict)
        item = type(item)(**rehash_evidence({**item.model_dump(mode="python"), "run_id": run_id}))
        evidence = (item,)
        run_verdict = RunVerdict.BLOCK if verdict is CaseVerdict.VULNERABLE else RunVerdict.PASS
        coverage_gap_count = 0
    return RunnerResult(
        schema_version="3",
        run_id=run_id,
        job_id="job_" + run_id[4:],
        attempt=1,
        lease_owner="finalizer-test",
        fencing_token=1,
        finished_at_us=finished_at_us,
        result_type=RunnerResultType.SUCCESS,
        run_lifecycle=RunLifecycle.COMPLETED,
        job_state=JobState.SUCCEEDED,
        verdict=run_verdict,
        reason_codes=(),
        cleanup=CleanupResult(
            schema_version="2",
            status=CleanupStatus.SUCCEEDED,
            finished_at_us=finished_at_us,
        ),
        error=None,
        plan_fingerprint=runner_input().project_snapshot.plan.plan_fingerprint,
        coverage_record_count=1 if evidence else 0,
        coverage_gap_count=coverage_gap_count,
        evidence=evidence,
        artifacts=(),
    )


def _view(result: RunnerResult) -> PublishedRunView:
    published_at_us = result.finished_at_us + 1
    manifest = PublicationManifest(
        project_id=PROJECT_ID,
        run_id=result.run_id,
        job_id=result.job_id,
        attempt=1,
        lease_owner="finalizer-test",
        fencing_token=1,
        lease_expires_at_us=published_at_us + 1_000,
        published_at_us=published_at_us,
        result_sha256=result.run_id[4:6] * 32,
        files=(
            StagedArtifact(
                path="result.json",
                byte_count=1,
                sha256=result.run_id[4:6] * 32,
            ),
        ),
    )
    return PublishedRunView(
        run=RunRecord(
            run_id=result.run_id,
            project_id=PROJECT_ID,
            contract_id="runner-contract",
            contract_version=1,
            engine_version="runner-test",
            lifecycle=RunLifecycle.COMPLETED,
            verdict=result.verdict,
            created_at_us=1,
            updated_at_us=result.finished_at_us,
            finished_at_us=result.finished_at_us,
        ),
        job=SimpleNamespace(job_id=result.job_id),
        publication=ValidatedPublication(result=result, manifest=manifest, final_dir=Path(".")),
        evidence=(),
    )


def _services(tmp_path: Path, results: tuple[RunnerResult, ...]):
    var_dir = tmp_path / "var"
    database = var_dir / "data" / "jiejian.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    uow_factory = partial(StorageUnitOfWork, factory)
    views = {item.run_id: _view(item) for item in results}
    with uow_factory() as work:
        work.projects.add(
            ProjectRecord(
                project_id=PROJECT_ID,
                name="结果最终化测试",
                status=ProjectStatus.READY,
                created_at_us=1,
                updated_at_us=1,
            )
        )
        for view in views.values():
            work.runs.add(view.run)
        work.commit()
    reader = _Reader(views)
    materializer = FindingMaterializer(uow_factory, reader, utc_now_us=lambda: 10_000)
    finalizer = ResultFinalizer(
        var_dir,
        uow_factory,
        reader,
        materializer,
        utc_now_us=lambda: 10_000,
    )
    return engine, uow_factory, reader, materializer, finalizer, var_dir


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_finalizer_orders_runs_recovers_running_and_is_idempotent(tmp_path: Path) -> None:
    results = (
        _result(RUN_TWO, 100, CaseVerdict.SAFE),
        _result(RUN_ONE, 100, CaseVerdict.VULNERABLE),
        _result(RUN_THREE, 200, CaseVerdict.VULNERABLE),
    )
    engine, uow_factory, reader, _, finalizer, _ = _services(tmp_path, results)
    try:
        completed = finalizer.finalize(RUN_TWO)
        queries = FindingQueries(uow_factory)
        first = queries.findings_for_run(RUN_ONE)
        second = queries.findings_for_run(RUN_TWO)
        assert first[0]["occurrence"]["status"] == "APPEARED"
        assert second[0]["occurrence"]["status"] == "DISAPPEARED"
        assert completed.findings_snapshot_sha256 == _canonical_sha256(second)
        assert completed.findings_completed_at_us is not None
        assert completed.findings_completed_at_us >= completed.created_at_us
        assert completed.base_report_state is BaseReportFinalizationState.PENDING

        repeated = finalizer.finalize(RUN_TWO)
        assert repeated.findings_attempt == completed.findings_attempt == 1
        assert queries.findings_for_run(RUN_TWO) == second

        third_view = reader.read(RUN_THREE)
        with uow_factory() as work:
            pending = work.finalizations.ensure_initial(
                RUN_THREE,
                publication_manifest_sha256(third_view.publication.manifest),
                third_view.publication.manifest.published_at_us,
            )
            work.finalizations.save(
                RunFinalizationRecord.model_validate(
                    {
                        **pending.model_dump(mode="python"),
                        "findings_state": FindingFinalizationState.RUNNING,
                        "findings_attempt": 1,
                    }
                )
            )
            work.commit()
        counts = finalizer.reconcile()
        recovered = finalizer.status(RUN_THREE)
        assert counts["processed"] == 1
        assert recovered.findings_state is FindingFinalizationState.COMPLETE
        assert recovered.findings_attempt == 2
    finally:
        engine.dispose()

def test_finalizer_promotes_base_report_after_findings_and_does_not_rollback_on_report_failure(tmp_path: Path) -> None:
    result = _result(RUN_ONE, 100, CaseVerdict.VULNERABLE)
    engine, _, _, _, finalizer, _ = _services(tmp_path, (result,))

    class Reports:
        def __init__(self, failure: bool = False) -> None:
            self.failure = failure
            self.calls: list[str] = []
            self.report = None

        def generate_base(self, run_id: str):
            self.calls.append(run_id)
            if self.failure:
                raise JiejianError(ErrorCode.REPORT_PUBLISH_FAILED, "测试注入失败")
            self.report = SimpleNamespace(
                report_id="report_" + "a" * 32,
                semantic_input_sha256="b" * 64,
            )
            return self.report

        def read(self, *_args):
            if self.report is None:
                raise AssertionError("尚未生成基础报告")
            return {
                "report_type": "BASE",
                "report_id": self.report.report_id,
                "semantic_input_sha256": self.report.semantic_input_sha256,
            }

    try:
        reports = Reports()
        finalizer.attach_report_builder(reports)
        complete = finalizer.finalize(RUN_ONE)
        assert complete.findings_state is FindingFinalizationState.COMPLETE
        assert complete.base_report_state is BaseReportFinalizationState.COMPLETE, complete.base_report_error_code
        assert reports.calls == [RUN_ONE]
        repeated = finalizer.finalize(RUN_ONE)
        assert repeated.base_report_state is BaseReportFinalizationState.COMPLETE
        assert repeated.base_report_attempt == complete.base_report_attempt == 1
        assert reports.calls == [RUN_ONE]
    finally:
        engine.dispose()

    engine, uow_factory, _, _, finalizer, _ = _services(
        tmp_path / "interrupted-report",
        (result,),
    )
    try:
        pending = finalizer.finalize(RUN_ONE)
        assert pending.base_report_state is BaseReportFinalizationState.PENDING
        with uow_factory() as work:
            current = work.finalizations.get(RUN_ONE)
            assert current is not None
            work.finalizations.save(
                RunFinalizationRecord.model_validate(
                    {
                        **current.model_dump(mode="python"),
                        "base_report_state": BaseReportFinalizationState.RUNNING,
                        "base_report_attempt": 1,
                    }
                )
            )
            work.commit()
        reports = Reports()
        finalizer.attach_report_builder(reports)
        finalizer.reconcile()
        recovered = finalizer.status(RUN_ONE)
        assert recovered.base_report_state is BaseReportFinalizationState.COMPLETE
        assert recovered.base_report_attempt == 2
        assert reports.calls == [RUN_ONE]
    finally:
        engine.dispose()

    engine, _, _, _, finalizer, _ = _services(tmp_path / "failed", (result,))
    try:
        reports = Reports(failure=True)
        finalizer.attach_report_builder(reports)
        failed = finalizer.finalize(RUN_ONE)
        assert failed.findings_state is FindingFinalizationState.COMPLETE
        assert failed.base_report_state is BaseReportFinalizationState.FAILED
        assert failed.base_report_error_code == ErrorCode.REPORT_PUBLISH_FAILED.value
        reports.failure = False
        repaired = finalizer.repair(RUN_ONE)
        assert repaired.findings_state is FindingFinalizationState.COMPLETE
        assert repaired.base_report_state is BaseReportFinalizationState.COMPLETE
        assert repaired.base_report_attempt == 2
    finally:
        engine.dispose()


def test_finalizer_lock_busy_returns_current_status_without_duplicate_work(tmp_path: Path) -> None:
    result = _result(RUN_ONE, 100, CaseVerdict.VULNERABLE)
    engine, uow_factory, reader, _, finalizer, var_dir = _services(tmp_path, (result,))
    lock_path = RuntimePaths(var_dir).locks / "result-finalization.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_path.open("a+b")
    try:
        view = reader.read(RUN_ONE)
        with uow_factory() as work:
            pending = work.finalizations.ensure_initial(
                RUN_ONE,
                publication_manifest_sha256(view.publication.manifest),
                view.publication.manifest.published_at_us,
            )
            work.commit()
        assert try_lock_stream(stream)
        locked = finalizer.finalize(RUN_ONE)
        assert locked == pending
        with uow_factory() as work:
            assert work.findings.list_occurrences_for_run(RUN_ONE) == ()
    finally:
        unlock_stream(stream)
        stream.close()
        engine.dispose()


def test_predecessor_failure_blocks_successor_and_repair_unblocks(tmp_path: Path) -> None:
    results = (
        _result(RUN_ONE, 100, CaseVerdict.VULNERABLE),
        _result(RUN_TWO, 200, None),
    )
    engine, uow_factory, reader, materializer, _, var_dir = _services(tmp_path, results)

    class FailOnceMaterializer:
        def __init__(self) -> None:
            self.failed = False

        def materialize(self, view: PublishedRunView) -> str:
            if view.run.run_id == RUN_ONE and not self.failed:
                self.failed = True
                raise JiejianError(ErrorCode.STORAGE_FAILURE, "测试注入失败")
            return materializer.materialize(view)

    finalizer = ResultFinalizer(
        var_dir,
        uow_factory,
        reader,
        FailOnceMaterializer(),
        utc_now_us=lambda: 10_000,
    )
    try:
        blocked = finalizer.finalize(RUN_TWO)
        failed = finalizer.status(RUN_ONE)
        assert failed.findings_state is FindingFinalizationState.FAILED
        assert failed.findings_error_code == ErrorCode.STORAGE_FAILURE.value
        assert blocked.findings_state is FindingFinalizationState.BLOCKED
        assert blocked.blocked_by_run_id == RUN_ONE

        repaired = finalizer.repair(RUN_ONE)
        successor = finalizer.status(RUN_TWO)
        assert repaired.run_id == RUN_ONE
        assert repaired.findings_state is FindingFinalizationState.COMPLETE
        assert successor.findings_state is FindingFinalizationState.COMPLETE
        assert successor.blocked_by_run_id is None
        assert FindingQueries(uow_factory).findings_for_run(RUN_TWO) == []
    finally:
        engine.dispose()


def test_materialization_rolls_back_with_state_and_detects_publication_conflict(tmp_path: Path) -> None:
    result = _result(RUN_ONE, 100, CaseVerdict.VULNERABLE)
    engine, uow_factory, reader, _, finalizer, _ = _services(tmp_path, (result,))
    view = reader.read(RUN_ONE)
    try:
        with uow_factory() as work:
            initial = work.finalizations.ensure_initial(
                RUN_ONE,
                publication_manifest_sha256(view.publication.manifest),
                view.publication.manifest.published_at_us,
            )
            work.commit()

        class FailFinalizationSave:
            def __init__(self, delegate) -> None:
                self._delegate = delegate

            def get(self, run_id: str):
                return self._delegate.get(run_id)

            def save(self, _record) -> None:
                raise JiejianError(ErrorCode.STORAGE_FAILURE, "测试注入失败")

        class FailSaveUnitOfWork(StorageUnitOfWork):
            def begin(self):
                work = super().begin()
                self.finalizations = FailFinalizationSave(self.finalizations)
                return work

        failing_materializer = FindingMaterializer(
            partial(FailSaveUnitOfWork, uow_factory.args[0]),
            reader,
            utc_now_us=lambda: 10_000,
        )
        with pytest.raises(JiejianError) as failed_save:
            failing_materializer.materialize(view)
        assert failed_save.value.code == ErrorCode.STORAGE_FAILURE.value
        with uow_factory() as work:
            assert work.findings.list_occurrences_for_run(RUN_ONE) == ()
            assert work.findings.list_for_project(PROJECT_ID) == ()
            assert work.finalizations.get(RUN_ONE) == initial

        with uow_factory() as work:
            work.finalizations.save(
                RunFinalizationRecord.model_validate(
                    {
                        **initial.model_dump(mode="python"),
                        "publication_sha256": "f" * 64,
                    }
                )
            )
            work.commit()
        conflict = finalizer.finalize(RUN_ONE)
        assert conflict.findings_state is FindingFinalizationState.FAILED
        assert conflict.findings_error_code == ErrorCode.ARTIFACT_HASH_MISMATCH.value
    finally:
        engine.dispose()


def test_verification_job_keeps_published_success_when_immediate_finalization_fails() -> None:
    staged = SimpleNamespace(result=_result(RUN_ONE, 100, CaseVerdict.VULNERABLE))

    class FailingFinalizer:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def finalize(self, run_id: str) -> None:
            self.calls.append(run_id)
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "测试注入失败")

    finalizer = FailingFinalizer()
    handler = object.__new__(VerificationRunJobHandler)
    handler._prepared = True
    handler._supervisor = SimpleNamespace(run_job=lambda _job_id: staged)
    handler._result_finalizer = finalizer
    returned = handler.run_job("job_" + "1" * 32)
    assert returned is staged
    assert finalizer.calls == [RUN_ONE]
