# 验证 Recording workflow 生命周期与当前 attempt 的持久化接线。

from __future__ import annotations
from uuid import uuid4
from pathlib import Path
import pytest
from product.backend.core.lifecycle import JobState
from product.backend.core.recording import RecordingState
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RecordingEventKind, RecordingRunnerResultType
from product.backend.workflows.recording.submission import SubmitRecording
from product.backend.infra.recording.control import (
    control_paths_for_attempt,
    write_control_marker,
)
from product.backend.infra.recording.browser import BrowserRecordingAdapter, RecordingBrowserSession
from product.backend.infra.runtime.jobs.recording import RecordingJobHandler
from product.backend.infra.runtime.jobs.models import ClaimJob
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.artifacts.run_packages import attempt_paths_for
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from tests.fixtures.recording import COOKIE_ENV_NAME, browser_server, recording_request, RecordingContext as _Context, runner_request as _request
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
                request=context.bind_request(request),
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
                    "project_id": context.project_id,
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
            request = context.bind_request(request)
            signals = {"start": False, "stop": False}

            def interact(session: RecordingBrowserSession) -> None:
                page = session.new_page(request.test_identity_id)
                page.goto(server.url("/ui"))
                signals["start"] = True
                assert session.wait_for_capture_start(page, request.test_identity_id)
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
                request=context.bind_request(request),
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
        assert all("/ui" not in (event.url or "") for event in result.events), [
            (event.kind.value, event.url) for event in result.events if "/ui" in (event.url or "")
        ]
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
        request = context.bind_request(request)
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
                request=context.bind_request(request),
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

def _context(tmp_path: Path) -> _Context:
    return _Context(tmp_path)


@pytest.mark.parametrize("name,value", [
    ("timeout_seconds", 2.0), ("timeout_seconds", 5.0),
    ("max_requests", 32), ("max_requests", 64),
    ("max_response_bytes", 65_536), ("max_response_bytes", 262_144),
])
def test_submission_allows_only_equal_or_narrower_budgets(tmp_path, name, value):
    context = _context(tmp_path)
    try:
        request = context.bind_request(_request("rec_" + uuid4().hex))
        request = request.model_copy(update={"target_scope": request.target_scope.model_copy(update={name: value})})
        job_id = "job_" + uuid4().hex
        submitted = context.application.submit(SubmitRecording(request=request, flow_id="budget-flow",
            idempotency_key=uuid4().hex, available_at_us=request.created_at_us,
            now_us=request.created_at_us, job_id=job_id))
        assert submitted.created is True
        stored = context.request_store.load(job_id, expected_hash=submitted.job.request_hash)
        assert getattr(stored.target_scope, name) == value
    finally:
        context.harness.close()


@pytest.mark.parametrize("scope_change", [
    {"timeout_seconds": 6.0}, {"max_requests": 65}, {"max_response_bytes": 262_145},
    {"allowed_origins": ("http://127.0.0.1:18080", "http://127.0.0.1:18081")},
    {"allowed_hosts": ("127.0.0.1", "127.0.0.2")},
    {"allowed_ports": (18080, 18081)},
    {"base_url": "http://127.0.0.1:18081", "allowed_origins": ("http://127.0.0.1:18081",), "allowed_ports": (18081,)},
    {"follow_redirects": True},
])
def test_submission_rejects_scope_expansion_without_orphaned_state(tmp_path, scope_change):
    context = _context(tmp_path)
    try:
        request = context.bind_request(_request("rec_" + uuid4().hex))
        request = request.model_copy(update={"target_scope": request.target_scope.model_copy(update=scope_change)})
        job_id = "job_" + uuid4().hex
        with pytest.raises(JiejianError) as error:
            context.application.submit(SubmitRecording(request=request, flow_id="scope-flow",
                idempotency_key=uuid4().hex, available_at_us=request.created_at_us,
                now_us=request.created_at_us, job_id=job_id))
        assert error.value.code == "RECORD_STATE_PRECONDITION"
        with context.uow_factory() as work:
            assert work.recordings.get(request.recording_id) is None
            assert work.jobs.get(job_id) is None
        assert not context.request_store.path_for(job_id).exists()
    finally:
        context.harness.close()


@pytest.mark.parametrize("source", ["deleted", "foreign"])
def test_new_recording_rejects_missing_or_foreign_identity(tmp_path, source):
    context = _context(tmp_path)
    try:
        request = context.bind_request(_request("rec_" + uuid4().hex))
        if source == "deleted":
            context.harness.core.test_identities.delete(request.test_identity_id)
        else:
            from product.backend.core.business_boundary import BusinessActor, boundary_sha256
            from product.backend.infra.storage import ProjectRecord
            from product.backend.core.lifecycle import ProjectStatus
            from product.backend.workflows.test_identities import PreparedLoginState
            from product.backend.core.test_identity import TestIdentityAuthMethod
            from tests.fixtures.assurance import actor
            # 使用同一数据库中真实存在且已准备的外项目身份，隔离项目所有权拒绝原因。
            revision = actor(actor_id="bar_" + "9" * 32).model_copy(update={"project_id": "foreign-project"})
            revision = revision.model_copy(update={"semantic_fingerprint": boundary_sha256(revision.semantic_payload())})
            with context.uow_factory() as work:
                work.projects.add(ProjectRecord(project_id="foreign-project", name="外项目",
                    status=ProjectStatus.READY, created_at_us=1, updated_at_us=1))
                work.business_boundaries.add_actor_revision(revision)
                work.business_boundaries.add_actor(BusinessActor(actor_id=revision.actor_id,
                    project_id="foreign-project", current_revision=1, created_at_us=1, updated_at_us=1))
                work.commit()
            core = context.harness.core
            foreign_id = core.test_identities.create("foreign-project",
                actor_id=revision.actor_id, actor_revision=1, label="外来账号")
            reference = f"cred:jiejian/test-identity/foreign-project/{foreign_id.identity_id}/bearer"
            core.secret_store.write(reference, "foreign-test-secret")
            core.test_identities.save_prepared_state(foreign_id.identity_id, PreparedLoginState(
                auth_method=TestIdentityAuthMethod.BEARER, bearer_secret_ref=reference,
                prepared_at_us=foreign_id.updated_at_us + 1))
            request = request.model_copy(update={"test_identity_id": foreign_id.identity_id,
                "sessions": (request.sessions[0].model_copy(update={"test_identity_id": foreign_id.identity_id}),)})
        job_id = "job_" + uuid4().hex
        with pytest.raises(JiejianError) as error:
            context.application.submit(SubmitRecording(request=request, flow_id="identity-flow",
                idempotency_key=uuid4().hex, available_at_us=request.created_at_us,
                now_us=request.created_at_us, job_id=job_id))
        assert error.value.code == "RECORD_STATE_PRECONDITION"
        with context.uow_factory() as work:
            assert work.recordings.get(request.recording_id) is None
            assert work.jobs.get(job_id) is None
        assert not context.request_store.path_for(job_id).exists()
    finally:
        context.harness.close()
