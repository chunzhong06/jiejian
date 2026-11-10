"""GUI与Agent共用的场景试运行用例；预览不发请求，确认后只提交一次Job。"""
from typing import Literal
from uuid import uuid4
from pydantic import Field
from product.protocols.web.base import ProtocolModel
from product.protocols.preparation.flow_trial import FlowTrialPlan,FlowTrialRequest
from product.protocols.preparation.proof_sources import proof_fingerprint
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.domain.lifecycle import JobState
from product.backend.application.checks.runtime_bundle import recorded_request_template
from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.application.test_identities.freezing import freeze_check_identity
from product.backend.application.preparation.trial_jobs import FlowTrialJobs,trial_recovery_gaps,read_trial_facts,recovery_gaps_from_facts
from product.backend.infrastructure.artifacts.trial_guard import trial_inputs_current
from product.backend.infrastructure.runtime.jobs.models import RequestCancellation


class TrialSelection(ProtocolModel):
    flow_id: str = Field(pattern=r'^ofl_[0-9a-f]{32}$')
    revision: int = Field(ge=1)
    subject_identity_id: str | None = Field(default=None,pattern=r'^tid_[0-9a-f]{32}$')
    resource_owner_identity_id: str | None = Field(default=None,pattern=r'^tid_[0-9a-f]{32}$')
    resource_id: str | None = Field(default=None,min_length=1,max_length=256)
    restore_trial_id: str | None = Field(default=None,pattern=r'^ftr_[0-9a-f]{32}$')


class StartFlowTrial(ProtocolModel):
    selection: TrialSelection
    plan_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    operation_id: str = Field(min_length=1,max_length=128,pattern=r'^[A-Za-z0-9._:-]+$')
    confirmed: Literal[True]


class FlowTrialService:
    def __init__(self,flows,credentials,registry,queue,*,control_session_id):
        self._flows,self._uow,self._clock=flows,flows._uow,flows._clock
        self._credentials,self._registry,self._queue=credentials,registry,queue
        self.control_session_id=control_session_id
        self.jobs=FlowTrialJobs(flows._var_dir,self._uow)

    def _plan(self,work,project_id,selection):
        flow=work.operation_flows.get(selection.flow_id,selection.revision)
        if flow is None:raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先保存要试运行的场景修订')
        action,_,understanding=self._flows.validate_saved(work,project_id,flow)
        if flow.resource_injection.consumer.value.startswith('RESPONSE_'):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'试运行需要已有明确编号的资源；创建资源场景请使用正式检查及其恢复核验')
        may_change=action.state_changing or any(step.request_template.method not in {'GET','HEAD'} for step in flow.steps)
        subject=selection.subject_identity_id or flow.subject_test_identity_id
        owner=selection.resource_owner_identity_id or flow.resource_owner_test_identity_id
        resource=selection.resource_id or flow.actual_resource_id
        if selection.restore_trial_id is not None:
            original=work.flow_trials.get(project_id,selection.restore_trial_id)
            if original is None or original.plan.mode!='TRIAL' or original.plan.flow!=flow:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'恢复必须引用原试运行的准确场景修订')
            case=original.plan.case
            if (subject,owner,resource)!=(case.subject_test_identity_id,case.resource_owner_test_identity_id,case.resource_id):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'恢复账号和资源必须与原试运行一致')
        registered=self._registry.snapshot(project_id)
        verification={} if registered is None else {item.identity_id:item.verification for item in registered.identities}
        identities=[];updated={}
        for identity_id in sorted({subject,owner}):
            record=work.test_identities.get(identity_id)
            root=None if record is None else work.business_boundaries.actor(record.actor_id)
            actor=None if record is None else work.business_boundaries.actor_revision(record.actor_id,record.actor_revision)
            if record is None or record.project_id!=project_id or root is None or actor is None or root.current_revision!=record.actor_revision:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY,'所选测试账号的业务角色已变化')
            identities.append(freeze_check_identity(record,self._credentials.profile_identity(record),actor.display_name,
                verification.get(identity_id),environment=understanding.environment))
            updated[identity_id]=record.updated_at_us
        requests=len(flow.steps)+len(identities)+2
        if requests>flow.target_scope.max_requests:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'环境请求预算不足以完成场景及身份核验、恢复')
        payload=dict(flow=flow.model_dump(mode='json'),runtime=dict(project_id=project_id,target=flow.target_scope.model_dump(mode='json'),
            identities=identities,budget=dict(max_requests=requests,request_timeout_us=int(flow.target_scope.timeout_seconds*1_000_000),
                max_duration_us=min(300_000_000,int(flow.target_scope.timeout_seconds*1_000_000)*requests),
                max_response_bytes=flow.target_scope.max_response_bytes,max_cases=1,recovery_reserve_requests=2 if may_change else 0)),
            case=dict(case_id='trial_'+boundary_sha256(selection.model_dump(mode='json'))[:32],resource_id=resource,
                subject_test_identity_id=subject,resource_owner_test_identity_id=owner),identity_updated_at_us=updated,
            recovery_request=None if flow.recovery is None else recorded_request_template(flow.recovery).model_dump(mode='json'),
            state_changing=may_change,mode='RESTORE' if selection.restore_trial_id else 'TRIAL',origin_trial_id=selection.restore_trial_id)
        try:plan=FlowTrialPlan.model_validate_json(__import__('json').dumps(payload),strict=True)
        except ValueError:raise JiejianError(ErrorCode.STATE_PRECONDITION,'请确认主体核验、唯一末尾受检步骤和必要的恢复请求') from None
        return plan

    def preview(self,project_id,selection):
        with self._uow() as work:
            plan=self._plan(work,project_id,selection)
        return dict(plan=plan.model_dump(mode='json'),plan_hash=proof_fingerprint(plan))

    def start(self,project_id,command):
        with self._uow() as work:
            work.acquire_write_lock()
            existing=work.jobs.get_by_idempotency(project_id,'FLOW_TRIAL',command.operation_id)
            if existing is not None:
                request=work.flow_trials.get(project_id,existing.flow_trial_id)
                if proof_fingerprint(request.plan)!=command.plan_hash:
                    raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT,'同一操作编号已经提交其他试运行计划')
                return self._read(work,project_id,request.trial_id)
            try:
                plan=self._plan(work,project_id,command.selection)
            except JiejianError as error:
                raise error.not_accepted() from None
            if proof_fingerprint(plan)!=command.plan_hash:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'场景、环境或账号已变化，请重新预览').not_accepted()
            if any(job.state in {JobState.PENDING,JobState.RUNNING,JobState.RETRY_WAIT} for job in work.jobs.list_for_project(project_id)):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先结束当前应用的其他执行任务').not_accepted()
            gaps=trial_recovery_gaps(work,project_id)
            if plan.mode=='RESTORE':
                if not any(item.trial_id==plan.origin_trial_id for item in gaps):
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,'原试运行没有待处理的恢复请求').not_accepted()
            elif any(item.plan.case.resource_id==plan.case.resource_id for item in gaps):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'该资源的上次试运行恢复情况未明确，请先处理原记录').not_accepted()
            request=FlowTrialRequest(trial_id='ftr_'+uuid4().hex,operation_id=command.operation_id,
                control_session_id=self.control_session_id,created_at_us=self._clock(),plan=plan)
            self.jobs.submit(work,request)
            result=self._read(work,project_id,request.trial_id)
            work.commit();return result

    def _read(self,work,project_id,trial_id):
        readings=read_trial_facts(work,project_id)
        item=next((item for item in readings if item.request.trial_id==trial_id),None)
        if item is None:raise JiejianError(ErrorCode.STATE_PRECONDITION,'未找到该应用的试运行')
        return self._view(item,{request.trial_id for request in recovery_gaps_from_facts(readings)})

    @staticmethod
    def _view(item,pending):
        request,job,report=item.request,item.job,item.report
        return dict(request=request.model_dump(mode='json'),job_id=job.job_id,state=job.state.value,
            report=None if report is None else report.model_dump(mode='json'),operation_may_have_run=job.attempt>0,
            recovery_pending=request.trial_id in pending)

    def read(self,project_id,trial_id):
        with self._uow() as work:
            work.begin_read_snapshot()
            return self._read(work,project_id,trial_id)

    def requested(self,project_id,operation_id):
        with self._uow() as work:
            work.begin_read_snapshot()
            job=work.jobs.get_by_idempotency(project_id,'FLOW_TRIAL',operation_id)
            return None if job is None else self._read(work,project_id,job.flow_trial_id)

    def history(self,project_id):
        with self._uow() as work:
            work.begin_read_snapshot()
            readings=read_trial_facts(work,project_id)
            pending={item.trial_id for item in recovery_gaps_from_facts(readings)}
            return [self._view(item,pending) for item in readings]

    def cancel(self,project_id,trial_id):
        with self._uow() as work:
            work.acquire_write_lock();value=self._read(work,project_id,trial_id)
            self._queue.request_cancellation(RequestCancellation(job_id=value['job_id'],now_us=self._clock()),work=work)
            result=self._read(work,project_id,trial_id)
            work.commit();return result

    def job_authorized(self,job):
        if job.flow_trial_id is None:return True
        with self._uow() as work:
            request=work.flow_trials.get(job.project_id,job.flow_trial_id)
            return request is not None and request.control_session_id==self.control_session_id and trial_inputs_current(work,request)

    def gaps(self,project_id):
        with self._uow() as work:
            work.begin_read_snapshot()
            resources=tuple(item for root in work.business_boundaries.list_actions(project_id)
                for item in work.action_preparation.resources(root.action_id,root.current_revision))
            readings=read_trial_facts(work,project_id)
            pending={item.trial_id for item in recovery_gaps_from_facts(readings)}
            result=[]
            for item in readings:
                request,job=item.request,item.job
                active=job.state in {JobState.PENDING,JobState.RUNNING,JobState.RETRY_WAIT}
                if not active and request.trial_id not in pending:continue
                case=request.plan.case
                affected=tuple(sorted({item.business_action_id for item in resources if active or
                    (item.actual_resource_id,item.resource_owner_test_identity_id)==(case.resource_id,case.resource_owner_test_identity_id)}))
                if affected:result.append(dict(trial_id=request.trial_id,action_id=request.plan.flow.business_action_id,
                    resource_id=case.resource_id,owner_identity_id=case.resource_owner_test_identity_id,affected_action_ids=affected,
                    reason='FLOW_TRIAL_IN_PROGRESS' if active else 'FLOW_TRIAL_RECOVERY_UNCONFIRMED'))
            return tuple(result)
