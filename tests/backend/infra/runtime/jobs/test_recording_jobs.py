# 验证录制 Job handler 的 pending、fatal 与 attempt 边界。

from __future__ import annotations
from pathlib import Path
import pytest
from product.backend.core.lifecycle import JobState
from product.backend.core.recording import RecordingState
from product.protocols import ConfirmFlowDraftResource, ConfirmFlowDraftTarget, ConfirmFlowDraftVariableChoice, flow_draft_source_choice_id
from product.backend.workflows.recording.submission import SubmitRecording
from product.backend.infra.runtime.jobs.recording import RecordingJobHandler
from product.backend.infra.runtime.jobs.models import WaitingFatalFailure
from product.backend.infra.artifacts.run_packages import attempt_paths_for
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from tests.fixtures.recording import RecordingContext as _Context, runner_request as _request, captured_result as _captured_result
pytestmark = pytest.mark.database
NOW_US = 1_820_000_000_000_000
PROJECT_ID = "recording-project"

def test_recording_job_reaches_pending_review_with_atomic_draft(tmp_path: Path) -> None:
    context = _context(tmp_path)
    try:
        request = _request("rec_" + "1" * 32)
        submission = context.application.submit(
            SubmitRecording(
                request=context.bind_request(request),
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
                request.recording_id, project_id=context.project_id
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
            ConfirmFlowDraftVariableChoice(
                schema_version="1",
                operation="CONFIRM_VARIABLE_CHOICE",
                variable_name=variable.name,
                choice_id=flow_draft_source_choice_id(source),
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
                request=context.bind_request(request),
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

def _context(tmp_path: Path) -> _Context:
    return _Context(tmp_path)
