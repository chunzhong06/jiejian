# =============================================================================
# WorkerContainer 组合根
#
# 定位
#   独立 Worker 进程的完整应用服务与基础设施装配边界。
#
# 职责
#   只读核验数据库，装配录制 Job、请求与结果接受服务。
#
# 边界
#   不继承 ApplicationCore，不创建 Cache、Onboarding、LLM 或 GUI 能力。
# =============================================================================

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path

from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.factory import WorkerHandlerFactory
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.jobs.targets import recording_job_targets
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.recording.submission import RecordingSubmission
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.infra.storage.db import require_current_database


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
        self.job_targets = recording_job_targets()
        self.job_attempts = JobAttempts(self.uow_factory, targets=self.job_targets)
        self.job_queue = JobQueue(self.uow_factory, targets=self.job_targets)
        self.recording_request_store = RecordingRequestStore(self.var_dir)
        self.recording_lifecycle = RecordingLifecycle(self.uow_factory, var_dir=self.var_dir)
        self.handler_factory = WorkerHandlerFactory(
            self.var_dir,
            self.uow_factory,
            self.job_attempts,
            self.recording_request_store,
            self._build_recording_submission,
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
