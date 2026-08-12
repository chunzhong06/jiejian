# =============================================================================
# Verification Runner 监督
#
# 定位
#   当前 fenced attempt 与隔离 Verification Runner 进程之间的监督边界
#
# 职责
#   claim 并加载冻结请求｜启动和监督 Runner｜重验 staging 并发布或收敛失败
#
# 调用链
#   VerificationRunJobHandler → WorkerSupervisor → runner process / Publication / JobAttemptService
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..domain.lifecycle import JobState
from ..errors import ErrorCode, JiejianError
from ..protocols import (
    RunnerInputV1,
    RunnerResultType,
    RunnerResultV1,
    canonical_json_bytes,
)
from ..storage import JobRecord, StorageUnitOfWork
from .attempts import JobAttemptService
from .models import (
    ClaimJobV1,
    CompleteCancellationV1,
    FatalFailureCode,
    FatalFailureV1,
    RetryableFailureCode,
    RetryableFailureV1,
)
from .process_control import (
    DEFAULT_LEASE_DURATION_US,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TERMINATION_GRACE_SECONDS,
    AttemptProcessControl,
)
from .process_environment import minimal_process_environment
from .publication import RunPublicationService
from .published_artifacts import (
    AttemptPaths,
    StagedAttempt,
    TrustedResultReceiptV1,
    attempt_paths_for,
    validate_runner_staging,
)
from .request_store import (
    ExecutionRequestStore,
    PersistedExecutionRequestV1,
    required_secret_names,
)

class WorkerSupervisor:
    """监督一个持久 Job 的当前 fenced Runner 尝试。"""

    def __init__(
        self,
        *,
        var_dir: Path,
        lease_owner: str,
        uow_factory: Callable[..., StorageUnitOfWork],
        attempt_service: JobAttemptService,
        request_store: ExecutionRequestStore,
        publication_service: RunPublicationService,
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
        self._attempts = attempt_service
        self._request_store = request_store
        self._publication = publication_service
        self._environ = os.environ if environ is None else environ
        self._utc_now_us = utc_now_us or (lambda: time.time_ns() // 1_000)
        self._popen = popen
        self._lease_duration_us = lease_duration_us
        self._process_control = AttemptProcessControl(
            uow_factory=uow_factory,
            attempt_service=attempt_service,
            lease_owner=lease_owner,
            utc_now_us=self._utc_now_us,
            monotonic=monotonic,
            sleep=sleep,
            lease_duration_us=lease_duration_us,
            poll_interval_seconds=poll_interval_seconds,
            termination_grace_seconds=termination_grace_seconds,
        )

    def run_job(self, job_id: str) -> StagedAttempt | None:
        """领取并监督指定 Job 的当前 attempt，只有可信结果才进入发布。"""

        # --- 阶段：领取当前 attempt 并加载冻结请求 ---
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
        job = claimed.job
        try:
            request = self._request_store.load(job.job_id, expected_hash=job.request_hash)
        except JiejianError:
            self._record_fatal(job, FatalFailureCode.PROTOCOL_INVALID)
            raise
        secret_names = required_secret_names(request)
        known_secrets = tuple(
            self._environ[name] for name in secret_names if self._environ.get(name)
        )
        request = self._request_store.load(
            job.job_id,
            expected_hash=job.request_hash,
            known_secrets=known_secrets,
        )
        # --- 阶段：构造最小 Runner 环境并启动隔离进程 ---
        paths = attempt_paths_for(self.var_dir, job)
        runner_input = self._runner_input(job, request)
        self._write_runner_input(paths, runner_input, known_secrets)
        child_environment = minimal_process_environment(
            self._environ,
            secret_names=secret_names,
        )
        try:
            process = self._popen(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "jiejian.runner",
                    "--input",
                    str(paths.input_path),
                    "--staging",
                    str(paths.staging_dir),
                ],
                cwd=str(self.var_dir),
                env=child_environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError:
            self._record_retryable(job, RetryableFailureCode.RUNNER_START_FAILED)
            raise JiejianError(
                ErrorCode.RUNNER_START_FAILED,
                "Runner 进程启动失败",
            ) from None

        # --- 阶段：监督 lease、取消和 Runner 退出 ---
        timed_out, forced_after_cancel = self._process_control.monitor(
            process,
            job,
            max_duration_us=request.budget.max_duration_us,
            cancel_path=paths.cancel_path,
        )
        if timed_out or forced_after_cancel:
            reason = (
                FatalFailureCode.CLEANUP_FAILED
                if forced_after_cancel
                else None
            )
            if reason is not None:
                self._record_fatal(job, reason)
            else:
                self._record_retryable(job, RetryableFailureCode.EXEC_TIMEOUT)
            raise JiejianError(
                ErrorCode.RUNNER_TIMEOUT,
                "Runner 执行超过有界时限",
            )

        return_code = process.returncode
        if return_code != 0:
            if return_code == 64:
                self._record_fatal(job, FatalFailureCode.PROTOCOL_INVALID)
                code = ErrorCode.RUNNER_PROTOCOL_INVALID
            elif return_code == 74:
                self._record_retryable(job, RetryableFailureCode.WORKER_INTERRUPTED)
                code = ErrorCode.RUNNER_RESULT_MISSING
            else:
                self._record_fatal(job, FatalFailureCode.RUNNER_FATAL)
                code = ErrorCode.RUNNER_RESULT_MISSING
            raise JiejianError(code, "Runner 未形成可信结果")

        # --- 阶段：重验 staging 并发布或收敛失败 ---
        try:
            result, _ = validate_runner_staging(
                paths,
                job,
                known_secrets=known_secrets,
                require_receipt=False,
            )
        except JiejianError:
            self._record_fatal(job, FatalFailureCode.PROTOCOL_INVALID)
            raise
        self._process_control.renew(job)
        self._write_receipt(paths, result)
        staged = StagedAttempt(result=result, paths=paths)
        if result.result_type in {
            RunnerResultType.SUCCESS,
            RunnerResultType.SAFETY_STOPPED,
        }:
            return self._publication.publish(staged, known_secrets=known_secrets)
        self._apply_non_success_result(job, result)
        return staged

    def _apply_non_success_result(
        self,
        job: JobRecord,
        result: RunnerResultV1,
    ) -> None:
        if result.result_type in {
            RunnerResultType.SUCCESS,
            RunnerResultType.SAFETY_STOPPED,
        }:
            return
        if result.result_type is RunnerResultType.CANCELLED:
            current = self._process_control.read_job(job.job_id)
            if current.cancel_requested_at_us is None:
                self._record_fatal(job, FatalFailureCode.PROTOCOL_INVALID)
                raise JiejianError(
                    ErrorCode.RUNNER_PROTOCOL_INVALID,
                    "Runner 取消结果缺少控制面请求",
                )
            self._attempts.complete_cancellation(
                CompleteCancellationV1(
                    job_id=job.job_id,
                    lease_owner=self.lease_owner,
                    fencing_token=job.fencing_token,
                    now_us=self._utc_now_us(),
                )
            )
            return
        if result.result_type is RunnerResultType.RETRYABLE_ERROR:
            reason = (
                RetryableFailureCode(result.error.code)
                if result.error is not None
                and result.error.code in {item.value for item in RetryableFailureCode}
                else RetryableFailureCode.WORKER_INTERRUPTED
            )
            self._record_retryable(job, reason)
            return
        reason = (
            FatalFailureCode.CLEANUP_FAILED
            if result.cleanup.status.value == "FAILED"
            else FatalFailureCode.PROTOCOL_INVALID
            if result.error is not None and result.error.code == "PROTOCOL_INVALID"
            else FatalFailureCode.RUNNER_FATAL
        )
        self._record_fatal(job, reason)

    def _runner_input(
        self,
        job: JobRecord,
        request: PersistedExecutionRequestV1,
    ) -> RunnerInputV1:
        return RunnerInputV1(
            schema_version="1",
            run_id=job.run_id,
            job_id=job.job_id,
            attempt=job.attempt,
            lease_owner=job.lease_owner,
            fencing_token=job.fencing_token,
            created_at_us=job.updated_at_us,
            budget=request.budget,
            project_snapshot=request.project_snapshot,
        )

    def _write_runner_input(
        self,
        paths: AttemptPaths,
        runner_input: RunnerInputV1,
        known_secrets: Sequence[str],
    ) -> None:
        encoded = canonical_json_bytes(runner_input, known_secrets=known_secrets)
        paths.attempt_dir.mkdir(parents=True, exist_ok=False)
        temporary = paths.input_path.with_name(f".{paths.input_path.name}.tmp-{uuid4().hex}")
        try:
            with temporary.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, paths.input_path)
        except OSError:
            self._record_retryable(
                self._process_control.read_job(runner_input.job_id),
                RetryableFailureCode.WORKER_INTERRUPTED,
            )
            raise JiejianError(
                ErrorCode.RUNNER_START_FAILED,
                "Runner 输入文件写入失败",
            ) from None
        finally:
            temporary.unlink(missing_ok=True)

    def _write_receipt(self, paths: AttemptPaths, result: RunnerResultV1) -> None:
        temporary = paths.receipt_path.with_name(
            f".{paths.receipt_path.name}.tmp-{uuid4().hex}"
        )
        try:
            receipt = TrustedResultReceiptV1(
                schema_version="1",
                run_id=result.run_id,
                job_id=result.job_id,
                attempt=result.attempt,
                lease_owner=result.lease_owner,
                fencing_token=result.fencing_token,
                result_sha256=hashlib.sha256(paths.result_path.read_bytes()).hexdigest(),
            )
            encoded = json.dumps(
                receipt.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            with temporary.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, paths.receipt_path)
        except OSError:
            self._record_retryable(
                self._process_control.read_job(result.job_id),
                RetryableFailureCode.WORKER_INTERRUPTED,
            )
            raise JiejianError(
                ErrorCode.RUNNER_RESULT_MISSING,
                "Runner 可信结果标记写入失败",
            ) from None
        finally:
            temporary.unlink(missing_ok=True)

    def _record_retryable(
        self,
        job: JobRecord,
        reason_code: RetryableFailureCode,
    ) -> None:
        self._attempts.record_retryable_failure(
            RetryableFailureV1(
                job_id=job.job_id,
                lease_owner=self.lease_owner,
                fencing_token=job.fencing_token,
                now_us=self._utc_now_us(),
                reason_code=reason_code,
            )
        )

    def _record_fatal(
        self,
        job: JobRecord,
        reason_code: FatalFailureCode,
    ) -> None:
        self._attempts.record_fatal_failure(
            FatalFailureV1(
                job_id=job.job_id,
                lease_owner=self.lease_owner,
                fencing_token=job.fencing_token,
                now_us=self._utc_now_us(),
                reason_code=reason_code,
            )
        )
