# =============================================================================
# Execution 同步调度适配
#
# 定位
#   把持久 Job 适配为 CLI 等同步调用者可等待的进程边界
#
# 职责
#   启动独立 Worker｜等待 Job 或 Recording｜读取可信 attempt / 已发布结果
#
# 边界
#   同步调用者不直接执行 Handler；返回前必须核对目标身份、hash 与最终状态。
#
# 调用链
#   CLI commands → WorkerDispatcher → worker process / Storage / published artifacts
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from product.backend.core.identifiers import JOB_ID_PATTERN
from product.backend.core.lifecycle import JobState
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RunnerResultType
from product.backend.infra.storage import JobRecord, StorageUnitOfWork
from product.backend.infra.runtime.process_environment import ProcessEnvironmentRole, spawn_python_module
from product.backend.infra.runtime.process_tree import release_process_tree, terminate_process_tree
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.worker_lifetime import write_worker_tree_identity, worker_tree_name
from product.backend.infra.artifacts.run_packages import StagedAttempt, TrustedResultReceipt, attempt_paths_for, final_run_dir, validate_published_run, _parse_runner_result

WORKER_LOG_MAX_BYTES = 1_048_576
WORKER_LOG_BACKUPS = 2


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
        self._paths = RuntimePaths(self.var_dir).ensure_layout()
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
        """以最小环境启动独立 Worker；秘密仅通过受控名称解析，不继承完整父进程环境。"""

        source_environment = dict(self._environ)
        source_environment.setdefault("JIEJIAN_VAR_DIR", str(self.var_dir))
        source_environment.setdefault(
            "JIEJIAN_PYTHON_EXECUTABLE", str(Path(sys.executable).resolve())
        )
        source_environment.setdefault(
            "JIEJIAN_PYTHON_ENVIRONMENT_PATH", str(Path(sys.prefix).resolve())
        )
        source_environment.setdefault("JIEJIAN_PYTHON_ENVIRONMENT_TYPE", "当前 Python 环境")
        arguments = [
            "--var-dir",
            str(self.var_dir),
            "--job-id",
            job_id,
            "--lease-owner",
            lease_owner,
        ]
        for name in secret_names:
            arguments.extend(("--secret-name", name))
        log_path = self._prepare_worker_log(job_id)
        try:
            worker_log = log_path.open("ab", buffering=0)
        except OSError:
            raise JiejianError(
                ErrorCode.RUNNER_START_FAILED,
                "Worker 诊断日志无法打开",
            ) from None
        try:
            return spawn_python_module(
                source_environment,
                "product.backend.infra.runtime.worker_process",
                *arguments,
                role=ProcessEnvironmentRole.WORKER,
                secret_names=secret_names,
                cwd=self._paths.temp,
                popen=self._popen,
                tree_name=worker_tree_name(job_id, lease_owner),
                before_release=lambda _process, controller: write_worker_tree_identity(
                    self.var_dir,
                    job_id,
                    lease_owner,
                    controller,
                ),
                stdin=subprocess.DEVNULL,
                stdout=worker_log,
                stderr=worker_log,
                close_fds=True,
            )
        except (OSError, JiejianError):
            raise JiejianError(
                ErrorCode.RUNNER_START_FAILED,
                "独立 Worker 进程启动失败",
            ) from None
        finally:
            worker_log.close()

    def _prepare_worker_log(self, job_id: str) -> Path:
        """返回按 Job 可定位的有界日志，并在新 launch 前执行固定备份轮换。"""

        if re.fullmatch(JOB_ID_PATTERN, job_id) is None:
            raise JiejianError(ErrorCode.RUNNER_START_FAILED, "Worker 任务 ID 无效")
        root = RuntimePaths(self.var_dir).worker_logs.resolve()
        path = (root / f"{job_id}.log").resolve()
        if not path.is_relative_to(root):
            raise JiejianError(ErrorCode.RUNNER_START_FAILED, "Worker 日志路径越界")
        try:
            root.mkdir(parents=True, exist_ok=True)
            if path.is_file() and path.stat().st_size >= WORKER_LOG_MAX_BYTES:
                oldest = path.with_name(f"{path.name}.{WORKER_LOG_BACKUPS}")
                oldest.unlink(missing_ok=True)
                for index in range(WORKER_LOG_BACKUPS - 1, 0, -1):
                    source = path.with_name(f"{path.name}.{index}")
                    if source.is_file():
                        os.replace(source, path.with_name(f"{path.name}.{index + 1}"))
                os.replace(path, path.with_name(f"{path.name}.1"))
        except OSError:
            raise JiejianError(
                ErrorCode.RUNNER_START_FAILED,
                "Worker 诊断日志准备失败",
            ) from None
        return path

    def wait(
        self,
        job_id: str,
        process: subprocess.Popen[Any] | None,
        *,
        known_secrets: Sequence[str],
        timeout_seconds: float,
    ) -> StagedAttempt:
        """等待受信 staging 或已发布结果；超时和异常退出均转换为稳定领域错误。"""

        deadline = self._monotonic() + timeout_seconds
        while self._monotonic() < deadline:
            job = self._read_job(job_id)
            if job.state is JobState.SUCCEEDED:
                return self._read_published_attempt(job, known_secrets)
            if job.attempt > 0:
                # staging 只有通过完整性校验后才可越过进程边界成为可信结果。
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
            receipt = TrustedResultReceipt.model_validate(
                json.loads(
                    paths.receipt_path.read_text(encoding="utf-8"),
                    object_pairs_hook=_unique_receipt_object,
                ),
                strict=True,
            )
            raw = paths.result_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != receipt.result_sha256:
                raise ValueError("result hash mismatch")
            result = _parse_runner_result(raw, known_secrets=known_secrets)
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
        if result.result_type.value in {"SUCCESS", "SAFETY_STOPPED"}:
            return None
        if (
            result.result_type.value == "CANCELLED"
            and job.state is not JobState.CANCELLED
        ):
            return None
        if (
            result.result_type.value == "RETRYABLE_ERROR"
            and job.state not in {JobState.RETRY_WAIT, JobState.FAILED}
        ):
            return None
        if (
            result.result_type.value == "FATAL_ERROR"
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

    @staticmethod
    def close_process(process: subprocess.Popen[Any] | None, timeout: float = 2.0) -> None:
        """结束同步调用者拥有的 Worker 整棵进程树；清理失败不得伪装为任务完成。"""

        if process is None:
            return
        try:
            if process.poll() is None:
                terminate_process_tree(process, timeout)
            else:
                release_process_tree(process, timeout)
        except Exception:
            raise JiejianError(
                ErrorCode.PROCESS_TREE_FAILED,
                "Worker 进程树未能完整退出",
            ) from None


def _unique_receipt_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate receipt key")
        result[key] = value
    return result
