# =============================================================================
# Execution 子进程监督
#
# 定位
#   Verification 与 Recording Handler 共用的 lease/cancel/process 控制器
#
# 职责
#   周期续租｜传播持久取消｜超时后温和终止并最终杀死子进程
#
# 边界
#   租约或 fencing 失效时必须停止子进程；控制器不解释 Runner 业务结果。
#
# 调用链
#   RunnerSupervisor / RecordingJobHandler → AttemptProcessControl → subprocess / JobAttempts
# =============================================================================

from __future__ import annotations

import subprocess
import time
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import JobRecord, StorageUnitOfWork
from product.backend.infra.runtime.jobs.handlers import JobAttemptPort
from product.backend.infra.runtime.jobs.models import RenewLease, checked_time_add
from product.backend.infra.runtime.process.tree import terminate_process_tree

DEFAULT_LEASE_DURATION_US = 30_000_000
DEFAULT_POLL_INTERVAL_SECONDS = 0.05
DEFAULT_TERMINATION_GRACE_SECONDS = 2.0
logger = logging.getLogger("jiejian.runtime.process_control")


def force_terminate_process_tree(process: subprocess.Popen[Any], timeout: float) -> None:
    """通过共享进程树控制器结束进程及后代，避免浏览器成为孤儿。"""

    terminate_process_tree(process, timeout)


class AttemptProcessControl:
    """监督一个 fenced 子进程，不解释具体 Runner 协议或结果。"""

    def __init__(
        self,
        *,
        uow_factory: Callable[..., StorageUnitOfWork],
        attempt_service: JobAttemptPort,
        lease_owner: str,
        utc_now_us: Callable[[], int],
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        lease_duration_us: int,
        poll_interval_seconds: float,
        termination_grace_seconds: float,
    ) -> None:
        self._uow_factory = uow_factory
        self._attempts = attempt_service
        self._lease_owner = lease_owner
        self._utc_now_us = utc_now_us
        self._monotonic = monotonic
        self._sleep = sleep
        self._lease_duration_us = lease_duration_us
        self._poll_interval_seconds = poll_interval_seconds
        self._termination_grace_seconds = termination_grace_seconds

    @property
    def termination_grace_seconds(self) -> float:
        """暴露同一监督边界的树回收预算，避免调用方另造超时常量。"""

        return self._termination_grace_seconds

    def monitor(
        self,
        process: subprocess.Popen[Any],
        job: JobRecord,
        *,
        max_duration_us: int,
        cancel_path: Path,
    ) -> tuple[bool, bool]:
        """返回 `(超时, 取消后被强制终止)`，同时维持当前 fence。"""

        started = self._monotonic()
        next_renew = started + self._lease_duration_us / 3_000_000
        deadline = started + max_duration_us / 1_000_000
        cancellation_started: float | None = None
        while process.poll() is None:
            current_time = self._monotonic()
            current_job = self.read_job(job.job_id)
            if current_job.cancel_requested_at_us is not None:
                if cancellation_started is None:
                    cancel_path.write_text("cancel\n", encoding="utf-8")
                    cancellation_started = current_time
                    logger.info(
                        "cancellation marker written",
                        extra={"component": "process_control", "event_code": "PROCESS_CANCEL_REQUESTED", "run_id": job.run_id, "job_id": job.job_id},
                    )
                if (
                    current_time - cancellation_started
                    >= self._termination_grace_seconds
                ):
                    self._terminate(process)
                    return False, True
            if current_time >= deadline:
                self._terminate(process)
                return True, False
            if current_time >= next_renew:
                self.renew(job)
                next_renew = current_time + self._lease_duration_us / 3_000_000
            self._sleep(self._poll_interval_seconds)
        return False, False

    def renew(self, job: JobRecord) -> None:
        now_us = self._utc_now_us()
        self._attempts.renew_lease(
            RenewLease(
                job_id=job.job_id,
                lease_owner=self._lease_owner,
                fencing_token=job.fencing_token,
                now_us=now_us,
                lease_expires_at_us=checked_time_add(
                    now_us,
                    self._lease_duration_us,
                ),
            )
        )

    def read_job(self, job_id: str) -> JobRecord:
        with self._uow_factory() as work:
            job = work.jobs.get(job_id)
            if job is None:
                raise JiejianError(ErrorCode.JOB_NOT_FOUND, "任务不存在")
            return job

    def _terminate(self, process: subprocess.Popen[Any]) -> None:
        """沿受控 Job/session 结束整棵树；根进程退出不能代替后代退出证明。"""

        logger.warning(
            "process terminate requested",
            extra={"component": "process_control", "event_code": "PROCESS_TERMINATE"},
        )
        try:
            force_terminate_process_tree(process, self._termination_grace_seconds)
        except Exception:
            logger.exception(
                "process tree termination failed",
                extra={"component": "process_control", "event_code": "PROCESS_TREE_TERMINATION_FAILED"},
            )
            raise JiejianError(
                ErrorCode.PROCESS_TREE_FAILED,
                "Runner 进程树无法在有界时间内终止",
            ) from None
