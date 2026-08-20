# =============================================================================
# Recording JobHandler
#
# 定位
#   Execution 通用 Handler 端口的 Recording 实现
#
# 职责
#   领取 fenced attempt｜监督 Recording Runner｜校验并交给 Recording 应用服务完成
#
# 边界
#   Handler 不在 Worker 进程执行浏览器动作，只接受当前 fencing token 的结果。
#
# 调用链
#   JobHandlerRegistry → RecordingJobHandler → recording process / RecordingSubmission
# =============================================================================

from __future__ import annotations

import os
import logging
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from product.backend.core.lifecycle import JobState
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.jobs.handlers import JobAttemptPort
from product.backend.infra.runtime.jobs.models import ClaimJob, FatalFailureCode, FatalFailure, RetryableFailureCode, RetryableFailure
from product.backend.infra.runtime.process_control import DEFAULT_LEASE_DURATION_US, DEFAULT_POLL_INTERVAL_SECONDS, DEFAULT_TERMINATION_GRACE_SECONDS, AttemptProcessControl
from product.backend.infra.runtime.process_environment import minimal_process_environment
from product.protocols import RECORDING_RESULT_MAX_BYTES, RecordingRunnerRequest, RecordingRunnerResult, canonical_recording_json_bytes, parse_recording_result
from product.backend.workflows.recording.submission import RecordingSubmission, RecordingCompletionResult
from product.backend.infra.recording.request_store import RecordingRequestStore
from product.backend.infra.recording.control import control_paths_for_attempt
from product.backend.infra.storage import JobRecord, StorageUnitOfWork

_CANCEL_PATH_ENV = "JIEJIAN_RECORDING_CANCEL_FILE"
_ATTEMPT_DIR_ENV = "JIEJIAN_RECORDING_ATTEMPT_DIR"
logger = logging.getLogger("jiejian.runtime.recording_job")


class RecordingJobHandler:
    """复用既有 Job 租约服务监督一次 Recording Runner 尝试。"""

    def __init__(
        self,
        *,
        var_dir: Path,
        lease_owner: str,
        uow_factory: Callable[..., StorageUnitOfWork],
        attempts: JobAttemptPort,
        application: RecordingSubmission,
        request_store: RecordingRequestStore,
        cancel_path_for: Callable[[Path, JobRecord], Path],
        controlled_runner: Callable[
            [RecordingRunnerRequest, Callable[[], bool]],
            RecordingRunnerResult,
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

    def run_job(self, job_id: str) -> RecordingCompletionResult | None:
        """领取并执行录制任务；未取得租约时返回 ``None``，失败会落入受控任务终态。"""

        now_us = self._utc_now_us()
        claimed = self._attempts.claim(
            ClaimJob(
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
        # 请求哈希先于浏览器进程校验，避免篡改输入进入高风险执行边界。
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
        request: RecordingRunnerRequest,
        cancel_path: Path,
    ) -> RecordingRunnerResult:
        environment = minimal_process_environment(self._environ)
        environment[_CANCEL_PATH_ENV] = str(cancel_path)
        control = control_paths_for_attempt(cancel_path.parent)
        environment[_ATTEMPT_DIR_ENV] = str(control.attempt_dir)
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                process = self._popen(
                    [sys.executable, "-B", "-m", "product.backend.infra.runtime.recording_process"],
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
                logger.exception(
                    "recording process start failed",
                    extra={"component": "recording_job", "event_code": "RECORDING_START_FAILED", "run_id": job.run_id},
                )
                self._record_retryable(job, RetryableFailureCode.RUNNER_START_FAILED)
                raise JiejianError(ErrorCode.RUNNER_START_FAILED, "录制 Runner 启动失败") from None
            timed_out, forced_after_cancel = self._process_control.monitor(
                process,
                job,
                max_duration_us=request.budget.max_duration_us,
                cancel_path=cancel_path,
            )
            if timed_out or forced_after_cancel:
                logger.warning(
                    "recording process stopped by control boundary",
                    extra={"component": "recording_job", "event_code": "RECORDING_CANCELLED" if forced_after_cancel else "RECORDING_TIMEOUT", "run_id": job.run_id},
                )
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
            RetryableFailure(
                job_id=job.job_id,
                lease_owner=self.lease_owner,
                fencing_token=job.fencing_token,
                now_us=self._utc_now_us(),
                reason_code=reason,
            )
        )

    def _record_fatal(self, job: JobRecord, reason: FatalFailureCode) -> None:
        self._attempts.record_fatal_failure(
            FatalFailure(
                job_id=job.job_id,
                lease_owner=self.lease_owner,
                fencing_token=job.fencing_token,
                now_us=self._utc_now_us(),
                reason_code=reason,
            )
        )


# =============================================================================
# Recording Job target
#
# 定位
#   通用 Job 状态变化与 Recording 状态机之间的适配边界
#
# 职责
#   校验 Recording 目标｜映射领取/取消/失败/恢复结果｜保持两类状态语义分离
#
# 调用链
#   JobTargetRegistry / JobControlRepository → RecordingJobTargetHandler → Recording repository
# =============================================================================

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.jobs.targets import JobTargetHandler, JobTargetOutcome
from product.backend.core.recording import RecordingReasonCode, RecordingState, RecordingTerminalState, transition_recording_state
from product.backend.infra.storage import JobRecord, RecordingRecord, RunRecord, StorageUnitOfWork


class RecordingJobTargetHandler(JobTargetHandler):
    def load(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        """加载并验证 Job 与 Recording 的单一关联。"""

        if job.recording_id is None or job.run_id is not None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务录制目标关联非法")
        recording = work.recordings.get(job.recording_id)
        if recording is None:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务关联录制不存在")
        return None, recording

    def advance_after_claim(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        now_us: int,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        """在领取任务的同一事务内将 Recording 推进到启动中。"""

        _, recording = self.load(work, job)
        assert recording is not None
        if recording.state is RecordingState.CREATED:
            started = transition_recording_state(
                recording.to_domain(),
                RecordingState.STARTING,
                operator="WORKER",
                occurred_at_us=now_us,
            )
            recording = RecordingRecord.from_domain(
                started,
                flow_id=recording.flow_id,
                browser_events=recording.browser_events,
            )
            work.recordings.replace(recording)
        elif recording.state is not RecordingState.STARTING:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "录制状态无法进入启动")
        return None, recording

    def finish(
        self,
        work: StorageUnitOfWork,
        job: JobRecord,
        now_us: int,
        outcome: JobTargetOutcome,
    ) -> tuple[RunRecord | None, RecordingRecord | None]:
        """把取消或失败结果映射为 Recording 终态，不覆盖已形成的业务事实。"""

        _, recording = self.load(work, job)
        assert recording is not None
        recording_target = (
            RecordingTerminalState.CANCELLED
            if outcome is JobTargetOutcome.CANCELLED
            else RecordingTerminalState.FAILED
        )
        recording_reason = (
            RecordingReasonCode.CANCEL_REQUESTED
            if outcome is JobTargetOutcome.CANCELLED
            else RecordingReasonCode.PROCESSING_FAILED
        )
        domain = recording.to_domain()
        # Worker 尚未 claim 时没有真实启动事实，直接落终态，不能伪造 STARTING/CLEANING。
        if domain.state is RecordingState.CREATED:
            domain = transition_recording_state(
                domain,
                RecordingState(recording_target.value),
                operator="WORKER",
                occurred_at_us=now_us,
                reason_code=recording_reason,
            )
        else:
            if domain.state is not RecordingState.CLEANING:
                domain = transition_recording_state(
                    domain,
                    RecordingState.CLEANING,
                    operator="WORKER",
                    occurred_at_us=now_us,
                    reason_code=recording_reason,
                    pending_terminal_state=recording_target,
                )
            domain = transition_recording_state(
                domain,
                RecordingState(recording_target.value),
                operator="WORKER",
                occurred_at_us=now_us,
                reason_code=recording_reason,
            )
        updated = RecordingRecord.from_domain(
            domain,
            flow_id=recording.flow_id,
            browser_events=recording.browser_events,
        )
        work.recordings.replace(updated)
        return None, updated
