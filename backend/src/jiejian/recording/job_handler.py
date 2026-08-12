# =============================================================================
# Recording JobHandler
#
# 定位
#   Execution 通用 Handler 端口的 Recording 实现
#
# 职责
#   领取 fenced attempt｜监督 Recording Runner｜校验并交给 Recording 应用服务完成
#
# 调用链
#   JobHandlerRegistry → RecordingJobHandler → recording_runner process / RecordingApplicationService
# =============================================================================

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..domain.lifecycle import JobState
from ..errors import ErrorCode, JiejianError
from ..execution.handlers import JobAttemptPort
from ..execution.models import (
    ClaimJobV1,
    FatalFailureCode,
    FatalFailureV1,
    RetryableFailureCode,
    RetryableFailureV1,
)
from ..execution.process_control import (
    DEFAULT_LEASE_DURATION_US,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TERMINATION_GRACE_SECONDS,
    AttemptProcessControl,
)
from ..execution.process_environment import minimal_process_environment
from ..protocols import (
    RECORDING_RESULT_MAX_BYTES,
    RecordingRunnerRequestV1,
    RecordingRunnerResultV1,
    canonical_recording_json_bytes,
    parse_recording_result,
)
from ..recording.application import (
    RecordingApplicationService,
    RecordingCompletionResultV1,
)
from ..recording.request_store import RecordingRequestStore
from ..storage import JobRecord, StorageUnitOfWork

_CANCEL_PATH_ENV = "JIEJIAN_RECORDING_CANCEL_FILE"


class RecordingJobHandler:
    """复用既有 Job 租约服务监督一次 Recording Runner 尝试。"""

    def __init__(
        self,
        *,
        var_dir: Path,
        lease_owner: str,
        uow_factory: Callable[..., StorageUnitOfWork],
        attempts: JobAttemptPort,
        application: RecordingApplicationService,
        request_store: RecordingRequestStore,
        cancel_path_for: Callable[[Path, JobRecord], Path],
        controlled_runner: Callable[
            [RecordingRunnerRequestV1, Callable[[], bool]],
            RecordingRunnerResultV1,
        ]
        | None = None,
        known_secrets: Sequence[str] = (),
        environ: Mapping[str, str] | None = None,
        utc_now_us: Callable[[], int] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        popen: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
        lease_duration_us: int = DEFAULT_LEASE_DURATION_US,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        termination_grace_seconds: float = DEFAULT_TERMINATION_GRACE_SECONDS,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self.lease_owner = lease_owner
        self._attempts = attempts
        self._application = application
        self._request_store = request_store
        self._cancel_path_for = cancel_path_for
        self._controlled_runner = controlled_runner
        self._known_secrets = tuple(secret for secret in known_secrets if secret)
        self._environ = os.environ if environ is None else environ
        self._utc_now_us = utc_now_us or (lambda: time.time_ns() // 1_000)
        self._popen = popen
        self._lease_duration_us = lease_duration_us
        self._process_control = AttemptProcessControl(
            uow_factory=uow_factory,
            attempt_service=attempts,
            lease_owner=lease_owner,
            utc_now_us=self._utc_now_us,
            monotonic=monotonic,
            sleep=sleep,
            lease_duration_us=lease_duration_us,
            poll_interval_seconds=poll_interval_seconds,
            termination_grace_seconds=termination_grace_seconds,
        )

    def run_job(self, job_id: str) -> RecordingCompletionResultV1 | None:
        now_us = self._utc_now_us()
        claimed = self._attempts.claim(
            ClaimJobV1(
                lease_owner=self.lease_owner,
                now_us=now_us,
                lease_duration_us=self._lease_duration_us,
                job_id=job_id,
            )
        )
        if claimed is None:
            return None
        if claimed.recording is None or claimed.job.recording_id is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务不是录制任务")
        job = claimed.job
        try:
            request = self._request_store.load(
                job.job_id,
                expected_hash=job.request_hash,
                known_secrets=self._known_secrets,
            )
        except JiejianError:
            self._record_fatal(job, FatalFailureCode.PROTOCOL_INVALID)
            raise
        if request.recording_id != job.recording_id:
            self._record_fatal(job, FatalFailureCode.PROTOCOL_INVALID)
            raise JiejianError(ErrorCode.RECORD_PROTOCOL_INVALID, "录制请求关联不匹配")
        cancel_path = self._cancel_path_for(self.var_dir, job)
        cancel_path.parent.mkdir(parents=True, exist_ok=True)
        result = (
            self._controlled_runner(request, cancel_path.exists)
            if self._controlled_runner is not None
            else self._run_process(job, request, cancel_path)
        )
        if (
            result.recording_id != job.recording_id
            or result.project_id != job.project_id
        ):
            self._record_fatal(job, FatalFailureCode.PROTOCOL_INVALID)
            raise JiejianError(
                ErrorCode.RUNNER_PROTOCOL_INVALID,
                "录制结果关联不匹配",
            )
        try:
            return self._application.consume_result(
                job_id=job.job_id,
                lease_owner=self.lease_owner,
                fencing_token=job.fencing_token,
                result=result,
                now_us=self._utc_now_us(),
                known_secrets=self._known_secrets,
            )
        except JiejianError:
            current = self._process_control.read_job(job.job_id)
            if (
                current.state is JobState.RUNNING
                and current.lease_owner == self.lease_owner
                and current.fencing_token == job.fencing_token
            ):
                self._record_fatal(job, FatalFailureCode.PROTOCOL_INVALID)
            raise

    def _run_process(
        self,
        job: JobRecord,
        request: RecordingRunnerRequestV1,
        cancel_path: Path,
    ) -> RecordingRunnerResultV1:
        environment = minimal_process_environment(self._environ)
        environment[_CANCEL_PATH_ENV] = str(cancel_path)
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                process = self._popen(
                    [sys.executable, "-B", "-m", "jiejian.recording_runner"],
                    cwd=str(self.var_dir),
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    close_fds=True,
                )
                assert process.stdin is not None
                process.stdin.write(
                    canonical_recording_json_bytes(
                        request,
                        known_secrets=self._known_secrets,
                    )
                )
                process.stdin.close()
            except OSError:
                self._record_retryable(job, RetryableFailureCode.RUNNER_START_FAILED)
                raise JiejianError(ErrorCode.RUNNER_START_FAILED, "录制 Runner 启动失败") from None
            timed_out, forced_after_cancel = self._process_control.monitor(
                process,
                job,
                max_duration_us=request.budget.max_duration_us,
                cancel_path=cancel_path,
            )
            if timed_out or forced_after_cancel:
                if forced_after_cancel:
                    self._record_fatal(job, FatalFailureCode.CLEANUP_FAILED)
                else:
                    self._record_retryable(job, RetryableFailureCode.EXEC_TIMEOUT)
                raise JiejianError(ErrorCode.RUNNER_TIMEOUT, "录制 Runner 超时")
            stdout_file.seek(0, os.SEEK_END)
            size = stdout_file.tell()
            stdout_file.seek(0)
            raw = stdout_file.read(RECORDING_RESULT_MAX_BYTES + 1)
            if process.returncode != 0 or size > RECORDING_RESULT_MAX_BYTES:
                self._record_fatal(job, FatalFailureCode.PROTOCOL_INVALID)
                raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, "录制 Runner 结果无效")
            try:
                result = parse_recording_result(
                    raw,
                    known_secrets=self._known_secrets,
                )
            except JiejianError:
                self._record_fatal(job, FatalFailureCode.PROTOCOL_INVALID)
                raise
            return result

    def _record_retryable(
        self,
        job: JobRecord,
        reason: RetryableFailureCode,
    ) -> None:
        self._attempts.record_retryable_failure(
            RetryableFailureV1(
                job_id=job.job_id,
                lease_owner=self.lease_owner,
                fencing_token=job.fencing_token,
                now_us=self._utc_now_us(),
                reason_code=reason,
            )
        )

    def _record_fatal(self, job: JobRecord, reason: FatalFailureCode) -> None:
        self._attempts.record_fatal_failure(
            FatalFailureV1(
                job_id=job.job_id,
                lease_owner=self.lease_owner,
                fencing_token=job.fencing_token,
                now_us=self._utc_now_us(),
                reason_code=reason,
            )
        )
