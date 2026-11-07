# 普通 Node 证明接线：源码、权限与账号走生产服务，不替代浏览器验收。
import json
import socket
import time
from uuid import uuid4

import httpx
from product.backend.bootstrap.application import ApplicationCore
from product.backend.domain.applications.models import CandidateSelection
from product.backend.domain.identities.models import TestIdentityAuthMethod, TestIdentityCookie
from product.backend.domain.recording.models import RecordingPurpose
from product.backend.application.business_boundaries.models import BoundaryProposalCommand
from product.backend.application.test_identities.service import PreparedLoginState
from product.protocols.preparation.proof_sources import AtomicProofSourceConfig
from tests.support.builders.preparation.action_preparation import PreparationHarness, add_recording
from tests.support.secrets import MemorySecrets
from tests.support.builders.runtime.runtime_environment import runtime_identity_environment


def wait_for(read, terminal=('SUCCEEDED','FAILED','CANCELLED')):
    deadline = time.monotonic()+40
    while time.monotonic()<deadline:
        value = read()
        if value['state'] in terminal:
            return value
        time.sleep(.08)
    raise AssertionError('bounded task wait expired')


def ordinary_application(tmp_path, *, regression=False, read_only=False, core=None, source_edits=None, alternate=False,file_delivery=False,recovery_failures=0,async_export=None,database_backend=None,edit_driver=None,edit_proposal=None,edit_source=None,max_requests=None):
    source = tmp_path/'application'
    from tests.support.builders.preparation.record_driver import write_record_driver
    write_record_driver(source,alternate=alternate)
    if recovery_failures:
        # 故障仅在临时应用中注入；公开计数证明恢复路径没有重发正常TARGET。
        driver=source/'app.mjs';text=driver.read_text(encoding='utf-8')
        text=text.replace("const roles=",f"let recoveryFailures={int(recovery_failures)},publishCalls=0;\nconst roles=")
        text=text.replace("    if(req.url==='/api/login')", "    if(req.url==='/__test_counts')return reply(200,{publishCalls});\n    if(req.url==='/api/login')")
        text=text.replace("    const allowed=", "    if(action==='publish')publishCalls++;\n    if(action==='withdraw'&&recoveryFailures-->0)return reply(503,{error:'recovery'});\n    const allowed=")
        driver.write_text(text,encoding='utf-8')
    if file_delivery:
        assert not alternate and not read_only
        driver=source/'app.mjs'
        original=driver.read_text(encoding='utf-8')
        marker="    return reply(action==='withdraw'?(allowed?200:403):publicationStatus(allowed),{ok:allowed});"
        assert marker in original
        driver.write_text(original.replace(marker,"    if(action==='publish'&&allowed){res.writeHead(publicationStatus(allowed),{'Content-Type':'application/octet-stream'});return res.end(Buffer.from('controlled test file content'));}\n"+marker.replace('{ok:allowed}',"allowed?{ok:true}:{error:'denied'}")),encoding='utf-8')
    if async_export is not None:
        assert file_delivery
        driver=source/'app.mjs';text=driver.read_text(encoding='utf-8')
        text=text.replace('const roles=',"const tasks=new Map();let exportsStarted=0;const mode="+json.dumps(async_export)+";\nconst roles=")
        text=text.replace("    const match=",r"""
    if(req.url==='/__export_counts')return reply(200,{exportsStarted});
    const taskMatch=/^\/exports\/([a-f0-9]+)(\/content)?$/.exec(req.url);
    if(taskMatch){
      const task=tasks.get(taskMatch[1]);if(!task||task.subject!==actor.id)return reply(403,{error:'task'});
      if(!taskMatch[2])return reply(200,task);
      if(task.state!=='done')return reply(409,{error:'pending'});
      res.writeHead(200,{'Content-Type':'application/octet-stream'});
      if(mode==='TRUNCATED'){res.write('controlled');return res.end();}
      return res.end(Buffer.from('controlled test file content'));
    }
    const match=""")
        text=text.replace("    if(action==='publish'&&allowed){res.writeHead",r"""
    if(action==='publish'&&allowed){
      exportsStarted++;const job=crypto.randomBytes(16).toString('hex');
      tasks.set(job,{job,state:'queued',resource:mode==='UNRELATED'?'another':resource_id,owner:item.owner_id,subject:actor.id,nonce:req.headers['x-jiejian-request-nonce']});
      if(mode!=='ID_ONLY')setTimeout(()=>{tasks.get(job).state=mode==='FAILED'?'failed':mode==='CANCELLED'?'cancelled':'done';},120);
      return reply(202,{export_job:job});
    }
    if(action==='publish'&&allowed){res.writeHead""")
        driver.write_text(text,encoding='utf-8')
    if database_backend is not None:
        assert not alternate and not read_only and not file_delivery
        _database_driver(source,database_backend)
    entry='workbench.mjs' if alternate else 'app.mjs'
    if edit_driver is not None:
        driver=source/entry
        driver.write_text(edit_driver(driver.read_text(encoding='utf-8')),encoding='utf-8')
    if edit_source is not None:
        edit_source(source)
    if regression:
        (source/'policy.mjs').write_text("export function mayPublish(actor, ownerId) { return true; }",encoding='utf8')
    for name,content in (source_edits or {}).items():
        assert name in {'policy.mjs','response.mjs','transition.mjs','projection.mjs'}
        (source/name).write_text(content,encoding='utf8')
    var = tmp_path/'var' if core is None else core.var_dir
    core = core or ApplicationCore(var,secret_store=MemorySecrets(),environ=runtime_identity_environment(var))
    try:
        connection = core.application_understanding.connect(source)
        project = connection.project.project_id
        databases=()
        if database_backend is not None:
            from product.protocols.runtime.database_capture import DatabaseCapture
            credential=core.node_runtime.configure_database_credential(project,'primary',database_backend.password)
            databases=(DatabaseCapture(connection_id='primary',engine=database_backend.engine,port=database_backend.port,
                database=database_backend.database,namespace=database_backend.namespace,username=database_backend.username,
                password_env=credential['password_env'],table='business_records',resource_column='id',owner_column='owner_id',fields=('state',)),)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port = sock.getsockname()[1]
        preview = core.node_runtime.preview(project,entry=entry,port=port,revision=connection.understanding.revision,consent_source_read=True,databases=databases)
        operation = uuid4().hex
        core.node_runtime.start(project,entry=entry,port=port,revision=preview.revision,
            preview_fingerprint=preview.preview_fingerprint,operation_id=operation,consent_execute=True,databases=databases)
        core.runtime_worker.start()
        assert wait_for(lambda:core.node_runtime.operation(project,operation))['state']=='SUCCEEDED'
        understanding = core.application_understanding.get(project)
        if max_requests is not None:
            from product.protocols.web.environment import FrozenEnvironment
            from product.backend.application.recording.submission import recording_target_scope
            configuration=FrozenEnvironment(environment_id='env_'+uuid4().hex,revision=1,name='显式场景预算',
                target=recording_target_scope(f'http://127.0.0.1:{port}').model_copy(update={'max_requests':max_requests}))
            core.application_environments.save(project,configuration,expected_revision=0)
            understanding=core.application_environments.activate(project,configuration.environment_id,revision=1,expected_revision=understanding.revision)
        understanding = core.application_understanding.confirm_endpoint(project,endpoint=f'http://127.0.0.1:{port}',revision=understanding.revision)
        understanding = core.application_understanding.analyze_source(project,revision=understanding.revision)
        selected = core.application_understanding.decide_candidates(project,revision=understanding.revision,
            decisions=tuple(CandidateSelection(kind=kind,candidate_id=item.candidate_id,decision='CONFIRMED',display_name=item.display_name)
                for kind,items in [('ROLE',understanding.role_candidates),('ACTION',understanding.action_candidates)] for item in items))
        roles = {item.canonical_key:item.candidate_id for item in selected.role_candidates}
        action_candidate = next(item.candidate_id for item in selected.action_candidates if item.canonical_key=='POST /api/resources/{resource_id}/publish')
        owner,member,action_item,effect_item = 'pactr_'+'1'*16,'pactr_'+'2'*16,'pactn_'+'1'*16,'peff_'+'1'*16
        command = dict(proposed_actors=[dict(item_id=item,write_mode='CREATE',display_name=label,description=label,
            effective_state='ACTIVE',source_candidate_ids=[roles[role]]) for item,label,role in
            [(owner,'负责人','owner'),(member,'普通成员','member')]],
            proposed_actions=[dict(item_id=action_item,write_mode='CREATE',display_name='发布资料',description='将资料发布',
                primary_resource_concept='资料',operation_kind='CHANGE',state_changing=True,effective_state='ACTIVE',
                source_candidate_ids=[action_candidate],effect_catalog=[dict(item_id=effect_item,business_label='资料被发布',
                    effect_kind='STATE_MUTATION',resource_concept='资料',expected_state='ready' if alternate else 'published',description='发布事实被持久保存')])],
            proposed_permissions=[dict(item_id='pperm_'+str(index)*16,write_mode='CREATE',effective_state='ACTIVE',
                subject_actor_item_id=actor,business_action_item_id=action_item,resource_owner_actor_item_id=owner,
                relation=relation,expectation=expectation,protected_effect_item_ids=[effect_item])
                for index,actor,relation,expectation in [(1,owner,'OWNS','ALLOW'),(2,member,'OTHER_ROLE','DENY')]],
            provenance='人工确认的组件验收权限')
        if read_only:
            definition = command['proposed_actions'][0]
            definition.update(display_name='读取资料摘要',description='读取本人的有限资料',operation_kind='READ',state_changing=False,
                source_candidate_ids=[next(item.candidate_id for item in selected.action_candidates if item.canonical_key=='GET /api/resources/{resource_id}')])
            definition['effect_catalog']=[dict(item_id=effect_item,business_label='资料摘要可见',effect_kind='DATA_DISCLOSURE',
                resource_concept='资料',protected_projection=['summary','title'],description='只返回标题与摘要')]
            command['proposed_permissions']=[dict(item_id='pperm_'+'1'*16,write_mode='CREATE',effective_state='ACTIVE',
                subject_actor_item_id=member,business_action_item_id=action_item,resource_owner_actor_item_id=member,
                relation='OWNS',expectation='ALLOW',protected_effect_item_ids=[effect_item])]
        if file_delivery:
            command['proposed_actions'][0]['display_name']='取得测试文件'
            command['proposed_actions'][0]['effect_catalog'][0].update(effect_kind='FILE_CONTENT_DELIVERY',
                business_label='完整测试文件已接收',expected_state=None,description='实际接收已确认的文件字节')
        if edit_proposal is not None:
            edit_proposal(command,selected)
        proposed = core.business_boundaries.create_initial_proposal(project,BoundaryProposalCommand.model_validate_json(json.dumps(command)))
        boundary = core.business_boundaries.approve(project,proposed.proposal.proposal_id,
            expected_fingerprint=proposed.proposal.proposal_fingerprint,reason='核对发布资料规则')
        actors = {item.display_name:item for item in boundary.actors}
        identities = []
        for label,account in [('负责人','alice'),('普通成员','bob')]:
            actor = actors[label]
            identity = core.test_identities.create(project,actor_id=actor.actor_id,actor_revision=actor.revision,label=account)
            if understanding.environment is not None:
                from product.backend.domain.identities.models import AuthenticationProfile,IdentityVerificationConfig
                profile=AuthenticationProfile(verification=IdentityVerificationConfig(path='/api/me',subject_path=('id',),
                    role_path=('role',),expected_subject=account,expected_role='owner' if account=='alice' else 'member'))
                core.test_identities.configure_authentication(identity.identity_id,profile,expected_updated_at_us=identity.updated_at_us)
                identity=core.test_identities.get_record(identity.identity_id)
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False) as client:
                assert client.post('/api/login',json={'account':account}).status_code==200
                cookie = next(iter(client.cookies.jar))
                reference = f'cred:jiejian/test-identity/{project}/{identity.identity_id}/session'
                core.secret_store.write(reference,cookie.value)
                prepared_at=time.time_ns()//1000
                state = PreparedLoginState(auth_method=TestIdentityAuthMethod.COOKIE_SESSION,
                    cookies=(TestIdentityCookie(name=cookie.name,domain='127.0.0.1',path='/',secure=False,
                        http_only=True,same_site='STRICT',value_secret_ref=reference),),prepared_at_us=prepared_at,
                    verification=_login_verification(identity,client,f'http://127.0.0.1:{port}',prepared_at))
                core.test_identities.save_prepared_state(identity.identity_id,state)
            identities.append(core.test_identities.get_record(identity.identity_id))
        action = next(item for item in boundary.actions if item.display_name==command['proposed_actions'][0]['display_name'])
        harness = PreparationHarness(core,project,source,action,actors['负责人'],tuple(identities),action.effect_catalog[0].effect_id)
        target = add_recording(harness,identity_index=1 if read_only else 0,
            method='GET' if read_only else 'POST',request_path='/api/resources/beta' if read_only else '/api/resources/alpha/publish',
            resource_location='path[2]',request_json={},response_status=202 if async_export is not None else 200)
        core.recording_lifecycle.finalize(target.recording_id,var_dir=var,now_us=100)
        if not read_only:
            recovery = add_recording(harness,purpose=RecordingPurpose.RECOVERY,parent_recording_id=target.recording_id,
                request_path='/api/resources/alpha/withdraw',resource_location='path[2]',request_json={},target_step_id='first')
            core.recording_lifecycle.finalize(recovery.recording_id,var_dir=var,now_us=101)
        return harness
    except BaseException:
        core.close()
        raise


def _database_driver(source,server):
    """同一业务处理器改用真实 Promise 连接池保存状态；身份、权限和恢复仍走正式流程。"""
    from pathlib import Path
    import shutil
    dependencies=Path(__file__).resolve().parents[3]/'fixtures/database-node'
    for name in ('package.json','package-lock.json'):shutil.copyfile(dependencies/name,source/name)
    pg=server.engine=='POSTGRESQL'
    options=dict(host='127.0.0.1',port=server.port,user=server.username,database=server.database)
    setup="import {createRequire} from 'node:module';const require=createRequire(import.meta.url);\n"
    setup+='const dbOptions='+json.dumps(options)+";dbOptions.password=process.env[Object.keys(process.env).find(name=>name.startsWith('JIEJIAN_DB_'))];\n"
    setup+=("const db=new (require('pg').Pool)(dbOptions);" if pg else "const db=require('mysql2/promise').createPool(dbOptions);")
    setup+="\nawait db.query(\"CREATE TABLE IF NOT EXISTS business_records(id VARCHAR(64) PRIMARY KEY,owner_id VARCHAR(64) NOT NULL,state VARCHAR(64) NOT NULL)\");\n"
    seed="INSERT INTO business_records VALUES('alpha','alice','draft'),('beta','bob','draft') ON CONFLICT DO NOTHING" if pg else "INSERT IGNORE INTO business_records VALUES('alpha','alice','draft'),('beta','bob','draft')"
    setup+='await db.query('+json.dumps(seed)+');\n'
    path=source/'app.mjs';text=path.read_text(encoding='utf-8')
    text=text.replace("const roles=",setup+'const roles=')
    sql='UPDATE business_records SET state='+('$1' if pg else '?')+' WHERE id='+('$2' if pg else '?')
    text=text.replace('    await records.transact(',"    if(allowed)await db.query("+json.dumps(sql)+",[action==='withdraw'?'draft':'published',resource_id]);\n    await records.transact(")
    path.write_text(text,encoding='utf-8')


def source_configuration(harness):
    context = harness.core.proof_preparation.context(harness.project_id)
    read_only = not harness.action.state_changing
    alternate = (harness.source_root/'workbench.mjs').exists()
    collection = 'tickets' if alternate else 'units'
    paths = {'resource_id':('resource_id',),'owner_id':('owner_id',)}
    if not read_only:
        paths['state']=('data','phase' if alternate else 'state')
    return AtomicProofSourceConfig(action_id=harness.action.action_id,action_revision=1,effect_id=harness.effect_id,
        observation_identity_id=harness.identities[1 if read_only else 0].identity_id,resource_binding_id=next(item['resource_binding_id'] for item in context['resources']
            if item['action_id']==harness.action.action_id and item['owner_identity_id']==harness.identities[1 if read_only else 0].identity_id),
        collection=collection,relative_path_template=f'/collections/{collection}/{{resource_id}}',mappings=paths,
        source_contract_id='RESOURCE_FIELDS_V1' if read_only else 'TRANSACTION_HISTORY_V2',
        protected_projection=('summary','title') if read_only else (),
        identity_claims=tuple(dict(identity_id=item.identity_id,application_subject_id=item.label,
            request_path='/session/current' if alternate else '/api/me',subject_path=('id',),role_path=('role',),application_role='owner' if item.label=='alice' else 'member')
            for item in (harness.identities[1:] if read_only else harness.identities)))


def reload_ordinary_policy(harness,policy,*,repair_reference=None,databases=()):
    """真实改码、登记和重启后恢复账号；不重建业务数据、录制或原题合同。"""
    core,project=harness.core,harness.project_id
    previous=core.node_runtime.reference(project)
    core.node_runtime.stop(project,instance_id=previous.instance_id)
    (harness.source_root/'policy.mjs').write_text(f'export function mayPublish(actor, ownerId) {{ return {policy}; }}',encoding='utf8')
    registration=core.development.registration_preview(project)
    receipt=core.development.register_change(project,operation_id=uuid4().hex,expected_registration_fingerprint=registration['fingerprint'],
        reason='修改实际业务权限实现',claimed_paths=('policy.mjs',),repair_reference=repair_reference)
    understanding=core.application_understanding.get(project)
    preview=core.node_runtime.preview(project,entry='app.mjs',port=previous.port,revision=understanding.revision,consent_source_read=True,databases=databases)
    operation=uuid4().hex
    core.node_runtime.start(project,entry='app.mjs',port=previous.port,revision=preview.revision,
        preview_fingerprint=preview.preview_fingerprint,operation_id=operation,consent_execute=True,databases=databases)
    assert wait_for(lambda:core.node_runtime.operation(project,operation))['state']=='SUCCEEDED'
    understanding=core.application_understanding.get(project)
    core.application_understanding.analyze_source(project,revision=understanding.revision)
    refresh_ordinary_sessions(harness)
    return receipt.change_id


def refresh_ordinary_sessions(harness):
    """重启后通过应用真实登录获取新会话，只替换凭据，不重建业务账号身份。"""
    core,project = harness.core,harness.project_id
    reference = core.node_runtime.reference(project)
    for identity in harness.identities:
        core.test_identities.reset(identity.identity_id)
        identity=core.test_identities.get_record(identity.identity_id)
        with httpx.Client(base_url=f'http://127.0.0.1:{reference.port}',trust_env=False) as client:
            assert client.post('/api/login',json={'account':identity.label}).status_code==200
            cookie = next(iter(client.cookies.jar))
            secret = f'cred:jiejian/test-identity/{project}/{identity.identity_id}/session'
            core.secret_store.write(secret,cookie.value)
            prepared_at=time.time_ns()//1000
            core.test_identities.save_prepared_state(identity.identity_id,PreparedLoginState(
                auth_method=TestIdentityAuthMethod.COOKIE_SESSION,prepared_at_us=prepared_at,
                verification=_login_verification(identity,client,f'http://127.0.0.1:{reference.port}',prepared_at),
                cookies=(TestIdentityCookie(name=cookie.name,domain='127.0.0.1',path='/',secure=False,
                    http_only=True,same_site='STRICT',value_secret_ref=secret),)))


def _login_verification(identity,client,origin,prepared_at):
    """配置了环境的账号须经真实 /me 核验，不用已写入 Cookie 冒充核验成功。"""
    if identity.authentication is None:return None
    from product.backend.domain.identities.models import IdentityVerificationSnapshot
    from product.backend.domain.boundaries.entities import boundary_sha256
    profile=identity.authentication
    response=client.get(profile.verification.path)
    data=response.json()
    assert response.status_code==200 and data['id']==profile.verification.expected_subject and data['role']==profile.verification.expected_role
    return IdentityVerificationSnapshot(status='VERIFIED',checked_at_us=prepared_at,origin=origin,
        profile_fingerprint=boundary_sha256(profile.model_dump(mode='json')),session_prepared_at_us=prepared_at,
        subject=data['id'],role=data['role'])
