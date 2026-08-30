# 验证 Recording workflow 生命周期与当前 attempt 的持久化接线。

from __future__ import annotations
import sqlite3
from functools import partial
from io import BytesIO, StringIO
from pathlib import Path
import pytest
from product.backend.core.lifecycle import JobState, ProjectStatus
from product.backend.core.recording import RecordingState, RecordingStateEvent
from product.protocols.web.target import WebTargetScope
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import (
    ConfirmFlowDraftResource,
    ConfirmFlowDraftTarget,
    RecordingAuthMethod,
    RecordingBudget,
    RecordingCleanupStatus,
    RecordingEventKind,
    RecordingEvent,
    RecordingHeader,
    RecordingRunnerRequest,
    RecordingRunnerResultType,
    RecordingRunnerResult,
    RecordingSessionRef,
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
from product.backend.infra.recording.process import execute_recording_runner
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
from product.backend.infra.runtime.jobs.models import ClaimJob, WaitingFatalFailure
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.artifacts.run_packages import attempt_paths_for
from product.backend.infra.runtime.jobs.targets import JobTargetType, default_run_job_targets
from product.backend.infra.runtime.jobs.recording import RecordingJobTargetHandler
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from tests.backend.infra.recording.test_browser_boundary import COOKIE_ENV_NAME, TEST_IDENTITY_ID, browser_server, recording_request
pytestmark = pytest.mark.database
NOW_US = 1_820_000_000_000_000
PROJECT_ID = "recording-project"

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
                            update={
                                "expires_at_us": NOW_US + 60_000_000,
                            }
                        ),
                    ),
                }
            )
            signals = {"start": False, "stop": False}

            def interact(session: RecordingBrowserSession) -> None:
                page = session.new_page(TEST_IDENTITY_ID)
                page.goto(server.url("/ui"))
                signals["start"] = True
                assert session.wait_for_capture_start(page, TEST_IDENTITY_ID)
                page.fill("input[name='password']", sentinel)
                page.click("button[data-testid='submit']")
                page.wait_for_timeout(250)
                signals["stop"] = True
                assert session.stop_requested()

            result = BrowserRecordingAdapter().run(
                request,
                interact,
                known_secrets=(sentinel,),
                secret_values={COOKIE_ENV_NAME: sentinel},
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
            environ={COOKIE_ENV_NAME: sentinel},
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
            secret_values={"RECORDING_SECRET": "recording-test-secret"},
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
            environ={"RECORDING_SECRET": "recording-test-secret"},
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

class _Context:
    def __init__(self, tmp_path: Path) -> None:
        self.var_dir = tmp_path / "var"
        self.database_path = self.var_dir / "data" / "jiejian.db"
        upgrade_database(self.database_path)
        self.engine = create_sqlite_engine(self.database_path)
        factory = create_session_factory(self.engine)
        self.uow_factory = partial(StorageUnitOfWork, factory)
        with self.uow_factory() as work:
            work.projects.add(
                ProjectRecord(
                    project_id=PROJECT_ID,
                    name="录制项目",
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

def _request(
    recording_id: str,
    *,
    secret_refs: tuple[str, ...] = ("env:RECORDING_SECRET",),
) -> RecordingRunnerRequest:
    return RecordingRunnerRequest(
        schema_version="1",
        recording_id=recording_id,
        project_id=PROJECT_ID,
        action_candidate_id="action_0123456789abcdef0123456789abcdef",
        created_at_us=NOW_US if recording_id.endswith("1" * 32) else NOW_US + 100,
        target_scope=WebTargetScope(
            base_url="http://127.0.0.1:18080",
            allowed_origins=("http://127.0.0.1:18080",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(18080,),
            allow_private_network=True,
        ),
        sessions=(
            RecordingSessionRef(
                test_identity_id="tid_0123456789abcdef0123456789abcdef",
                session_ref="session_" + "5" * 32,
                auth_method=RecordingAuthMethod.BEARER,
                bearer_ref=secret_refs[0],
                expires_at_us=NOW_US + 1_000_000,
            ),
        ),
        budget=RecordingBudget(
            max_duration_us=1_000_000,
        ),
        headless=True,
        trace_enabled=False,
    )
