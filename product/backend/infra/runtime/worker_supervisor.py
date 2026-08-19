# =============================================================================
# 本地 Worker 管理器
#
# 定位
#   API serve 生命周期与独立 Worker 调度循环之间的资源监督边界
#
# 职责
#   启停后台调度线程｜报告就绪状态｜确保 API 进程不执行目标流量
#
# 边界
#   监督器只管理 Worker 调度线程；目标请求仍由独立 Runner 进程执行。
#
# 调用链
#   FastAPI lifespan → LocalWorkerSupervisor → WorkerDispatcher
# =============================================================================

from __future__ import annotations

import threading
import time
import logging
from pathlib import Path
from uuid import uuid4

from product.backend.infra.storage import StorageUnitOfWork
from product.backend.infra.runtime.jobs.dispatch import WorkerDispatcher
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.job_requests import ExecutionRequestStore, required_secret_names

logger = logging.getLogger("jiejian.runtime.worker_supervisor")


class LocalWorkerSupervisor:
    """在服务生命周期内拥有唯一后台 Worker 线程，并负责确定性停止。"""

    def __init__(
        self,
        var_dir: Path,
        uow_factory,
        job_queue: JobQueue | None = None,
        environment_provider=None,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._job_queue = job_queue or JobQueue(uow_factory)
        self._environment_provider = environment_provider or (lambda names: {})
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process = None
        self._job_id: str | None = None

    def start(self) -> None:
        """幂等启动后台调度；已有存活线程时不创建第二个 Worker。"""

        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="jiejian-worker-supervisor", daemon=True)
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self, timeout: float = 5.0) -> None:
        """请求停止并等待线程退出；超时后报告失败而不伪装为已关闭。"""

        self._stop.set()
        process = self._process
        if process is not None and process.poll() is None:
            try:
                from product.backend.infra.runtime.jobs.models import RequestCancellation

                if self._job_id is not None:
                    self._job_queue.request_cancellation(
                        RequestCancellation(
                            schema_version="1",
                            job_id=self._job_id,
                            now_us=time.time_ns() // 1_000,
                        )
                    )
            except Exception:
                logger.exception(
                    "worker cancellation request failed",
                    extra={"component": "worker_supervisor", "event_code": "WORKER_CANCEL_REQUEST_FAILED", "job_id": self._job_id},
                )
            try:
                process.wait(timeout=timeout)
            except Exception:
                logger.warning(
                    "worker terminate requested",
                    extra={"component": "worker_supervisor", "event_code": "WORKER_TERMINATE"},
                )
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except Exception:
                    logger.error(
                        "worker kill requested",
                        extra={"component": "worker_supervisor", "event_code": "WORKER_KILL"},
                    )
                    process.kill()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None

    def _loop(self) -> None:
        """串行选择 Job 并启动独立 Worker 进程，异常仅终止当前调度迭代。"""

        while not self._stop.is_set():
            try:
                if self._process is None or self._process.poll() is not None:
                    if self._process is not None and self._process.returncode:
                        logger.error(
                            "worker exited with non-zero status",
                            extra={"component": "worker_supervisor", "event_code": "WORKER_EXIT_NONZERO", "job_id": self._job_id},
                        )
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
                            secret_names = required_secret_names(request)
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
            except Exception:
                logger.exception(
                    "worker supervisor loop failed",
                    extra={"component": "worker_supervisor", "event_code": "WORKER_LOOP_ERROR", "job_id": self._job_id},
                )
                self._stop.wait(0.25)
                continue
            self._stop.wait(0.1)

    def _next_job(self):
        with self._uow_factory() as work:
            return work.jobs.next_pending()
