# Worker监督独立只读Runner；报告发布依赖有效租约，失败或取消不重放预检查。
import os
import subprocess
import time

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.infra.artifacts.check_packages import read_check_bytes, reject_check_links
from product.backend.infra.execution.web.check_runtime import check_secret_names
from product.backend.infra.runtime.jobs.models import ClaimJob, CompleteCancellation, FatalFailure, FatalFailureCode
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.control import AttemptProcessControl, DEFAULT_LEASE_DURATION_US, DEFAULT_POLL_INTERVAL_SECONDS, DEFAULT_TERMINATION_GRACE_SECONDS
from product.backend.infra.runtime.process.environment import ProcessEnvironmentRole, spawn_python_module
from product.backend.infra.runtime.process.tree import release_process_tree, terminate_process_tree
from product.protocols.proof_sources import ProofRunnerInput, ProofPreflightReport, proof_bytes


class ProofPreflightHandler:
    def __init__(self, var_dir, *, lease_owner, uow_factory, attempts, publisher, environ):
        self.var_dir, self._owner, self._uow, self._attempts = var_dir, lease_owner, uow_factory, attempts
        self._publisher, self._environ = publisher, environ
        self._clock = lambda: time.time_ns() // 1000
        self._control = AttemptProcessControl(uow_factory=uow_factory, attempt_service=attempts,
            lease_owner=lease_owner, utc_now_us=self._clock, lease_duration_us=DEFAULT_LEASE_DURATION_US,
            poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS, termination_grace_seconds=DEFAULT_TERMINATION_GRACE_SECONDS)

    def run_job(self, job_id):
        initial = self._control.read_job(job_id)
        if initial.operation_type != 'PROOF_PREFLIGHT' or initial.attempt != 0 or initial.max_attempts != 1:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '预检查任务不能自动重试')
        claimed = self._attempts.claim(ClaimJob(job_id=job_id, lease_owner=self._owner,
            now_us=self._clock(), lease_duration_us=DEFAULT_LEASE_DURATION_US))
        if claimed is None:
            return None
        job, process = claimed.job, None
        try:
            with self._uow() as work:
                request = work.proof_sources.preflight(job.project_id, job.preflight_id)
            input = ProofRunnerInput(job_id=job_id, attempt=job.attempt, fencing_token=job.fencing_token,
                lease_owner=self._owner, request=request, request_fingerprint=job.request_hash)
            names = check_secret_names(request)
            known = tuple(self._environ[name] for name in names if self._environ.get(name))
            paths = RuntimePaths(self.var_dir).ensure_layout()
            directory = paths.jobs / job_id / 'attempts' / f'{job.attempt}-{job.fencing_token}'
            reject_check_links(paths.jobs, directory)
            directory.mkdir(parents=True, exist_ok=False)
            raw = proof_bytes(input)
            if any(secret and secret.encode() in raw for secret in known):
                raise JiejianError(ErrorCode.STORAGE_SECRET, '预检查输入包含敏感内容')
            with (directory / 'proof-input.json').open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            process = spawn_python_module(dict(self._environ) | {'JIEJIAN_VAR_DIR':str(self.var_dir)},
                'product.backend.infra.runtime.proof_runner', '--input', str(directory / 'proof-input.json'),
                role=ProcessEnvironmentRole.RUNNER, secret_names=names, cwd=paths.temp,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
            timed_out, forced = self._control.monitor(process, job, max_duration_us=30_000_000,
                cancel_path=directory / 'cancel.requested')
            code = process.returncode
            release_process_tree(process)
            process = None
            current = self._control.read_job(job_id)
            if current.cancel_requested_at_us is not None:
                self._attempts.complete_cancellation(CompleteCancellation(job_id=job_id,
                    lease_owner=self._owner, fencing_token=job.fencing_token, now_us=self._clock()))
                return None
            if timed_out or forced or code != 0:
                raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, '预检查未形成可读取的报告')
            report = ProofPreflightReport.model_validate_json(read_check_bytes(directory / 'proof-report.json', known_secrets=known))
            if (report.job_id, report.preflight_id, report.request_fingerprint, report.attempt,
                    report.fencing_token, report.lease_owner) != (job_id, job.preflight_id, job.request_hash,
                    job.attempt, job.fencing_token, self._owner):
                raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, '预检查报告不属于当前尝试')
            return self._publisher.publish(report, known_secrets=known)
        except Exception as primary:
            cleanup_failed = False
            if process is not None:
                try:
                    terminate_process_tree(process, DEFAULT_TERMINATION_GRACE_SECONDS) if process.poll() is None else release_process_tree(process)
                except Exception:
                    cleanup_failed = True
            current = self._control.read_job(job_id)
            if current.state is JobState.RUNNING:
                try:
                    self._attempts.record_fatal_failure(FatalFailure(job_id=job_id, lease_owner=self._owner,
                        fencing_token=job.fencing_token, now_us=self._clock(), reason_code=FatalFailureCode.RUNNER_FATAL,
                        error_code=primary.code if isinstance(primary, JiejianError) else 'RUNNER_FATAL',
                        cause_code='PROCESS_TREE_FAILED' if cleanup_failed else None))
                except JiejianError:
                    pass
            raise
