# =============================================================================
# Verification Run JobHandler
#
# 定位
#   Execution 通用 Handler 端口的 Verification Run 实现
#
# 职责
#   先尝试 publication 对账｜监督当前 Runner attempt｜返回可信 staged attempt
#
# 调用链
#   JobHandlerRegistry → VerificationRunJobHandler → Reconciliation / WorkerSupervisor
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from ..errors import ErrorCode, JiejianError
from ..storage import JobRecord, StorageUnitOfWork
from .attempts import JobAttemptService
from .handlers import JobHandler
from .published_artifacts import StagedAttempt
from .publication import RunPublicationService
from .reconciliation import RunReconciliationService
from .request_store import ExecutionRequestStore, required_secret_names
from .supervisor import WorkerSupervisor


class VerificationRunJobHandler(JobHandler[StagedAttempt]):
    """为单个 Run Job 组合请求、恢复、监督和发布服务。"""

    def __init__(
        self,
        *,
        var_dir: Path,
        lease_owner: str,
        uow_factory: Callable[..., StorageUnitOfWork],
        attempt_service: JobAttemptService,
        request_store: ExecutionRequestStore,
        publication_service: RunPublicationService,
        reconciliation_service: RunReconciliationService,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._request_store = request_store
        self._reconciliation = reconciliation_service
        self._environ = environ or {}
        self._prepared = False
        self._known_secrets: tuple[str, ...] = ()
        self._supervisor = WorkerSupervisor(
            var_dir=var_dir,
            lease_owner=lease_owner,
            uow_factory=uow_factory,
            attempt_service=attempt_service,
            request_store=request_store,
            publication_service=publication_service,
            environ=self._environ,
        )

    def run_job(self, job_id: str) -> StagedAttempt | None:
        if not self._prepared:
            with self._uow_factory() as work:
                job = work.jobs.get(job_id)
            if job is None:
                raise JiejianError(ErrorCode.JOB_NOT_FOUND, "任务不存在")
            request = self._request_store.load(
                job_id,
                expected_hash=job.request_hash,
            )
            secret_names = required_secret_names(request)
            self._known_secrets = tuple(
                self._environ[name]
                for name in secret_names
                if self._environ.get(name)
            )
            self._reconciliation.reconcile(known_secrets=self._known_secrets)
            self._prepared = True
        try:
            return self._supervisor.run_job(job_id)
        except JiejianError:
            self._reconciliation.reconcile(known_secrets=self._known_secrets)
            raise
