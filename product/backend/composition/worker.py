# =============================================================================
# WorkerContainer 组合根
#
# 定位
#   独立 Worker 进程的完整应用服务与基础设施装配边界。
#
# 职责
#   创建 RuntimePaths、Storage、Job、Request、Publication 和结果派生服务。
#
# 边界
#   不继承 ApplicationCore，不创建 Cache、Onboarding、LLM 或 GUI 能力。
# =============================================================================

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path

from product.backend.infra.artifacts.run_publication import RunPublisher
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.factory import WorkerHandlerFactory
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.jobs.reconciliation import RunReconciler
from product.backend.infra.runtime.jobs.recording import RecordingJobTargetHandler
from product.backend.infra.runtime.jobs.requests import ExecutionRequestStore
from product.backend.infra.runtime.jobs.targets import (
    JobTargetType,
    default_run_job_targets,
)
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.recording.submission import RecordingSubmission
from product.backend.workflows.results.services import ResultServices, build_result_services


class WorkerContainer:
    """Worker 独立组合根；其生命周期只覆盖当前 Worker 进程。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        environ: Mapping[str, str] | None = None,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        from product.backend.infra.storage import (
            create_session_factory,
            create_sqlite_engine,
            default_database_path,
            upgrade_database,
        )

        self.var_dir = var_dir.resolve()
        self.paths = RuntimePaths(self.var_dir).ensure_layout()
        self._environment = dict(environ if environ is not None else os.environ)
        database_path = default_database_path(self.var_dir)
        upgrade_database(database_path)
        self.engine = create_sqlite_engine(database_path)
        self.uow_factory = partial(
            StorageUnitOfWork,
            create_session_factory(self.engine),
        )
        self.job_targets = default_run_job_targets()
        self.job_targets.register(
            JobTargetType.RECORDING,
            RecordingJobTargetHandler(),
        )
        self.job_attempts = JobAttempts(self.uow_factory, targets=self.job_targets)
        self.job_queue = JobQueue(self.uow_factory, targets=self.job_targets)
        self.execution_request_store = ExecutionRequestStore(self.var_dir)
        self.recording_request_store = RecordingRequestStore(self.var_dir)
        self.run_publisher = RunPublisher(self.var_dir, self.uow_factory)
        self.run_reconciler = RunReconciler(
            self.var_dir,
            self.uow_factory,
            self.run_publisher,
        )
        self.result_services: ResultServices = build_result_services(
            self.var_dir,
            self.uow_factory,
            clock_us=clock_us,
        )
        self.results = self.result_services.reader
        self.finding_materializer = self.result_services.materializer
        self.findings = self.result_services.queries
        self.gating = self.result_services.gate
        self.reports = self.result_services.reports
        self.result_finalizer = self.result_services.finalizer
        self.handler_factory = WorkerHandlerFactory(
            self.var_dir,
            self.uow_factory,
            self.job_attempts,
            self.execution_request_store,
            self.result_finalizer,
            self.recording_request_store,
            self._build_recording_submission,
            self.run_publisher,
            self.run_reconciler,
        )
        self._closed = False

    def _build_recording_submission(self) -> RecordingSubmission:
        """在组合根创建应用服务，Infra Factory 只接收已冻结的窄能力。"""

        return RecordingSubmission(
            self.uow_factory,
            self.recording_request_store,
            attempts=self.job_attempts,
        )

    def close(self) -> None:
        """释放 Worker 独占的数据库 Engine；重复关闭保持幂等。"""

        if self._closed:
            return
        self._closed = True
        self.engine.dispose()
