# 按任务类型和租约所有者惰性装配执行器，依赖由 WorkerContainer 显式提供。
# 只在对应任务被选择时构造其服务，不创建控制面的 ApplicationCore。

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from product.backend.infrastructure.artifacts.run_packages import attempt_paths_for
from product.backend.infrastructure.runtime.jobs.attempts import JobAttempts
from product.backend.infrastructure.runtime.jobs.handlers import JobHandlerRegistry
from product.backend.infrastructure.runtime.jobs.recording import RecordingJobHandler, RecordingSubmissionPort
from product.backend.infrastructure.runtime.jobs.targets import JobTargetType
from product.backend.infrastructure.recording.request_store import RecordingRequestStore
from product.backend.infrastructure.storage import StorageUnitOfWork


class WorkerHandlerFactory:
    """按 lease owner 为一个 Worker 构造惰性 Handler Registry。"""

    def __init__(
        self,
        var_dir: Path,
        uow_factory: Callable[..., StorageUnitOfWork],
        attempts: JobAttempts,
        recording_store: RecordingRequestStore,
        recording_submission_factory: Callable[[], RecordingSubmissionPort],
        proof_publisher=None,
        capture_publisher=None,
    ) -> None:
        self._var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._attempts = attempts
        self._recording_submission_factory = recording_submission_factory
        self._recording_store = recording_store
        self._proof_publisher = proof_publisher
        self._capture_publisher=capture_publisher

    def build_registry(
        self,
        lease_owner: str,
        environ: Mapping[str, str],
    ) -> JobHandlerRegistry:
        """按任务类型惰性装配执行器，不提前构造未选中的能力。"""

        registry = JobHandlerRegistry()
        def build_identity_handler():
            from product.backend.application.test_identities.login_execution import IdentityPreparationHandler
            return IdentityPreparationHandler(self._var_dir, lease_owner=lease_owner,
                uow_factory=self._uow_factory, attempts=self._attempts, environ=environ)
        registry.register(JobTargetType.IDENTITY_PREPARATION, build_identity_handler,
            operation_types=frozenset({'IDENTITY_PREPARATION'}))


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
        def build_check_handler():
            from product.backend.infrastructure.runtime.check_runner.supervisor import CheckJobHandler
            return CheckJobHandler(self._var_dir, lease_owner=lease_owner, uow_factory=self._uow_factory,
                attempts=self._attempts, environ=environ)
        registry.register(JobTargetType.RUN, build_check_handler, operation_types=frozenset({"CHECK"}))
        if self._proof_publisher is not None:
            def build_proof_handler():
                from product.backend.infrastructure.runtime.proof_runner.supervisor import ProofPreflightHandler
                return ProofPreflightHandler(self._var_dir, lease_owner=lease_owner,
                    uow_factory=self._uow_factory, attempts=self._attempts,
                    publisher=self._proof_publisher, environ=environ)
            registry.register(JobTargetType.PROOF_PREFLIGHT, build_proof_handler,
                operation_types=frozenset({"PROOF_PREFLIGHT"}))
        if self._capture_publisher is not None:
            def build_capture_handler():
                from product.backend.infrastructure.runtime.capture_runner.supervisor import ReferenceCaptureHandler
                return ReferenceCaptureHandler(self._var_dir,lease_owner=lease_owner,uow_factory=self._uow_factory,
                    attempts=self._attempts,publisher=self._capture_publisher,environ=environ)
            registry.register(JobTargetType.REFERENCE_CAPTURE,build_capture_handler,operation_types=frozenset({'REFERENCE_CAPTURE'}))
        return registry
