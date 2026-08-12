from __future__ import annotations

import sqlite3
from functools import partial
from io import BytesIO, StringIO
from pathlib import Path

import pytest

from jiejian.domain.lifecycle import JobState, ProjectStatus
from jiejian.recording.models import RecordingState, RecordingStateEvent
from jiejian.verification.models import TargetScope
from jiejian.errors import ErrorCode, JiejianError
from jiejian.protocols import (
    RecordingBudgetV1,
    RecordingCleanupStatus,
    RecordingEventKind,
    RecordingEventV1,
    RecordingHeaderV1,
    RecordingRunnerRequestV1,
    RecordingRunnerResultType,
    RecordingRunnerResultV1,
    RecordingSessionRefV1,
    canonical_recording_json_bytes,
    parse_recording_result,
)
from jiejian.recording.application import (
    RecordingApplicationService,
    SubmitRecordingV1,
)
from jiejian.recording.request_store import RecordingRequestStore
from jiejian.recording_runner.execution import execute_recording_runner
from jiejian.storage import (
    ProjectRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)
from jiejian.recording.job_handler import RecordingJobHandler
from jiejian.execution.attempts import JobAttemptService
from jiejian.execution.published_artifacts import attempt_paths_for
from jiejian.execution.targets import JobTargetType, default_run_job_targets
from jiejian.recording.job_target import RecordingJobTargetHandler

pytestmark = pytest.mark.database

NOW_US = 1_820_000_000_000_000
PROJECT_ID = "stage33-project"


def test_recording_runner_uses_single_json_stdin_and_stdout() -> None:
    request = _request("rec_" + "6" * 32)
    expected = _captured_result(request.recording_id)
    stdout = BytesIO()
    stderr = StringIO()

    exit_code = execute_recording_runner(
        stdin=BytesIO(canonical_recording_json_bytes(request)),
        stdout=stdout,
        stderr=stderr,
        adapter=_ControlledAdapter(expected),
    )

    assert exit_code == 0
    assert parse_recording_result(stdout.getvalue()) == expected
    assert stderr.getvalue() == ""


def test_recording_job_reaches_pending_review_with_atomic_draft(tmp_path: Path) -> None:
    context = _context(tmp_path)
    try:
        request = _request("rec_" + "1" * 32)
        submission = context.application.submit(
            SubmitRecordingV1(
                request=request,
                flow_id="recorded-flow",
                idempotency_key="recording-success",
                max_attempts=2,
                available_at_us=NOW_US,
                now_us=NOW_US,
                job_id="job_" + "2" * 32,
            )
        )
        times = iter((NOW_US + 10, NOW_US + 30))
        worker = RecordingJobHandler(
            var_dir=context.var_dir,
            lease_owner="recording-worker",
            uow_factory=context.uow_factory,
            attempts=context.attempts,
            application=context.application,
            request_store=context.request_store,
            cancel_path_for=lambda root, job: attempt_paths_for(root, job).cancel_path,
            controlled_runner=lambda _request, _cancelled: _captured_result(
                request.recording_id
            ),
            utc_now_us=lambda: next(times),
        )

        completed = worker.run_job(submission.job.job_id)

        assert completed is not None
        assert completed.job.state is JobState.SUCCEEDED
        assert completed.job.run_id is None
        assert completed.job.recording_id == request.recording_id
        assert completed.recording.state is RecordingState.PENDING_REVIEW
        assert completed.draft is not None
        assert "resource-42" not in completed.draft.model_dump_json()
        with context.uow_factory() as work:
            persisted = work.recordings.get(request.recording_id)
            drafts = work.flow_drafts.list_for_recording(request.recording_id)
            events = work.job_events.list_for_job(submission.job.job_id)
        assert persisted is not None
        assert persisted.state is RecordingState.PENDING_REVIEW
        assert len(persisted.browser_events) == 5
        assert len(drafts) == 1 and drafts[0].draft == completed.draft
        assert [event.sequence for event in events] == [1, 2, 3]
    finally:
        context.engine.dispose()


def test_secret_bearing_runner_result_fails_without_persisting_payload(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    sentinel = "stage33-real-secret-sentinel"
    try:
        request = _request("rec_" + "3" * 32)
        submission = context.application.submit(
            SubmitRecordingV1(
                request=request,
                flow_id="secret-rejection-flow",
                idempotency_key="recording-secret-failure",
                max_attempts=1,
                available_at_us=NOW_US + 100,
                now_us=NOW_US + 100,
                job_id="job_" + "4" * 32,
            ),
            known_secrets=(sentinel,),
        )
        times = iter((NOW_US + 110, NOW_US + 120, NOW_US + 130))
        worker = RecordingJobHandler(
            var_dir=context.var_dir,
            lease_owner="recording-worker",
            uow_factory=context.uow_factory,
            attempts=context.attempts,
            application=context.application,
            request_store=context.request_store,
            cancel_path_for=lambda root, job: attempt_paths_for(root, job).cancel_path,
            controlled_runner=lambda _request, _cancelled: _captured_result(
                request.recording_id,
                response_body=f'{{"id":"{sentinel}"}}',
            ),
            known_secrets=(sentinel,),
            utc_now_us=lambda: next(times),
        )

        with pytest.raises(JiejianError) as raised:
            worker.run_job(submission.job.job_id)

        assert raised.value.code == ErrorCode.RECORD_SECRET_EXPOSED.value
        with context.uow_factory() as work:
            job = work.jobs.get(submission.job.job_id)
            recording = work.recordings.get(request.recording_id)
            drafts = work.flow_drafts.list_for_recording(request.recording_id)
        assert job is not None and job.state is JobState.FAILED
        assert recording is not None and recording.state is RecordingState.FAILED
        assert recording.browser_events == ()
        assert drafts == ()
        connection = sqlite3.connect(context.database_path)
        try:
            dump = "\n".join(connection.iterdump())
        finally:
            connection.close()
        assert sentinel not in dump
    finally:
        context.engine.dispose()


class _Context:
    def __init__(self, tmp_path: Path) -> None:
        self.var_dir = tmp_path / "var"
        self.database_path = self.var_dir / "jiejian.db"
        upgrade_database(self.database_path)
        self.engine = create_sqlite_engine(self.database_path)
        factory = create_session_factory(self.engine)
        self.uow_factory = partial(StorageUnitOfWork, factory)
        with self.uow_factory() as work:
            work.projects.add(
                ProjectRecord(
                    project_id=PROJECT_ID,
                    name="阶段 3.3 项目",
                    status=ProjectStatus.READY,
                    created_at_us=NOW_US - 1,
                    updated_at_us=NOW_US - 1,
                )
            )
            work.commit()
        self.request_store = RecordingRequestStore(self.var_dir)
        self.job_targets = default_run_job_targets()
        self.job_targets.register(JobTargetType.RECORDING, RecordingJobTargetHandler())
        self.attempts = JobAttemptService(
            self.uow_factory,
            jitter_source=lambda _: 0,
            targets=self.job_targets,
        )
        self.application = RecordingApplicationService(
            self.uow_factory,
            self.request_store,
            attempts=self.attempts,
        )


def _context(tmp_path: Path) -> _Context:
    return _Context(tmp_path)


class _ControlledAdapter:
    def __init__(self, result: RecordingRunnerResultV1) -> None:
        self._result = result

    def run(self, *_args: object, **_kwargs: object) -> RecordingRunnerResultV1:
        return self._result


def _request(recording_id: str) -> RecordingRunnerRequestV1:
    return RecordingRunnerRequestV1(
        schema_version="1",
        recording_id=recording_id,
        project_id=PROJECT_ID,
        created_at_us=NOW_US if recording_id.endswith("1" * 32) else NOW_US + 100,
        target_scope=TargetScope(
            schema_version="1",
            base_url="http://127.0.0.1:18080",
            allowed_origins=("http://127.0.0.1:18080",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(18080,),
            allow_private_network=True,
        ),
        sessions=(
            RecordingSessionRefV1(
                schema_version="1",
                identity_id="owner",
                session_ref="session_" + "5" * 32,
                expires_at_us=NOW_US + 1_000_000,
            ),
        ),
        budget=RecordingBudgetV1(
            schema_version="1",
            max_duration_us=1_000_000,
        ),
        headless=True,
        trace_enabled=False,
    )


def _captured_result(
    recording_id: str,
    *,
    response_body: str = '{"id":"resource-42"}',
) -> RecordingRunnerResultV1:
    lifecycle = (
        RecordingStateEvent(
            sequence=1,
            source=RecordingState.CREATED,
            target=RecordingState.STARTING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 11,
        ),
        RecordingStateEvent(
            sequence=2,
            source=RecordingState.STARTING,
            target=RecordingState.RECORDING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 12,
        ),
        RecordingStateEvent(
            sequence=3,
            source=RecordingState.RECORDING,
            target=RecordingState.CLEANING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 13,
            reason_code="RECORDING_FINISHED",
        ),
        RecordingStateEvent(
            sequence=4,
            source=RecordingState.CLEANING,
            target=RecordingState.PROCESSING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 14,
        ),
    )
    events = (
        RecordingEventV1(
            schema_version="1",
            sequence=1,
            occurred_at_us=NOW_US + 12,
            kind=RecordingEventKind.UI_SUBMIT,
            identity_id="owner",
            page_id="page_000001",
            frame_id="frame_000001",
            action_id="action_000001",
            element_locator="#resource-form",
        ),
        RecordingEventV1(
            schema_version="1",
            sequence=2,
            occurred_at_us=NOW_US + 12,
            kind=RecordingEventKind.REQUEST,
            identity_id="owner",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000001",
            caused_by_action_id="action_000001",
            url="http://127.0.0.1:18080/resources",
            method="POST",
            resource_type="fetch",
            body='{"name":"demo"}',
        ),
        RecordingEventV1(
            schema_version="1",
            sequence=3,
            occurred_at_us=NOW_US + 13,
            kind=RecordingEventKind.RESPONSE,
            identity_id="owner",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000001",
            url="http://127.0.0.1:18080/resources",
            status_code=201,
            headers=(
                RecordingHeaderV1(
                    schema_version="1",
                    name="location",
                    value="/resources/resource-42",
                ),
            ),
            body=response_body,
        ),
        RecordingEventV1(
            schema_version="1",
            sequence=4,
            occurred_at_us=NOW_US + 14,
            kind=RecordingEventKind.REQUEST,
            identity_id="owner",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000002",
            url="http://127.0.0.1:18080/resources/resource-42",
            method="GET",
            resource_type="fetch",
        ),
        RecordingEventV1(
            schema_version="1",
            sequence=5,
            occurred_at_us=NOW_US + 15,
            kind=RecordingEventKind.RESPONSE,
            identity_id="owner",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000002",
            url="http://127.0.0.1:18080/resources/resource-42",
            status_code=200,
            body="{}",
        ),
    )
    return RecordingRunnerResultV1(
        schema_version="1",
        recording_id=recording_id,
        project_id=PROJECT_ID,
        finished_at_us=NOW_US + 20,
        result_type=RecordingRunnerResultType.CAPTURED,
        recording_state=RecordingState.PROCESSING,
        cleanup_status=RecordingCleanupStatus.SUCCEEDED,
        reason_codes=("RECORDING_FINISHED",),
        state_events=lifecycle,
        events=events,
    )
