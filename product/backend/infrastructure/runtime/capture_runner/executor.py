# 一次正常TARGET取样、身份/资源核对和精确恢复；未知结果不自动重发，正文只写本attempt私有文件。
import hashlib
import json
import os
import time
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.domain.lifecycle import JobState
from product.backend.infrastructure.execution.web.check_runtime import CheckWebRuntime,check_secret_names
from product.backend.infrastructure.execution.web.file_entity import FileEntityPolicy
from product.backend.infrastructure.observers.adapters.json_source import strict_json
from product.backend.infrastructure.observers.records.record_facts import record_value
from product.backend.infrastructure.observers.records.record_source import read_record_source
from product.backend.infrastructure.runtime.process.controlled.node_owned import node_corresponds
from product.backend.infrastructure.runtime.process.controlled.node_locator import controlled_node_executable
from product.backend.infrastructure.artifacts.capture_guard import capture_inputs_current
from product.protocols.preparation.reference_capture import ReferenceCaptureReport,ReferenceCaptureBaseline
from product.backend.infrastructure.artifacts.capture_baselines import save_capture_baseline
from product.protocols.checks.business_facts import ArtifactManifestReference
from product.protocols.web.request import HttpRequestTemplate


def execute_capture(input,*,var_dir,directory,uow_factory,environ,cancellation_requested):
    request=input.request;plan=request.plan;case=plan.case;action=plan.runtime.actions[0]
    started=time.time_ns()//1000
    may_run,identity_matched,resource_matched,recovered,runtime_matched=False,False,False,False,False
    baseline_hash,restored_hash,manifest=None,None,None
    restore_may_run,flow_may_run=False,False
    reasons=[]
    node=controlled_node_executable(environ)
    def active():
        if cancellation_requested() or time.time_ns()//1000-started>plan.runtime.budget.max_duration_us:return False
        with uow_factory() as work:
            job=work.jobs.get(input.job_id)
            valid=(job is not None and job.state is JobState.RUNNING and job.reference_capture_id==request.capture_id
                and (job.attempt,job.fencing_token,job.lease_owner,job.request_hash)==(input.attempt,input.fencing_token,input.lease_owner,input.request_hash)
                and job.cancel_requested_at_us is None and job.lease_expires_at_us>time.time_ns()//1000
                and capture_inputs_current(work,request,var_dir))
        return valid and node_corresponds(var_dir,plan.runtime.runtime_reference,node)
    web=CheckWebRuntime(plan.runtime,environ=environ,cancellation_requested=lambda:not active(),
        request_scope=(request.capture_id,input.job_id,input.attempt),
        reserved_origins=(environ['JIEJIAN_CONTROL_ORIGIN'],) if environ.get('JIEJIAN_CONTROL_ORIGIN') else ())
    claims={item.identity_id:item for item in plan.resource_source.identity_claims}
    owner=claims[case.resource_owner_test_identity_id].application_subject_id
    def snapshot(cleanup=False):
        view=read_record_source(var_dir,plan.runtime.runtime_reference,plan.resource_source,case.resource_id,
            cancelled=(lambda:False) if cleanup else (lambda:not active()))
        if view.snapshot.owner_id!=owner:raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样资源所有者不一致')
        return view.snapshot
    def digest(value):
        return hashlib.sha256(json.dumps(dict(generation=value.generation,resource_id=value.resource_id,
            owner_id=value.owner_id,data=value.data),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def before_target(status):
        nonlocal may_run,identity_matched
        identity_matched=status=='MATCH'
        if not identity_matched or not active():raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样身份或授权无法确认')
        # 发出前保存不确定副作用标记；缺少标记也不能被恢复器解释成可重发。
        with (directory/'target-may-have-run').open('xb') as stream:
            stream.write(b'1');stream.flush();os.fsync(stream.fileno())
        may_run=True
    def save_candidate(raw):
        nonlocal manifest
        with (directory/'candidate.bin').open('xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        manifest=ArtifactManifestReference(asset_id=request.asset_id,size=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    def recover(*,cleanup):
        nonlocal restore_may_run
        recovery=action.recovery
        if recovery is None:raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前没有已确认的恢复操作')
        if web.verify_identity(recovery.source_subject_identity_id,case,cleanup=cleanup)!='MATCH':
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'恢复身份无法确认')
        if not cleanup and not active():raise JiejianError(ErrorCode.STATE_PRECONDITION,'恢复授权已失效')
        restore_may_run=True
        response=web.request(recovery.request,case=case,action_id=action.action_id,
            identity_id=recovery.source_subject_identity_id,cleanup=cleanup)
        if not 200<=response.status_code<300:raise JiejianError(ErrorCode.STATE_PRECONDITION,'恢复请求未完成')
    try:
        if not active() or any(not environ.get(name) for name in check_secret_names(plan.runtime)):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样授权或运行已失效')
        for identity_id,claim in claims.items():
            response=web.request(HttpRequestTemplate(method='GET',path=claim.request_path),case=case,
                action_id=action.action_id,identity_id=identity_id)
            data=strict_json(response.body,262144)
            if (response.status_code!=200 or record_value(data,claim.subject_path)!=claim.application_subject_id
                or record_value(data,claim.role_path)!=claim.application_role):raise JiejianError(ErrorCode.STATE_PRECONDITION,'实际身份或角色不一致')
        before=snapshot();resource_matched=True
        if plan.restore is not None:
            # 此分支没有Flow或TARGET调用；只对照原起点，必要时执行本次明确批准的恢复。
            baseline_hash=plan.restore.baseline_sha256
            if before.generation!=plan.restore.generation:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'原资源代际已变化，不能用新资源证明原操作已恢复')
            identity_matched=web.verify_identity(case.subject_test_identity_id,case)=='MATCH'
            if not identity_matched:raise JiejianError(ErrorCode.STATE_PRECONDITION,'实际身份无法确认')
            if digest(before)!=baseline_hash:recover(cleanup=False)
            restored_hash=digest(snapshot());recovered=baseline_hash==restored_hash
            if not recovered:reasons.append('REFERENCE_RECOVERY_UNVERIFIED')
        else:
            baseline_hash=digest(before)
            save_capture_baseline(directory,ReferenceCaptureBaseline(capture_id=request.capture_id,job_id=input.job_id,
                attempt=input.attempt,fencing_token=input.fencing_token,lease_owner=input.lease_owner,request_hash=input.request_hash,
                baseline_sha256=baseline_hash,generation=before.generation,resource_id=case.resource_id,owner_identity_id=case.resource_owner_test_identity_id,
                collection=plan.resource_source.collection,observed_at_us=time.time_ns()//1000))
            # 起点先持久化；SETUP也可能改变状态，未到TARGET的失败仍需核对恢复。
            flow_may_run=True
            execution,response,identity=web.execute_flow(action,case,verify_identity=True,before_target=before_target,
                entity_policy=FileEntityPolicy(max_bytes=min(plan.runtime.target.max_response_bytes,4194304),private_capture=save_candidate))
            receipt=response.entity_receipt
            if (execution.outcome.value!='ACCEPTED' or not 200<=response.status_code<300 or response.status_code in {202,206}
                or receipt is None or not receipt.complete or manifest is None):
                reasons.extend(receipt.reason_codes if receipt is not None and receipt.reason_codes else ('REFERENCE_FILE_NOT_RECEIVED',))
    except (JiejianError,ValueError,OSError):
        reasons.append('REFERENCE_CAPTURE_INCOMPLETE')
    finally:
        if flow_may_run:
            try:
                if action.state_changing:
                    recover(cleanup=True)
                restored_hash=digest(snapshot(cleanup=True));recovered=baseline_hash==restored_hash
            except (JiejianError,ValueError,OSError):recovered=False
            if not recovered:reasons.append('REFERENCE_RECOVERY_UNVERIFIED')
        runtime_matched=node_corresponds(var_dir,plan.runtime.runtime_reference,node)
        if not runtime_matched:reasons.append('RUNTIME_IDENTITY_UNCONFIRMED')
        if not active():reasons.append('REFERENCE_AUTHORITY_UNAVAILABLE')
        web.close()
    candidate=not reasons and manifest is not None and all((may_run,identity_matched,resource_matched,recovered,runtime_matched))
    recovery_complete=plan.restore is not None and not reasons and all((identity_matched,resource_matched,recovered,runtime_matched))
    return ReferenceCaptureReport(capture_id=request.capture_id,job_id=input.job_id,attempt=input.attempt,
        fencing_token=input.fencing_token,lease_owner=input.lease_owner,request_hash=input.request_hash,plan_hash=plan.plan_hash,
        authorization_id=request.authorization_id,state='CANDIDATE' if candidate else 'RECOVERED' if recovery_complete else 'INCOMPLETE',manifest=manifest if candidate else None,
        restores_capture_id=None if plan.restore is None else plan.restore.capture_id,restore_may_have_run=restore_may_run,
        flow_may_have_run=flow_may_run,
        target_may_have_run=may_run,identity_matched=identity_matched,resource_matched=resource_matched,runtime_matched=runtime_matched,
        recovery_verified=recovered,baseline_sha256=baseline_hash,restored_sha256=restored_hash,started_at_us=started,
        completed_at_us=time.time_ns()//1000,reason_codes=tuple(dict.fromkeys(reasons))[:16])
