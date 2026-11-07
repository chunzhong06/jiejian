"""同一真实授权先可用，再撤销或实际到期，保留原题和各轮修改结果。"""
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from product.backend.application.preparation.proofs.commands import SaveProofSource,GrantProofScope,StartProofPreflight,AdoptProofSource
from product.protocols.checks.execution_request import PermissionReference
from product.protocols.preparation.proof_sources import AtomicProofSourceConfig
from tests.support.builders.runtime.managed_records import ordinary_application,source_configuration,wait_for,reload_ordinary_policy

POLICY="actor.id === ownerId || actor.grant_active"


@pytest.mark.parametrize('kind,state',[('SHARING','REVOKED'),('DELEGATION','REVOKED'),('SHARING','EXPIRED'),('DELEGATION','EXPIRED')])
def test_live_grant_changes_and_original_repair(tmp_path,kind,state):
    def driver(text):
        text=text.replace("{state:'draft',title:'unit-a',summary:'value-a'}","{state:'draft',title:'unit-a',summary:'value-a',scope_complete:true,source_time:1,grants:[]}")
        routes="""
    if(req.url.startsWith('/api/grant/')){
      if(actor.id!=='alice')return reply(403,{error:'denied'});
      const item=await records.read('alpha'),operation=req.url.split('/').at(-1),now=Date.now()*1000;
      let grants=item.data.grants;
      if(operation==='activate')grants=[{grant_id:'lifecycle',kind:GRANT_KIND,grantor_id:'alice',grantee_id:'bob',resource_id:'alpha',actions:['publish'],valid_from_us:1,valid_until_us:now+3600000000}];
      if(operation==='revoke')grants=grants.map(g=>({...g,revoked_at_us:now}));
      if(operation==='expire')grants=grants.map(g=>({...g,valid_until_us:now+100000}));
      await records.transact({resource_id:'alpha',subject_id:actor.id,expected_version:item.version,changes:[{path:['grants'],value:grants},{path:['source_time'],value:now}]});
      return reply(200,{expires:grants[0]?.valid_until_us});
    }
""".replace('GRANT_KIND',json.dumps(kind))
        text=text.replace('    const match=',routes+'    const match=')
        return text.replace('mayPublish(actor,item.owner_id)',"mayPublish({...actor,grant_active:item.data.grants.some(g=>g.kind==="+json.dumps(kind)+"&&g.grantee_id===actor.id&&!g.revoked_at_us&&g.valid_from_us<=Date.now()*1000&&g.valid_until_us>Date.now()*1000)},item.owner_id)")
    def proposal(command,selected):
        active=command['proposed_permissions'][1]
        active.update(expectation='ALLOW',conditions=dict(relationships=[dict(kind=kind,state='ACTIVE')]))
        denied={**active,'item_id':'pperm_'+'3'*16,'expectation':'DENY','conditions':dict(relationships=[dict(kind=kind,state=state)])}
        command['proposed_permissions'].append(denied)
    harness=ordinary_application(tmp_path,edit_driver=driver,edit_proposal=proposal,source_edits={'policy.mjs':'export function mayPublish(actor, ownerId) { return '+POLICY+'; }'})
    core,project,proofs=harness.core,harness.project_id,harness.core.proof_preparation
    try:
        config=source_configuration(harness).model_dump(mode='json')
        config['relationship_mapping']=dict(application_action='publish',scope_complete_path=['scope_complete'],
            source_time_path=['source_time'],grants_path=['grants'],clock_uncertainty_us=5_000_000)
        basis=proofs.context(project)['basis_id']
        saved=proofs.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=AtomicProofSourceConfig.model_validate_json(json.dumps(config))))
        common=dict(basis_id=basis,source_id=saved['result']['source_id'],revision=1)
        proofs.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,confirmed=True,**common));core.worker.start()
        permissions=core.business_boundaries.view(project).permission_intents
        def selected(expected_state):
            permission=next(item for item in permissions if item.conditions is not None and item.conditions.relationships[0].state==expected_state)
            return (PermissionReference(intent_id=permission.intent_id,revision=permission.revision,intent_hash=permission.intent_hash),)
        reference=None;original=None;history=[]
        for stage,expected in [(0,'PASS'),(1,'PASS'),(2,'BLOCK'),(3,'BLOCK'),(4,'PASS')]:
            change=None
            if stage>=2:change=reload_ordinary_policy(harness,'true' if stage==2 else 'true /* ineffective correction */' if stage==3 else POLICY,repair_reference=reference if stage>=3 else None)
            common={**common,'basis_id':proofs.context(project)['basis_id']}
            if stage!=1:
                queued=proofs.start(project,StartProofPreflight(operation_id=uuid4().hex,**common))
                report=wait_for(lambda:proofs.status(project,queued['result']['preflight_id']))
                assert report['report']['assessment']=='USABLE',report
                proofs.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['result']['preflight_id'],confirmed=True,**common))
            runtime=core.node_runtime.reference(project)
            with httpx.Client(base_url=f'http://127.0.0.1:{runtime.port}',trust_env=False) as client:
                assert client.post('/api/login',json={'account':'alice'}).status_code==200
                if stage==0:assert client.post('/api/grant/activate').status_code==200
                if stage==1:
                    changed=client.post('/api/grant/'+('revoke' if state=='REVOKED' else 'expire'));assert changed.status_code==200
                    # 等待真实有效期跨过边界，仍保留时钟不确定区间；不以预置过期样本代替。
                    if state=='EXPIRED':
                        deadline=time.monotonic()+7
                        while time.time_ns()//1000<=changed.json()['expires']+5_020_000 and time.monotonic()<deadline:time.sleep(.01)
                    else:time.sleep(5.03)
                assert client.post('/api/grant/sample').status_code==200
            scope=dict(change_id=change) if stage>=3 else dict(selected_permissions=selected('ACTIVE' if stage==0 else state))
            preview=core.checks.preview(project,**scope);assert preview.can_execute,preview.gaps
            submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,**scope)
            deadline=time.monotonic()+50
            while time.monotonic()<deadline:
                status=core.check_results.status(submitted.run.run_id,project_id=project)
                if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
                time.sleep(.1)
            package=core.check_results.package(submitted.run.run_id,project_id=project)
            diagnostic=dict(stage=stage,result=package.result.model_dump(mode='json'),evidence=[item.model_dump(mode='json') for item in package.evidence])
            output=Path(__file__).resolve().parents[4]/'var/audit/phase-b/relationship'/submitted.run.run_id
            output.mkdir(parents=True,exist_ok=True)
            (output/'result.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
            assert package.result.verdict.value==expected,(stage,[(item.verdict,item.reason_codes) for item in package.result.case_results])
            if stage==2:original=submitted.run.run_id;reference=core.check_repairs.contracts(original)[0].reference()
            if stage>=3:
                repair=core.check_story.build(submitted.run.run_id).repair_verification
                assert repair.status==('VERIFIED' if stage==4 else 'NOT_VERIFIED'),repair
                assert repair.source_run_id==original
            history.append((submitted.run.run_id,expected))
            assert all(core.check_results.status(key,project_id=project).run.verdict.value==value for key,value in history)
    finally:harness.close()


pytestmark=pytest.mark.level4
