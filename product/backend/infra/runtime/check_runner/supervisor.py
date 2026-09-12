# 当前 CHECK 的受控进程监督器；复用租约/进程树机制，任何不确定 TARGET 都不自动重试。
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.infra.artifacts.check_packages import check_final_directory, read_check_bytes, reject_check_links, validate_check_package
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.infra.artifacts.check_validation import validate_check_inputs
from product.backend.infra.execution.web.check_runtime import check_secret_names
from product.backend.infra.runtime.jobs.check_requests import CheckRequestStore
from product.backend.infra.runtime.jobs.models import ClaimJob, CompleteCancellation, FatalFailure, FatalFailureCode
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.control import (AttemptProcessControl, DEFAULT_LEASE_DURATION_US,
    DEFAULT_POLL_INTERVAL_SECONDS, DEFAULT_TERMINATION_GRACE_SECONDS)
from product.backend.infra.runtime.process.environment import ProcessEnvironmentRole, spawn_python_module
from product.backend.infra.runtime.process.tree import release_process_tree, terminate_process_tree
from product.protocols.check_result import CheckAssetReference, CheckRunnerInput, canonical_check_document
from product.protocols.check_runtime import check_payload_contains_secret


class CheckRunnerSupervisor:
    def __init__(self, var_dir: Path, *, lease_owner: str, uow_factory, attempts, environ=None, clock_us=None):
        self.var_dir = var_dir.resolve()
        self.lease_owner, self._uow_factory, self._attempts = lease_owner, uow_factory, attempts
        self._environ = dict(os.environ if environ is None else environ)
        self._clock = clock_us or (lambda: time.time_ns() // 1000)
        self._store = CheckRequestStore(self.var_dir)
        self._publisher = CheckPublisher(self.var_dir, uow_factory, clock_us=self._clock)
        self._control = AttemptProcessControl(uow_factory=uow_factory, attempt_service=attempts,
            lease_owner=lease_owner, utc_now_us=self._clock, lease_duration_us=DEFAULT_LEASE_DURATION_US,
            poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS, termination_grace_seconds=DEFAULT_TERMINATION_GRACE_SECONDS)

    def run_job(self, job_id: str):
        initial = self._control.read_job(job_id)
        final = check_final_directory(self.var_dir, initial.project_id, initial.run_id)
        if final.exists():
            request = self._store.load(job_id, expected_hash=initial.request_hash)
            bundle = self._store.load_bundle(job_id, expected_hash=request.config_fingerprint)
            known = tuple(self._environ[name] for name in check_secret_names(bundle) if self._environ.get(name))
            return self._publisher.complete_existing(final, known_secrets=known)
        if initial.attempt != 0 or initial.max_attempts != 1 or initial.operation_type != "CHECK":
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "任务执行请求与既有快照不一致")
        claimed = self._attempts.claim(ClaimJob(job_id=job_id, lease_owner=self.lease_owner,
            now_us=self._clock(), lease_duration_us=DEFAULT_LEASE_DURATION_US))
        if claimed is None:
            return None
        job, process = claimed.job, None
        try:
            request = self._store.load(job_id, expected_hash=job.request_hash)
            bundle = self._store.load_bundle(job_id, expected_hash=request.config_fingerprint)
            validate_check_inputs(request, bundle)
            names = check_secret_names(bundle)
            if any(not self._environ.get(name) for name in names):
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, "执行身份与所需凭据类型不一致，请重新生成检查配置")
            known = tuple(self._environ[name] for name in names)
            if any(check_payload_contains_secret(item.model_dump(mode="json"), known) for item in (request, bundle)):
                raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, "执行快照格式无效")
            paths = RuntimePaths(self.var_dir).ensure_layout()
            attempt = paths.jobs / job_id / "attempts" / f"{job.attempt}-{job.fencing_token}"
            reject_check_links(paths.jobs, attempt)
            attempt.mkdir(parents=True, exist_ok=False)
            input = CheckRunnerInput(run_id=job.run_id, job_id=job_id, attempt=job.attempt,
                lease_owner=job.lease_owner, fencing_token=job.fencing_token, created_at_us=self._clock(),
                request_hash=job.request_hash, config_hash=request.config_fingerprint,
                assets=(CheckAssetReference(logical_id="request", sha256=job.request_hash),
                    CheckAssetReference(logical_id="runtime", sha256=request.config_fingerprint)))
            with (attempt / "input.json").open("xb") as stream:
                stream.write(canonical_check_document(input, known_secrets=known))
                stream.flush()
                os.fsync(stream.fileno())
            source = self._environ | {"JIEJIAN_VAR_DIR": str(self.var_dir)}
            process = spawn_python_module(source, "product.backend.infra.runtime.check_runner",
                "--input", str(attempt / "input.json"), "--staging", str(attempt / "staging"),
                role=ProcessEnvironmentRole.RUNNER, secret_names=names, cwd=paths.temp,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
            timed_out, forced_cancel = self._control.monitor(process, job,
                max_duration_us=bundle.budget.max_duration_us, cancel_path=attempt / "cancel.requested")
            return_code = process.returncode
            # 超时/取消已先发生时，随后释放句柄的错误不能覆盖原始停止原因。
            current = self._control.read_job(job_id)
            try:
                release_process_tree(process)
            except Exception:
                primary_code = (ErrorCode.EXEC_CANCELLED if current.cancel_requested_at_us is not None
                    else ErrorCode.RUNNER_TIMEOUT if timed_out or forced_cancel else ErrorCode.PROCESS_TREE_FAILED)
                raise JiejianError(primary_code, "Runner 进程树无法在有界时间内终止",
                    details={"cleanup_error_code": ErrorCode.PROCESS_TREE_FAILED.value}) from None
            process = None
            if current.cancel_requested_at_us is not None:
                self._attempts.complete_cancellation(CompleteCancellation(job_id=job_id,
                    lease_owner=self.lease_owner, fencing_token=job.fencing_token, now_us=self._clock()))
                return None
            if timed_out or forced_cancel:
                raise JiejianError(ErrorCode.RUNNER_TIMEOUT, "Runner 执行超过有界时限")
            if return_code != 0:
                raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, "执行快照格式无效")
            package = validate_check_package(attempt / "staging", known_secrets=known)
            if package.result.result_type not in ("SUCCESS", "SAFETY_STOPPED"):
                raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, "执行快照格式无效")
            return self._publisher.publish(attempt / "staging", known_secrets=known)
        except Exception as primary:
            cleanup_failed = False
            if process is not None:
                try:
                    terminate_process_tree(process, DEFAULT_TERMINATION_GRACE_SECONDS) if process.poll() is None else release_process_tree(process)
                except Exception:
                    cleanup_failed = True
            # 提升后提交失败留下的 manifest 必须保持 RUNNING，交给幂等 reconciliation；不能标记失败再重放。
            if not final.exists():
                try:
                    current = self._control.read_job(job_id)
                except JiejianError:
                    current = None
                if current is not None and (current.state, current.lease_owner, current.fencing_token) == (JobState.RUNNING, self.lease_owner, job.fencing_token):
                    try:
                        self._attempts.record_fatal_failure(FatalFailure(job_id=job_id, lease_owner=self.lease_owner,
                            fencing_token=job.fencing_token, now_us=self._clock(), reason_code=FatalFailureCode.RUNNER_FATAL,
                            error_code=primary.code if isinstance(primary, JiejianError) else "RUNNER_FATAL",
                            cause_code="PROCESS_TREE_FAILED" if cleanup_failed else None))
                    except JiejianError:
                        pass
            raise


class CheckJobHandler(CheckRunnerSupervisor):
    """Worker registry 的当前 CHECK handler；不提供旧 Run 请求格式回退。"""
