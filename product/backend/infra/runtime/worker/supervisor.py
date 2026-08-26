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
from product.backend.infra.runtime.jobs.recovery import JobRecovery
from product.backend.infra.runtime.jobs.models import (
    ConfirmRecovery,
    FatalFailure,
    FatalFailureCode,
    RecoveryOperator,
    RecoveryProofType,
    RecoveryReasonCode,
    RecoveryScan,
    WaitingFatalFailure,
)
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.jobs.requests import ExecutionRequestStore, required_secret_names
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.protocols import required_recording_secret_names
from product.backend.infra.runtime.worker.lifetime import WorkerLifetimeLock
from product.backend.infra.runtime.process.tree import release_process_tree, terminate_process_tree
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.paths import RuntimePaths

logger = logging.getLogger("jiejian.runtime.worker_supervisor")


class LocalWorkerSupervisor:
    """在服务生命周期内拥有唯一后台 Worker 线程，并负责确定性停止。"""

    def __init__(
        self,
        var_dir: Path,
        uow_factory,
        job_queue: JobQueue | None = None,
        attempt_service: JobAttempts | None = None,
        recovery_service: JobRecovery | None = None,
        environment_provider=None,
        clock_us=None,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._job_queue = job_queue or JobQueue(uow_factory)
        self._attempts = attempt_service or JobAttempts(uow_factory)
        self._recovery = recovery_service or JobRecovery(uow_factory)
        self._environment_provider = environment_provider or (lambda names: {})
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process = None
        self._job_id: str | None = None
        self._lease_owner: str | None = None
        self._next_recovery_scan_us = 0
        self._recovered_jobs = 0

    def start(self) -> None:
        """幂等启动后台调度；已有存活线程时不创建第二个 Worker。"""

        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="jiejian-worker-supervisor", daemon=True)
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def recovered_jobs(self) -> int:
        return self._recovered_jobs

    def stop(self, timeout: float = 5.0) -> None:
        """请求停止并等待线程退出；超时后报告失败而不伪装为已关闭。"""

        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        process = self._process
        stopping_job_id = self._job_id
        stopping_lease_owner = self._lease_owner
        if process is not None and process.poll() is None:
            try:
                from product.backend.infra.runtime.jobs.models import RequestCancellation

                if self._job_id is not None:
                    self._job_queue.request_cancellation(
                        RequestCancellation(
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
                    "worker process tree termination requested",
                    extra={"component": "worker_supervisor", "event_code": "WORKER_TERMINATE"},
                )
                try:
                    terminate_process_tree(process, 2.0)
                except Exception:
                    logger.exception(
                        "Worker 进程树无法完整退出",
                        extra={"component": "worker_supervisor", "event_code": "WORKER_TREE_EXIT_FAILED", "job_id": stopping_job_id},
                    )
                    raise JiejianError(
                        ErrorCode.PROCESS_TREE_FAILED,
                        "Worker 进程树无法在有界时间内退出",
                    ) from None
        if process is not None and process.poll() is not None and stopping_job_id is not None:
            release_process_tree(process)
            self._finish_worker_exit(stopping_job_id, process.returncode, stopping_lease_owner)
            self._process = None
            self._job_id = None
            self._lease_owner = None
        self._thread = None

    def _loop(self) -> None:
        """串行监督 Worker；已承担的等待态 Job 在 bootstrap 失败后必须收口。"""

        while not self._stop.is_set():
            try:
                self._recover_expired_workers()
                self._reap_finished_worker()
                if self._process is None and not self._stop.is_set():
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
        finished_lease_owner = self._lease_owner
        return_code = process.returncode
        release_process_tree(process)
        self._process = None
        self._job_id = None
        self._lease_owner = None
        if finished_job_id is not None:
            self._finish_worker_exit(finished_job_id, return_code, finished_lease_owner)

    def _start_job(self, job) -> None:
        """建立启动责任并完成 request、secret 与进程准备；失败时结束仍匹配的 waiting Job。"""

        self._job_id = job.job_id
        self._lease_owner = f"serve-worker-{uuid4().hex}"
        try:
            secret_names = ()
            if job.run_id is not None:
                request = ExecutionRequestStore(self.var_dir).load(
                    job.job_id,
                    expected_hash=job.request_hash,
                )
                secret_names = required_secret_names(request)
            elif job.recording_id is not None:
                recording_request = RecordingRequestStore(self.var_dir).load(
                    job.job_id,
                    expected_hash=job.request_hash,
                )
                secret_names = required_recording_secret_names(recording_request)
            environment = self._environment_provider(secret_names)
            self._process = WorkerDispatcher(
                var_dir=self.var_dir,
                uow_factory=self._uow_factory,
                environ=environment,
            ).start(
                job_id=job.job_id,
                lease_owner=self._lease_owner,
                secret_names=secret_names,
            )
            logger.info(
                "Worker 已启动",
                extra={
                    "component": "worker_supervisor",
                    "event_code": "WORKER_STARTED",
                    "job_id": job.job_id,
                    "log_path": str(RuntimePaths(self.var_dir).worker_logs / f"{job.job_id}.log"),
                },
            )
        except Exception:
            failed_job_id = self._job_id
            self._process = None
            self._job_id = None
            self._lease_owner = None
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

    def _finish_worker_exit(
        self,
        job_id: str,
        return_code: int | None,
        expected_lease_owner: str | None,
    ) -> None:
        """按数据库当前 fence 结束异常退出，禁止 RUNNING 永久悬挂。"""

        current = self._read_job(job_id)
        if current is None or current.state in {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
        }:
            return
        logger.log(
            logging.ERROR if return_code else logging.WARNING,
            "Worker 在任务终态前退出",
            extra={
                "component": "worker_supervisor",
                "event_code": "WORKER_EXITED",
                "job_id": job_id,
                "return_code": return_code,
                "log_path": str(
                    RuntimePaths(self.var_dir).worker_logs / f"{job_id}.log"
                ),
            },
        )
        if current.state in {JobState.PENDING, JobState.RETRY_WAIT}:
            self._finish_waiting_failure(job_id)
            return
        now_us = self._clock_us()
        if current.lease_owner is None or current.fencing_token < 1:
            return
        if expected_lease_owner is None or current.lease_owner != expected_lease_owner:
            return
        try:
            if current.lease_expires_at_us is not None and current.lease_expires_at_us > now_us:
                if current.cancel_requested_at_us is not None:
                    from product.backend.infra.runtime.jobs.models import CompleteCancellation

                    self._attempts.complete_cancellation(
                        CompleteCancellation(
                            job_id=job_id,
                            lease_owner=current.lease_owner,
                            fencing_token=current.fencing_token,
                            now_us=now_us,
                        )
                    )
                else:
                    self._attempts.record_fatal_failure(
                        FatalFailure(
                            job_id=job_id,
                            lease_owner=current.lease_owner,
                            fencing_token=current.fencing_token,
                            now_us=now_us,
                            reason_code=FatalFailureCode.WORKER_FATAL,
                        )
                    )
                return
            self._confirm_exited_recovery(current, now_us)
        except Exception:
            logger.exception(
                "Worker 退出状态收口失败",
                extra={
                    "component": "worker_supervisor",
                    "event_code": "WORKER_EXIT_FINALIZE_FAILED",
                    "job_id": job_id,
                    "return_code": return_code,
                },
            )

    def _recover_expired_workers(self) -> None:
        """周期扫描过期任务；仅在 Worker 系统锁可获取时确认旧进程已退出。"""

        now_us = self._clock_us()
        if now_us < self._next_recovery_scan_us:
            return
        self._next_recovery_scan_us = now_us + 1_000_000
        for candidate in self._recovery.list_recovery_candidates(
            RecoveryScan(now_us=now_us, limit=100)
        ):
            if not WorkerLifetimeLock.execution_has_exited(
                self.var_dir,
                candidate.job_id,
                candidate.lease_owner,
            ):
                continue
            try:
                self._confirm_exited_recovery(candidate, now_us)
            except Exception:
                logger.exception(
                    "过期 Worker 自动恢复失败",
                    extra={
                        "component": "worker_supervisor",
                        "event_code": "WORKER_RECOVERY_FAILED",
                        "job_id": candidate.job_id,
                    },
                )

    def _confirm_exited_recovery(self, current, now_us: int) -> None:
        if not WorkerLifetimeLock.execution_has_exited(
            self.var_dir,
            current.job_id,
            current.lease_owner,
        ):
            raise JiejianError(
                ErrorCode.PROCESS_TREE_FAILED,
                "Worker 锁或内核进程树退出证明不足，任务不会自动重试",
            )
        result = self._recovery.confirm_recovery(
            ConfirmRecovery(
                job_id=current.job_id,
                lease_owner=current.lease_owner,
                fencing_token=current.fencing_token,
                now_us=now_us,
                proof_type=RecoveryProofType.EXECUTION_EXITED,
                operator=RecoveryOperator.WORKER_SUPERVISOR,
                reason_code=RecoveryReasonCode.PROCESS_EXIT_CONFIRMED,
            )
        )
        self._recovered_jobs += 1
        logger.warning(
            "已自动恢复异常中断的 Worker 任务",
            extra={
                "component": "worker_supervisor",
                "event_code": "WORKER_RECOVERED",
                "job_id": current.job_id,
                "target_state": result.job.state.value,
            },
        )

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
