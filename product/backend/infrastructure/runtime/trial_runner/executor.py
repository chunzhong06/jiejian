"""独立进程执行冻结HTTP步骤；响应原文与动态值只在内存中使用。"""
import time
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.domain.lifecycle import JobState
from product.backend.infrastructure.execution.web.check_runtime import CheckWebRuntime
from product.backend.infrastructure.artifacts.trial_guard import trial_inputs_current
from product.protocols.checks.check_runtime import CheckFlowStep
from product.protocols.preparation.flow_trial import FlowTrialReport,FlowTrialStep


def execute_trial(input,*,uow_factory,environ,cancellation_requested):
    request,plan=input.request,input.request.plan
    started=time.time_ns()//1000
    def active():
        if cancellation_requested() or time.time_ns()//1000-started>plan.runtime.budget.max_duration_us:return False
        with uow_factory() as work:
            job=work.jobs.get(input.job_id)
            return (job is not None and job.flow_trial_id==request.trial_id and job.state is JobState.RUNNING
                and (job.attempt,job.fencing_token,job.lease_owner,job.request_hash)==(input.attempt,input.fencing_token,input.lease_owner,input.request_hash)
                and job.cancel_requested_at_us is None and job.lease_expires_at_us>time.time_ns()//1000
                and work.flow_trials.get(job.project_id,request.trial_id)==request and trial_inputs_current(work,request))
    # 冻结授权范围不变；实际传输使用更小的本次预算，包含身份核验和恢复请求。
    budget=plan.runtime.budget
    target=plan.runtime.target.model_copy(update={'max_requests':budget.max_requests,
        'timeout_seconds':min(plan.runtime.target.timeout_seconds,budget.request_timeout_us/1_000_000),
        'max_response_bytes':min(plan.runtime.target.max_response_bytes,budget.max_response_bytes)})
    runtime=plan.runtime.model_copy(update={'target':target})
    web=CheckWebRuntime(runtime,environ=environ,cancellation_requested=lambda:not active(),
        request_scope=(request.trial_id,input.job_id,input.attempt),
        reserved_origins=(environ['JIEJIAN_CONTROL_ORIGIN'],) if environ.get('JIEJIAN_CONTROL_ORIGIN') else ())
    steps=[];identity='UNKNOWN';flow_attempted=False;error=None
    recovery='NOT_ATTEMPTED' if plan.state_changing or plan.mode=='RESTORE' else 'NOT_REQUIRED'
    def observe(step,execution,response,error_code=None):
        steps.append(FlowTrialStep(step_id=step.step_id,purpose=step.purpose,
            status_code=None if response is None else response.status_code,
            response_bytes=None if response is None else len(response.body),
            classification='UNKNOWN' if execution is None else execution.outcome.value,error_code=error_code))
    def before_target(status):
        nonlocal identity
        identity=status or 'UNKNOWN'
        if identity!='MATCH' or not active():
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY,'试运行的真实主体或授权无法确认')
    def restore_once():
        nonlocal recovery,error,identity
        try:
            if not active():raise JiejianError(ErrorCode.STATE_PRECONDITION,'恢复前的环境或授权已变化')
            _,response=web.execute_recovery(plan.recovery_request,plan.case,plan.flow.business_action_id)
            if plan.mode=='RESTORE':identity='MATCH'
            # 恢复只陈述HTTP接受/拒绝，不把响应成功解释成业务状态已恢复。
            classification='ACCEPTED' if 200<=response.status_code<300 else 'DENIED' if response.status_code in {401,403} else 'UNKNOWN'
            steps.append(FlowTrialStep(step_id='restore',purpose='RESTORE',status_code=response.status_code,
                response_bytes=len(response.body),classification=classification))
            recovery={'ACCEPTED':'REQUEST_ACCEPTED','DENIED':'REQUEST_DENIED'}.get(classification,'UNCONFIRMED')
        except JiejianError as exc:
            recovery='UNCONFIRMED';error=error or exc.code
            steps.append(FlowTrialStep(step_id='restore',purpose='RESTORE',classification='UNKNOWN',error_code=exc.code))
    try:
        if not active():raise JiejianError(ErrorCode.STATE_PRECONDITION,'试运行输入或授权已变化')
        if plan.mode=='TRIAL':
            actual=tuple(CheckFlowStep(step_id=step.id,purpose=step.purpose.value,request=step.request_template,
                classifier=step.classifier,depends_on_step_ids=step.depends_on_step_ids) for step in plan.flow.steps)
            flow_attempted=True
            web.execute_steps(plan.flow.business_action_id,actual,plan.case,verify_identity=True,
                before_target=before_target,on_step=observe)
        if plan.mode=='RESTORE' or plan.state_changing and flow_attempted:restore_once()
    except JiejianError as exc:
        error=exc.code
        # SETUP失败也可能已改变数据；授权有效时只尝试明确配置的恢复。
        if plan.mode=='TRIAL' and plan.state_changing and flow_attempted and recovery=='NOT_ATTEMPTED':restore_once()
    finally:web.close()
    return FlowTrialReport(trial_id=request.trial_id,job_id=input.job_id,request_hash=input.request_hash,
        fencing_token=input.fencing_token,lease_owner=input.lease_owner,steps=tuple(steps),identity_status=identity,
        target_attempted=web.target_attempted(plan.case.case_id),flow_attempted=flow_attempted,
        recovery=recovery,error_code=error,finished_at_us=time.time_ns()//1000)
