# =============================================================================
# Verification Run JobHandler
#
# 定位
#   Execution 通用 Handler 端口的 Verification Run 实现
#
# 职责
#   先尝试 publication 对账｜监督当前 Runner attempt｜返回可信 staged attempt
#
# 边界
#   只有完整性重验通过的 publication 或 staging 才能推进完成态。
#
# 调用链
#   JobHandlerRegistry → VerificationRunJobHandler → Reconciliation / RunnerSupervisor
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import JobRecord, StorageUnitOfWork
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.handlers import JobHandler
from product.backend.infra.artifacts.run_packages import StagedAttempt
from product.backend.infra.artifacts.run_publication import RunPublisher
from product.backend.infra.runtime.jobs.reconciliation import RunReconciler
from product.backend.infra.runtime.job_requests import ExecutionRequestStore, required_secret_names
from product.backend.infra.runtime.runner_supervisor import RunnerSupervisor
from product.backend.workflows.results.finalizer import ResultFinalizer
import logging


_LOGGER = logging.getLogger(__name__)


class VerificationRunJobHandler(JobHandler[StagedAttempt]):
    """为单个 Run Job 组合请求、恢复、监督和发布服务。"""

    def __init__(
        self,
        *,
        var_dir: Path,
        lease_owner: str,
        uow_factory: Callable[..., StorageUnitOfWork],
        attempt_service: JobAttempts,
        request_store: ExecutionRequestStore,
        publication_service: RunPublisher,
        reconciliation_service: RunReconciler,
        result_finalizer: ResultFinalizer,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._request_store = request_store
        self._reconciliation = reconciliation_service
        self._result_finalizer = result_finalizer
        self._environ = environ or {}
        self._prepared = False
        self._known_secrets: tuple[str, ...] = ()
        self._supervisor = RunnerSupervisor(
            var_dir=var_dir,
            lease_owner=lease_owner,
            uow_factory=uow_factory,
            attempt_service=attempt_service,
            request_store=request_store,
            publication_service=publication_service,
            environ=self._environ,
        )

    def run_job(self, job_id: str) -> StagedAttempt | None:
        """准备恢复环境后执行验证任务；只有实际领取成功时返回 staged attempt。"""

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
            # Worker 首次执行前修复上次崩溃留下的工件/数据库分歧，随后复用该恢复点。
            self._reconciliation.reconcile(known_secrets=self._known_secrets)
            self._prepared = True
        try:
            staged = self._supervisor.run_job(job_id)
            if staged is not None and staged.result.result_type.value in {"SUCCESS", "SAFETY_STOPPED"}:
                try:
                    self._result_finalizer.finalize(staged.result.run_id)
                except JiejianError as exc:
                    _LOGGER.error("结果最终化未能完成", extra={"code": exc.code, "run_id": staged.result.run_id})
            return staged
        except JiejianError:
            # 失败路径仍需收敛可能已完成 publication 但尚未提交数据库的窗口。
            self._reconciliation.reconcile(known_secrets=self._known_secrets)
            raise
