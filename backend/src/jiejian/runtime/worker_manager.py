# =============================================================================
# 本地 Worker 管理器
#
# 定位
#   API serve 生命周期与独立 Worker 调度循环之间的资源监督边界
#
# 职责
#   启停后台调度线程｜报告就绪状态｜确保 API 进程不执行目标流量
#
# 调用链
#   FastAPI lifespan → LocalWorkerManager → WorkerDispatcher
# =============================================================================

from __future__ import annotations

import threading
import time
from pathlib import Path
from uuid import uuid4

from ..storage import StorageUnitOfWork
from ..execution.dispatch import WorkerDispatcher
from ..execution.queue import JobQueueService
from ..execution.request_store import ExecutionRequestStore


class LocalWorkerManager:
    def __init__(
        self,
        var_dir: Path,
        uow_factory,
        job_queue: JobQueueService | None = None,
        environment_provider=None,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._job_queue = job_queue or JobQueueService(uow_factory)
        self._environment_provider = environment_provider or (lambda names: {})
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process = None
        self._job_id: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="jiejian-worker-manager", daemon=True)
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        process = self._process
        if process is not None and process.poll() is None:
            try:
                from ..execution.models import RequestCancellationV1

                if self._job_id is not None:
                    self._job_queue.request_cancellation(
                        RequestCancellationV1(
                            schema_version="1",
                            job_id=self._job_id,
                            now_us=time.time_ns() // 1_000,
                        )
                    )
            except Exception:
                pass
            try:
                process.wait(timeout=timeout)
            except Exception:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except Exception:
                    process.kill()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._process is None or self._process.poll() is not None:
                self._process = None
                self._job_id = None
                job = self._next_job()
                if job is not None:
                    secret_names = ()
                    if job.run_id is not None:
                        request = ExecutionRequestStore(self.var_dir).load(
                            job.job_id,
                            expected_hash=job.request_hash,
                        )
                        secret_names = tuple(
                            item.removeprefix("env:")
                            for item in (
                                identity.secret_ref
                                for identity in request.project_snapshot.identities
                            )
                        )
                    self._job_id = job.job_id
                    environment = self._environment_provider(secret_names)
                    self._process = WorkerDispatcher(
                        var_dir=self.var_dir,
                        uow_factory=self._uow_factory,
                        environ=environment,
                    ).start(
                        job_id=job.job_id,
                        lease_owner=f"serve-worker-{uuid4().hex}",
                        secret_names=secret_names,
                    )
            self._stop.wait(0.1)

    def _next_job(self):
        with self._uow_factory() as work:
            return work.jobs.next_pending()
