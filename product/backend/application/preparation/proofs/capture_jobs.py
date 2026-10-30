# 一次取样的提交与发布事务；只有当前授权、冻结材料和有效fence允许候选进入原材料流程。
import time
from uuid import uuid4
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.domain.lifecycle import JobState
from product.backend.infrastructure.storage import JobRecord
from product.backend.infrastructure.runtime.jobs.events import append_job_event
from product.backend.infrastructure.runtime.jobs.models import JobEventType
from product.backend.infrastructure.artifacts.proof_artifacts import ProofArtifactStore,CaptureReportStore
from product.backend.application.preparation.bindings.sources import BindingSourceInspector
from product.protocols.preparation.proof_sources import proof_fingerprint


def capture_inputs_current(work,request,var_dir):
    from product.backend.infrastructure.artifacts.capture_guard import capture_inputs_current as frozen_inputs_current
    if not frozen_inputs_current(work,request,var_dir):return False
    action=request.plan.runtime.actions[0]
    definition=work.business_boundaries.action_revision(action.action_id,action.action_revision)
    understanding=work.application_understanding.get(request.project_id)
    bindings=[work.action_preparation.execution(action.action_id,action.action_revision),
        work.action_preparation.resource(action.action_id,action.action_revision,request.plan.case.resource_owner_test_identity_id)]
    if action.state_changing:bindings.append(work.action_preparation.recovery(action.action_id,action.action_revision))
    inspector=BindingSourceInspector(var_dir)
    return all(not inspector.reasons(work,binding,definition,understanding) for binding in bindings)


def capture_recovery_gaps(var_dir,work,project_id):
    """只限制当前仍使用的同一资源；新资源不会冒充旧操作已恢复。"""
    work.begin_read_snapshot()
    result=[];reports=CaptureReportStore(var_dir)
    resources=tuple(item for root in work.business_boundaries.list_actions(project_id)
        for item in work.action_preparation.resources(root.action_id,root.current_revision))
    for request in work.proof_artifacts.unresolved_captures(project_id):
        job=work.jobs.get_by_capture(request.capture_id)
        if job is None:raise JiejianError(ErrorCode.STORAGE_STATE,'取样任务缺失')
        active=job.state in {JobState.PENDING,JobState.RUNNING,JobState.RETRY_WAIT}
        if not active and (request.plan.restore is not None or job.attempt==0):continue
        report_hash=work.proof_artifacts.report_hash(project_id,request.capture_id)
        report=None if report_hash is None else reports.read(report_hash)
        if not active and report is not None and (not report.flow_may_have_run and not report.target_may_have_run or report.recovery_verified):continue
        action=request.plan.runtime.actions[0]
        # 不按动作筛选：同一资源也可能被另一条已批准动作继续使用。
        affected=any((item.actual_resource_id,item.resource_owner_test_identity_id)==(request.plan.case.resource_id,
            request.plan.case.resource_owner_test_identity_id) for item in resources)
        if active or affected:
            result.append(dict(capture_id=request.capture_id,action_id=action.action_id,resource_id=request.plan.case.resource_id,
                owner_identity_id=request.plan.case.resource_owner_test_identity_id,
                affected_action_ids=tuple(sorted({item.business_action_id for item in resources if active or
                    (item.actual_resource_id,item.resource_owner_test_identity_id)==(request.plan.case.resource_id,request.plan.case.resource_owner_test_identity_id)})),
                reason='REFERENCE_CAPTURE_IN_PROGRESS' if active else 'REFERENCE_RECOVERY_UNVERIFIED'))
    return tuple(result)


class ReferenceCaptureJobs:
    def __init__(self,var_dir,uow_factory):
        self.var_dir,self._uow=var_dir,uow_factory
        self.artifacts=ProofArtifactStore(var_dir);self.reports=CaptureReportStore(var_dir)

    def submit(self,work,request):
        work.proof_artifacts.add_capture(request)
        job=JobRecord(job_id='job_'+uuid4().hex,project_id=request.project_id,reference_capture_id=request.capture_id,
            operation_type='REFERENCE_CAPTURE',state=JobState.PENDING,idempotency_key=request.operation_id,
            request_hash=proof_fingerprint(request),attempt=0,max_attempts=1,available_at_us=request.created_at_us,
            fencing_token=0,created_at_us=request.created_at_us,updated_at_us=request.created_at_us)
        work.jobs.add(job)
        append_job_event(work,job=job,event_type=JobEventType.JOB_SUBMITTED,source_state=None,target_state=JobState.PENDING,
            occurred_at_us=request.created_at_us,metadata={'operation_type':'REFERENCE_CAPTURE'})
        return job

    def publish(self,report,*,candidate=None,known_secrets=(),require_active_lease=True):
        with self._uow() as work:
            work.acquire_write_lock()
            job=work.jobs.get(report.job_id)
            request=None if job is None else work.proof_artifacts.capture(job.project_id,report.capture_id)
            if (request is None or job.reference_capture_id!=report.capture_id or proof_fingerprint(request)!=report.request_hash
                or (report.plan_hash,report.authorization_id,report.attempt,report.fencing_token)!=(
                    request.plan.plan_hash,request.authorization_id,job.attempt,job.fencing_token)):
                raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样报告不属于原授权和尝试')
            prior=work.proof_artifacts.report_hash(job.project_id,report.capture_id)
            if prior is not None:
                if self.reports.read(prior)!=report or job.state is not JobState.SUCCEEDED:raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样报告不可覆盖')
                return report
            now=time.time_ns()//1000
            if not request.created_at_us<=report.started_at_us<=report.completed_at_us<=now or not capture_inputs_current(work,request,self.var_dir):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样授权或材料已失效')
            if (job.state is not JobState.RUNNING or job.cancel_requested_at_us is not None or job.lease_owner!=report.lease_owner
                or job.lease_expires_at_us is None or require_active_lease and job.lease_expires_at_us<=now):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样已取消或不再属于当前执行者')
            asset=None if request.asset_id is None else work.proof_artifacts.input(job.project_id,request.asset_id)
            if request.asset_id is not None and (asset is None or asset.state!='PENDING'):raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样输入不可发布')
            restore=request.plan.restore
            if restore is None and report.flow_may_have_run:
                from product.backend.infrastructure.artifacts.capture_baselines import read_capture_baseline
                baseline=read_capture_baseline(self.var_dir,work,job.project_id,request.capture_id)
                if baseline.baseline_sha256!=report.baseline_sha256:
                    raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样报告与执行前保存的资源起点不同')
            if (report.restores_capture_id!=(None if restore is None else restore.capture_id)
                or restore is not None and (report.state=='CANDIDATE' or report.target_may_have_run
                    or report.baseline_sha256!=restore.baseline_sha256)):
                raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'恢复报告与原起点不一致')
            if report.state=='CANDIDATE':
                if report.manifest.asset_id!=request.asset_id:raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样文件归属不一致')
                if candidate is not None:
                    content=self.artifacts.accept(candidate,known_secrets)
                    manifest=self.artifacts.save(job.project_id,request.asset_id,content)
                    if manifest!=report.manifest:raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'取样文件内容与报告不同')
                self.artifacts.read(job.project_id,report.manifest,known_secrets=known_secrets)
            digest=self.reports.save(report,known_secrets)
            if not require_active_lease and self.reports.publication(report.capture_id)!=report:
                raise JiejianError(ErrorCode.ARTIFACT_MANIFEST,'恢复只能接收已经封存的原取样报告')
            self.reports.seal_publication(report)
            completed=work.job_control.complete_reference_capture(job_id=job.job_id,capture_id=request.capture_id,
                request_hash=report.request_hash,attempt=report.attempt,lease_owner=report.lease_owner,
                fencing_token=report.fencing_token,now_us=now,require_active_lease=require_active_lease)
            if completed is None:raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样任务已变化')
            if asset is not None:
                work.proof_artifacts.update_input(asset.model_copy(update={'state':'COMPLETE' if report.state=='CANDIDATE' else 'INCOMPLETE',
                    'manifest':report.manifest}),expected_state='PENDING')
            work.proof_artifacts.publish(job.project_id,request.capture_id,digest)
            if report.state=='RECOVERED':work.proof_artifacts.resolve_recovery(job.project_id,restore.capture_id,digest,now)
            if restore is not None or report.recovery_verified or not (report.flow_may_have_run or report.target_may_have_run):
                work.proof_artifacts.resolve_recovery(job.project_id,request.capture_id,digest,now)
            append_job_event(work,job=completed,event_type=JobEventType.JOB_SUCCEEDED,source_state=JobState.RUNNING,
                target_state=JobState.SUCCEEDED,occurred_at_us=now,metadata={'attempt':report.attempt,'fencing_token':report.fencing_token})
            work.commit()
        return report

    def read(self,work,project_id,capture_id):
        work.begin_read_snapshot()
        request=work.proof_artifacts.capture(project_id,capture_id)
        if request is None:raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'这次取样不存在')
        job=work.jobs.get_by_capture(capture_id)
        digest=work.proof_artifacts.report_hash(project_id,capture_id)
        report=None if digest is None else self.reports.read(digest)
        if (job is None or job.request_hash!=proof_fingerprint(request) or (job.state is JobState.SUCCEEDED)!=(report is not None)
            or report is not None and (report.job_id,report.capture_id,report.request_hash,report.attempt,report.fencing_token)!=(
                job.job_id,capture_id,job.request_hash,job.attempt,job.fencing_token)):
            raise JiejianError(ErrorCode.STORAGE_STATE,'取样任务和结果关联不一致')
        return request,job,report
