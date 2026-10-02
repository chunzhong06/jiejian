# 普通Node证明接线fixture：源码、权限与账号走生产服务；捕获事件仅用于S3组件验收，不替代S6浏览器验收。
import json
import socket
import time
from uuid import uuid4

import httpx
from product.backend.composition import ApplicationCore
from product.backend.core.applications.models import CandidateSelection
from product.backend.core.identities.models import TestIdentityAuthMethod,TestIdentityCookie
from product.backend.core.recording.models import RecordingPurpose
from product.backend.workflows.business_boundaries.models import BoundaryProposalCommand
from product.backend.workflows.test_identities.service import PreparedLoginState
from product.protocols.proof_sources import ManagedProofSourceConfig
from tests.fixtures.action_preparation import MemorySecretStore,PreparationHarness,add_recording
from tests.fixtures.runtime_environment import runtime_identity_environment


def wait_for(read, terminal=('SUCCEEDED','FAILED','CANCELLED')):
    deadline = time.monotonic()+40
    while time.monotonic()<deadline:
        value = read()
        if value['state'] in terminal:
            return value
        time.sleep(.08)
    raise AssertionError('bounded task wait expired')


def ordinary_application(tmp_path, *, regression=False, read_only=False, core=None, source_edits=None, alternate=False):
    source = tmp_path/'application'
    from tests.fixtures.record_driver import write_record_driver
    write_record_driver(source,alternate=alternate)
    entry='workbench.mjs' if alternate else 'app.mjs'
    if regression:
        (source/'policy.mjs').write_text("export function mayPublish(actor, ownerId) { return true; }",encoding='utf8')
    for name,content in (source_edits or {}).items():
        assert name in {'policy.mjs','response.mjs','transition.mjs','projection.mjs'}
        (source/name).write_text(content,encoding='utf8')
    var = tmp_path/'var' if core is None else core.var_dir
    core = core or ApplicationCore(var,secret_store=MemorySecretStore(),environ=runtime_identity_environment(var))
    try:
        connection = core.application_understanding.connect(source)
        project = connection.project.project_id
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port = sock.getsockname()[1]
        preview = core.node_runtime.preview(project,entry=entry,port=port,revision=connection.understanding.revision,consent_source_read=True)
        operation = uuid4().hex
        core.node_runtime.start(project,entry=entry,port=port,revision=preview.revision,
            preview_fingerprint=preview.preview_fingerprint,operation_id=operation,consent_execute=True)
        core.runtime_worker.start()
        assert wait_for(lambda:core.node_runtime.operation(project,operation))['state']=='SUCCEEDED'
        understanding = core.application_understanding.get(project)
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
        proposed = core.business_boundaries.create_initial_proposal(project,BoundaryProposalCommand.model_validate_json(json.dumps(command)))
        boundary = core.business_boundaries.approve(project,proposed.proposal.proposal_id,
            expected_fingerprint=proposed.proposal.proposal_fingerprint,reason='核对发布资料规则')
        actors = {item.display_name:item for item in boundary.actors}
        identities = []
        for label,account in [('负责人','alice'),('普通成员','bob')]:
            actor = actors[label]
            identity = core.test_identities.create(project,actor_id=actor.actor_id,actor_revision=actor.revision,label=account)
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False) as client:
                assert client.post('/api/login',json={'account':account}).status_code==200
                cookie = next(iter(client.cookies.jar))
                reference = f'cred:jiejian/test-identity/{project}/{identity.identity_id}/session'
                core.secret_store.write(reference,cookie.value)
                state = PreparedLoginState(auth_method=TestIdentityAuthMethod.COOKIE_SESSION,
                    cookies=(TestIdentityCookie(name=cookie.name,domain='127.0.0.1',path='/',secure=False,
                        http_only=True,same_site='STRICT',value_secret_ref=reference),),prepared_at_us=time.time_ns()//1000)
                core.test_identities.save_prepared_state(identity.identity_id,state)
            identities.append(core.test_identities.get_record(identity.identity_id))
        action = boundary.actions[0]
        harness = PreparationHarness(core,project,source,action,actors['负责人'],tuple(identities),action.effect_catalog[0].effect_id)
        target = add_recording(harness,identity_index=1 if read_only else 0,
            method='GET' if read_only else 'POST',request_path='/api/resources/beta' if read_only else '/api/resources/alpha/publish',
            resource_location='path[2]',request_json={})
        core.recording_lifecycle.finalize(target.recording_id,var_dir=var,now_us=100)
        if not read_only:
            recovery = add_recording(harness,purpose=RecordingPurpose.RECOVERY,parent_recording_id=target.recording_id,
                request_path='/api/resources/alpha/withdraw',resource_location='path[2]',request_json={},target_step_id='first')
            core.recording_lifecycle.finalize(recovery.recording_id,var_dir=var,now_us=101)
        return harness
    except BaseException:
        core.close()
        raise


def source_configuration(harness):
    context = harness.core.proof_preparation.context(harness.project_id)
    read_only = not harness.action.state_changing
    alternate = (harness.source_root/'workbench.mjs').exists()
    collection = 'tickets' if alternate else 'units'
    paths = {'resource_id':('resource_id',),'owner_id':('owner_id',)}
    if not read_only:
        paths['state']=('data','phase' if alternate else 'state')
    return ManagedProofSourceConfig(action_id=harness.action.action_id,action_revision=1,effect_id=harness.effect_id,
        observation_identity_id=harness.identities[1 if read_only else 0].identity_id,resource_binding_id=context['resources'][0]['resource_binding_id'],
        collection=collection,relative_path_template=f'/collections/{collection}/{{resource_id}}',mappings=paths,
        source_contract_id='RESOURCE_FIELDS_V1' if read_only else 'TRANSACTION_HISTORY_V1',
        protected_projection=('summary','title') if read_only else (),
        identity_claims=tuple(dict(identity_id=item.identity_id,application_subject_id=item.label,
            request_path='/session/current' if alternate else '/api/me',subject_path=('id',),role_path=('role',),application_role='owner' if item.label=='alice' else 'member')
            for item in (harness.identities[1:] if read_only else harness.identities)))


def refresh_ordinary_sessions(harness):
    """重启后通过应用真实登录获取新会话，只替换凭据，不重建业务账号身份。"""
    core,project = harness.core,harness.project_id
    reference = core.node_runtime.reference(project)
    for identity in harness.identities:
        core.test_identities.reset(identity.identity_id)
        with httpx.Client(base_url=f'http://127.0.0.1:{reference.port}',trust_env=False) as client:
            assert client.post('/api/login',json={'account':identity.label}).status_code==200
            cookie = next(iter(client.cookies.jar))
            secret = f'cred:jiejian/test-identity/{project}/{identity.identity_id}/session'
            core.secret_store.write(secret,cookie.value)
            core.test_identities.save_prepared_state(identity.identity_id,PreparedLoginState(
                auth_method=TestIdentityAuthMethod.COOKIE_SESSION,prepared_at_us=time.time_ns()//1000,
                cookies=(TestIdentityCookie(name=cookie.name,domain='127.0.0.1',path='/',secure=False,
                    http_only=True,same_site='STRICT',value_secret_ref=secret),)))
