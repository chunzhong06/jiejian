"""Run 与 Recording Runner 共用的租约、取消和进程终止边界。"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..errors import ErrorCode, JiejianError
from ..storage import JobRecord, StorageUnitOfWork
from .attempts import JobAttemptService
from .models import RenewLeaseV1, checked_time_add


class AttemptProcessControl:
    """监督一个 fenced 子进程，不解释具体 Runner 协议或结果。"""

    def __init__(
        self,
        *,
        uow_factory: Callable[..., StorageUnitOfWork],
        attempt_service: JobAttemptService,
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
            RenewLeaseV1(
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
        process.terminate()
        try:
            process.wait(timeout=self._termination_grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=self._termination_grace_seconds)
            except subprocess.TimeoutExpired:
                raise JiejianError(
                    ErrorCode.RUNNER_TIMEOUT,
                    "Runner 进程无法在有界时间内终止",
                ) from None
