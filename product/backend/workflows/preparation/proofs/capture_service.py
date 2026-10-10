# GUI一次授权正常取样；预览与提交共用计划，未知响应只按原operation_id回读。
from typing import Literal
from uuid import uuid4
from pydantic import Field
from product.backend.core.errors import ErrorCode,JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.backend.workflows.preparation.proofs.commands import ProofOperation
from product.backend.workflows.preparation.proofs.capture_plan import CaptureSelection,build_capture_plan
from product.backend.workflows.preparation.proofs.capture_jobs import ReferenceCaptureJobs,capture_inputs_current
from product.protocols.preparation.reference_capture import ReferenceCaptureRequest
from product.protocols.preparation.proof_artifacts import ProofArtifactInput,CaptureId


class StartReferenceCapture(ProofOperation):
    selection:CaptureSelection
    plan_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    plan_created_at_us:int=Field(ge=0)
    confirmed:Literal[True]


class CancelReferenceCapture(ProofOperation):
    capture_id:CaptureId


class ReferenceCaptureService:
    def __init__(self,proofs,inspector):
        self.proofs,self.inspector=proofs,inspector
        self.jobs=ReferenceCaptureJobs(proofs.var_dir,proofs._uow)

    def preview(self,project_id,selection):
        with self.proofs._uow() as work:
            return build_capture_plan(self.proofs,self.inspector,work,project_id,selection,created_at_us=self.proofs._clock())

    def gaps(self,project_id):
        from product.backend.workflows.preparation.proofs.capture_jobs import capture_recovery_gaps
        with self.proofs._uow() as work:
            return capture_recovery_gaps(self.proofs.var_dir,work,project_id)

    def start(self,project_id,command):
        def execute(work):
            if command.selection.basis_id!=command.basis_id or command.plan_created_at_us>self.proofs._clock():
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样预览与当前操作不一致')
            plan=build_capture_plan(self.proofs,self.inspector,work,project_id,command.selection,created_at_us=command.plan_created_at_us)
            if plan.plan_hash!=command.plan_hash:raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样材料或范围已变化，请重新查看预览')
            request=ReferenceCaptureRequest(capture_id='rpc_'+uuid4().hex,asset_id='pai_'+uuid4().hex if plan.restore is None else None,project_id=project_id,
                operation_id=command.operation_id,authorization_id='rca_'+uuid4().hex,control_session_id=self.proofs.control_session_id,
                plan=plan,created_at_us=self.proofs._clock())
            action=plan.runtime.actions[0]
            if request.asset_id is not None:
                work.proof_artifacts.add_input(ProofArtifactInput(asset_id=request.asset_id,project_id=project_id,
                    operation_id=command.operation_id,action_id=action.action_id,action_revision=action.action_revision,
                    resource_binding_id=plan.case.resource_binding_id,resource_id=plan.case.resource_id,
                    owner_identity_id=plan.case.resource_owner_test_identity_id,origin='REFERENCE_CAPTURE',
                    reference_capture_id=request.capture_id,state='PENDING',created_at_us=request.created_at_us,basis_id=plan.basis_id))
            job=self.jobs.submit(work,request)
            return dict(capture_id=request.capture_id,asset_id=request.asset_id,job_id=job.job_id,state=job.state.value)
        return self.proofs._operation(project_id,'START_REFERENCE_CAPTURE',command,execute)

    def status(self,project_id,capture_id):
        with self.proofs._uow() as work:
            request,job,report=self.jobs.read(work,project_id,capture_id)
            return dict(capture_id=capture_id,asset_id=request.asset_id,state=job.state.value,
                action_id=request.plan.runtime.actions[0].action_id,resource_binding_id=request.plan.case.resource_binding_id,
                report=None if report is None else report.model_dump(mode='json'),plan_hash=request.plan.plan_hash,
                operation_may_have_run=job.attempt>0 if report is None else report.flow_may_have_run or report.target_may_have_run or report.restore_may_have_run,
                target_may_have_run=job.attempt>0 if report is None else report.target_may_have_run)

    def cancel(self,project_id,command):
        def execute(work):
            request,job,_=self.jobs.read(work,project_id,command.capture_id)
            work.proof_artifacts.revoke(request,self.proofs._clock())
            if job.state in {JobState.PENDING,JobState.RETRY_WAIT,JobState.RUNNING}:
                result=self.proofs._queue.request_cancellation(RequestCancellation(job_id=job.job_id,now_us=self.proofs._clock()),work=work)
                job=result.job
            return dict(capture_id=request.capture_id,state=job.state.value)
        return self.proofs._operation(project_id,'CANCEL_REFERENCE_CAPTURE',command,execute)

    def job_authorized(self,job):
        if job.reference_capture_id is None:return True
        with self.proofs._uow() as work:
            request=work.proof_artifacts.capture(job.project_id,job.reference_capture_id)
            if request is None or request.control_session_id!=self.proofs.control_session_id:return False
            if not capture_inputs_current(work,request,self.proofs.var_dir):return False
            facts=self.proofs._facts(work,job.project_id)
            return facts.basis_id==request.plan.basis_id and facts.runtime==request.plan.runtime.runtime_reference
