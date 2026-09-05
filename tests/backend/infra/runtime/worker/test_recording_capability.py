# =============================================================================
# Recording-only Worker 能力直接测试
#
# 定位
#   验证当前 Worker 装配、SQLite 目标过滤、线程生命周期与秘密边界。
#
# 边界
#   只使用离线 SQLite 和受控端口替身，不启动产品实例、浏览器、网络或外部凭据。
# =============================================================================

from __future__ import annotations

import time
from pathlib import Path
from threading import Event

import pytest
import product.backend.infra.runtime.worker.supervisor as worker_supervisor_module
from product.backend.composition.worker import WorkerContainer
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState, RunLifecycle
from product.backend.infra.runtime.jobs.models import (
    ClaimJob,
    ConfirmRecovery,
    RecoveryOperator,
    RecoveryProofType,
    RecoveryReasonCode,
    RecoveryScan,
)
from product.backend.infra.runtime.jobs.targets import JobTargetType
from product.backend.infra.runtime.process.environment import (
    ProcessEnvironmentRole,
    minimal_process_environment,
)
from product.backend.infra.storage import JobRecord, RunRecord, default_database_path
from tests.fixtures.action_preparation import PreparationHarness, build_preparation_harness
from tests.fixtures.control_plane import TestClient as ControlPlaneTestClient
from tests.fixtures.control_plane import create_app as create_control_plane_app
from tests.fixtures.runtime_environment import runtime_identity_environment


def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    """用有界事件等待观察线程事实，避免通过任意长睡眠掩盖生命周期问题。"""

    deadline = time.monotonic() + timeout
    gate = Event()
    while time.monotonic() < deadline:
        if predicate():
            return
        gate.wait(0.01)
    assert predicate()


def _submit_recording(harness: PreparationHarness, suffix: str = "recording"):
    """从真实当前动作、身份和 source fingerprint 提交正式 Recording Job。"""

    return harness.core.project_recordings.submit(
        harness.project_id,
        business_action_id=harness.action.action_id,
        action_revision=harness.action.revision,
        test_identity_id=harness.identities[0].identity_id,
        duration_seconds=1,
        idempotency_key=f"worker-{suffix}",
        headless=True,
    )


def _run_and_job(
    project_id: str,
    ordinal: int,
    *,
    now_us: int,
    state: JobState = JobState.PENDING,
    lease_owner: str | None = None,
    fencing_token: int = 0,
    lease_expires_at_us: int | None = None,
) -> tuple[RunRecord, JobRecord]:
    """构造满足外键、生命周期和 attempt/fence 矩阵的正式 Run/Job 聚合。"""

    suffix = f"{ordinal:032x}"
    run_id = f"run_{suffix}"
    job_id = f"job_{suffix}"
    run_state = RunLifecycle.RUNNING if state is JobState.RUNNING else RunLifecycle.QUEUED
    run = RunRecord(
        run_id=run_id,
        project_id=project_id,
        contract_id="worker-fixture-contract",
        contract_version=1,
        engine_version="worker-fixture",
        lifecycle=run_state,
        verdict=None,
        created_at_us=now_us,
        updated_at_us=now_us,
        finished_at_us=None,
    )
    job = JobRecord(
        job_id=job_id,
        project_id=project_id,
        run_id=run_id,
        recording_id=None,
        operation_type="RUN",
        state=state,
        idempotency_key=f"run-fixture-{ordinal}",
        request_hash="a" * 64,
        attempt=1 if state is JobState.RUNNING else 0,
        max_attempts=3,
        available_at_us=now_us,
        lease_owner=lease_owner,
        fencing_token=fencing_token,
        lease_expires_at_us=lease_expires_at_us,
        cancel_requested_at_us=None,
        created_at_us=now_us,
        updated_at_us=now_us,
    )
    return run, job


def _insert_runs(harness: PreparationHarness, rows: tuple[tuple[RunRecord, JobRecord], ...]) -> None:
    with harness.core.uow_factory() as work:
        for run, job in rows:
            work.runs.add(run)
            work.jobs.add(job)
        work.commit()


def _read_job(harness: PreparationHarness, job_id: str) -> JobRecord:
    with harness.core.uow_factory() as work:
        job = work.jobs.get(job_id)
    assert job is not None
    return job


def test_application_core_worker_is_recording_only_and_lifecycle_is_idempotent(tmp_path: Path) -> None:
    harness = build_preparation_harness(tmp_path)
    try:
        core = harness.core
        assert core.worker_status() == {
            "worker": "stopped",
            "worker_capabilities": ("RECORDING",),
            "check": "unavailable",
            "recovered_jobs": 0,
        }
        assert not core.worker.is_running()

        core.worker.start()
        _wait_until(core.worker.is_running)
        thread = core.worker._thread
        core.worker.start()
        assert core.worker._thread is thread
        assert core.worker_status()["worker"] == "running"

        core.worker.stop(timeout=2.0)
        assert not core.worker.is_running()
        core.worker.stop(timeout=2.0)
        assert core.worker_status()["worker"] == "stopped"
    finally:
        harness.close()


def test_sqlite_claim_and_next_job_filter_run_before_limit_and_explicit_claim(tmp_path: Path) -> None:
    harness = build_preparation_harness(tmp_path)
    try:
        now_us = time.time_ns() // 1_000
        runs = tuple(
            _run_and_job(harness.project_id, index + 1, now_us=now_us - 100)
            for index in range(24)
        )
        _insert_runs(harness, runs)
        submitted = _submit_recording(harness, "filter")

        selected = harness.core.worker._next_job()
        assert selected is not None
        assert selected.job_id == submitted.result.job.job_id
        claimed = harness.core.job_attempts.claim(
            ClaimJob(
                lease_owner="recording-test-worker",
                now_us=now_us + 1_000_000,
                lease_duration_us=10_000,
            )
        )
        assert claimed is not None
        assert claimed.job.recording_id == submitted.result.recording.recording_id
        assert _read_job(harness, runs[0][1].job_id).state is JobState.PENDING
        assert _read_job(harness, runs[0][1].job_id).attempt == 0
        assert _read_job(harness, runs[0][1].job_id).fencing_token == 0

        with pytest.raises(JiejianError):
            harness.core.job_attempts.claim(
                ClaimJob(
                    job_id=runs[0][1].job_id,
                    lease_owner="recording-test-worker",
                    now_us=now_us + 1_000_001,
                    lease_duration_us=10_000,
                )
            )
        unchanged = _read_job(harness, runs[0][1].job_id)
        assert (unchanged.state, unchanged.attempt, unchanged.fencing_token) == (
            JobState.PENDING,
            0,
            0,
        )
    finally:
        harness.close()


def test_all_run_queue_is_invisible_to_recording_worker(tmp_path: Path) -> None:
    harness = build_preparation_harness(tmp_path)
    try:
        now_us = time.time_ns() // 1_000
        rows = tuple(
            _run_and_job(harness.project_id, index + 100, now_us=now_us)
            for index in range(3)
        )
        _insert_runs(harness, rows)
        assert harness.core.worker._next_job() is None
        with pytest.raises(JiejianError):
            harness.core.job_attempts.claim(
                ClaimJob(
                    job_id=rows[0][1].job_id,
                    lease_owner="recording-only",
                    now_us=now_us + 1,
                    lease_duration_us=10_000,
                )
            )
        assert _read_job(harness, rows[0][1].job_id).state is JobState.PENDING
    finally:
        harness.close()


def test_recovery_filters_run_before_limit_and_rejects_unsupported_run(tmp_path: Path) -> None:
    harness = build_preparation_harness(tmp_path)
    try:
        now_us = time.time_ns() // 1_000
        run, run_job = _run_and_job(
            harness.project_id,
            200,
            now_us=now_us - 10_000,
            state=JobState.RUNNING,
            lease_owner="run-owner",
            fencing_token=4,
            lease_expires_at_us=now_us - 1,
        )
        _insert_runs(harness, ((run, run_job),))
        submitted = _submit_recording(harness, "recovery")
        recording_claim = harness.core.job_attempts.claim(
            ClaimJob(
                job_id=submitted.result.job.job_id,
                lease_owner="recording-owner",
                now_us=now_us + 1_000_000,
                lease_duration_us=1,
            )
        )
        assert recording_claim is not None
        candidates = harness.core.worker._recovery.list_recovery_candidates(
            RecoveryScan(now_us=now_us + 1_000_001, limit=1)
        )
        assert len(candidates) == 1
        assert candidates[0].recording_id == submitted.result.recording.recording_id
        assert candidates[0].run_id is None

        with pytest.raises(JiejianError):
            harness.core.worker._recovery.confirm_recovery(
                ConfirmRecovery(
                    job_id=run_job.job_id,
                    lease_owner="run-owner",
                    fencing_token=4,
                    now_us=now_us + 1_000_001,
                    proof_type=RecoveryProofType.EXECUTION_EXITED,
                    operator=RecoveryOperator.WORKER_SUPERVISOR,
                    reason_code=RecoveryReasonCode.PROCESS_EXIT_CONFIRMED,
                )
            )
        unchanged = _read_job(harness, run_job.job_id)
        assert (unchanged.state, unchanged.fencing_token) == (JobState.RUNNING, 4)
    finally:
        harness.close()


class _ExitedProcess:
    returncode = 0

    def poll(self) -> int:
        return self.returncode

    def wait(self, timeout: float) -> int:
        return self.returncode


class _HangingProcess:
    returncode = None

    def poll(self) -> None:
        return None

    def wait(self, timeout: float) -> None:
        raise TimeoutError(timeout)


def test_shutdown_releases_exited_process_and_preserves_timed_out_handle(tmp_path: Path, monkeypatch) -> None:
    released: list[object] = []
    monkeypatch.setattr(
        worker_supervisor_module,
        "release_process_tree",
        lambda process, timeout=2.0: released.append((process, timeout)),
    )
    manager = worker_supervisor_module.LocalWorkerSupervisor(tmp_path / "var", lambda: None)
    manager._job_id = "job_" + "d" * 32
    monkeypatch.setattr(manager, "_finish_worker_exit", lambda *_args: None)
    exited = _ExitedProcess()
    manager._process = exited
    manager.stop(timeout=0.1)
    assert released == [(exited, 2.0)]
    assert manager._process is None

    hanging = _HangingProcess()
    manager._job_id = None
    manager._process = hanging
    monkeypatch.setattr(
        worker_supervisor_module,
        "terminate_process_tree",
        lambda *_args: (_ for _ in ()).throw(
            JiejianError(ErrorCode.PROCESS_TREE_FAILED, "controlled timeout")
        ),
    )
    with pytest.raises(JiejianError) as error:
        manager.stop(timeout=0.1)
    assert error.value.code == ErrorCode.PROCESS_TREE_FAILED.value
    assert manager._process is hanging


def test_stop_timeout_truthfully_keeps_thread_and_application_close_keeps_resources(
    tmp_path: Path, monkeypatch
) -> None:
    manager = worker_supervisor_module.LocalWorkerSupervisor(tmp_path / "var", lambda: None)
    blocked = Event()
    manager._loop = blocked.wait
    manager.start()
    _wait_until(manager.is_running)
    try:
        with pytest.raises(JiejianError) as error:
            manager.stop(timeout=0.01)
        assert error.value.code == ErrorCode.PROCESS_TREE_FAILED.value
        assert manager.is_running()
        assert manager._thread is not None
    finally:
        blocked.set()
        manager._thread.join(timeout=1.0)
        assert not manager.is_running()

    close_root = tmp_path / "close"
    close_root.mkdir()
    harness = build_preparation_harness(close_root)
    try:
        disposed = []
        cleared = []
        def fail_stop(timeout: float = 5.0) -> None:
            raise JiejianError(ErrorCode.PROCESS_TREE_FAILED, "worker stop failed")

        # 断言期间拦截释放；离开替身作用域后必须用真实 close 收口 fixture。
        with monkeypatch.context() as patch:
            patch.setattr(harness.core.engine, "dispose", lambda: disposed.append(True))
            patch.setattr(harness.core.runtime_secrets, "clear", lambda: cleared.append(True))
            patch.setattr(harness.core.worker, "stop", fail_stop)
            with pytest.raises(JiejianError):
                harness.core.close()
        assert disposed == []
        assert cleared == []
    finally:
        harness.close()


def test_worker_container_is_recording_only_and_does_not_upgrade_missing_database(tmp_path: Path) -> None:
    current_root = tmp_path / "current"
    current_root.mkdir()
    harness = build_preparation_harness(current_root)
    try:
        container = WorkerContainer(harness.var_dir, environ={})
        try:
            assert container.job_targets.target_types == (JobTargetType.RECORDING,)
            registry = container.handler_factory.build_registry("recording-worker", {})
            recording_job = JobRecord(
                job_id="job_" + "b" * 32,
                project_id=harness.project_id,
                run_id=None,
                recording_id="rec_" + "b" * 32,
                operation_type="BROWSER_RECORDING",
                state=JobState.PENDING,
                idempotency_key="container-recording",
                request_hash="b" * 64,
                attempt=0,
                max_attempts=3,
                available_at_us=1,
                lease_owner=None,
                fencing_token=0,
                lease_expires_at_us=None,
                cancel_requested_at_us=None,
                created_at_us=1,
                updated_at_us=1,
            )
            assert registry.resolve(recording_job) is not None
            run_job = recording_job.model_copy(
                update={
                    "job_id": "job_" + "c" * 32,
                    "run_id": "run_" + "c" * 32,
                    "recording_id": None,
                    "operation_type": "RUN",
                    "request_hash": "c" * 64,
                    "idempotency_key": "container-run",
                }
            )
            with pytest.raises(JiejianError):
                registry.resolve(run_job)
        finally:
            container.close()
            container.close()

        missing = tmp_path / "missing"
        with pytest.raises(JiejianError):
            WorkerContainer(missing, environ={})
        assert not default_database_path(missing).exists()
    finally:
        harness.close()


def test_recording_secret_resolution_is_requested_and_worker_allowlist_is_minimal(tmp_path: Path) -> None:
    harness = build_preparation_harness(tmp_path)
    try:
        submitted = _submit_recording(harness, "secrets")
        secret_name = submitted.request.sessions[0].bearer_ref
        assert secret_name is not None
        secret_name = secret_name.removeprefix("env:")
        harness.core._base_environment["JIEJIAN_RECORDING_PARENT"] = "parent-secret"
        environment = harness.core.environment_for_secret_names((secret_name,))
        assert environment[secret_name] == "fixture-secret"
        assert "JIEJIAN_RECORDING_PARENT" not in environment
        with pytest.raises(JiejianError):
            harness.core.environment_for_secret_names(("JIEJIAN_RECORDING_MISSING",))

        filtered = minimal_process_environment(
            runtime_identity_environment(
                harness.var_dir,
                extra={secret_name: environment[secret_name], "EXTRA": "not-allowed"},
            ),
            role=ProcessEnvironmentRole.WORKER,
            secret_names=(secret_name,),
        )
        assert filtered[secret_name] == "fixture-secret"
        assert "EXTRA" not in filtered
        assert "fixture-secret" not in submitted.request.model_dump_json()
    finally:
        harness.close()


def test_control_plane_ready_and_status_follow_worker_lifecycle_without_writer(tmp_path: Path) -> None:
    stopped_app = create_control_plane_app(tmp_path / "stopped", start_worker=False)
    with ControlPlaneTestClient(stopped_app) as client:
        ready = client.get("/ready")
        status = client.get("/api/system/status")
        assert ready.status_code == 200
        assert ready.json()["worker"] == "stopped"
        assert ready.json()["worker_capabilities"] == ["RECORDING"]
        assert ready.json()["check"] == "unavailable"
        assert status.json()["data"]["worker"] == "stopped"
        assert status.json()["data"]["worker_capabilities"] == ["RECORDING"]
        assert status.json()["data"]["check"] == "unavailable"

    running_app = create_control_plane_app(tmp_path / "running", start_worker=True)
    with ControlPlaneTestClient(running_app) as client:
        _wait_until(lambda: running_app.state.context.worker.is_running())
        assert client.get("/ready").json()["worker"] == "running"
        assert client.get("/api/system/status").json()["data"]["worker"] == "running"
    assert not running_app.state.context.worker.is_running()
