"""普通 Node 应用创建真实对象，后续换主体发布；最后先撤回，再移除本轮对象。"""
import json
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from product.backend.application.preparation.proofs.commands import SaveProofSource,GrantProofScope,StartProofPreflight,AdoptProofSource
from product.protocols.checks.scenarios import BusinessScenarioRevision,ScenarioReference
from product.protocols.preparation.proof_sources import CreationProofSourceConfig
from tests.support.builders.preparation.action_preparation import add_recording
from product.backend.domain.recording.models import RecordingPurpose
from tests.support.builders.runtime.managed_records import ordinary_application,source_configuration,wait_for,reload_ordinary_policy


def creation_driver(text):
    text=text.replace("const roles=","const created=[],removed=[];\nconst roles=")
    marker="    const match="
    routes=r"""
    if(req.url==='/api/create'){
      if(actor.id!=='alice')return reply(403,{error:'denied'});
      const id='scenario'+crypto.randomBytes(8).toString('hex');
      await records.seed(id,actor.id,{state:'draft',title:'unit-new',summary:'value-new'});
      created.push(id);return reply(201,{id});
    }
    if(req.url.startsWith('/api/remove/')){
      const id=req.url.split('/').at(-1),item=await records.read(id);
      if(actor.id!==item.owner_id)return reply(403,{error:'denied'});
      await records.remove(id,item.version);removed.push(id);return reply(200,{ok:true});
    }
    if(req.url==='/api/scenario-counts')return reply(200,{created,removed});
"""
    return text.replace(marker,routes+marker).replace('([a-z]+)','([a-z0-9]+)')


def creation_source(source):
    path=source/'openapi.json'
    document=json.loads(path.read_text(encoding='utf-8'))
    document['paths']['/api/create']={'post':{'summary':'创建资料','responses':{'201':{'description':'created'}}}}
    path.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8')


def creation_proposal(command,selected):
    command['proposed_actions'].append(dict(item_id='pactn_'+'3'*16,write_mode='CREATE',display_name='创建资料',
        description='创建归本人所有的新资料',primary_resource_concept='资料',operation_kind='CHANGE',state_changing=True,
        effective_state='ACTIVE',source_candidate_ids=[next(item.candidate_id for item in selected.action_candidates if item.canonical_key=='POST /api/create')],effect_catalog=[dict(item_id='peff_'+'3'*16,
            business_label='资料已创建',effect_kind='OBJECT_CREATION',resource_concept='资料',description='独立记录中新对象已形成')]))
    command['proposed_permissions'].append(dict(item_id='pperm_'+'3'*16,write_mode='CREATE',effective_state='ACTIVE',
        subject_actor_item_id='pactr_'+'1'*16,business_action_item_id='pactn_'+'3'*16,
        resource_owner_actor_item_id='pactr_'+'1'*16,relation='OWNS',expectation='ALLOW',protected_effect_item_ids=['peff_'+'3'*16]))


@pytest.mark.parametrize('regression,expected',[(False,'PASS'),(True,'BLOCK')])
def test_created_identifier_flows_to_later_action_and_exact_reverse_recovery(tmp_path,regression,expected):
    harness=ordinary_application(tmp_path,regression=regression,edit_driver=creation_driver,edit_proposal=creation_proposal,edit_source=creation_source)
    core,project=harness.core,harness.project_id
    try:
        boundary=core.business_boundaries.view(project)
        created=next(item for item in boundary.actions if item.display_name=='创建资料')
        creator=replace(harness,action=created,effect_id=created.effect_catalog[0].effect_id)
        recording=add_recording(creator,method='POST',request_path='/api/create',request_json={},response_status=201,created_response_resource='alpha')
        core.recording_lifecycle.finalize(recording.recording_id,var_dir=harness.var_dir,now_us=100)
        recovery=add_recording(creator,purpose=RecordingPurpose.RECOVERY,parent_recording_id=recording.recording_id,
            request_path='/api/remove/alpha',resource_location='path[2]',request_json={},target_step_id='first')
        core.recording_lifecycle.finalize(recovery.recording_id,var_dir=harness.var_dir,now_us=101)
        creation=source_configuration(creator).model_dump(mode='json')
        creation.update(source_kind='CREATED_OBJECT_RECORDS',source_contract_id='OBJECT_CREATION_V1',
            mappings={'resource_id':['resource_id'],'owner_id':['owner_id']})
        proofs=core.proof_preparation
        adopted=[]
        for config in (source_configuration(harness),CreationProofSourceConfig.model_validate_json(json.dumps(creation))):
            basis=proofs.context(project)['basis_id']
            saved=proofs.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=config))
            common=dict(basis_id=basis,source_id=saved['result']['source_id'],revision=1)
            proofs.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,confirmed=True,**common))
            queued=proofs.start(project,StartProofPreflight(operation_id=uuid4().hex,**common));core.worker.start()
            report=wait_for(lambda:proofs.status(project,queued['result']['preflight_id']))
            assert report['report']['assessment']=='USABLE',report
            proofs.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['result']['preflight_id'],confirmed=True,**common))
            adopted.append(common)
        context=core.business_scenarios.context(project)
        def node(action_id,key,expectation,resource_from=None):
            action=next(item for item in context['actions'] if item['action_id']==action_id)
            case=next(item for item in action['cases'] if item['permission']['expectation']==expectation)
            return dict(id=key,label=action['label'],depends_on=['create'] if resource_from else [],items=[dict(
                id='item',resource_id=case['resource_id'],subject_identity_id=case['subject_test_identity_id'],
                permission={name:case['permission'][name] for name in ('intent_id','revision','intent_hash')},
                **({} if resource_from is None else dict(resource_from=resource_from)))])
        document=BusinessScenarioRevision.model_validate_json(json.dumps(dict(id='bsc_'+uuid4().hex,project_id=project,
            revision=1,label='创建后发布',experiments=[dict(id='normal',label='本人正常发布',kind='NORMAL',invocations=[
                node(created.action_id,'create','ALLOW'),node(harness.action.action_id,'publish','ALLOW','create')]),
                dict(id='member',label='换主体发布新对象',kind='CHANGE_SUBJECT',control_experiment_id='normal',invocations=[
                    node(created.action_id,'create','ALLOW'),node(harness.action.action_id,'publish','DENY','create')])])) )
        core.business_scenarios.save(project,document)
        reference=ScenarioReference(scenario_id=document.id,revision=1)
        preview=core.checks.preview(project,scenario_reference=reference)
        assert preview.can_execute,preview.gaps
        run=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,scenario_reference=reference)
        deadline=time.monotonic()+50
        while time.monotonic()<deadline:
            state=core.check_results.status(run.run.run_id,project_id=project)
            if state.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
            time.sleep(.1)
        package=core.check_results.package(run.run.run_id,project_id=project)
        diagnostic=dict(
            result=package.result.model_dump(mode='json',exclude={'runtime_identity'}),
            evidence=[dict(outcome=item.outcome.model_dump(mode='json'),binding=item.resource_binding,
                observations=[(ob.phase,ob.state,ob.reason_codes) for ob in item.observations],
                creation_windows=[dict(phase=ref.phase,window=ref.creation_window.model_dump(mode='json')) for ref in item.fact_references if hasattr(ref,'creation_window')]) for item in package.evidence])
        output=Path(__file__).resolve().parents[4]/'var/audit/phase-b/dynamic-scenario'/run.run.run_id
        output.mkdir(parents=True)
        (output/'result.json').write_text(json.dumps(diagnostic,ensure_ascii=False,default=str,indent=2),encoding='utf-8')
        assert package.result.verdict is not None and package.result.verdict.value==expected,json.dumps(diagnostic,ensure_ascii=False,default=str)
        bound=[item for item in package.evidence if item.resource_binding is not None]
        assert len(bound)==2 and len({item.resource_binding.resource_id for item in bound})==2
        assert all(item.effective_case.resource_id!='alpha' and item.outcome.recovery_verified for item in bound)
        for item in bound:
            assert core.check_results.evidence_records(run.run.run_id,item.evidence_id,item.case.case_id,project_id=project).records
        story=core.check_story.build(run.run.run_id)
        assert {item.fact_comparison.resource_id for item in story.actions if item.case_id in {value.case.case_id for value in bound}}=={item.resource_binding.resource_id for item in bound}
        from product.backend.infrastructure.artifacts.checks.fact_validation import validate_scenario_bindings
        altered=bound[0].model_copy(update={'resource_binding':bound[0].resource_binding.model_copy(update={'producer_case_id':bound[1].resource_binding.producer_case_id})})
        with pytest.raises(ValueError,match='producer'):
            validate_scenario_bindings(package.request,[altered if item.evidence_id==bound[0].evidence_id else item for item in package.evidence])
        with httpx.Client(base_url=core.application_understanding.get(project).confirmed_endpoint,trust_env=False) as client:
            client.post('/api/login',json={'account':'alice'})
            counts=client.get('/api/scenario-counts').json()
            assert sorted(counts['created'])==sorted(counts['removed']) and len(counts['created'])==2
        if regression:
            reference=core.check_repairs.contracts(run.run.run_id)[0].reference()
            original_ids={item.resource_binding.resource_id for item in bound}
            for policy,repaired in [('true /* preserves the faulty policy */','BLOCK'),("actor.role === 'owner' && actor.id === ownerId",'PASS')]:
                change=reload_ordinary_policy(harness,policy,repair_reference=reference)
                for source in adopted:
                    common={**source,'basis_id':proofs.context(project)['basis_id']}
                    queued=proofs.start(project,StartProofPreflight(operation_id=uuid4().hex,**common))
                    report=wait_for(lambda:proofs.status(project,queued['result']['preflight_id']))
                    assert report['report']['assessment']=='USABLE'
                    proofs.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['result']['preflight_id'],confirmed=True,**common))
                preview=core.checks.preview(project,change_id=change)
                assert preview.can_execute,preview.gaps
                repeat=core.checks.submit(project,change_id=change,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex)
                deadline=time.monotonic()+50
                while time.monotonic()<deadline:
                    state=core.check_results.status(repeat.run.run_id,project_id=project)
                    if state.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
                    time.sleep(.1)
                verified=core.check_results.package(repeat.run.run_id,project_id=project)
                assert verified.result.verdict.value==repaired,[(item.verdict,item.reason_codes) for item in verified.result.case_results]
                assert verified.request.scenario.document==document
                actual_ids={item.resource_binding.resource_id for item in verified.evidence if item.resource_binding is not None}
                assert len(actual_ids)==2 and not actual_ids.intersection(original_ids)
                original_ids.update(actual_ids)
                repair=core.check_story.build(repeat.run.run_id).repair_verification
                assert repair.status==('VERIFIED' if repaired=='PASS' else 'NOT_VERIFIED'),repair
                assert repair.source_run_id==run.run.run_id
    finally:harness.close()


pytestmark=pytest.mark.level4


def test_private_record_transport_closes_without_hiding_application_background_work(tmp_path):
    def driver(text):
        return text.replace('    const match=',"""
    if(req.url==='/api/background'){
      const item=await records.read('alpha');
      await records.transact({resource_id:'alpha',subject_id:actor.id,expected_version:item.version,changes:[]});
      setTimeout(()=>{},1000);return reply(200,{ok:true});
    }
    const match=""")
    harness=ordinary_application(tmp_path,edit_driver=driver)
    try:
        from product.backend.infrastructure.observers.records.record_source import read_record_source
        config=source_configuration(harness)
        runtime=harness.core.node_runtime.reference(harness.project_id)
        with httpx.Client(base_url=f'http://127.0.0.1:{runtime.port}',trust_env=False) as client:
            assert client.post('/api/login',json={'account':'alice'}).status_code==200
            # 多次读取同时覆盖宿主连接首次建立及复用，不能靠时间等待使记录变为完整。
            for number in range(1,9):
                nonce=f'{number:064x}'
                assert client.post('/api/resources/alpha/publish',headers={'X-Jiejian-Request-Nonce':nonce}).status_code==200
                view=read_record_source(harness.var_dir,runtime,config,'alpha',request_nonce=nonce)
                assert view.scope.state=='COMPLETE'
            nonce='f'*64
            assert client.post('/api/background',headers={'X-Jiejian-Request-Nonce':nonce}).status_code==200
            view=read_record_source(harness.var_dir,runtime,config,'alpha',request_nonce=nonce)
            assert view.scope.state=='INCOMPLETE'
    finally:harness.close()
