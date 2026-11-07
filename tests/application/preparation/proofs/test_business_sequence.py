"""真实审批前提、跳步/乱序/重复，以及无效修改和原题修复复验。"""
import json
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from product.backend.application.preparation.proofs.commands import SaveProofSource,GrantProofScope,StartProofPreflight,AdoptProofSource
from product.backend.domain.recording.models import RecordingPurpose
from product.protocols.checks.scenarios import BusinessScenarioRevision,ScenarioReference
from product.protocols.preparation.proof_sources import AtomicProofSourceConfig
from tests.support.builders.preparation.action_preparation import add_recording
from tests.support.builders.runtime.managed_records import ordinary_application,source_configuration,wait_for,reload_ordinary_policy

POLICY="actor.id === ownerId && actor.sequence_state === 'reviewed'"


def source(source_root):
    path=source_root/'openapi.json'
    document=json.loads(path.read_text(encoding='utf-8'))
    document['paths']['/api/resources/{resource_id}/review']={'post':{'summary':'审阅资料','responses':{'200':{'description':'reviewed'}}}}
    path.write_text(json.dumps(document),encoding='utf-8')
    (source_root/'policy.mjs').write_text('export function mayPublish(actor, ownerId) { return '+POLICY+'; }',encoding='utf-8')


def driver(text):
    text=text.replace("{state:'draft',title:'unit-a',summary:'value-a'}","{state:'draft',count:0,title:'unit-a',summary:'value-a'}")
    route="""
    const review=/^\\/api\\/resources\\/([a-z]+)\\/review$/.exec(req.url);
    if(review){
      const resource_id=review[1],item=await records.read(resource_id);
      const allowed=actor.id===item.owner_id&&item.data.state==='draft';
      await records.transact({resource_id,subject_id:actor.id,expected_version:item.version,changes:allowed?[{path:['state'],value:'reviewed'}]:[]});
      return reply(allowed?200:403,{ok:allowed});
    }
"""
    text=text.replace('    const match=',route+'    const match=')
    text=text.replace('mayPublish(actor,item.owner_id)','mayPublish({...actor,sequence_state:item.data.state},item.owner_id)')
    return text.replace("steps.map(step=>({path:['state'],value:step==='publish'?'published':'draft'}))",
        "(action==='withdraw'?[{path:['state'],value:'draft'},{path:['count'],value:0}]:[{path:['state'],value:'published'},{path:['count'],value:item.data.count+1}])")


def proposal(command,selected):
    action=command['proposed_actions'][0]
    action['effect_catalog'].append(dict(item_id='peff_'+'4'*16,business_label='审批次数改变',effect_kind='STATE_MUTATION',
        resource_concept='资料',field_mutation=dict(path=['count'],operation='CHANGE'),description='区分重复审批和只读重试'))
    command['proposed_permissions'][0].update(conditions=dict(resource_states=['reviewed']),protected_effect_item_ids=['peff_'+'1'*16,'peff_'+'4'*16])
    command['proposed_permissions'].append(dict(item_id='pperm_'+'4'*16,write_mode='CREATE',effective_state='ACTIVE',
        subject_actor_item_id='pactr_'+'1'*16,business_action_item_id='pactn_'+'1'*16,resource_owner_actor_item_id='pactr_'+'1'*16,
        relation='OWNS',expectation='DENY',conditions=dict(resource_states=['draft','published']),protected_effect_item_ids=['peff_'+'1'*16,'peff_'+'4'*16]))
    command['proposed_actions'].append(dict(item_id='pactn_'+'3'*16,write_mode='CREATE',display_name='审阅资料',description='批准前完成审阅',
        primary_resource_concept='资料',operation_kind='CHANGE',state_changing=True,effective_state='ACTIVE',
        source_candidate_ids=[next(item.candidate_id for item in selected.action_candidates if item.canonical_key=='POST /api/resources/{resource_id}/review')],
        effect_catalog=[dict(item_id='peff_'+'3'*16,business_label='资料已审阅',effect_kind='STATE_MUTATION',resource_concept='资料',expected_state='reviewed',description='审批前提已持久保存')]))
    command['proposed_permissions'].append(dict(item_id='pperm_'+'3'*16,write_mode='CREATE',effective_state='ACTIVE',subject_actor_item_id='pactr_'+'1'*16,
        business_action_item_id='pactn_'+'3'*16,resource_owner_actor_item_id='pactr_'+'1'*16,relation='OWNS',expectation='ALLOW',protected_effect_item_ids=['peff_'+'3'*16]))


@pytest.mark.parametrize('kind',['OMIT','REORDER','REPEAT'])
def test_sequence_family_keeps_exact_preconditions_through_repairs(tmp_path,kind):
    harness=ordinary_application(tmp_path,edit_driver=driver,edit_source=source,edit_proposal=proposal,max_requests=500)
    core,project,proofs=harness.core,harness.project_id,harness.core.proof_preparation
    try:
        review_action=next(item for item in core.business_boundaries.view(project).actions if item.display_name=='审阅资料')
        review=replace(harness,action=review_action,effect_id=review_action.effect_catalog[0].effect_id)
        recording=add_recording(review,request_path='/api/resources/alpha/review',resource_location='path[2]',request_json={})
        core.recording_lifecycle.finalize(recording.recording_id,var_dir=harness.var_dir,now_us=100)
        recovery=add_recording(review,purpose=RecordingPurpose.RECOVERY,parent_recording_id=recording.recording_id,
            request_path='/api/resources/alpha/withdraw',resource_location='path[2]',request_json={},target_step_id='first')
        core.recording_lifecycle.finalize(recovery.recording_id,var_dir=harness.var_dir,now_us=101)
        configs=[source_configuration(review)]
        for effect in harness.action.effect_catalog:
            config=source_configuration(replace(harness,effect_id=effect.effect_id)).model_dump(mode='json')
            config['mappings']['condition_state']=['data','state']
            if effect.field_mutation is not None:config['mappings']['state']=['data','count']
            configs.append(AtomicProofSourceConfig.model_validate_json(json.dumps(config)))
        sources=[];reference=None;original=None;history=[]
        for stage,expected in [(0,'PASS'),(1,'BLOCK'),(2,'BLOCK'),(3,'PASS')]:
            change=None
            if stage:change=reload_ordinary_policy(harness,'true' if stage==1 else 'true /* ineffective correction */' if stage==2 else POLICY,repair_reference=reference if stage>=2 else None)
            basis=proofs.context(project)['basis_id']
            if not sources:
                for config in configs:
                    saved=proofs.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=config))
                    common=dict(basis_id=basis,source_id=saved['result']['source_id'],revision=1)
                    proofs.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,confirmed=True,**common));sources.append(common)
            core.worker.start()
            for saved in sources:
                common={**saved,'basis_id':basis}
                queued=proofs.start(project,StartProofPreflight(operation_id=uuid4().hex,**common))
                report=wait_for(lambda:proofs.status(project,queued['result']['preflight_id']))
                assert report['report']['assessment']=='USABLE',report['report']
                proofs.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['result']['preflight_id'],confirmed=True,**common))
            if original is None:
                context=core.business_scenarios.context(project)
                def node(action_id,key,denied=False):
                    action=next(item for item in context['actions'] if item['action_id']==action_id)
                    case=next(item for item in action['cases'] if item['subject_test_identity_id']==item['resource_owner_test_identity_id'] and item['permission']['expectation']==('DENY' if denied else 'ALLOW'))
                    return dict(id=key,label=action['label'],items=[dict(id='resource',permission={name:case['permission'][name] for name in ('intent_id','revision','intent_hash')},subject_identity_id=case['subject_test_identity_id'],resource_id=case['resource_id'])])
                normal=[node(review_action.action_id,'review'),node(harness.action.action_id,'approve')]
                denied=node(harness.action.action_id,'approve' if kind!='REPEAT' else 'approve_again',True)
                variant=[denied] if kind=='OMIT' else [denied,normal[0]] if kind=='REORDER' else [*normal,denied]
                original=BusinessScenarioRevision.model_validate_json(json.dumps(dict(id='bsc_'+uuid4().hex,project_id=project,revision=1,label='资料审批：'+kind,experiments=[
                    dict(id='normal',label='审阅后审批',kind='NORMAL',invocations=normal),dict(id='challenge',label='检查顺序约束',kind=kind,control_experiment_id='normal',invocations=variant)])))
                core.business_scenarios.save(project,original)
            scope=dict(scenario_reference=ScenarioReference(scenario_id=original.id,revision=1)) if stage<2 else dict(change_id=change)
            preview=core.checks.preview(project,**scope);assert preview.can_execute,preview.gaps
            submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,**scope)
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                status=core.check_results.status(submitted.run.run_id,project_id=project)
                if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
                time.sleep(.1)
            package=core.check_results.package(submitted.run.run_id,project_id=project)
            diagnostic=dict(stage=stage,family=kind,result=package.result.model_dump(mode='json'),evidence=[dict(
                case_id=item.case.case_id,expectation=item.case.permission.expectation,outcome=item.outcome.model_dump(mode='json'),
                observations=[(ob.phase,ob.state,ob.reason_codes) for ob in item.observations],
                windows=[dict(phase=ref.phase,proof=ref.proof_fingerprint,window=ref.record_window.model_dump(mode='json')) for ref in item.fact_references if getattr(ref,'record_window',None) is not None]) for item in package.evidence])
            output=Path(__file__).resolve().parents[4]/'var/audit/phase-b/sequence'/submitted.run.run_id
            output.mkdir(parents=True)
            (output/'result.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
            assert package.result.verdict.value==expected,json.dumps(diagnostic,ensure_ascii=False)
            assert package.request.scenario.document==original
            story=core.check_story.build(submitted.run.run_id)
            if stage==1:reference=core.check_repairs.contracts(submitted.run.run_id)[0].reference()
            if stage>=2:assert story.repair_verification.status==('VERIFIED' if expected=='PASS' else 'NOT_VERIFIED'),story.repair_verification
            history.append((submitted.run.run_id,expected))
            assert all(core.check_results.status(key,project_id=project).run.verdict.value==value for key,value in history)
    finally:harness.close()


pytestmark=pytest.mark.level4
