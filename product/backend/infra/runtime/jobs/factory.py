# =============================================================================
# Worker Handler Factory
#
# 定位
#   WorkerContainer 内的 Job Handler 组合边界。
#
# 职责
#   只注册真实 Recording Handler，并注入录制结果接受服务。
#
# 边界
#   不创建 ApplicationCore，不拥有 GUI/Onboarding/LLM/Cache 服务。
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from product.backend.infra.artifacts.run_packages import attempt_paths_for
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.handlers import JobHandlerRegistry
from product.backend.infra.runtime.jobs.recording import (
    RecordingJobHandler,
    RecordingSubmissionPort,
)
from product.backend.infra.runtime.jobs.targets import JobTargetType
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.storage import StorageUnitOfWork


class WorkerHandlerFactory:
    """按 lease owner 为一个 Worker 构造惰性 Handler Registry。"""

    def __init__(
        self,
        var_dir: Path,
        uow_factory: Callable[..., StorageUnitOfWork],
        attempts: JobAttempts,
        recording_store: RecordingRequestStore,
        recording_submission_factory: Callable[[], RecordingSubmissionPort],
    ) -> None:
        self._var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._attempts = attempts
        self._recording_submission_factory = recording_submission_factory
        self._recording_store = recording_store

    def build_registry(
        self,
        lease_owner: str,
        environ: Mapping[str, str],
    ) -> JobHandlerRegistry:
        """创建只含录制能力的 Handler；不装配 Run 或安全检查。"""

        registry = JobHandlerRegistry()

        def build_recording_handler() -> RecordingJobHandler:
            return RecordingJobHandler(
                var_dir=self._var_dir,
                lease_owner=lease_owner,
                uow_factory=self._uow_factory,
                attempts=self._attempts,
                application=self._recording_submission_factory(),
                request_store=self._recording_store,
                cancel_path_for=lambda root, job: attempt_paths_for(root, job).cancel_path,
                environ=environ,
            )

        registry.register(JobTargetType.RECORDING, build_recording_handler)
        return registry
