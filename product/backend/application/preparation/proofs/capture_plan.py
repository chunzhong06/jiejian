# 取样计划只冻结既有ALLOW、账号、资源、正常Flow和恢复；不要求尚未取得的文件证明已采用。
import hashlib
import json
from types import SimpleNamespace
from pydantic import Field
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.application.checks.runtime_bundle import CheckRuntimeBuilder,recorded_request_template
from product.backend.infrastructure.recording.request_store import RecordingRequestStore
from product.protocols.runtime.runtime_identity import RuntimeModel
from product.protocols.preparation.proof_sources import ManagedIdentityClaim,proof_fingerprint
from product.protocols.preparation.reference_capture import ReferenceCapturePlan
from product.protocols.checks.execution_request import FrozenPermission
from product.backend.infrastructure.recording.flows import recorded_flow_path, read_recorded_flow


class CaptureSelection(RuntimeModel):
    basis_id:str=Field(pattern=r'^pb_[0-9a-f]{64}$')
    action_id:str=Field(pattern=r'^bac_[0-9a-f]{32}$')
    action_revision:int=Field(ge=1)
    allow_intent_id:str=Field(pattern=r'^pin_[0-9a-f]{32}$')
    resource_binding_id:str=Field(pattern=r'^res_[0-9a-f]{32}$')
    collection:str=Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
    identity_claims:tuple[ManagedIdentityClaim,...]=Field(min_length=1,max_length=3)
    restore_capture_id:str|None=Field(default=None,pattern=r'^rpc_[0-9a-f]{32}$')


def build_capture_plan(proofs,inspector,work,project_id,selection,*,created_at_us):
    from product.backend.application.preparation.proofs.capture_jobs import capture_recovery_gaps
    from product.backend.infrastructure.artifacts.capture_baselines import read_capture_baseline
    gaps=capture_recovery_gaps(proofs.var_dir,work,project_id)
    if any(item.state.value in {'PENDING','RUNNING','RETRY_WAIT'} for item in work.jobs.list_for_project(project_id)):
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先结束当前任务，再准备参照或核对恢复')
    restore=None
    if selection.restore_capture_id is not None:
        if not any(item['capture_id']==selection.restore_capture_id and item['reason']=='REFERENCE_RECOVERY_UNVERIFIED' for item in gaps):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'这次取样没有待核对的恢复')
        restore=read_capture_baseline(proofs.var_dir,work,project_id,selection.restore_capture_id)
    elif gaps:
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先核对上次取样的恢复情况',details={'reason':gaps[0]['reason']})
    facts=proofs._current(work,project_id,selection)
    action=next((item for item in facts.boundary.actions if (item.action_id,item.revision)==(selection.action_id,selection.action_revision)),None)
    resource=next((item for item in facts.resources if proofs._resource_id(item)==selection.resource_binding_id),None)
    permission=next((item for item in facts.boundary.permission_intents if item.intent_id==selection.allow_intent_id),None)
    if (action is None or resource is None or facts.runtime is None or permission is None
        or permission.expectation.value!='ALLOW' or permission.effective_state.value!='ACTIVE'
        or (permission.business_action_id,permission.action_revision)!=(action.action_id,action.revision)):
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先确认正常权限、测试资源和当前运行实例')
    if not any(effect.effect_kind.value=='FILE_CONTENT_DELIVERY' and effect.effect_id in permission.protected_effect_ids for effect in action.effect_catalog):
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'这条正常权限没有约定完整文件接收，请先核对业务要求')
    execution=work.action_preparation.execution(action.action_id,action.revision)
    recovery=work.action_preparation.recovery(action.action_id,action.revision) if action.state_changing else None
    for binding in (execution,resource,*((recovery,) if action.state_changing else ())):
        reasons=('MATERIAL_MISSING',) if binding is None else inspector.reasons(work,binding,action,facts.understanding)
        if reasons:raise JiejianError(ErrorCode.STATE_PRECONDITION,'正常操作材料尚未齐备',details={'reason':reasons[0]})
    subject,owner=execution.subject_test_identity_id,resource.resource_owner_test_identity_id
    known={item.identity_id:item for item in facts.identities}
    if (subject not in known or owner not in known or execution.resource_owner_test_identity_id!=owner
        or (known[subject].actor_id,known[subject].actor_revision)!=(permission.subject_actor_id,permission.subject_actor_revision)
        or (known[owner].actor_id,known[owner].actor_revision)!=(permission.resource_owner_actor_id,permission.resource_owner_actor_revision)
        or (permission.relation.value=='OWNS')!=(subject==owner)):
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'正常权限与录制账号、资源所有者不一致')
    selected={subject,owner}
    if recovery is not None:selected.add(recovery.subject_test_identity_id)
    if {item.identity_id for item in selection.identity_claims}!=selected:
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'请为本次实际使用的账号提供准确身份核对方式')
    identities,_=proofs._identities(work,SimpleNamespace(config=selection),facts,known)
    recording=work.recordings.get(execution.source_recording_id)
    job=work.jobs.get_by_recording(recording.recording_id)
    recorded=RecordingRequestStore(proofs.var_dir).load(job.job_id,expected_hash=job.request_hash)
    flow=read_recorded_flow(recorded_flow_path(proofs.var_dir,recording),expected_hash=execution.flow_sha256)
    config=dict(action_id=action.action_id,action_revision=action.revision,action_semantic_fingerprint=action.semantic_fingerprint,
        display_name=action.display_name,primary_resource_concept=action.primary_resource_concept,state_changing=action.state_changing,
        flow_id=flow.id,flow_sha256=execution.flow_sha256,execution_binding_fingerprint=execution.binding_fingerprint,
        steps=CheckRuntimeBuilder._ordered_steps(flow),proofs=[])
    if recovery is not None:
        config['recovery']=dict(binding_fingerprint=recovery.binding_fingerprint,source_subject_identity_id=recovery.subject_test_identity_id,
            request=recorded_request_template(recovery.request_template).model_dump(mode='json'))
    # 直接返回文件的TARGET才可取样；原有SETUP和分类器照常冻结，202不能转成后台轮询。
    if config['steps'][-1]['classifier'].get('completion_binding') is not None:
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'请录制实际下载动作，取样不代替异步生成与轮询')
    target=recorded.target_scope
    if target.base_url!=f'http://127.0.0.1:{facts.runtime.port}':raise JiejianError(ErrorCode.STATE_PRECONDITION,'录制地址与当前实例不一致')
    payload=dict(schema_version='1',project_id=project_id,basis_id=facts.basis_id,
        permission=permission.model_dump(mode='json',include=set(FrozenPermission.model_fields)),
        case=dict(case_id='case_'+proof_fingerprint(selection)[:32],resource_id=resource.actual_resource_id,
            subject_test_identity_id=subject,resource_owner_test_identity_id=owner,resource_binding_id=selection.resource_binding_id,
            resource_binding_fingerprint=resource.binding_fingerprint),
        resource_source=dict(collection=selection.collection,identity_claims=[item.model_dump(mode='json') for item in selection.identity_claims]),
        runtime=dict(project_id=project_id,source_fingerprint=facts.observed_source,target=target.model_dump(mode='json'),
            budget=dict(max_requests=target.max_requests,request_timeout_us=int(target.timeout_seconds*1000000),max_duration_us=300000000,
                max_response_bytes=target.max_response_bytes,max_cases=1,recovery_reserve_requests=min(8,target.max_requests-1)),
            identities=[item.model_dump(mode='json') for item in identities],actions=[config],runtime_reference=facts.runtime.model_dump(mode='json')),
        restore=None if restore is None else restore.model_dump(mode='json'),created_at_us=created_at_us)
    # 补齐嵌套DTO默认值后再计算计划摘要，提交端用同一时间和选择重新构建。
    from product.protocols.preparation.reference_capture import CaptureCase,CaptureResourceSource,CaptureRuntimeConfig
    payload['case']=CaptureCase.model_validate_json(json.dumps(payload['case'])).model_dump(mode='json')
    payload['resource_source']=CaptureResourceSource.model_validate_json(json.dumps(payload['resource_source'])).model_dump(mode='json')
    payload['runtime']=CaptureRuntimeConfig.model_validate_json(json.dumps(payload['runtime'])).model_dump(mode='json')
    payload['plan_hash']=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return ReferenceCapturePlan.model_validate_json(json.dumps(payload),strict=True)
