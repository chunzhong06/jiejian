"""单次场景试运行的提交、fence发布和恢复缺口，不拥有正式检查结果。"""
import time
from uuid import uuid4
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.domain.lifecycle import JobState
from product.backend.infrastructure.storage import JobRecord
from product.backend.infrastructure.runtime.jobs.models import JobEventType
from product.backend.infrastructure.runtime.jobs.events import append_job_event
from product.protocols.preparation.proof_sources import proof_fingerprint


def trial_recovery_gaps(work,project_id):
    requests=work.flow_trials.list(project_id)
    restored=set()
    for request in requests:
        report=work.flow_trials.report(project_id,request.trial_id)
        if request.plan.mode=='RESTORE' and report is not None and report.recovery=='REQUEST_ACCEPTED':
            restored.add(request.plan.origin_trial_id)
    gaps=[]
    for request in requests:
        if request.plan.mode!='TRIAL' or not request.plan.state_changing or request.trial_id in restored:continue
        job=work.jobs.get_by_flow_trial(request.trial_id)
        report=work.flow_trials.report(project_id,request.trial_id)
        if job is None or job.attempt==0:continue
        if report is not None and (not report.flow_attempted or report.recovery=='REQUEST_ACCEPTED'):continue
        gaps.append(request)
    return tuple(gaps)


class FlowTrialJobs:
    def __init__(self,var_dir,uow_factory):
        self.var_dir,self._uow=var_dir,uow_factory

    def submit(self,work,request):
        work.flow_trials.add(request)
        job=JobRecord(job_id='job_'+uuid4().hex,project_id=request.plan.flow.project_id,flow_trial_id=request.trial_id,
            operation_type='FLOW_TRIAL',state=JobState.PENDING,idempotency_key=request.operation_id,
            request_hash=proof_fingerprint(request),attempt=0,max_attempts=1,available_at_us=request.created_at_us,
            fencing_token=0,created_at_us=request.created_at_us,updated_at_us=request.created_at_us)
        work.jobs.add(job)
        append_job_event(work,job=job,event_type=JobEventType.JOB_SUBMITTED,source_state=None,target_state=JobState.PENDING,
            occurred_at_us=request.created_at_us,metadata={'operation_type':'FLOW_TRIAL'})
        return job

    def publish(self,report,*,require_active_lease=True):
        now=time.time_ns()//1000
        with self._uow() as work:
            work.acquire_write_lock()
            request=work.flow_trials.get(work.jobs.get(report.job_id).project_id,report.trial_id)
            if request is None or proof_fingerprint(request)!=report.request_hash:
                raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID,'试运行报告与授权不符')
            existing=work.flow_trials.report(request.plan.flow.project_id,report.trial_id)
            if existing is not None:
                if existing!=report:raise JiejianError(ErrorCode.STATE_PRECONDITION,'试运行已有不同报告')
                return existing
            completed=work.job_control.complete_flow_trial(job_id=report.job_id,trial_id=report.trial_id,
                request_hash=report.request_hash,attempt=report.attempt,lease_owner=report.lease_owner,
                fencing_token=report.fencing_token,now_us=now,require_active_lease=require_active_lease)
            if completed is None:raise JiejianError(ErrorCode.STATE_PRECONDITION,'试运行已取消或失去发布权')
            work.flow_trials.publish(report)
            append_job_event(work,job=completed,event_type=JobEventType.JOB_SUCCEEDED,source_state=JobState.RUNNING,
                target_state=JobState.SUCCEEDED,occurred_at_us=now,metadata={'attempt':report.attempt,'fencing_token':report.fencing_token})
            work.commit()
        return report
