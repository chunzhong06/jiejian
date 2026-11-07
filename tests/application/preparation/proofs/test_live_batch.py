"""普通应用真实混合批量：同形正常对照、逐资源取证和原题修复，不用 HTTP 状态替代业务事实。"""
import json
import time
from pathlib import Path
from uuid import uuid4

import pytest

from product.backend.domain.recording.models import RecordingPurpose
from product.protocols.web.request import ValueSlotConsumer
from product.protocols.checks.scenarios import BusinessScenarioRevision,ScenarioReference
from product.backend.application.preparation.proofs.commands import SaveProofSource,GrantProofScope,StartProofPreflight,AdoptProofSource
from tests.support.builders.preparation.action_preparation import add_recording
from tests.support.builders.runtime.managed_records import ordinary_application,source_configuration,wait_for,reload_ordinary_policy

POLICY="actor.role === 'owner' || actor.id === ownerId"


@pytest.mark.parametrize('strategy',['ATOMIC','PER_ITEM'])
def test_mixed_batch_retains_each_resource_and_original_repair(tmp_path,strategy):
    def driver(text):
        route="""
    if(req.url==='/api/batch/publish'){
      let raw='';for await(const chunk of req)raw+=chunk;
      const ids=JSON.parse(raw).ids,items=await Promise.all(ids.map(id=>records.read(id)));
      const decisions=items.map(item=>mayPublish(actor,item.owner_id));
      const accepted=BATCH_STRATEGY==='ATOMIC'?decisions.every(Boolean):true;
      for(let i=0;i<ids.length;i++)if(accepted&&decisions[i])await records.transact({resource_id:ids[i],subject_id:actor.id,expected_version:items[i].version,changes:[{path:['state'],value:'published'}]});
      return reply(200,{items:ids.map((id,index)=>({id,accepted:accepted&&decisions[index]}))});
    }
""".replace('BATCH_STRATEGY',json.dumps(strategy))
        return text.replace('    const match=',route+'    const match=')
    def proposal(command,selected):
        for ordinal,subject,owner,relation in [(3,'pactr_'+'2'*16,'pactr_'+'2'*16,'OWNS'),(4,'pactr_'+'1'*16,'pactr_'+'2'*16,'OTHER_ROLE')]:
            command['proposed_permissions'].append(dict(item_id='pperm_'+str(ordinal)*16,write_mode='CREATE',effective_state='ACTIVE',
                subject_actor_item_id=subject,business_action_item_id='pactn_'+'1'*16,resource_owner_actor_item_id=owner,
                relation=relation,expectation='ALLOW',protected_effect_item_ids=['peff_'+'1'*16]))
    harness=ordinary_application(tmp_path,edit_driver=driver,edit_proposal=proposal,
        source_edits={'policy.mjs':'export function mayPublish(actor,ownerId){return '+POLICY+';}'},max_requests=500)
    core,project,proofs=harness.core,harness.project_id,harness.core.proof_preparation
    try:
        # 两份正常录制分别确认 alpha/alice 和 beta/bob，保留同一采用模板及每个资源的归属。
        for owner,resource in [(0,'alpha'),(1,'beta')]:
            recording=add_recording(harness,identity_index=owner,owner_identity_index=owner,request_path='/api/batch/publish',
                resource_consumer=ValueSlotConsumer.JSON_BODY,resource_location='$.ids[0]',request_json={'ids':[resource]})
            core.recording_lifecycle.finalize(recording.recording_id,var_dir=harness.var_dir,now_us=100)
            recovery=add_recording(harness,purpose=RecordingPurpose.RECOVERY,parent_recording_id=recording.recording_id,
                identity_index=owner,owner_identity_index=owner,request_path='/api/resources/'+resource+'/withdraw',resource_location='path[2]',request_json={},target_step_id='first')
            core.recording_lifecycle.finalize(recovery.recording_id,var_dir=harness.var_dir,now_us=101)
        saved=proofs.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=proofs.context(project)['basis_id'],config=source_configuration(harness)))
        common=dict(source_id=saved['result']['source_id'],revision=1)
        proofs.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,basis_id=proofs.context(project)['basis_id'],confirmed=True,**common))
        core.worker.start();document=None;reference=None;original=None;history=[]
        for stage,expected in [(0,'PASS'),(1,'BLOCK'),(2,'BLOCK'),(3,'PASS')]:
            change=None
            if stage:change=reload_ordinary_policy(harness,'true' if stage==1 else 'true /* ineffective correction */' if stage==2 else POLICY,repair_reference=reference if stage>=2 else None)
            common={**common,'basis_id':proofs.context(project)['basis_id']}
            queued=proofs.start(project,StartProofPreflight(operation_id=uuid4().hex,**common))
            report=wait_for(lambda:proofs.status(project,queued['result']['preflight_id']))
            assert report['report']['assessment']=='USABLE',report
            proofs.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['result']['preflight_id'],confirmed=True,**common))
            if document is None:
                context=core.business_scenarios.context(project)
                action=next(item for item in context['actions'] if item['action_id']==harness.action.action_id)
                def invocation(subject,key):
                    cases=[next(item for item in action['cases'] if item['subject_test_identity_id']==harness.identities[subject].identity_id and item['resource_id']==resource) for resource in ['alpha','beta']]
                    return dict(id='batch',label=key,batch=dict(strategy=strategy,array_path=['ids']),items=[dict(id='item'+str(index),resource_id=case['resource_id'],subject_identity_id=case['subject_test_identity_id'],permission={name:case['permission'][name] for name in ('intent_id','revision','intent_hash')}) for index,case in enumerate(cases)])
                document=BusinessScenarioRevision.model_validate_json(json.dumps(dict(id='bsc_'+uuid4().hex,project_id=project,revision=1,label='混合批量 '+strategy,experiments=[
                    dict(id='normal',label='负责人正常处理',kind='NORMAL',invocations=[invocation(0,'正常批量')]),
                    dict(id='limited',label='成员混合处理',kind='CHANGE_SUBJECT',control_experiment_id='normal',invocations=[invocation(1,'混合批量')]) ])))
                core.business_scenarios.save(project,document)
            scope=dict(scenario_reference=ScenarioReference(scenario_id=document.id,revision=1)) if stage<2 else dict(change_id=change)
            preview=core.checks.preview(project,**scope);assert preview.can_execute,preview.gaps
            submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,**scope)
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                status=core.check_results.status(submitted.run.run_id,project_id=project)
                if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
                time.sleep(.1)
            package=core.check_results.package(submitted.run.run_id,project_id=project)
            output=Path(__file__).resolve().parents[4]/'var/audit/phase-b/batch'/submitted.run.run_id
            output.mkdir(parents=True,exist_ok=True)
            (output/'result.json').write_text(json.dumps(dict(stage=stage,strategy=strategy,result=package.result.model_dump(mode='json')),ensure_ascii=False,indent=2),encoding='utf8')
            assert package.result.verdict.value==expected,(stage,[(item.verdict,item.reason_codes) for item in package.result.case_results])
            assert package.request.scenario.document==document
            assert len(package.evidence)==4
            assert {item.case.resource_id for item in package.evidence}=={'alpha','beta'}
            if stage==1:original=submitted.run.run_id;reference=core.check_repairs.contracts(original)[0].reference()
            if stage>=2:
                repair=core.check_story.build(submitted.run.run_id).repair_verification
                assert repair.status==('VERIFIED' if stage==3 else 'NOT_VERIFIED'),repair
                assert repair.source_run_id==original
            history.append((submitted.run.run_id,expected))
            assert all(core.check_results.status(key,project_id=project).run.verdict.value==value for key,value in history)
    finally:harness.close()


pytestmark=pytest.mark.level4
