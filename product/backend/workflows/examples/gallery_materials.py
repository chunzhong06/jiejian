# 官方材料通过独立进程实际登录示例账号，再准备录制和来源候选；来源授权、文件确认和采用仍由人决定。
import json
import hashlib
from uuid import uuid4
from product.backend.core.errors import ErrorCode,JiejianError
from product.backend.core.recording.models import RecordingPurpose
from product.backend.workflows.test_identities.service import TestIdentityStatus
from product.backend.workflows.preparation.proofs.commands import SaveProofSource
from product.backend.workflows.preparation.proofs.artifact_inputs import UploadProofArtifact
from product.protocols.preparation.proof_sources import AtomicProofSourceConfig,FileProofSourceConfig
from product.protocols import RecordingEventKind,ValueSlotConsumer
from product.backend.workflows.examples.materials import _event
from product.backend.workflows.examples.gallery_recipe import ACTION_ROUTES


def gallery_identities(service,project):
    boundary=service.boundaries.view(project)
    actors={item.display_name:item for item in boundary.actors}
    actions={item.display_name:item for item in boundary.actions}
    if set(actors)!={'项目负责人','评审'} or set(actions)!=set(ACTION_ROUTES):
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先审阅数字展馆的权限提案，再准备示例材料')
    if any(item.status!='CURRENT' for item in (*boundary.actor_bindings,*boundary.action_bindings)):
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先核对当前代码与原业务动作的对应')
    identities=[];existing=service.identities.list(project)
    state=service.runtime.state(project);origin=f"http://127.0.0.1:{state['configuration']['port']}"
    for name,label in [('项目负责人','curator · 项目负责人'),('评审','judge · 评审')]:
        actor=actors[name];found=[item for item in existing if item.actor_id==actor.actor_id and item.actor_revision==actor.revision]
        if len(found)>1:raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前角色有多个账号，请在普通准备界面选择实际测试账号')
        if found and found[0].label != label:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前角色使用自定义账号，请在账号页完成登录后准备材料')
        identities.append(found[0] if found else service.identities.create(project,actor_id=actor.actor_id,actor_revision=actor.revision,label=label))
    return identities


def prepare_gallery_materials(service,project):
    identities=gallery_identities(service,project)
    state=service.runtime.state(project);origin=f"http://127.0.0.1:{state['configuration']['port']}"
    for identity,account in zip(identities,('curator','judge'),strict=True):
        service.identity_preparations.prepare_official(identity.identity_id,account=account,origin=origin)
    prepare_gallery_content(service,project,[service.identities.get(item.identity_id) for item in identities])


def prepare_gallery_content(service,project,identities):
    """复用身份就绪事实建立录制、资源和文件；已有当前绑定不重复创建。"""
    boundary=service.boundaries.view(project)
    actions={item.display_name:item for item in boundary.actions}
    state=service.runtime.state(project);origin=f"http://127.0.0.1:{state['configuration']['port']}"
    if any(item.status is not TestIdentityStatus.PREPARED for item in identities):
        raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY,'示例账号尚未准备好')
    owner,reviewer=identities
    source=service.understanding.get(project).source_fingerprint
    views={item.action_id:item for item in service.preparation.get(project).actions}
    for name,action in actions.items():
        prior=views[action.action_id]
        if prior.execution.status.value=='SATISFIED' and all(item.status.value=='SATISFIED' for item in prior.resources) and prior.recovery.status.value in {'SATISFIED','NOT_REQUIRED'}:continue
        subject=reviewer if name=='查看公开预览' else owner
        suffix={'取得内部完整包':'internal','查看公开预览':'preview','下载公开展示版':'exhibition'}[name]
        method='POST' if suffix=='internal' else 'GET'
        recording=service.installer.install_recording(project_id=project,action_id=action.action_id,identity_id=subject.identity_id,
            resource_owner_identity_id=owner.identity_id,endpoint=origin,event_factory=lambda endpoint,identity,now:_events(endpoint,identity,now,method,suffix),
            resource_consumer=ValueSlotConsumer.PATH,resource_location='path[2]',source_fingerprint=source,target_request_id='request_000002',runtime_instance_id=state['operation']['instance_id'])
        if action.state_changing:
            service.installer.install_recording(project_id=project,action_id=action.action_id,identity_id=owner.identity_id,
                resource_owner_identity_id=owner.identity_id,endpoint=origin,event_factory=lambda endpoint,identity,now:_events(endpoint,identity,now,'POST','withdraw'),
                resource_consumer=ValueSlotConsumer.PATH,resource_location='path[2]',source_fingerprint=source,target_request_id='request_000002',
                purpose=RecordingPurpose.RECOVERY,parent_recording_id=recording,runtime_instance_id=state['operation']['instance_id'])
    context=service.proofs.context(project)
    claims=tuple(dict(identity_id=item.identity_id,application_subject_id=subject,application_role=role,request_path='/api/me',subject_path=('id',),role_path=('role',))
        for item,subject,role in [(owner,'curator','owner'),(reviewer,'judge','reviewer')])
    for action in actions.values():
        resource=next((item for item in context['resources'] if item['action_id']==action.action_id and item['owner_identity_id']==owner.identity_id),None)
        if resource is None:raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先核对示例资源与负责人的对应')
        for effect in action.effect_catalog:
            existing_source=next((item for item in context['sources'] if item['config']['action_id']==action.action_id and item['config']['effect_id']==effect.effect_id),None)
            # 旧候选缺文件时也补齐可选输入；已采用和人工配置的来源不被示例配方覆盖。
            reference=None
            if effect.effect_kind.value=='FILE_CONTENT_DELIVERY' and (existing_source is None or not existing_source['config'].get('reference_artifact') or existing_source['config']['resource_binding_id']!=resource['resource_binding_id']):
                reference=_prepare_reference(service,project,action,resource)
            if existing_source is not None and existing_source['config']['resource_binding_id']==resource['resource_binding_id'] and (effect.effect_kind.value!='FILE_CONTENT_DELIVERY' or existing_source['config'].get('reference_artifact')):continue
            common=dict(action_id=action.action_id,action_revision=action.revision,effect_id=effect.effect_id,observation_identity_id=owner.identity_id,
                resource_binding_id=resource['resource_binding_id'],collection='galleries',relative_path_template='/collections/galleries/{resource_id}',identity_claims=claims,
                mappings={'resource_id':('resource_id',),'owner_id':('owner_id',)})
            if effect.effect_kind.value=='FILE_CONTENT_DELIVERY':
                config=FileProofSourceConfig(**common,reference_resource_id=resource['resource_id'],reference_owner_identity_id=owner.identity_id,
                    reference_artifact=reference,reference_origin='UPLOAD')
            elif effect.effect_kind.value=='STATE_MUTATION':
                common['mappings']['state']=('data','visibility');config=AtomicProofSourceConfig(**common,source_contract_id='TRANSACTION_HISTORY_V2')
            elif effect.effect_kind.value=='DATA_DISCLOSURE':
                config=AtomicProofSourceConfig(**common,source_contract_id='RESOURCE_FIELDS_V1',protected_projection=effect.protected_projection)
            else:raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前规则不符合示例材料范围，请使用普通材料准备')
            basis=service.proofs.context(project)['basis_id']
            if existing_source is not None:
                # 仅续接官方配方原有的来源，手工改变证明方法时交回人工处理。
                before=dict(existing_source['config']);after=config.model_dump(mode='json')
                for key in ('resource_binding_id','reference_artifact','reference_origin','read_scope_id'):
                    before.pop(key,None);after.pop(key,None)
                if before!=after:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,'这项材料经过手动调整，请先核对配置，再重新准备示例')
            service.proofs.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=config,
                source_id=None if existing_source is None else existing_source['source_id'],
                expected_revision=None if existing_source is None else existing_source['revision']))


def _prepare_reference(service,project,action,resource):
    """导入当前官方实例生成的虚构测试文件；不运行目标操作、不代替人的来源采用。"""
    names={'取得内部完整包':'internal.zip','下载公开展示版':'exhibition.pdf'}
    name=names.get(action.display_name)
    if name is None:raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前动作没有随示例提供的测试文件')
    root=service.runtime.var_dir.resolve()/'data'/'controlled-applications'/project
    path=root/name
    if root.resolve()!=root or path.resolve()!=path or not path.is_file():
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前官方实例的测试文件不可用，请核对示例运行状态')
    with path.open('rb') as stream:content=stream.read(4_194_305)
    if not content or len(content)>4_194_304:
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'官方测试文件超出参照范围')
    digest=hashlib.sha256(content).hexdigest()
    context=service.proofs.context(project)
    existing=next((item for item in context['reference_inputs'] if item['state']=='COMPLETE'
        and item['action_id']==action.action_id and item['action_revision']==action.revision
        and item['resource_binding_id']==resource['resource_binding_id'] and item['manifest']['sha256']==digest),None)
    if existing is not None:return existing['manifest']
    # 复用同一输入身份；中断后重试只回读原上传回执，不能不断增加相同文件。
    operation=hashlib.sha256(json.dumps([project,action.action_id,action.revision,resource['resource_binding_id'],context['basis_id'],digest]).encode()).hexdigest()[:32]
    receipt=service.artifacts.upload(project,UploadProofArtifact(operation_id=operation,basis_id=context['basis_id'],
        action_id=action.action_id,action_revision=action.revision,resource_binding_id=resource['resource_binding_id'],
        size=len(content),sha256=digest,confirmed=True),content)
    return receipt['result']['manifest']


def _events(endpoint,identity,now,method,suffix):
    parent=endpoint+'/api/galleries/campus';target=parent+'/'+suffix
    body=json.dumps({'resource_id':'campus','owner_id':'curator'})
    return (_event(1,now+1,RecordingEventKind.REQUEST,identity,'request_000001',parent,method='GET'),
        _event(2,now+2,RecordingEventKind.RESPONSE,identity,'request_000001',parent,status_code=200,body=body),
        _event(3,now+3,RecordingEventKind.REQUEST,identity,'request_000002',target,method=method),
        _event(4,now+4,RecordingEventKind.RESPONSE,identity,'request_000002',target,status_code=200,body='{}'))
