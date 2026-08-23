# =============================================================================
# Recording Run Service
#
# 定位
#   GUI、API 和 CLI 之外的 Recording 提交与 Worker 等待应用服务。
#
# 职责
#   解析最小秘密环境｜提交 Recording Job｜等待并回收 Recording Worker。
#
# 边界
#   不直接执行浏览器；目标动作仍由 Worker/Recording Runner 完成。
# =============================================================================

from __future__ import annotations

import os
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
    ) -> None:
        self._var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._submission = submission
        self._environment_provider = environment_provider

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
        dispatcher = WorkerDispatcher(
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
