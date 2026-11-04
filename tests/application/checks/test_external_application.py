"""无源码的 Python Web 应用经正式准备、Worker/Runner 两轮验证；不注册伪造观察器。"""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import uuid4

import httpx
import pytest
from product.backend.bootstrap.application import ApplicationCore
from product.backend.application.business_boundaries.models import BoundaryProposalCommand
from product.backend.application.test_identities.service import PreparedLoginState
from product.backend.application.checks.service import ExternalRecheckCommand
from product.backend.domain.applications.models import CandidateSelection
from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.identities.models import AuthenticationProfile, IdentityVerificationSnapshot, TestIdentityAuthMethod as AuthMethod
from product.backend.infrastructure.secrets.refs import credential_ref
from product.protocols.preparation.operation_flow import OperationFlowDraft
from product.protocols.web.environment import FrozenEnvironment
from product.protocols.web.target import WebTargetScope
from tests.support.builders.runtime.runtime_environment import runtime_identity_environment
from tests.support.secrets import MemorySecrets

pytestmark=[pytest.mark.level4,pytest.mark.process]


def test_source_free_entity_disclosure_and_repeat_check(tmp_path):
    tokens={uuid4().hex:'owner',uuid4().hex:'member'}
    state={'vulnerable':True,'target_calls':0}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            role=tokens.get(self.headers.get('Authorization','').removeprefix('Bearer '))
            if self.path=='/me':
                status,data=(200,dict(id=role,role=role)) if role else (401,dict(error='unauthorized'))
            elif self.path in ('/orders/order-1','/owner/orders/order-1'):
                allowed=role=='owner' or (self.path.startswith('/orders/') and state['vulnerable'])
                if self.path.startswith('/orders/'):
                    state['target_calls']+=1
                status=200 if role=='owner' else 403
                data=dict(id='order-1',owner_id='owner',note='confidential-order-note') if allowed else dict(error='forbidden')
            else:
                status,data=404,dict(error='missing')
            raw=json.dumps(data).encode()
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*args):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    var=tmp_path/'instance'
    core=ApplicationCore(var,secret_store=MemorySecrets(),environ=runtime_identity_environment(var))
    try:
        origin=f'http://127.0.0.1:{server.server_port}'
        project=core.application_environments.create_application(operation_id=uuid4().hex,name='订单系统').project_id
        environment=FrozenEnvironment(environment_id='env_'+uuid4().hex,revision=1,name='Python测试环境',
            target=WebTargetScope(base_url=origin,allowed_origins=(origin,),allowed_hosts=('127.0.0.1',),allowed_ports=(server.server_port,),allow_private_network=True))
        core.application_environments.save(project,environment,expected_revision=0)
        current=core.application_environments.activate(project,environment.environment_id,revision=1,expected_revision=0)
        current=core.application_understanding.confirm_endpoint(project,endpoint=origin,revision=current.revision)
        for label in ('owner','member'):
            current=core.application_understanding.add_manual_role(project,revision=current.revision,display_name=label)
        source='src_'+uuid4().hex
        preview=core.application_sources.preview(project,kind='OPENAPI',raw=json.dumps({'openapi':'3.1.0','paths':{'/orders/{id}':{'get':{'summary':'订单详情'}}}}))
        document=core.application_sources.accept(project,candidate_id=preview['candidate_id'],name='订单接口',source_id=source,expected_revision=0,expected_fingerprint=preview['fingerprint'])
        current=core.application_sources.propose_action(project,source,document.requests[0].item_id,expected_revision=current.revision)
        current=core.application_understanding.decide_candidates(project,revision=current.revision,decisions=tuple(
            CandidateSelection(kind='ACTION',candidate_id=item.candidate_id,decision='CONFIRMED',display_name=item.display_name) for item in current.action_candidates))
        actors={'owner':'pactr_'+'1'*16,'member':'pactr_'+'2'*16};action_item='pactn_'+'1'*16;effect_item='peff_'+'1'*16
        command=dict(provenance='人工确认订单可见范围',
            proposed_actors=[dict(item_id=actors[role.canonical_key],write_mode='CREATE',display_name=role.canonical_key,description='业务角色',effective_state='ACTIVE',source_candidate_ids=[role.candidate_id]) for role in current.role_candidates],
            proposed_actions=[dict(item_id=action_item,write_mode='CREATE',display_name='读取订单',description='读取订单详情',primary_resource_concept='订单',operation_kind='READ',state_changing=False,effective_state='ACTIVE',source_candidate_ids=[current.action_candidates[0].candidate_id],effect_catalog=[dict(item_id=effect_item,business_label='订单备注可见',effect_kind='DATA_DISCLOSURE',resource_concept='订单',protected_projection=['note'],description='订单备注实际返回')])],
            proposed_permissions=[dict(item_id='pperm_'+str(i)*16,write_mode='CREATE',effective_state='ACTIVE',subject_actor_item_id=actors[role],business_action_item_id=action_item,resource_owner_actor_item_id=actors['owner'],relation=relation,expectation=expectation,protected_effect_item_ids=[effect_item]) for i,role,relation,expectation in [(1,'owner','OWNS','ALLOW'),(2,'member','OTHER_ROLE','DENY')]])
        proposal=core.business_boundaries.create_initial_proposal(project,BoundaryProposalCommand.model_validate_json(json.dumps(command))).proposal
        boundary=core.business_boundaries.approve(project,proposal.proposal_id,expected_fingerprint=proposal.proposal_fingerprint,reason='核对本人及其他角色访问范围')
        identities={}
        for token,role in tokens.items():
            actor=next(item for item in boundary.actors if item.display_name==role)
            identity=core.test_identities.create(project,actor_id=actor.actor_id,actor_revision=actor.revision,label=role)
            profile=AuthenticationProfile.model_validate_json(json.dumps(dict(method='BEARER',verification=dict(path='/me',subject_path=['id'],role_path=['role'],expected_subject=role,expected_role=role))))
            core.test_identities.configure_authentication(identity.identity_id,profile,expected_updated_at_us=identity.updated_at_us)
            with httpx.Client(trust_env=False) as client:
                observed=client.get(origin+'/me',headers={'Authorization':'Bearer '+token})
                assert observed.status_code==200 and observed.json()==dict(id=role,role=role)
            reference=credential_ref('test-identity',project,identity.identity_id,'bearer')
            core.secret_store.write(reference,token)
            now=time.time_ns()//1000
            core.test_identities.save_prepared_state(identity.identity_id,PreparedLoginState(auth_method=AuthMethod.BEARER,bearer_secret_ref=reference,prepared_at_us=now,
                verification=IdentityVerificationSnapshot(status='VERIFIED',checked_at_us=now,origin=environment.target.allowed_origins[0],profile_fingerprint=boundary_sha256(profile.model_dump(mode='json')),session_prepared_at_us=now,subject=role,role=role)))
            identities[role]=identity.identity_id
        action=boundary.actions[0]
        request=dict(method='GET',path='/orders/{case_resource_id}',input_slots=[dict(slot_id='case_resource_id',source='CASE_RESOURCE_ID',consumer='PATH')])
        query=dict(request=request|dict(path='/owner/orders/{case_resource_id}'),resource_path='$.id',owner_path='$.owner_id',data_path='$')
        draft=OperationFlowDraft.model_validate_json(json.dumps(dict(id='ofl_'+uuid4().hex,revision=1,business_action_id=action.action_id,action_revision=action.revision,
            subject_test_identity_id=identities['owner'],resource_owner_test_identity_id=identities['owner'],source_fingerprint=None,actual_resource_id='order-1',target_step_id='read',
            source_request=core.application_sources.context(project)['request_references'][0],entity_evidence=[dict(effect_id=action.effect_catalog[0].effect_id,query=query)],
            steps=[dict(id='read',purpose='TARGET',identity_id='CASE_SUBJECT',request_template=request,classifier=dict(accepted=[dict(kind='STATUS_IN',statuses=[200])],denied=[dict(kind='STATUS_IN',statuses=[401,403])]),depends_on_step_ids=[])])))
        flow=core.operation_flows.candidate(project,draft)
        core.operation_flows.save(project,flow)
        core.operation_flows.adopt(project,flow.id,flow.revision)
        core.worker.start()
        contract=None
        for vulnerable,expected in [(True,'BLOCK'),(False,'PASS')]:
            state['vulnerable']=vulnerable
            recheck=None if contract is None else ExternalRecheckCommand(reference=contract.reference(),deployment_statement='订单读取授权已处理，核对当前部署的原问题')
            preview=core.checks.preview(project,external_recheck=recheck)
            assert preview.can_execute,preview
            submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,external_recheck=recheck)
            deadline=time.monotonic()+35
            while time.monotonic()<deadline:
                status=core.check_results.status(submitted.run.run_id,project_id=project)
                if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:
                    break
                time.sleep(.1)
            assert status.run.verdict is not None and status.run.verdict.value==expected,status
            if vulnerable:
                contract=core.check_repairs.contracts(submitted.run.run_id)[0]
            else:
                verification=core.check_repairs.verification(submitted.run.run_id)
                assert verification.status=='VERIFIED' and verification.verification_scope=='EXTERNAL_OBSERVATION'
                assert core.project_repair.evaluate(project).tasks[0].status=='VERIFIED'
        assert state['target_calls']==4
        assert core.application_understanding.get(project).source_root is None
        changed=environment.model_copy(update=dict(revision=2,deployment_label='部署者声明的新构建'))
        core.application_environments.save(project,changed,expected_revision=1)
        current=core.application_understanding.get(project)
        core.application_environments.activate(project,changed.environment_id,revision=2,expected_revision=current.revision)
        assert all(core.test_identities.get(identity).status.value=='NEEDS_REVIEW' for identity in identities.values())
        assert not core.checks.preview(project).can_execute
        assert state['target_calls']==4
        for path in var.rglob('*'):
            if path.is_file() and path.suffix in {'.json','.jsonl','.log'}:
                data=path.read_bytes()
                assert b'confidential-order-note' not in data
                assert all(token.encode() not in data for token in tokens)
    finally:
        core.close();server.shutdown();server.server_close();thread.join(timeout=3)
        assert not thread.is_alive()
