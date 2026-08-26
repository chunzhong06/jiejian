# 验证录制 Job handler 的 pending、fatal 与 attempt 边界。

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
            environ={"RECORDING_SECRET": "recording-test-secret"},
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
        assert reviewed.draft is not None
        targeted = lifecycle.review(
            request.recording_id,
            ConfirmFlowDraftTarget(
                schema_version="1",
                operation="CONFIRM_TARGET_STEP",
                step_id=reviewed.draft.steps[-1].id,
            ),
        )
        assert targeted.draft is not None
        resource = next(
            item
            for item in targeted.draft.steps[-1].resource_candidates
            if item.location == "path[1]"
        )
        lifecycle.review(
            request.recording_id,
            ConfirmFlowDraftResource(
                schema_version="1",
                operation="CONFIRM_RESOURCE_SLOT",
                candidate_id=resource.candidate_id,
            ),
        )
        finalized = lifecycle.finalize(
            request.recording_id,
            var_dir=context.var_dir,
            now_us=NOW_US + 40,
        )
        assert finalized.recording.state is RecordingState.COMPLETED
        assert finalized.flow.steps
        with context.uow_factory() as work:
            final_drafts = work.flow_drafts.list_for_recording(request.recording_id)
        assert [item.revision for item in final_drafts] == [1, 2, 3, 4]
        assert final_drafts[-1].draft.resource_candidate_id == resource.candidate_id
    finally:
        context.engine.dispose()

def test_waiting_worker_fatal_finishes_recording_without_creating_attempt(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    try:
        request = _request("rec_" + "5" * 32)
        submission = context.application.submit(
            SubmitRecording(
                request=request,
                flow_id="waiting-worker-fatal",
                idempotency_key="waiting-worker-fatal",
                available_at_us=NOW_US + 100,
                now_us=NOW_US + 100,
                job_id="job_" + "5" * 32,
            )
        )

        failed = context.attempts.record_waiting_fatal_failure(
            WaitingFatalFailure(
                job_id=submission.job.job_id,
                now_us=NOW_US + 110,
            )
        )

        assert failed is not None
        assert failed.job.state is JobState.FAILED
        assert failed.job.attempt == 0
        assert failed.recording is not None
        assert failed.recording.state is RecordingState.FAILED
        assert failed.recording.started_at_us is None
        with context.uow_factory() as work:
            events = work.job_events.list_for_job(submission.job.job_id)
        assert events[-1].event_type == "JOB_FAILED"
        assert events[-1].metadata == {
            "attempt": 0,
            "reason_code": "WORKER_FATAL",
        }
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
                    name="location",
                    value="/resources/resource-42",
                ),
            ),
            body=response_body,
        ),
        RecordingEvent(
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
