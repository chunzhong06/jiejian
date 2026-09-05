# 验证待审录制明确放弃的事务边界、幂等性与历史技术资产保留。

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.core.recording import RecordingPurpose, RecordingState
from product.backend.infra.storage.execution.jobs import JobRecord
from tests.fixtures.action_preparation import add_recording, build_preparation_harness


@pytest.fixture
def harness(tmp_path):
    h = build_preparation_harness(tmp_path)
    yield h
    h.close()


def _job(h, recording, state):
    job = JobRecord(job_id="job_" + uuid4().hex, project_id=h.project_id,
        recording_id=recording.recording_id, operation_type="RECORDING", state=state,
        idempotency_key=recording.recording_id, request_hash="a" * 64,
        attempt=0, max_attempts=1, available_at_us=1, fencing_token=0,
        created_at_us=1, updated_at_us=3)
    with h.core.uow_factory() as work:
        work.jobs.add(job)
        work.commit()
    return job


@pytest.mark.parametrize("job_state", [JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED])
def test_discard_review_preserves_history_bindings_and_job_and_is_idempotent(harness, job_state):
    h = harness
    target = add_recording(h)
    final = h.core.recording_lifecycle.finalize(target.recording_id, var_dir=h.var_dir, now_us=100)
    flow_before = h.core.recording_lifecycle.load_final_flow(Path(final.flow_path))
    recording = add_recording(h, purpose=RecordingPurpose.OBSERVATION,
        parent_recording_id=target.recording_id, effect_id=h.effect_id, step_count=2)
    job = _job(h, recording, job_state)
    before = h.core.recording_lifecycle.status(recording.recording_id)
    boundary = h.core.business_boundaries.view(h.project_id)
    with h.core.uow_factory() as work:
        resource_before = work.action_preparation.resources(h.action.action_id, 1)
        execution_before = work.action_preparation.execution(h.action.action_id, 1)
    after = h.core.recording_lifecycle.discard_review(recording.recording_id, now_us=200)
    assert after.recording.state is RecordingState.CANCELLED and after.capture_phase == "FINISHED"
    assert after.draft == before.draft
    assert after.recording.flow_id == before.recording.flow_id
    assert after.recording.browser_events == before.recording.browser_events
    events = after.recording.to_domain().events
    assert len(events) == len(before.recording.to_domain().events) + 1
    assert events[-1].operator == "RECORDING_SERVICE" and events[-1].reason_code == "CANCEL_REQUESTED"
    assert h.core.recording_lifecycle.discard_review(recording.recording_id, now_us=300) == after
    with h.core.uow_factory() as work:
        assert work.jobs.get(job.job_id) == job
        assert work.action_preparation.resources(h.action.action_id, 1) == resource_before
        assert work.action_preparation.execution(h.action.action_id, 1) == execution_before
        assert work.flow_drafts.latest(recording.recording_id).draft == before.draft
    assert h.core.recording_lifecycle.load_final_flow(Path(final.flow_path)) == flow_before
    assert h.core.business_boundaries.view(h.project_id) == boundary


@pytest.mark.parametrize("state", [RecordingState.CREATED, RecordingState.STARTING,
    RecordingState.RECORDING, RecordingState.CLEANING, RecordingState.PROCESSING,
    RecordingState.COMPLETED, RecordingState.FAILED, RecordingState.SAFETY_STOPPED])
def test_discard_rejects_other_recording_states_without_writes(harness, state):
    h = harness
    recording = add_recording(h)
    with h.core.uow_factory() as work:
        terminal = state in {RecordingState.COMPLETED, RecordingState.FAILED, RecordingState.SAFETY_STOPPED}
        work.recordings.replace(recording.model_copy(update={"state": state, "finished_at_us": 3 if terminal else None}))
        work.commit()
    _job(h, recording, JobState.SUCCEEDED)
    before = h.core.recording_lifecycle.status(recording.recording_id)
    with pytest.raises(JiejianError) as exc:
        h.core.recording_lifecycle.discard_review(recording.recording_id, now_us=200)
    assert exc.value.code == "RECORD_REVIEW_STATE"
    assert h.core.recording_lifecycle.status(recording.recording_id) == before


@pytest.mark.parametrize("problem", ["missing", "pending", "running", "retry_wait", "wrong_recording", "run"])
def test_discard_rejects_unfinished_or_mismatched_job(harness, monkeypatch, problem):
    h = harness
    recording = add_recording(h)
    before = h.core.recording_lifecycle.status(recording.recording_id)
    # 不可能通过数据库约束的错关联仅替换读端口，仍使用真实录制仓储与事务。
    job = None if problem == "missing" else SimpleNamespace(
        recording_id="rec_" + "f" * 32 if problem == "wrong_recording" else recording.recording_id,
        run_id="run_" + "f" * 32 if problem == "run" else None,
        state={"pending": JobState.PENDING, "running": JobState.RUNNING,
               "retry_wait": JobState.RETRY_WAIT}.get(problem, JobState.SUCCEEDED))
    factory = h.core.uow_factory
    @contextmanager
    def controlled():
        with factory() as work:
            work.jobs.get_by_recording = lambda _: job
            yield work
    monkeypatch.setattr(h.core.recording_lifecycle, "_uow_factory", controlled)
    with pytest.raises(JiejianError) as exc:
        h.core.recording_lifecycle.discard_review(recording.recording_id, now_us=200)
    assert exc.value.code == "RECORD_REVIEW_STATE"
    with factory() as work:
        assert work.recordings.get(recording.recording_id) == before.recording
        assert work.flow_drafts.latest(recording.recording_id).draft == before.draft


def test_discard_missing_recording(harness):
    with pytest.raises(JiejianError) as exc:
        harness.core.recording_lifecycle.discard_review("rec_" + "f" * 32, now_us=200)
    assert exc.value.code == "RECORD_NOT_FOUND"
