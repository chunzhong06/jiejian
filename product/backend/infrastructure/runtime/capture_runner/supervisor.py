# Worker监督一次取样Runner；只有原授权和fence可发布，失败或取消永不重放TARGET。
import os
import subprocess
import time
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.domain.lifecycle import JobState
from product.backend.infrastructure.artifacts.checks.check_packages import read_check_bytes,reject_check_links
from product.backend.infrastructure.execution.web.check_runtime import check_secret_names
from product.backend.infrastructure.runtime.jobs.models import ClaimJob,CompleteCancellation,FatalFailure,FatalFailureCode
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.runtime.process.control import AttemptProcessControl,DEFAULT_LEASE_DURATION_US,DEFAULT_POLL_INTERVAL_SECONDS,DEFAULT_TERMINATION_GRACE_SECONDS
from product.backend.infrastructure.runtime.process.environment import ProcessEnvironmentRole,spawn_python_module
from product.backend.infrastructure.runtime.process.tree import release_process_tree,terminate_process_tree
from product.backend.infrastructure.artifacts.capture_guard import capture_inputs_current
from product.protocols.preparation.reference_capture import ReferenceCaptureRunnerInput,ReferenceCaptureReport
from product.protocols.preparation.proof_sources import proof_bytes


class ReferenceCaptureHandler:
    def __init__(self,var_dir,*,lease_owner,uow_factory,attempts,publisher,environ):
        self.var_dir,self._owner,self._uow,self._attempts=var_dir,lease_owner,uow_factory,attempts
        self._publisher,self._environ=publisher,environ;self._clock=lambda:time.time_ns()//1000
        self._control=AttemptProcessControl(uow_factory=uow_factory,attempt_service=attempts,lease_owner=lease_owner,
            utc_now_us=self._clock,lease_duration_us=DEFAULT_LEASE_DURATION_US,poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
            termination_grace_seconds=DEFAULT_TERMINATION_GRACE_SECONDS)

    def run_job(self,job_id):
        initial=self._control.read_job(job_id)
        if initial.operation_type!='REFERENCE_CAPTURE' or initial.attempt!=0 or initial.max_attempts!=1:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'正常取样任务不能自动重试')
        claimed=self._attempts.claim(ClaimJob(job_id=job_id,lease_owner=self._owner,now_us=self._clock(),lease_duration_us=DEFAULT_LEASE_DURATION_US))
        if claimed is None:return None
        job,process=claimed.job,None
        try:
            with self._uow() as work:
                request=work.proof_artifacts.capture(job.project_id,job.reference_capture_id)
                if request is None or not capture_inputs_current(work,request,self.var_dir):
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样授权或材料已变化')
            input=ReferenceCaptureRunnerInput(job_id=job_id,attempt=job.attempt,fencing_token=job.fencing_token,
                lease_owner=self._owner,request=request,request_hash=job.request_hash)
            names=check_secret_names(request)
            if any(not self._environ.get(name) for name in names):raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY,'取样账号已失效')
            known=tuple(self._environ[name] for name in names)
            paths=RuntimePaths(self.var_dir).ensure_layout()
            directory=paths.jobs/job_id/'attempts'/f'{job.attempt}-{job.fencing_token}'
            reject_check_links(paths.jobs,directory);directory.mkdir(parents=True,exist_ok=False)
            raw=proof_bytes(input)
            if any(secret and secret.encode() in raw for secret in known):raise JiejianError(ErrorCode.STORAGE_SECRET,'取样输入含敏感内容')
            with (directory/'capture-input.json').open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            process=spawn_python_module(dict(self._environ)|{'JIEJIAN_VAR_DIR':str(self.var_dir)},'product.backend.infrastructure.runtime.capture_runner',
                '--input',str(directory/'capture-input.json'),role=ProcessEnvironmentRole.RUNNER,secret_names=names,cwd=paths.temp,
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)
            timed_out,forced=self._control.monitor(process,job,max_duration_us=request.plan.runtime.budget.max_duration_us,
                cancel_path=directory/'cancel.requested')
            code=process.returncode;release_process_tree(process);process=None
            current=self._control.read_job(job_id)
            if current.cancel_requested_at_us is not None:
                self._attempts.complete_cancellation(CompleteCancellation(job_id=job_id,lease_owner=self._owner,
                    fencing_token=job.fencing_token,now_us=self._clock()))
                return None
            if timed_out or forced or code!=0:raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID,'取样未形成可核对报告')
            raw=read_check_bytes(directory/'capture-report.json',known_secrets=known)
            report=ReferenceCaptureReport.model_validate_json(raw,strict=True)
            if proof_bytes(report)!=raw or (report.job_id,report.capture_id,report.request_hash,report.attempt,report.fencing_token,report.lease_owner)!=(
                job_id,job.reference_capture_id,job.request_hash,job.attempt,job.fencing_token,self._owner):
                raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID,'取样报告不属于当前尝试')
            candidate=None
            if report.manifest is not None:
                path=directory/'candidate.bin';reject_check_links(directory,path)
                with path.open('rb') as stream:candidate=stream.read(4194305)
            return self._publisher.publish(report,candidate=candidate,known_secrets=known)
        except Exception as primary:
            cleanup_failed=False
            if process is not None:
                try:
                    terminate_process_tree(process,DEFAULT_TERMINATION_GRACE_SECONDS) if process.poll() is None else release_process_tree(process)
                except Exception:cleanup_failed=True
            current=self._control.read_job(job_id)
            if current.state is JobState.RUNNING and not self._publisher.reports.has_publication(job.reference_capture_id):
                try:self._attempts.record_fatal_failure(FatalFailure(job_id=job_id,lease_owner=self._owner,fencing_token=job.fencing_token,
                    now_us=self._clock(),reason_code=FatalFailureCode.RUNNER_FATAL,error_code=primary.code if isinstance(primary,JiejianError) else 'RUNNER_FATAL',
                    cause_code='PROCESS_TREE_FAILED' if cleanup_failed else None))
                except JiejianError:pass
            raise
