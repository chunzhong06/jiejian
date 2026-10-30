# 验证录制审阅的修订、来源核对、明确放弃和历史资产保留。

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from product.backend.domain.errors import JiejianError
from product.backend.domain.lifecycle import JobState
from product.backend.domain.recording.models import RecordingPurpose, RecordingState
from product.backend.infrastructure.storage.execution.jobs import JobRecord
from tests.support.builders.preparation.action_preparation import add_recording, build_preparation_harness
from product.backend.infrastructure.recording.flows import read_recorded_flow
from product.protocols.recording.flow_draft import RefreshFlowDraftResources
from tests.application.recording._support_project_submission import _arguments
from tests.support.builders.preparation.recording import RecordingContext
from tests.support.builders.preparation.recording_facts import captured_result


@pytest.fixture
def harness(tmp_path):
    h = build_preparation_harness(tmp_path)
    yield h
    h.close()


def _job(h, recording, state):
    from sqlalchemy import update
    from product.backend.infrastructure.storage.execution.jobs import JobRow
    # fixture 已有来源 Job；仅构造本测试需要的终态，保留原请求 hash 与唯一录制关联。
    with h.core.engine.begin() as connection:
        connection.execute(update(JobRow).where(JobRow.recording_id == recording.recording_id).values(state=state.value))
    with h.core.uow_factory() as work:
        job = work.jobs.get_by_recording(recording.recording_id)
        assert job is not None
    return job


@pytest.mark.parametrize('stale_revision', [False, True])
def test_resource_refresh_uses_saved_events_and_preserves_the_original_revision(tmp_path, stale_revision):
    # 先持久化受控事件，再只走审阅刷新；保护原事实和修订，不以重新发目标请求补齐候选。
    context = RecordingContext(tmp_path)
    core = context.harness.core
    try:
        events = tuple(event.model_copy(update={'identity_id': context.harness.identities[0].identity_id})
            for event in captured_result('rec_' + 'a' * 32, project_id=context.project_id).events)
        submitted = core.project_recordings.submit_captured(context.project_id, events=events, **_arguments(context))
        recording_id = submitted.result.recording.recording_id
        before = core.recording_lifecycle.status(recording_id)
        command = RefreshFlowDraftResources(operation='REFRESH_RESOURCE_CANDIDATES',
            expected_revision=before.draft.revision + int(stale_revision))
        if stale_revision:
            with pytest.raises(JiejianError) as rejected:
                core.recording_lifecycle.review(recording_id, command)
            assert rejected.value.code == 'RECORD_REVIEW_STATE'
            assert core.recording_lifecycle.status(recording_id) == before
        else:
            after = core.recording_lifecycle.review(recording_id, command)
            assert after.draft.revision == before.draft.revision + 1
            assert after.recording == before.recording
            assert after.draft.target_step_id == before.draft.target_step_id
        with context.uow_factory() as work:
            revisions = work.flow_drafts.list_for_recording(recording_id)
            original = next(item for item in revisions if item.revision == before.draft.revision)
            assert original.draft == before.draft
            assert len(work.jobs.list_for_project(context.project_id)) == 1
    finally:
        context.harness.close()


@pytest.mark.parametrize("job_state", [JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED])
def test_discard_review_preserves_history_bindings_and_job_and_is_idempotent(harness, job_state):
    h = harness
    target = add_recording(h)
    final = h.core.recording_lifecycle.finalize(target.recording_id, var_dir=h.var_dir, now_us=100)
    flow_before = read_recorded_flow(Path(final.flow_path))
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
    assert read_recorded_flow(Path(final.flow_path)) == flow_before
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

pytestmark = [pytest.mark.level3]
