# =============================================================================
# Recording Run Service
#
# 定位
#   GUI、API 和 CLI 之外的 Recording 提交与 Worker 等待应用服务。
#
# 职责
#   解析最小秘密环境｜提交或接续 Recording Job｜协调明确采集并回收 Worker。
#
# 边界
#   不直接执行浏览器；目标动作仍由 Worker/Recording Runner 完成。
# =============================================================================

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.jobs.dispatch import WorkerDispatcher
from product.backend.infra.storage import StorageUnitOfWork
from product.protocols import required_recording_secret_names
from product.backend.workflows.recording.submission import RecordingSubmission


class RecordingRunService:
    """提交 Recording 并等待 Worker；调用方不再自行组合调度基础设施。"""

    def __init__(
        self,
        var_dir: Path,
        uow_factory: Callable[..., StorageUnitOfWork],
        submission: RecordingSubmission,
        environment_provider: Callable[[tuple[str, ...]], Mapping[str, str]],
        *,
        dispatcher_factory=WorkerDispatcher,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._submission = submission
        self._environment_provider = environment_provider
        self._dispatcher_factory = dispatcher_factory
        self._monotonic = monotonic
        self._sleep = sleep

    def run(
        self,
        command,
        *,
        timeout_seconds: int,
        secret_names: tuple[str, ...] = (),
    ):
        """提交一个 Recording Job，并在返回前完成 Worker 进程边界收尾。"""

        requested_names = required_recording_secret_names(command.request)
        if secret_names and tuple(secret_names) != requested_names:
            raise JiejianError(
                ErrorCode.RECORD_PROTOCOL_INVALID,
                "录制秘密引用与调用参数不一致",
            )
        environment = dict(self._environment_provider(requested_names))
        known_secrets = tuple(
            value for name in requested_names if (value := environment.get(name))
        )
        submission = self._submission.submit(command, known_secrets=known_secrets)
        dispatcher = self._dispatcher_factory(
            var_dir=self._var_dir,
            uow_factory=self._uow_factory,
            environ=environment,
        )
        process = dispatcher.start(
            job_id=submission.job.job_id,
            lease_owner=f"recording-worker-{os.getpid()}-{id(submission)}",
            secret_names=requested_names,
        )
        try:
            dispatcher.wait_recording(
                submission.job.job_id,
                process,
                timeout_seconds=timeout_seconds,
            )
        finally:
            dispatcher.close_process(process)
        return submission

    def capture(
        self,
        started,
        *,
        lifecycle,
        capture_control: Callable[[], None],
        timeout_seconds: int,
    ):
        """在同一控制者生命周期内启动、控制并收口一次已提交录制。"""

        requested_names = required_recording_secret_names(started.request)
        environment = dict(self._environment_provider(requested_names))
        submission = started.result
        dispatcher = self._dispatcher_factory(
            var_dir=self._var_dir,
            uow_factory=self._uow_factory,
            environ=environment,
        )
        process = dispatcher.start(
            job_id=submission.job.job_id,
            lease_owner=f"recording-worker-{os.getpid()}-{id(submission)}",
            secret_names=requested_names,
        )
        deadline = self._monotonic() + timeout_seconds
        try:
            self._wait_for_capture_phase(
                lifecycle,
                started.request.recording_id,
                process,
                deadline=deadline,
                expected="AWAITING_CAPTURE",
            )
            lifecycle.start_capture(started.request.recording_id)
            self._wait_for_capture_phase(
                lifecycle,
                started.request.recording_id,
                process,
                deadline=deadline,
                expected="CAPTURING",
            )
            control_error: BaseException | None = None
            try:
                capture_control()
            except BaseException as exc:
                control_error = exc
            finally:
                current = lifecycle.status(started.request.recording_id)
                if current.capture_phase == "CAPTURING":
                    lifecycle.stop_capture(started.request.recording_id)
            remaining = max(deadline - self._monotonic(), 0.05)
            dispatcher.wait_recording(
                submission.job.job_id,
                process,
                timeout_seconds=remaining,
            )
            if control_error is not None:
                raise control_error
            return lifecycle.status(started.request.recording_id)
        finally:
            dispatcher.close_process(process)

    def _wait_for_capture_phase(
        self,
        lifecycle,
        recording_id: str,
        process,
        *,
        deadline: float,
        expected: str,
    ):
        """有界等待 Runner 控制标记，进程提前退出时立即失败。"""

        while self._monotonic() < deadline:
            view = lifecycle.status(recording_id)
            if view.capture_phase == expected:
                return view
            if view.capture_phase == "FINISHED":
                raise JiejianError(
                    ErrorCode.RECORD_REPLAY_FAILED,
                    "Recording Worker 在采集控制完成前结束",
                )
            if process.poll() is not None:
                raise JiejianError(
                    ErrorCode.RUNNER_RESULT_MISSING,
                    "Recording Worker 在采集控制完成前退出",
                )
            self._sleep(0.05)
        raise JiejianError(ErrorCode.RUNNER_TIMEOUT, "等待 Recording 采集阶段超时")
