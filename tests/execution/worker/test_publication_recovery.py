from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from jiejian.results.published import PublishedResultReader
from jiejian.domain.lifecycle import (
    JobState,
    ProjectStatus,
    RunLifecycle,
    RunVerdict,
)
from jiejian.errors import ErrorCode, JiejianError
from jiejian.protocols import (
    CleanupResultV1,
    CleanupStatus,
    RunnerResultType,
    RunnerResultV1,
    StagedArtifactV1,
    canonical_json_bytes,
    CleanupResultV2,
    CleanupStatusV2,
    RunnerResultTypeV2,
    RunnerResultV2,
    StagedArtifactV2,
    canonical_runner_v2_json_bytes,
)
from jiejian.storage import (
    EvidenceIndexRecord,
    ProjectRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    default_database_path,
    upgrade_database,
)
from jiejian.execution.attempts import JobAttemptService
from jiejian.execution.models import (
    ClaimJobV1,
    RetryableFailureCode,
    RetryableFailureV1,
    SubmitJobV1,
)
from jiejian.execution.publication import RunPublicationService
from jiejian.execution.queue import JobQueueService

pytestmark = pytest.mark.database
from jiejian.execution.reconciliation import RunReconciliationService
from jiejian.execution.request_store import ExecutionRequestStore
from jiejian.execution.published_artifacts import (
    StagedAttempt,
    TrustedResultReceiptV1,
    attempt_paths_for,
)
from jiejian.execution.request_store import ExecutionRequestStore, PersistedExecutionRequestV2
from tests.execution.protocol.test_runner_v2 import _evidence, _input, _snapshot

NOW_US = 1_790_000_000_000_000


@dataclass(frozen=True)
class PublicationParts:
    engine: object
    uow_factory: object
    attempts: JobAttemptService
    job: object


def _claimed_job(
    var_dir: Path,
    suffix: str,
    *,
    request_hash: str | None = None,
) -> PublicationParts:
    upgrade_database(default_database_path(var_dir))
    engine = create_sqlite_engine(default_database_path(var_dir))
    factory = create_session_factory(engine)
    uow_factory = partial(StorageUnitOfWork, factory)
    with uow_factory() as work:
        work.projects.add(
            ProjectRecord(
                project_id="publication-project",
                name="发布测试",
                status=ProjectStatus.READY,
                created_at_us=NOW_US - 1,
                updated_at_us=NOW_US - 1,
            )
        )
        work.commit()
    submitted = JobQueueService(uow_factory).submit(
        SubmitJobV1(
            project_id="publication-project",
            operation_type="ACTIVE_RUN",
            idempotency_key=f"publication-{suffix}",
            request_hash=request_hash or suffix * 64,
            contract_id="ownership-contract",
            contract_version=1,
            engine_version="0.1.0",
            max_attempts=2,
            available_at_us=NOW_US,
            now_us=NOW_US,
            run_id=f"run_{suffix * 32}",
            job_id=f"job_{suffix * 32}",
        )
    )
    attempts = JobAttemptService(uow_factory, jitter_source=lambda _: 0)
    claimed = attempts.claim(
        ClaimJobV1(
            job_id=submitted.job.job_id,
            lease_owner=f"worker-publication-{suffix}",
            now_us=NOW_US + 1,
            lease_duration_us=30_000_000,
        )
    )
    assert claimed is not None
    return PublicationParts(engine, uow_factory, attempts, claimed.job)


def _staged_attempt(var_dir: Path, job) -> StagedAttempt:
    paths = attempt_paths_for(var_dir, job)
    paths.staging_dir.mkdir(parents=True)
    artifact_path = paths.staging_dir / "artifacts" / "report" / "report.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"{}")
    artifact = StagedArtifactV1(
        schema_version="1",
        path="artifacts/report/report.json",
        byte_count=2,
        sha256=hashlib.sha256(b"{}").hexdigest(),
    )
    result = RunnerResultV1(
        schema_version="1",
        run_id=job.run_id,
        job_id=job.job_id,
        attempt=job.attempt,
        lease_owner=job.lease_owner,
        fencing_token=job.fencing_token,
        finished_at_us=NOW_US + 2,
        result_type=RunnerResultType.SUCCESS,
        run_lifecycle=RunLifecycle.COMPLETED,
        job_state=JobState.SUCCEEDED,
        verdict=RunVerdict.PASS,
        error=None,
        cleanup=CleanupResultV1(
            schema_version="1",
            status=CleanupStatus.NOT_REQUIRED,
        ),
        artifacts=(artifact,),
    )
    raw = canonical_json_bytes(result)
    paths.result_path.write_bytes(raw)
    receipt = TrustedResultReceiptV1(
        schema_version="1",
        run_id=result.run_id,
        job_id=result.job_id,
        attempt=result.attempt,
        lease_owner=result.lease_owner,
        fencing_token=result.fencing_token,
        result_sha256=hashlib.sha256(raw).hexdigest(),
    )
    paths.receipt_path.write_text(
        json.dumps(
            receipt.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return StagedAttempt(result=result, paths=paths)


def test_publication_rejects_old_fencing_token(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    parts = _claimed_job(var_dir, "7")
    staged = _staged_attempt(var_dir, parts.job)
    try:
        parts.attempts.record_retryable_failure(
            RetryableFailureV1(
                job_id=parts.job.job_id,
                lease_owner=parts.job.lease_owner,
                fencing_token=parts.job.fencing_token,
                now_us=NOW_US + 2,
                reason_code=RetryableFailureCode.WORKER_INTERRUPTED,
            )
        )
        claimed_again = parts.attempts.claim(
            ClaimJobV1(
                job_id=parts.job.job_id,
                lease_owner="worker-publication-new",
                now_us=NOW_US + 2_000_000,
                lease_duration_us=30_000_000,
            )
        )
        assert claimed_again is not None and claimed_again.job.fencing_token == 2
        publisher = RunPublicationService(
            var_dir,
            parts.uow_factory,
            utc_now_us=lambda: NOW_US + 2_000_001,
        )
        with pytest.raises(JiejianError) as captured:
            publisher.publish(staged)
        assert captured.value.code == ErrorCode.ARTIFACT_FENCE.value
        assert not (var_dir / "projects" / "publication-project" / "runs").exists()
    finally:
        parts.engine.dispose()


def test_publication_rejects_tampered_artifact_hash(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    parts = _claimed_job(var_dir, "8")
    staged = _staged_attempt(var_dir, parts.job)
    try:
        (staged.paths.staging_dir / "artifacts" / "report" / "report.json").write_bytes(
            b'{"tampered":true}'
        )
        publisher = RunPublicationService(
            var_dir,
            parts.uow_factory,
            utc_now_us=lambda: NOW_US + 3,
        )
        with pytest.raises(JiejianError) as captured:
            publisher.publish(staged)
        assert captured.value.code == ErrorCode.ARTIFACT_MANIFEST.value
    finally:
        parts.engine.dispose()


def test_reconciliation_completes_promoted_run_once_after_commit_failure(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var"
    parts = _claimed_job(var_dir, "9")
    staged = _staged_attempt(var_dir, parts.job)
    fail_next_commit = [True]

    class FailOnceUnitOfWork(StorageUnitOfWork):
        def commit(self) -> None:
            if fail_next_commit[0]:
                fail_next_commit[0] = False
                self.rollback()
                raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库操作失败")
            super().commit()

    session_factory = parts.uow_factory.args[0]

    def failing_factory(*, known_secrets=()):
        return FailOnceUnitOfWork(session_factory, known_secrets=known_secrets)

    try:
        failing_publisher = RunPublicationService(
            var_dir,
            failing_factory,
            utc_now_us=lambda: NOW_US + 3,
        )
        with pytest.raises(JiejianError) as captured:
            failing_publisher.publish(staged)
        assert captured.value.code == ErrorCode.STORAGE_FAILURE.value
        final_dir = var_dir / "projects" / "publication-project" / "runs" / parts.job.run_id
        assert (final_dir / "publication-manifest.json").is_file()

        publisher = RunPublicationService(
            var_dir,
            parts.uow_factory,
            utc_now_us=lambda: NOW_US + 4,
        )
        reconciliation = RunReconciliationService(
            var_dir,
            parts.uow_factory,
            publisher,
            utc_now_us=lambda: NOW_US + 4,
        )
        first = reconciliation.reconcile()
        with parts.uow_factory() as work:
            job = work.jobs.get(parts.job.job_id)
            run = work.runs.get(parts.job.run_id)
            events = work.job_events.list_for_job(parts.job.job_id)
        assert first.published_completed == 1
        assert job is not None and job.state is JobState.SUCCEEDED
        assert run is not None and run.lifecycle is RunLifecycle.COMPLETED
        assert run.verdict is RunVerdict.PASS
        assert events[-1].event_type == "JOB_SUCCEEDED"

        second = reconciliation.reconcile()
        with parts.uow_factory() as work:
            repeated_events = work.job_events.list_for_job(parts.job.job_id)
        assert second.published_already_complete == 1
        assert repeated_events == events
    finally:
        parts.engine.dispose()


def test_result_reader_rejects_tampered_published_report(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    parts = _claimed_job(var_dir, "a")
    staged = _staged_attempt(var_dir, parts.job)
    try:
        RunPublicationService(
            var_dir,
            parts.uow_factory,
            utc_now_us=lambda: NOW_US + 3,
        ).publish(staged)
        reader = PublishedResultReader(var_dir, parts.uow_factory)
        assert reader.report(reader.read(parts.job.run_id)) == {}
        report = (
            var_dir
            / "projects"
            / "publication-project"
            / "runs"
            / parts.job.run_id
            / "artifacts"
            / "report"
            / "report.json"
        )
        report.write_text('{"tampered":true}', encoding="utf-8")
        with pytest.raises(JiejianError) as captured:
            reader.read(parts.job.run_id)
        assert captured.value.code == ErrorCode.ARTIFACT_MANIFEST.value
    finally:
        parts.engine.dispose()


def test_v2_publication_indexes_matching_evidence_and_rejects_v1_views(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    runner_input = _input()
    request = PersistedExecutionRequestV2(
        schema_version="2",
        budget=runner_input.budget,
        project_snapshot=runner_input.project_snapshot,
    )
    request_hash, _ = ExecutionRequestStore(var_dir).write(
        runner_input.job_id,
        request,
    )
    parts = _claimed_job(var_dir, "a", request_hash=request_hash)
    evidence = _evidence()
    evidence_raw = canonical_runner_v2_json_bytes(evidence)
    evidence_artifact = StagedArtifactV2(
        schema_version="2",
        path=f"artifacts/evidence/{evidence.evidence_id}.json",
        byte_count=len(evidence_raw),
        sha256=hashlib.sha256(evidence_raw).hexdigest(),
    )
    result = RunnerResultV2(
        schema_version="2",
        run_id=parts.job.run_id,
        job_id=parts.job.job_id,
        attempt=parts.job.attempt,
        lease_owner=parts.job.lease_owner,
        fencing_token=parts.job.fencing_token,
        finished_at_us=NOW_US + 2,
        result_type=RunnerResultTypeV2.SUCCESS,
        run_lifecycle=RunLifecycle.COMPLETED,
        job_state=JobState.SUCCEEDED,
        verdict=RunVerdict.PASS,
        reason_codes=(),
        cleanup=CleanupResultV2(status=CleanupStatusV2.SUCCEEDED),
        error=None,
        plan_fingerprint=_snapshot().plan.plan_fingerprint,
        coverage_record_count=1,
        coverage_gap_count=0,
        evidence=(evidence,),
        artifacts=(evidence_artifact,),
    )
    paths = attempt_paths_for(var_dir, parts.job)
    paths.staging_dir.mkdir(parents=True)
    evidence_path = paths.staging_dir / evidence_artifact.path
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_bytes(evidence_raw)
    result_raw = canonical_runner_v2_json_bytes(result)
    paths.result_path.write_bytes(result_raw)
    paths.receipt_path.parent.mkdir(parents=True, exist_ok=True)
    paths.receipt_path.write_text(json.dumps({
        "schema_version": "1",
        "run_id": result.run_id,
        "job_id": result.job_id,
        "attempt": result.attempt,
        "lease_owner": result.lease_owner,
        "fencing_token": result.fencing_token,
        "result_sha256": hashlib.sha256(result_raw).hexdigest(),
    }, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    try:
        published = RunPublicationService(var_dir, parts.uow_factory, utc_now_us=lambda: NOW_US + 3).publish(
            StagedAttempt(result=result, paths=paths)
        )
        reader = PublishedResultReader(var_dir, parts.uow_factory)
        view = reader.read(parts.job.run_id)
        assert published.result == result
        assert len(view.evidence) == 1
        assert view.evidence[0].case_id == evidence.case_snapshot.case_id
        overview = reader.overview(parts.job.run_id, published=view)
        assert overview["target_scope"] == _snapshot().target.model_dump(mode="json")
        assert overview["budget"] == request.budget.model_dump(mode="json")
        assert overview["execution_schema_version"] == "2"
        assert overview["result_schema_version"] == "2"
        assert overview["observer_health"]["required_observers"] == ["http", "owner_api"]
        assert overview["observer_health"]["owner_api"]["observer_type"] == "OWNER_API"
        assert overview["coverage_record_count"] == 1
        assert overview["coverage_gap_count"] == 0
        assert overview["case_progress"] == {
            "schema_version": "1",
            "status": "PUBLISHED",
            "completed": 1,
            "total": 1,
        }
        unpublished_overview = reader.overview(parts.job.run_id)
        assert unpublished_overview["case_progress"]["status"] == "UNAVAILABLE"
        assert unpublished_overview["case_progress"]["completed"] is None
        with pytest.raises(JiejianError) as report_error:
            reader.report(view)
        assert report_error.value.code == ErrorCode.REPORT_NOT_FOUND.value
        with pytest.raises(JiejianError) as finding_error:
            reader.findings(view)
        assert finding_error.value.code == ErrorCode.REPORT_NOT_FOUND.value
        assert reader.evidence_detail(view, evidence.evidence_id)["evidence_id"] == evidence.evidence_id
        published_evidence_path = (
            var_dir
            / "projects"
            / parts.job.project_id
            / "runs"
            / parts.job.run_id
            / evidence_artifact.path
        )
        published_evidence_path.write_bytes(evidence_raw + b"tamper")
        with pytest.raises(JiejianError) as tamper:
            reader.read(parts.job.run_id)
        assert tamper.value.code == ErrorCode.ARTIFACT_MANIFEST.value
    finally:
        parts.engine.dispose()


def test_result_reader_rejects_mismatched_evidence_index(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    parts = _claimed_job(var_dir, "b")
    staged = _staged_attempt(var_dir, parts.job)
    try:
        RunPublicationService(
            var_dir,
            parts.uow_factory,
            utc_now_us=lambda: NOW_US + 3,
        ).publish(staged)
        with parts.uow_factory() as work:
            work.evidence.add(
                EvidenceIndexRecord(
                    evidence_id="ev_" + "b" * 20,
                    run_id=parts.job.run_id,
                    case_id="forged-case",
                    artifact_path="artifacts/report/report.json",
                    sha256="b" * 64,
                    byte_count=2,
                    created_at_us=NOW_US + 3,
                )
            )
            work.commit()
        with pytest.raises(JiejianError) as captured:
            PublishedResultReader(var_dir, parts.uow_factory).read(parts.job.run_id)
        assert captured.value.code == ErrorCode.ARTIFACT_HASH_MISMATCH.value
    finally:
        parts.engine.dispose()


def test_evidence_detail_rebuilds_baseline_from_flow_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = SimpleNamespace(
        project_snapshot=SimpleNamespace(
            flow=SimpleNamespace(
                steps=(SimpleNamespace(
                    id="step-1",
                    identity_id="owner",
                    method="GET",
                    path="/resources/{resource_id}",
                    resource_id="resource-1",
                    json_body={"owner": "owner"},
                ),),
            ),
        ),
    )
    reader = PublishedResultReader(tmp_path / "var", lambda: None)
    monkeypatch.setattr(ExecutionRequestStore, "load", lambda self, job_id, expected_hash: request)
    reader.evidence_document = lambda view, evidence_id: {
        "evidence_id": evidence_id,
        "case_id": "case-1",
        "request": {"identity_id": "attacker", "method": "GET", "path": "/resources/other", "json_body": {"owner": "attacker"}},
        "observations": [],
    }
    reader.document = lambda view, artifact_path: {
        "cases": [{"case_id": "case-1", "step_id": "step-1", "identity_id": "attacker"}],
    }
    view = SimpleNamespace(job=SimpleNamespace(job_id="job-1", request_hash="hash"))
    detail = reader.evidence_detail(view, "ev_test")
    assert detail["difference"]["baseline_request"] == {
        "identity_id": "owner",
        "method": "GET",
        "path": "/resources/resource-1",
        "resource_id": "resource-1",
        "json_body": {"owner": "owner"},
    }
    assert detail["difference"]["mutation_request"]["identity_id"] == "attacker"
    assert detail["difference"]["mutation_request"]["path"] == "/resources/other"
