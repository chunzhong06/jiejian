# =============================================================================
# Verification Runner 监督
#
# 定位
#   当前 fenced attempt 与隔离 Verification Runner 进程之间的监督边界
#
# 职责
#   claim 并加载冻结请求｜启动和监督 Runner｜重验 staging 并发布或收敛失败
#
# 边界
#   只接受当前 owner/token 的 attempt；Runner 输出必须重新校验后才能 publication。
#
# 调用链
#   VerificationRunJobHandler → RunnerSupervisor → runner process / Publication / JobAttempts
# =============================================================================

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from product.backend.core.lifecycle import JobState
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import (
    CleanupIssueCode,
    RunnerFailurePhase,
    RunnerInput,
    RunnerResult,
    RunnerResultType,
    canonical_runner_json_bytes,
)
from product.backend.infra.storage import JobRecord, StorageUnitOfWork
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.models import ClaimJob, CompleteCancellation, FatalFailureCode, FatalFailure, RetryableFailureCode, RetryableFailure
from product.backend.infra.runtime.process.control import DEFAULT_LEASE_DURATION_US, DEFAULT_POLL_INTERVAL_SECONDS, DEFAULT_TERMINATION_GRACE_SECONDS, AttemptProcessControl
from product.backend.infra.runtime.process.environment import ProcessEnvironmentRole, spawn_python_module
from product.backend.infra.runtime.process.tree import release_process_tree, terminate_process_tree
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.artifacts.run_publication import RunPublisher
from product.backend.infra.artifacts.run_packages import AttemptPaths, StagedAttempt, TrustedResultReceipt, attempt_paths_for, validate_runner_staging
from product.backend.infra.runtime.jobs.requests import ExecutionRequestStore, PersistedExecutionRequest, required_secret_names

logger = logging.getLogger("jiejian.runtime.runner_supervisor")

class RunnerSupervisor:
    """监督一个持久 Job 的当前 fenced Runner 尝试。"""

    def __init__(
        self,
        *,
        var_dir: Path,
        lease_owner: str,
        uow_factory: Callable[..., StorageUnitOfWork],
        attempt_service: JobAttempts,
        request_store: ExecutionRequestStore,
        publication_service: RunPublisher,
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

        # --- 领取 attempt 并加载冻结请求 ---
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
        # --- 构造最小 Runner 环境并启动隔离进程 ---
        paths = attempt_paths_for(self.var_dir, job)
        runner_input = self._runner_input(job, request)
        self._write_runner_input(paths, runner_input, known_secrets)
        source_environment = dict(self._environ)
        source_environment.setdefault("JIEJIAN_VAR_DIR", str(self.var_dir))
        paths_runtime = RuntimePaths(self.var_dir).ensure_layout()
        try:
            process = spawn_python_module(
                source_environment,
                "product.backend.infra.runtime.runner",
                "--input",
                str(paths.input_path),
                "--staging",
                str(paths.staging_dir),
                role=ProcessEnvironmentRole.RUNNER,
                secret_names=secret_names,
                cwd=paths_runtime.temp,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                popen=self._popen,
            )
        except OSError:
            logger.exception(
                "runner process start failed",
                extra={"component": "runner_supervisor", "event_code": "RUNNER_START_FAILED", "run_id": job.run_id, "case_id": None},
            )
            self._record_retryable(job, RetryableFailureCode.RUNNER_START_FAILED)
            raise JiejianError(
                ErrorCode.RUNNER_START_FAILED,
                "Runner 进程启动失败",
            ) from None

        # --- 监督 lease、取消和 Runner 退出 ---
        try:
            timed_out, forced_after_cancel = self._process_control.monitor(
                process,
                job,
                max_duration_us=request.budget.max_duration_us,
                cancel_path=paths.cancel_path,
            )
        except Exception:
            try:
                if process.poll() is None:
                    terminate_process_tree(process, self._process_control.termination_grace_seconds)
                else:
                    release_process_tree(process)
            except Exception:
                self._record_fatal(
                    job,
                    FatalFailureCode.CLEANUP_FAILED,
                    error_code=ErrorCode.CLEANUP_FAILED.value,
                    phase=RunnerFailurePhase.RUNTIME_CLOSE,
                    cleanup_issue_codes=(
                        CleanupIssueCode.PROCESS_TREE_CLEANUP_FAILED,
                    ),
                )
                raise JiejianError(
                    ErrorCode.PROCESS_TREE_FAILED,
                    "Runner 异常后进程树未能完整退出",
                ) from None
            raise
        if timed_out or forced_after_cancel:
            logger.warning(
                "runner process stopped by control boundary",
                extra={"component": "runner_supervisor", "event_code": "RUNNER_CANCELLED" if forced_after_cancel else "RUNNER_TIMEOUT", "run_id": job.run_id},
            )
            reason = (
                FatalFailureCode.CLEANUP_FAILED
                if forced_after_cancel
                else None
            )
            if reason is not None:
                self._record_fatal(
                    job,
                    reason,
                    error_code=ErrorCode.CLEANUP_FAILED.value,
                    phase=RunnerFailurePhase.RUNTIME_CLOSE,
                    cleanup_issue_codes=(
                        CleanupIssueCode.RUNTIME_CLOSE_FAILED,
                    ),
                )
            else:
                self._record_retryable(
                    job,
                    RetryableFailureCode.EXEC_TIMEOUT,
                    error_code=ErrorCode.EXEC_TIMEOUT.value,
                )
            raise JiejianError(
                ErrorCode.RUNNER_TIMEOUT,
                "Runner 执行超过有界时限",
            )

        return_code = process.returncode
        try:
            release_process_tree(process)
        except Exception:
            self._record_fatal(
                job,
                FatalFailureCode.CLEANUP_FAILED,
                error_code=ErrorCode.CLEANUP_FAILED.value,
                phase=RunnerFailurePhase.RUNTIME_CLOSE,
                cleanup_issue_codes=(
                    CleanupIssueCode.PROCESS_TREE_CLEANUP_FAILED,
                ),
            )
            raise JiejianError(
                ErrorCode.PROCESS_TREE_FAILED,
                "Runner 退出后仍存在未回收后代",
            ) from None
        if return_code != 0:
            logger.error(
                "runner exited with non-zero status",
                extra={"component": "runner_supervisor", "event_code": "RUNNER_EXIT_NONZERO", "run_id": job.run_id},
            )
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

        # --- 重验 staging 并发布或收敛失败 ---
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
        if result.result_type.value in {"SUCCESS", "SAFETY_STOPPED"}:
            return self._publication.publish(staged, known_secrets=known_secrets)
        self._apply_non_success_result(job, result)
        return staged

    def _apply_non_success_result(
        self,
        job: JobRecord,
        result: RunnerResult,
    ) -> None:
        result_type = result.result_type.value
        if result_type in {"SUCCESS", "SAFETY_STOPPED"}:
            return
        if result_type == "CANCELLED":
            current = self._process_control.read_job(job.job_id)
            if current.cancel_requested_at_us is None:
                self._record_fatal(job, FatalFailureCode.PROTOCOL_INVALID)
                raise JiejianError(
                    ErrorCode.RUNNER_PROTOCOL_INVALID,
                    "Runner 取消结果缺少控制面请求",
                )
            self._attempts.complete_cancellation(
                CompleteCancellation(
                    job_id=job.job_id,
                    lease_owner=self.lease_owner,
                    fencing_token=job.fencing_token,
                    now_us=self._utc_now_us(),
                )
            )
            return
        if result_type == "RETRYABLE_ERROR":
            reason = (
                RetryableFailureCode(result.error.code)
                if result.error is not None
                and result.error.code in {item.value for item in RetryableFailureCode}
                else RetryableFailureCode.WORKER_INTERRUPTED
            )
            self._record_retryable(job, reason, result=result)
            return
        reason = (
            FatalFailureCode.CLEANUP_FAILED
            if result.cleanup.status.value == "FAILED"
            else FatalFailureCode.PROTOCOL_INVALID
            if result.error is not None and result.error.code == "PROTOCOL_INVALID"
            else FatalFailureCode.RUNNER_FATAL
        )
        self._record_fatal(job, reason, result=result)

    def _runner_input(
        self,
        job: JobRecord,
        request: PersistedExecutionRequest,
    ) -> RunnerInput:
        fields = dict(
            run_id=job.run_id,
            job_id=job.job_id,
            attempt=job.attempt,
            lease_owner=job.lease_owner,
            fencing_token=job.fencing_token,
            created_at_us=job.updated_at_us,
            budget=request.budget,
            project_snapshot=request.project_snapshot,
        )
        return RunnerInput(schema_version="1", **fields)

    def _write_runner_input(
        self,
        paths: AttemptPaths,
        runner_input: RunnerInput,
        known_secrets: Sequence[str],
    ) -> None:
        encoded = canonical_runner_json_bytes(runner_input, known_secrets=known_secrets)
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

    def _write_receipt(self, paths: AttemptPaths, result: RunnerResult) -> None:
        temporary = paths.receipt_path.with_name(
            f".{paths.receipt_path.name}.tmp-{uuid4().hex}"
        )
        try:
            receipt = TrustedResultReceipt(
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
        *,
        result: RunnerResult | None = None,
        error_code: str | None = None,
    ) -> None:
        error = result.error if result is not None else None
        self._attempts.record_retryable_failure(
            RetryableFailure(
                job_id=job.job_id,
                lease_owner=self.lease_owner,
                fencing_token=job.fencing_token,
                now_us=self._utc_now_us(),
                reason_code=reason_code,
                error_code=error.code if error is not None else error_code,
                phase=error.phase if error is not None else None,
                cause_code=error.cause_code if error is not None else None,
                cleanup_issue_codes=(
                    tuple(item.code for item in result.cleanup.issues)
                    if result is not None
                    else ()
                ),
            )
        )

    def _record_fatal(
        self,
        job: JobRecord,
        reason_code: FatalFailureCode,
        *,
        result: RunnerResult | None = None,
        error_code: str | None = None,
        phase: RunnerFailurePhase | None = None,
        cause_code: str | None = None,
        cleanup_issue_codes: tuple[CleanupIssueCode, ...] = (),
    ) -> None:
        error = result.error if result is not None else None
        self._attempts.record_fatal_failure(
            FatalFailure(
                job_id=job.job_id,
                lease_owner=self.lease_owner,
                fencing_token=job.fencing_token,
                now_us=self._utc_now_us(),
                reason_code=reason_code,
                error_code=error.code if error is not None else error_code,
                phase=error.phase if error is not None else phase,
                cause_code=(
                    error.cause_code if error is not None else cause_code
                ),
                cleanup_issue_codes=(
                    tuple(item.code for item in result.cleanup.issues)
                    if result is not None
                    else cleanup_issue_codes
                ),
            )
        )
