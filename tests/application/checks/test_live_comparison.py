"""真实受控应用的连续改码链；比较必须保留原题、正常对照及旧发布包。"""
import hashlib
import json
import time
from uuid import uuid4

import pytest

from product.backend.application.preparation.proofs.commands import (
    AdoptProofSource, GrantProofScope, SaveProofSource, StartProofPreflight,
)
from tests.support.builders.runtime.managed_records import (
    ordinary_application, reload_ordinary_policy, source_configuration, wait_for,
)


def _package_hash(core, project, run):
    package = core.check_results.package(run, project_id=project)
    # 比较完整已发布文档；不把路径或生成时间相同当作内容未变的证据。
    content = dict(request=package.request.model_dump(mode='json'),
        result=package.result.model_dump(mode='json'), manifest=package.manifest.model_dump(mode='json'))
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _run(core, project, change=None, **scope):
    if change is not None:
        scope = dict(change_id=change)
    preview = core.checks.preview(project, **scope)
    assert preview.can_execute, preview.gaps
    submitted = core.checks.submit(project, expected_plan_fingerprint=preview.plan_fingerprint,
        idempotency_key=uuid4().hex, **scope)
    deadline = time.monotonic()+45
    while time.monotonic() < deadline:
        status = core.check_results.status(submitted.run.run_id, project_id=project)
        if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:
            assert status.result_integrity == 'VALID', status
            return submitted.run.run_id, status.run.verdict.value
        time.sleep(.08)
    raise AssertionError('bounded check wait expired')


def test_real_source_repair_and_recurrence_preserve_comparison_contract(tmp_path):
    harness = ordinary_application(tmp_path, regression=True)
    core, project = harness.core, harness.project_id
    proofs = core.proof_preparation
    history = []
    try:
        basis = proofs.context(project)['basis_id']
        source = proofs.save(project, SaveProofSource(operation_id=uuid4().hex, basis_id=basis,
            config=source_configuration(harness)))['result']['source_id']
        proofs.grant_scope(project, GrantProofScope(operation_id=uuid4().hex, basis_id=basis,
            source_id=source, revision=1, confirmed=True))
        core.worker.start()
        repair = None
        stages = [('vulnerable',None,'BLOCK'), ('ineffective','true /* unchanged authorization */','BLOCK'),
            ('fixed',"actor.role === 'owner' && actor.id === ownerId",'PASS'), ('recurred','true','BLOCK')]
        for label, policy, expected in stages:
            change = None if policy is None else reload_ordinary_policy(harness, policy, repair_reference=repair)
            basis = proofs.context(project)['basis_id']
            queued = proofs.start(project, StartProofPreflight(operation_id=uuid4().hex, basis_id=basis,
                source_id=source, revision=1))['result']['preflight_id']
            assert wait_for(lambda:proofs.status(project,queued))['report']['assessment'] == 'USABLE'
            proofs.adopt(project, AdoptProofSource(operation_id=uuid4().hex, basis_id=basis,
                source_id=source, revision=1, preflight_id=queued, confirmed=True))
            # 首轮只查一个禁止要求和必要正常对照；后续完整交付检查保留原题并覆盖额外规则。
            scope = {}
            if change is None:
                from product.protocols.checks.execution_request import PermissionReference
                boundary = core.business_boundaries.view(project)
                item = next(item for item in boundary.permission_intents if item.expectation == 'DENY')
                scope['selected_permissions'] = (PermissionReference(intent_id=item.intent_id,revision=item.revision,intent_hash=item.intent_hash),)
            run, verdict = _run(core, project, change, **scope)
            assert verdict == expected
            package = core.check_results.package(run, project_id=project)
            correspondence = package.result.runtime_correspondence
            assert correspondence.before == correspondence.after == 'MATCHED'
            assert {item.case.permission.expectation for item in package.evidence} == {'ALLOW','DENY'}
            if repair is None:
                repair = core.check_repairs.contracts(run)[0].reference()
            elif label != 'recurred':
                verification = core.check_story.build(run).repair_verification
                assert verification.status == ('VERIFIED' if label == 'fixed' else 'NOT_VERIFIED')
                assert verification.source_run_id == history[0]['run_id']
            history.append(dict(stage=label, run_id=run, verdict=verdict,
                source_fingerprint=package.request.source_fingerprint, package_sha256=_package_hash(core,project,run)))
            for previous in history:
                assert _package_hash(core,project,previous['run_id']) == previous['package_sha256']

        # 复发刻意恢复原实现，应回到原内容指纹；加载实例和检查记录仍各自独立。
        assert len({item['source_fingerprint'] for item in history}) == 3
        assert history[0]['source_fingerprint'] == history[3]['source_fingerprint']
        for baseline, current, earlier, expected in [(0,1,None,'PERSISTING'),(0,2,None,'FIXED'),(2,3,0,'RECURRED')]:
            comparison = core.check_comparison.compare(project, history[baseline]['run_id'], history[current]['run_id'],
                earlier=None if earlier is None else history[earlier]['run_id'])
            denied = [item for item in comparison.items if item.after and item.after.expectation == 'DENY']
            assert len(denied) == 1 and denied[0].state == expected, comparison
            assert not comparison.limitations
            if expected == 'FIXED':
                assert denied[0].after.control_verdict == 'SAFE'
        (tmp_path/'continuous-repair-result.json').write_text(json.dumps(dict(project_id=project,stages=history,
            comparison_states=['PERSISTING','FIXED','RECURRED'], old_packages_unchanged=True),ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        harness.close()


def test_same_public_routine_requires_real_second_environment_materials(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    import httpx

    from product.backend.application.checks.routine_execution import BindRoutine, SaveRoutineRevision
    from product.backend.application.test_identities.service import PreparedLoginState
    from product.backend.domain.boundaries.entities import boundary_sha256
    from product.backend.domain.identities.models import IdentityVerificationSnapshot, TestIdentityAuthMethod
    from product.protocols.checks.execution_request import PermissionReference
    from product.protocols.checks.routines import RoutineScope, routine_bytes
    from product.protocols.checks.routine_reference import RoutineReference
    from product.protocols.preparation.operation_flow import OperationFlowDraft
    from product.protocols.web.environment import FrozenEnvironment
    from product.protocols.web.target import WebTargetScope
    from tests.support.builders.preparation.external_application import external_application

    tokens = {uuid4().hex:role for role in ('owner','member')}
    calls = []
    class SecondDeployment(BaseHTTPRequestHandler):
        def do_GET(self):
            role = tokens.get(self.headers.get('Authorization','').removeprefix('Bearer '))
            if self.path == '/me' and role:
                status, data = 200, dict(id=role+'-second', role=role)
            elif self.path in {'/orders/order-2','/owner/orders/order-2'} and role == 'owner':
                calls.append(self.path)
                status, data = 200, dict(id='order-2', owner_id='owner-second', note='second environment value')
            else:
                if self.path.startswith(('/orders/','/owner/orders/')):
                    calls.append(self.path)
                status, data = 403, dict(error='forbidden')
            raw = json.dumps(data).encode()
            self.send_response(status); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def log_message(self,*args):
            pass
    target = ThreadingHTTPServer(('127.0.0.1',0), SecondDeployment)
    thread = Thread(target=target.serve_forever, daemon=True); thread.start()
    try:
        with external_application(tmp_path) as harness:
            core, project = harness.core, harness.project_id
            core.operation_flows.adopt(project,harness.flow.id,harness.flow.revision)
            owner = core.check_routines.revisions
            permissions = core.business_boundaries.view(project).permission_intents
            document = owner.save(project,SaveRoutineRevision(operation_id=uuid4().hex,expected_revision=0,name='两个环境的订单范围',
                scope=RoutineScope(permissions=tuple(PermissionReference(intent_id=item.intent_id,revision=item.revision,
                    intent_hash=item.intent_hash) for item in permissions))))
            original = routine_bytes(document)
            def bind():
                prepared = owner.binding_preview(project,document.routine_id,1)
                assert prepared['can_bind'], prepared['preview'].gaps
                bound = owner.bind(project,document.routine_id,BindRoutine(operation_id=uuid4().hex,revision=1,
                    expected_material_fingerprint=prepared['material_fingerprint'],
                    expected_environment_fingerprint=prepared['environment_fingerprint']))
                return bound, RoutineReference(routine_id=document.routine_id,revision=1,binding_id=bound.binding_id)
            first_binding, first_ref = bind()
            core.worker.start()
            first_run, verdict = _run(core,project,routine_reference=first_ref)
            assert verdict == 'BLOCK'

            origin = f'http://127.0.0.1:{target.server_port}'
            environment = FrozenEnvironment(environment_id='env_'+uuid4().hex,revision=1,name='第二套订单部署',
                target=WebTargetScope(base_url=origin,allowed_origins=(origin,),allowed_hosts=('127.0.0.1',),
                    allowed_ports=(target.server_port,),allow_private_network=True))
            core.application_environments.save(project,environment,expected_revision=0)
            understanding = core.application_understanding.get(project)
            current = core.application_environments.activate(project,environment.environment_id,revision=1,expected_revision=understanding.revision)
            core.application_understanding.confirm_endpoint(project,endpoint=origin,revision=current.revision)
            assert not owner.binding_preview(project,document.routine_id,1)['can_bind']
            assert not core.checks.preview(project,routine_reference=first_ref).can_execute
            assert not calls

            # 第二套部署独立发放会话；实际 /me 与资源查询重新核验，不能沿用第一环境的就绪标记。
            for token, role in tokens.items():
                identity_id = harness.identities[role]
                core.test_identities.reset(identity_id)
                identity = core.test_identities.get_record(identity_id)
                profile = identity.authentication.model_copy(update={'verification':identity.authentication.verification.model_copy(
                    update={'expected_subject':role+'-second'})})
                core.test_identities.configure_authentication(identity_id,profile,expected_updated_at_us=identity.updated_at_us)
                with httpx.Client(trust_env=False) as client:
                    response = client.get(origin+'/me',headers={'Authorization':'Bearer '+token})
                    assert response.status_code == 200 and response.json() == dict(id=role+'-second',role=role)
                from product.backend.infrastructure.secrets.refs import credential_ref
                reference = credential_ref('test-identity',project,identity_id,'bearer')
                core.secret_store.write(reference,token)
                now = time.time_ns()//1000
                core.test_identities.save_prepared_state(identity_id,PreparedLoginState(auth_method=TestIdentityAuthMethod.BEARER,bearer_secret_ref=reference,
                    prepared_at_us=now,verification=IdentityVerificationSnapshot(status='VERIFIED',checked_at_us=now,origin=origin,
                        profile_fingerprint=boundary_sha256(profile.model_dump(mode='json')),session_prepared_at_us=now,subject=role+'-second',role=role)))
            request = dict(method='GET',path='/orders/{case_resource_id}',input_slots=[dict(slot_id='case_resource_id',source='CASE_RESOURCE_ID',consumer='PATH')])
            query = dict(request=request|dict(path='/owner/orders/{case_resource_id}'),resource_path='$.id',owner_path='$.owner_id',data_path='$')
            draft = OperationFlowDraft.model_validate_json(json.dumps(dict(id='ofl_'+uuid4().hex,revision=1,
                business_action_id=harness.flow.business_action_id,action_revision=harness.flow.action_revision,
                subject_test_identity_id=harness.identities['owner'],resource_owner_test_identity_id=harness.identities['owner'],source_fingerprint=None,
                actual_resource_id='order-2',target_step_id='read',source_request=core.application_sources.context(project)['request_references'][0],
                entity_evidence=[dict(effect_id=harness.flow.entity_evidence[0].effect_id,query=query)],steps=[dict(id='read',purpose='TARGET',
                    identity_id='CASE_SUBJECT',request_template=request,classifier=dict(accepted=[dict(kind='STATUS_IN',statuses=[200])],
                    denied=[dict(kind='STATUS_IN',statuses=[401,403])]),depends_on_step_ids=[])])))
            flow = core.operation_flows.candidate(project,draft)
            core.operation_flows.save(project,flow); core.operation_flows.adopt(project,flow.id,flow.revision)
            second_binding, second_ref = bind()
            assert second_binding.environment_fingerprint != first_binding.environment_fingerprint
            assert second_binding.material_fingerprint != first_binding.material_fingerprint
            assert routine_bytes(owner.read(project,document.routine_id,1)) == original
            second_run, verdict = _run(core,project,routine_reference=second_ref)
            assert verdict == 'PASS' and calls and all('order-2' in path for path in calls)
            comparison = core.check_comparison.compare(project,first_run,second_run)
            assert comparison.items and {item.state for item in comparison.items} == {'INCOMPARABLE'}
            assert all(item.reasons == ('SUBJECT_OR_RESOURCE_BINDING_CHANGED',) for item in comparison.items)
    finally:
        target.shutdown(); target.server_close(); thread.join(3)
        assert not thread.is_alive()


pytestmark = [pytest.mark.level4, pytest.mark.process, pytest.mark.slow]
