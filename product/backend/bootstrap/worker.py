# 装配独立 Worker 的任务领取、请求读取、执行器和结果发布服务。
# 复用当前数据库，不继承 Web 控制面的 ApplicationCore 或组装界面能力。

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path

from product.backend.infrastructure.recording.request_store import RecordingRequestStore
from product.backend.infrastructure.runtime.jobs.attempts import JobAttempts
from product.backend.infrastructure.runtime.jobs.factory import WorkerHandlerFactory
from product.backend.infrastructure.runtime.jobs.queue import JobQueue
from product.backend.infrastructure.runtime.jobs.registration import current_check_and_recording_targets
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.storage import StorageUnitOfWork
from product.backend.application.recording.submission import RecordingSubmission
from product.backend.application.recording.lifecycle import RecordingLifecycle
from product.backend.infrastructure.storage.db import require_current_database
from product.backend.application.preparation.proofs.jobs import ProofPreflightJobs
from product.backend.application.preparation.proofs.capture_jobs import ReferenceCaptureJobs


class WorkerContainer:
    """Worker 独立组合根；其生命周期只覆盖当前 Worker 进程。"""

    def __init__(
        self,
        var_dir: Path,
        *,
        environ: Mapping[str, str] | None = None,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        from product.backend.infrastructure.storage import (
            create_session_factory,
            create_sqlite_engine,
            default_database_path,
        )

        self.var_dir = var_dir.resolve()
        self.paths = RuntimePaths(self.var_dir).ensure_layout()
        self._environment = dict(environ if environ is not None else os.environ)
        database_path = default_database_path(self.var_dir)
        require_current_database(database_path)
        self.engine = create_sqlite_engine(database_path)
        self.uow_factory = partial(
            StorageUnitOfWork,
            create_session_factory(self.engine),
        )
        self.job_targets = current_check_and_recording_targets()
        self.job_attempts = JobAttempts(self.uow_factory, targets=self.job_targets)
        self.job_queue = JobQueue(self.uow_factory, targets=self.job_targets)
        from product.backend.infrastructure.runtime.jobs.registration import runtime_load_targets
        from product.backend.application.runtime.load_jobs import RuntimeLoadJobs
        self.runtime_attempts = JobAttempts(self.uow_factory,targets=runtime_load_targets())
        self.runtime_load_jobs = RuntimeLoadJobs(self.uow_factory)
        self.recording_request_store = RecordingRequestStore(self.var_dir)
        self.recording_lifecycle = RecordingLifecycle(self.uow_factory, var_dir=self.var_dir)
        self.handler_factory = WorkerHandlerFactory(
            self.var_dir,
            self.uow_factory,
            self.job_attempts,
            self.recording_request_store,
            self._build_recording_submission,
            proof_publisher=ProofPreflightJobs(self.var_dir, self.uow_factory),
            capture_publisher=ReferenceCaptureJobs(self.var_dir,self.uow_factory),
        )
        self._closed = False

    def _build_recording_submission(self) -> RecordingSubmission:
        """在组合根创建应用服务，Infra Factory 只接收已冻结的窄能力。"""

        return RecordingSubmission(
            self.uow_factory,
            self.recording_request_store,
            attempts=self.job_attempts,
            finalize_recording=self.recording_lifecycle.finalize_if_unambiguous,
        )

    def close(self) -> None:
        """释放 Worker 独占的数据库 Engine；重复关闭保持幂等。"""

        if self._closed:
            return
        self._closed = True
        self.engine.dispose()
