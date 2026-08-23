# =============================================================================
# Worker Handler Factory
#
# 定位
#   WorkerContainer 内的 Job Handler 组合边界。
#
# 职责
#   注入同一 ResultServices｜注册 Run/Recording/Artifact Check Handler。
#
# 边界
#   不创建 ApplicationCore，不拥有 GUI/Onboarding/LLM/Cache 服务。
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from product.backend.infra.artifacts.run_packages import attempt_paths_for
from product.backend.infra.artifacts.scan_job import ArtifactCheckJobHandler
from product.backend.infra.runtime.job_requests import ExecutionRequestStore
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.handlers import JobHandlerRegistry
from product.backend.infra.runtime.jobs.recording import RecordingJobHandler
from product.backend.infra.runtime.jobs.targets import JobTargetType
from product.backend.infra.runtime.jobs.verification import VerificationRunJobHandler
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.recording.submission import RecordingSubmission
from product.backend.workflows.results.services import ResultServices


class WorkerHandlerFactory:
    """按 lease owner 为一个 Worker 构造惰性 Handler Registry。"""

    def __init__(
        self,
        var_dir: Path,
        uow_factory: Callable[..., StorageUnitOfWork],
        attempts: JobAttempts,
        request_store: ExecutionRequestStore,
        result_services: ResultServices,
        publication_service,
        reconciliation_service,
    ) -> None:
        self._var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._attempts = attempts
        self._request_store = request_store
        self._results = result_services
        self._publication = publication_service
        self._reconciliation = reconciliation_service
        self._recording_store = RecordingRequestStore(self._var_dir)

    def build_registry(
        self,
        lease_owner: str,
        environ: Mapping[str, str],
    ) -> JobHandlerRegistry:
        """创建当前 Worker 的三类 Handler，并共享同一个 ResultFinalizer。"""

        registry = JobHandlerRegistry()

        def build_run_handler() -> VerificationRunJobHandler:
            return VerificationRunJobHandler(
                var_dir=self._var_dir,
                lease_owner=lease_owner,
                uow_factory=self._uow_factory,
                attempt_service=self._attempts,
                request_store=self._request_store,
                publication_service=self._publication,
                reconciliation_service=self._reconciliation,
                result_finalizer=self._results.finalizer,
                environ=environ,
            )

        def build_recording_handler() -> RecordingJobHandler:
            return RecordingJobHandler(
                var_dir=self._var_dir,
                lease_owner=lease_owner,
                uow_factory=self._uow_factory,
                attempts=self._attempts,
                application=RecordingSubmission(
                    self._uow_factory,
                    self._recording_store,
                    attempts=self._attempts,
                ),
                request_store=self._recording_store,
                cancel_path_for=lambda root, job: attempt_paths_for(root, job).cancel_path,
                environ=environ,
            )

        registry.register(JobTargetType.RUN, build_run_handler)
        registry.register(JobTargetType.RECORDING, build_recording_handler)
        registry.register_auxiliary("ARTIFACT_CHECK", self.build_artifact_check_handler)
        return registry

    def build_artifact_check_handler(self) -> ArtifactCheckJobHandler:
        """构造 Worker 专属的 Artifact Check Handler。"""

        return ArtifactCheckJobHandler(self._var_dir)
