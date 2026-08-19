from __future__ import annotations

import sqlite3
from functools import partial
from io import BytesIO, StringIO
from pathlib import Path

import pytest

from product.backend.core.lifecycle import JobState, ProjectStatus
from product.backend.core.recording import RecordingState, RecordingStateEvent
from product.protocols.runner import WebTargetScope
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import (
    RecordingBudget,
    RecordingCleanupStatus,
    RecordingEventKind,
    RecordingEvent,
    RecordingHeader,
    RecordingRunnerRequest,
    RecordingRunnerResultType,
    RecordingRunnerResult,
    RecordingSessionRef,
    ConfirmFlowDraftVariable,
    canonical_recording_json_bytes,
    parse_recording_result,
)
from product.backend.workflows.recording.submission import (
    RecordingSubmission,
    SubmitRecording,
)
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.recording.control import (
    control_paths_for_attempt,
    write_control_marker,
)
from product.backend.infra.runtime.recording_process import execute_recording_runner
from product.backend.infra.recording.browser import BrowserRecordingAdapter, RecordingBrowserSession
from product.backend.infra.storage import (
    ProjectRecord,
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    upgrade_database,
)
from product.backend.infra.runtime.jobs.recording import RecordingJobHandler
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.models import ClaimJob
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.artifacts.run_packages import attempt_paths_for
from product.backend.infra.runtime.jobs.targets import JobTargetType, default_run_job_targets
from product.backend.infra.runtime.jobs.recording import RecordingJobTargetHandler
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from tests.execution.recording.test_browser_boundary import browser_server, recording_request

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
            SubmitRecording(
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
        variable = completed.draft.variables[0]
        source = variable.candidate_sources[0]
        lifecycle = RecordingLifecycle(context.uow_factory, var_dir=context.var_dir)
        reviewed = lifecycle.review(
            request.recording_id,
            ConfirmFlowDraftVariable(
                schema_version="1",
                operation="CONFIRM_VARIABLE_SOURCE",
                variable_name=variable.name,
                source_event_sequence=source.source_event_sequence,
                source_json_path=source.json_path,
            ),
        )
        bindings = {
            step.id: {
                "alternate_identity_id": "attacker",
                "resource_id": "owner-resource",
                "alternate_resource_id": "attacker-resource",
            }
            for step in reviewed.draft.steps
            if step.method is not None
        }
        finalized = lifecycle.finalize(
            request.recording_id,
            var_dir=context.var_dir,
            now_us=NOW_US + 40,
            bindings=bindings,
        )
        assert finalized.recording.state is RecordingState.COMPLETED
        assert finalized.flow.steps
        with context.uow_factory() as work:
            final_drafts = work.flow_drafts.list_for_recording(request.recording_id)
        assert [item.revision for item in final_drafts] == [1, 2, 3]
        assert all(step.bindings_confirmed for step in final_drafts[-1].draft.steps)
    finally:
        context.engine.dispose()


def test_recording_lifecycle_controls_current_attempt_and_capture_phases(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    try:
        request = _request("rec_" + "9" * 32).model_copy(
            update={"created_at_us": NOW_US}
        )
        submission = context.application.submit(
            SubmitRecording(
                request=request,
                flow_id=PROJECT_ID,
                idempotency_key="recording-control-phases",
                available_at_us=NOW_US,
                now_us=NOW_US,
                job_id="job_" + "9" * 32,
            )
        )
        lifecycle = RecordingLifecycle(context.uow_factory, var_dir=context.var_dir)

        def assert_precondition(action) -> None:
            with pytest.raises(JiejianError) as raised:
                action()
            assert raised.value.code == ErrorCode.RECORD_STATE_PRECONDITION.value

        assert lifecycle.status(request.recording_id).capture_phase == "PREPARING_BROWSER"
        assert_precondition(lambda: lifecycle.start_capture(request.recording_id))

        claimed = context.attempts.claim(
            ClaimJob(
                lease_owner="recording-worker",
                now_us=NOW_US + 10,
                lease_duration_us=60_000_000,
                job_id=submission.job.job_id,
            )
        )
        assert claimed is not None
        paths = attempt_paths_for(context.var_dir, claimed.job)
        paths.attempt_dir.mkdir(parents=True)
        current = control_paths_for_attempt(paths.attempt_dir)
        stale_dir = paths.attempt_dir.parent / "1-999"
        stale_dir.mkdir(parents=True)
        write_control_marker(
            control_paths_for_attempt(stale_dir).ready_path,
            attempt_dir=stale_dir,
        )

        assert lifecycle.status(request.recording_id).capture_phase == "PREPARING_BROWSER"
        assert_precondition(lambda: lifecycle.start_capture(request.recording_id))

        write_control_marker(current.ready_path, attempt_dir=current.attempt_dir)
        assert lifecycle.status(request.recording_id).capture_phase == "AWAITING_CAPTURE"
        assert_precondition(lambda: lifecycle.stop_capture(request.recording_id))
        started = lifecycle.start_capture(request.recording_id)
        assert started.capture_phase == "CAPTURE_STARTING"
        assert_precondition(lambda: lifecycle.start_capture(request.recording_id))

        write_control_marker(current.started_path, attempt_dir=current.attempt_dir)
        assert lifecycle.status(request.recording_id).capture_phase == "CAPTURING"
        stopping = lifecycle.stop_capture(request.recording_id)
        assert stopping.capture_phase == "STOPPING"
        assert_precondition(lambda: lifecycle.stop_capture(request.recording_id))
    finally:
        context.engine.dispose()


def test_controlled_captured_result_is_consumed_into_pending_review_draft(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    sentinel = "persistent-controlled-recording-secret"
    try:
        with browser_server(sentinel) as server:
            request = recording_request(server.server_port)
            request = request.model_copy(
                update={
                    "recording_id": "rec_" + "a" * 32,
                    "project_id": PROJECT_ID,
                    "created_at_us": NOW_US,
                    "sessions": (
                        request.sessions[0].model_copy(
                            update={"expires_at_us": NOW_US + 60_000_000}
                        ),
                    ),
                }
            )
            signals = {"start": False, "stop": False}

            def interact(session: RecordingBrowserSession) -> None:
                page = session.new_page("owner")
                page.goto(server.url("/ui"))
                signals["start"] = True
                assert session.wait_for_capture_start(page, "owner")
                page.fill("input[name='password']", sentinel)
                page.click("button[data-testid='submit']")
                page.wait_for_timeout(250)
                signals["stop"] = True
                assert session.stop_requested()

            result = BrowserRecordingAdapter().run(
                request,
                interact,
                known_secrets=(sentinel,),
                capture_controlled=True,
                start_requested=lambda: signals["start"],
                stop_requested=lambda: signals["stop"],
                now_us=lambda: NOW_US + 100,
            )

        assert result.result_type is RecordingRunnerResultType.CAPTURED
        submission = context.application.submit(
            SubmitRecording(
                request=request,
                flow_id=PROJECT_ID,
                idempotency_key="controlled-captured-consumption",
                available_at_us=NOW_US,
                now_us=NOW_US,
                job_id="job_" + "a" * 32,
            ),
            known_secrets=(sentinel,),
        )
        times = iter((NOW_US + 10, NOW_US + 1_000))
        worker = RecordingJobHandler(
            var_dir=context.var_dir,
            lease_owner="recording-worker",
            uow_factory=context.uow_factory,
            attempts=context.attempts,
            application=context.application,
            request_store=context.request_store,
            cancel_path_for=lambda root, job: attempt_paths_for(root, job).cancel_path,
            controlled_runner=lambda _request, _cancelled: result,
            known_secrets=(sentinel,),
            utc_now_us=lambda: next(times),
        )

        completed = worker.run_job(submission.job.job_id)

        assert completed is not None
        assert completed.recording.state is RecordingState.PENDING_REVIEW
        assert completed.draft is not None
        assert any(
            event.kind is RecordingEventKind.REQUEST
            and "/echo" in (event.url or "")
            for event in result.events
        )
        assert all("/ui" not in (event.url or "") for event in result.events)
        with context.uow_factory() as work:
            persisted = work.recordings.get(request.recording_id)
            drafts = work.flow_drafts.list_for_recording(request.recording_id)
        assert persisted is not None and persisted.state is RecordingState.PENDING_REVIEW
        assert len(drafts) == 1
        final_view = RecordingLifecycle(
            context.uow_factory, var_dir=context.var_dir
        ).status(request.recording_id)
        assert final_view.capture_phase == "FINISHED"
    finally:
        context.engine.dispose()


def test_cancelled_result_is_consumed_without_flow_draft(tmp_path: Path) -> None:
    context = _context(tmp_path)
    try:
        request = _request("rec_" + "b" * 32).model_copy(
            update={"created_at_us": NOW_US}
        )
        cancelled = BrowserRecordingAdapter().run(
            request,
            lambda _session: pytest.fail("cancelled recording must not interact"),
            cancellation_requested=lambda: True,
            now_us=lambda: NOW_US + 100,
        )
        assert cancelled.result_type is RecordingRunnerResultType.CANCELLED
        submission = context.application.submit(
            SubmitRecording(
                request=request,
                flow_id=PROJECT_ID,
                idempotency_key="cancelled-consumption",
                available_at_us=NOW_US,
                now_us=NOW_US,
                job_id="job_" + "b" * 32,
            )
        )
        queue = JobQueue(context.uow_factory, targets=context.job_targets)
        times = iter((NOW_US + 10, NOW_US + 1_000))
        worker = RecordingJobHandler(
            var_dir=context.var_dir,
            lease_owner="recording-worker",
            uow_factory=context.uow_factory,
            attempts=context.attempts,
            application=context.application,
            request_store=context.request_store,
            cancel_path_for=lambda root, job: attempt_paths_for(root, job).cancel_path,
            controlled_runner=lambda _request, _cancelled: (
                queue.request_cancellation(
                    RequestCancellation(
                        job_id=submission.job.job_id,
                        now_us=NOW_US + 500,
                    )
                ),
                cancelled,
            )[1],
            utc_now_us=lambda: next(times),
        )

        completed = worker.run_job(submission.job.job_id)

        assert completed is not None
        assert completed.job.state is JobState.CANCELLED
        assert completed.recording.state is RecordingState.CANCELLED
        assert completed.draft is None
        with context.uow_factory() as work:
            assert work.flow_drafts.list_for_recording(request.recording_id) == ()
        final_view = RecordingLifecycle(
            context.uow_factory, var_dir=context.var_dir
        ).status(request.recording_id)
        assert final_view.capture_phase == "FINISHED"
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
            SubmitRecording(
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
        self.attempts = JobAttempts(
            self.uow_factory,
            jitter_source=lambda _: 0,
            targets=self.job_targets,
        )
        self.application = RecordingSubmission(
            self.uow_factory,
            self.request_store,
            attempts=self.attempts,
        )


def _context(tmp_path: Path) -> _Context:
    return _Context(tmp_path)


class _ControlledAdapter:
    def __init__(self, result: RecordingRunnerResult) -> None:
        self._result = result

    def run(self, *_args: object, **_kwargs: object) -> RecordingRunnerResult:
        return self._result


def _request(recording_id: str) -> RecordingRunnerRequest:
    return RecordingRunnerRequest(
        schema_version="1",
        recording_id=recording_id,
        project_id=PROJECT_ID,
        created_at_us=NOW_US if recording_id.endswith("1" * 32) else NOW_US + 100,
        target_scope=WebTargetScope(
            schema_version="2",
            base_url="http://127.0.0.1:18080",
            allowed_origins=("http://127.0.0.1:18080",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(18080,),
            allow_private_network=True,
        ),
        sessions=(
            RecordingSessionRef(
                schema_version="1",
                identity_id="owner",
                session_ref="session_" + "5" * 32,
                expires_at_us=NOW_US + 1_000_000,
            ),
        ),
        budget=RecordingBudget(
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
) -> RecordingRunnerResult:
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
        RecordingEvent(
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
        RecordingEvent(
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
        RecordingEvent(
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
                RecordingHeader(
                    schema_version="1",
                    name="location",
                    value="/resources/resource-42",
                ),
            ),
            body=response_body,
        ),
        RecordingEvent(
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
        RecordingEvent(
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
    return RecordingRunnerResult(
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
