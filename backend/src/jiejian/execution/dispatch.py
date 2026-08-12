# =============================================================================
# Execution 同步调度适配
#
# 定位
#   把持久 Job 适配为 CLI 等同步调用者可等待的进程边界
#
# 职责
#   启动独立 Worker｜等待 Job 或 Recording｜读取可信 attempt / 已发布结果
#
# 调用链
#   CLI commands → WorkerDispatcher → worker process / Storage / published artifacts
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..domain.lifecycle import JobState
from ..errors import ErrorCode, JiejianError
from ..protocols import RunnerResultType, parse_runner_result
from ..storage import JobRecord, StorageUnitOfWork
from .process_environment import minimal_process_environment
from .published_artifacts import (
    StagedAttempt,
    TrustedResultReceiptV1,
    attempt_paths_for,
    final_run_dir,
    validate_published_run,
)


class WorkerDispatcher:
    """启动与 CLI 生命周期解耦的 Worker，并等待其可信结果标记。"""

    def __init__(
        self,
        *,
        var_dir: Path,
        uow_factory: Callable[..., StorageUnitOfWork],
        environ: Mapping[str, str] | None = None,
        popen: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self._uow_factory = uow_factory
        self._environ = os.environ if environ is None else environ
        self._popen = popen
        self._monotonic = monotonic
        self._sleep = sleep

    def start(
        self,
        *,
        job_id: str,
        lease_owner: str,
        secret_names: Sequence[str],
    ) -> subprocess.Popen[Any]:
        environment = minimal_process_environment(
            self._environ,
            secret_names=secret_names,
        )
        command = [
            sys.executable,
            "-B",
            "-m",
            "jiejian.worker.runtime",
            "--var-dir",
            str(self.var_dir),
            "--job-id",
            job_id,
            "--lease-owner",
            lease_owner,
        ]
        kwargs: dict[str, Any] = {
            "cwd": str(self.var_dir),
            "env": environment,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
        else:
            kwargs["start_new_session"] = True
        try:
            return self._popen(command, **kwargs)
        except OSError:
            raise JiejianError(
                ErrorCode.RUNNER_START_FAILED,
                "独立 Worker 进程启动失败",
            ) from None

    def wait(
        self,
        job_id: str,
        process: subprocess.Popen[Any] | None,
        *,
        known_secrets: Sequence[str],
        timeout_seconds: float,
    ) -> StagedAttempt:
        deadline = self._monotonic() + timeout_seconds
        while self._monotonic() < deadline:
            job = self._read_job(job_id)
            if job.state is JobState.SUCCEEDED:
                return self._read_published_attempt(job, known_secrets)
            if job.attempt > 0:
                staged = self._read_trusted_attempt(job, known_secrets)
                if staged is not None:
                    if (
                        staged.result.result_type is RunnerResultType.RETRYABLE_ERROR
                        and job.state is JobState.RETRY_WAIT
                        and job.attempt < job.max_attempts
                    ):
                        pass
                    else:
                        return staged
            if process is None and job.state in {
                JobState.FAILED,
                JobState.CANCELLED,
            }:
                raise JiejianError(
                    ErrorCode.RUNNER_RESULT_MISSING,
                    "任务终态缺少可展示的可信结果",
                )
            if process is not None and process.poll() is not None and job.state not in {
                JobState.RUNNING,
                JobState.RETRY_WAIT,
            }:
                raise JiejianError(
                    ErrorCode.RUNNER_RESULT_MISSING,
                    "Worker 未留下可展示的可信结果",
                )
            if process is not None and process.poll() is not None and job.state in {
                JobState.RUNNING,
                JobState.RETRY_WAIT,
            }:
                raise JiejianError(
                    ErrorCode.RUNNER_RESULT_MISSING,
                    "Worker 在任务完成前退出",
                )
            self._sleep(0.05)
        raise JiejianError(ErrorCode.RUNNER_TIMEOUT, "等待 Worker 结果超时")

    def wait_recording(
        self,
        job_id: str,
        process: subprocess.Popen[Any] | None,
        *,
        timeout_seconds: float,
    ) -> JobRecord:
        """等待 Recording Worker 将 Recording 推进到可审阅或失败终态。"""

        deadline = self._monotonic() + timeout_seconds
        while self._monotonic() < deadline:
            job = self._read_job(job_id)
            if job.state is JobState.SUCCEEDED:
                return job
            if job.state in {JobState.FAILED, JobState.CANCELLED}:
                raise JiejianError(
                    ErrorCode.RECORD_REPLAY_FAILED,
                    "Recording Worker 未形成可审阅结果",
                )
            if process is not None and process.poll() is not None:
                raise JiejianError(
                    ErrorCode.RUNNER_RESULT_MISSING,
                    "Recording Worker 在任务完成前退出",
                )
            self._sleep(0.05)
        raise JiejianError(ErrorCode.RUNNER_TIMEOUT, "等待 Recording 结果超时")

    def _read_trusted_attempt(
        self,
        job: JobRecord,
        known_secrets: Sequence[str],
    ) -> StagedAttempt | None:
        paths = attempt_paths_for(self.var_dir, job)
        if not paths.receipt_path.is_file() or not paths.result_path.is_file():
            return None
        try:
            receipt = TrustedResultReceiptV1.model_validate(
                json.loads(
                    paths.receipt_path.read_text(encoding="utf-8"),
                    object_pairs_hook=_unique_receipt_object,
                ),
                strict=True,
            )
            raw = paths.result_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != receipt.result_sha256:
                raise ValueError("result hash mismatch")
            result = parse_runner_result(raw, known_secrets=known_secrets)
        except (OSError, json.JSONDecodeError, ValidationError, ValueError, JiejianError):
            raise JiejianError(
                ErrorCode.RUNNER_PROTOCOL_INVALID,
                "可信结果标记校验失败",
            ) from None
        if (
            receipt.job_id != result.job_id
            or receipt.run_id != result.run_id
            or receipt.attempt != result.attempt
            or receipt.lease_owner != result.lease_owner
            or receipt.fencing_token != result.fencing_token
            or receipt.job_id != job.job_id
            or receipt.run_id != job.run_id
            or receipt.attempt != job.attempt
            or receipt.fencing_token != job.fencing_token
            or result.lease_owner != job.lease_owner
        ):
            raise JiejianError(
                ErrorCode.RUNNER_PROTOCOL_INVALID,
                "可信结果标记关联信息不匹配",
            )
        if result.result_type in {
            RunnerResultType.SUCCESS,
            RunnerResultType.SAFETY_STOPPED,
        }:
            return None
        if (
            result.result_type is RunnerResultType.CANCELLED
            and job.state is not JobState.CANCELLED
        ):
            return None
        if (
            result.result_type is RunnerResultType.RETRYABLE_ERROR
            and job.state not in {JobState.RETRY_WAIT, JobState.FAILED}
        ):
            return None
        if (
            result.result_type is RunnerResultType.FATAL_ERROR
            and job.state is not JobState.FAILED
        ):
            return None
        return StagedAttempt(result=result, paths=paths)

    def _read_published_attempt(
        self,
        job: JobRecord,
        known_secrets: Sequence[str],
    ) -> StagedAttempt:
        final_dir = final_run_dir(self.var_dir, job.project_id, job.run_id)
        try:
            published = validate_published_run(
                final_dir,
                known_secrets=known_secrets,
            )
        except JiejianError:
            raise JiejianError(
                ErrorCode.RUNNER_RESULT_MISSING,
                "任务终态缺少已发布结果",
            ) from None
        if (
            published.manifest.job_id != job.job_id
            or published.manifest.attempt != job.attempt
            or published.manifest.fencing_token != job.fencing_token
        ):
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "已发布结果 fencing 不匹配")
        attempt_paths = attempt_paths_for(self.var_dir, job)
        published_paths = replace(
            attempt_paths,
            staging_dir=final_dir,
            result_path=final_dir / "result.json",
        )
        return StagedAttempt(result=published.result, paths=published_paths)

    def _read_job(self, job_id: str) -> JobRecord:
        with self._uow_factory() as work:
            job = work.jobs.get(job_id)
            if job is None:
                raise JiejianError(ErrorCode.JOB_NOT_FOUND, "任务不存在")
            return job


def _unique_receipt_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate receipt key")
        result[key] = value
    return result
