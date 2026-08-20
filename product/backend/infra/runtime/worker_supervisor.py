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

from product.backend.core.lifecycle import JobState
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.infra.runtime.jobs.dispatch import WorkerDispatcher
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.models import WaitingFatalFailure
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
        attempt_service: JobAttempts | None = None,
        environment_provider=None,
        clock_us=None,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._job_queue = job_queue or JobQueue(uow_factory)
        self._attempts = attempt_service or JobAttempts(uow_factory)
        self._environment_provider = environment_provider or (lambda names: {})
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)
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
        """串行监督 Worker；已承担的等待态 Job 在 bootstrap 失败后必须收口。"""

        while not self._stop.is_set():
            try:
                self._reap_finished_worker()
                if self._process is None:
                    job = self._next_job()
                    if job is not None:
                        self._start_job(job)
            except Exception:
                logger.exception(
                    "worker supervisor loop failed",
                    extra={"component": "worker_supervisor", "event_code": "WORKER_LOOP_ERROR", "job_id": self._job_id},
                )
                self._stop.wait(0.25)
                continue
            self._stop.wait(0.1)

    def _reap_finished_worker(self) -> None:
        process = self._process
        if process is None or process.poll() is None:
            return
        # 清理引用前保存责任 Job；否则非零退出会丢失需要结束的 waiting 身份。
        finished_job_id = self._job_id
        return_code = process.returncode
        self._process = None
        self._job_id = None
        if return_code and finished_job_id is not None:
            logger.error(
                "worker exited with non-zero status",
                extra={
                    "component": "worker_supervisor",
                    "event_code": "WORKER_EXIT_NONZERO",
                    "job_id": finished_job_id,
                },
            )
            self._finish_waiting_failure(finished_job_id)

    def _start_job(self, job) -> None:
        """建立启动责任并完成 request、secret 与进程准备；失败时结束仍匹配的 waiting Job。"""

        self._job_id = job.job_id
        try:
            secret_names = ()
            if job.run_id is not None:
                request = ExecutionRequestStore(self.var_dir).load(
                    job.job_id,
                    expected_hash=job.request_hash,
                )
                secret_names = required_secret_names(request)
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
            failed_job_id = self._job_id
            self._process = None
            self._job_id = None
            logger.exception(
                "worker bootstrap failed",
                extra={
                    "component": "worker_supervisor",
                    "event_code": "WORKER_BOOTSTRAP_ERROR",
                    "job_id": failed_job_id,
                },
            )
            if failed_job_id is not None:
                self._finish_waiting_failure(failed_job_id)

    def _finish_waiting_failure(self, job_id: str) -> None:
        """接受数据库真实状态，只结束仍为 waiting 且无租约的 Job。"""

        current = self._read_job(job_id)
        if current is None or current.state in {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.RUNNING,
        }:
            return
        if current.state not in {JobState.PENDING, JobState.RETRY_WAIT}:
            return
        if current.lease_owner is not None or current.lease_expires_at_us is not None:
            return
        changed = self._attempts.record_waiting_fatal_failure(
            WaitingFatalFailure(
                job_id=job_id,
                now_us=self._clock_us(),
            )
        )
        if changed is None:
            # claim/cancel 竞争可能已经获胜；重新读取后只接受新的真实状态，不做无条件覆盖。
            self._read_job(job_id)

    def _read_job(self, job_id: str):
        with self._uow_factory() as work:
            return work.jobs.get(job_id)

    def _next_job(self):
        with self._uow_factory() as work:
            return work.jobs.next_pending()
