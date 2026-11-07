"""真实写入后取消，多步骤逆序收尾；重启控制面不会重放已确认的动作。"""
import json
import time
from uuid import uuid4

import httpx
import pytest

from product.backend.bootstrap.application import ApplicationCore
from product.backend.application.preparation.proofs.commands import SaveProofSource,GrantProofScope,StartProofPreflight,AdoptProofSource,RevokeProofScope
from product.protocols.checks.scenarios import BusinessScenarioRevision,ScenarioReference
from tests.support.builders.runtime.managed_records import ordinary_application,source_configuration,wait_for
from tests.support.builders.runtime.runtime_environment import runtime_identity_environment
from tests.support.secrets import MemorySecrets


@pytest.mark.parametrize('interruption',['CANCEL','REVOKE','SOURCE_REVISION','SOURCE_FILES'])
def test_cancel_after_real_commit_restores_then_restart_does_not_replay(tmp_path,interruption):
    def driver(text):
        text=text.replace("{state:'draft',title:'unit-a',summary:'value-a'}","{state:'draft',target_count:0,title:'unit-a',summary:'value-a'}")
        text=text.replace('    const match=',"    if(req.url==='/__counts'){const item=await records.read('alpha');return reply(200,{count:item.data.target_count,state:item.data.state});}\n    const match=")
        text=text.replace("steps.map(step=>({path:['state'],value:step==='publish'?'published':'draft'}))",
            "(action==='withdraw'?[{path:['state'],value:'draft'}]:[{path:['state'],value:'published'},{path:['target_count'],value:item.data.target_count+1}])")
        return text.replace("    return reply(action==='withdraw'", "    if(action==='publish'&&allowed)await new Promise(resolve=>setTimeout(resolve,800));\n    return reply(action==='withdraw'")
    harness=ordinary_application(tmp_path,edit_driver=driver,max_requests=200)
    core,project=harness.core,harness.project_id
    replacement=None
    try:
        proofs=core.proof_preparation;basis=proofs.context(project)['basis_id']
        saved=proofs.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=source_configuration(harness)))
        common=dict(basis_id=basis,source_id=saved['result']['source_id'],revision=1)
        granted=proofs.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,confirmed=True,**common))
        queued=proofs.start(project,StartProofPreflight(operation_id=uuid4().hex,**common));core.worker.start()
        report=wait_for(lambda:proofs.status(project,queued['result']['preflight_id']))
        assert report['report']['assessment']=='USABLE',report
        proofs.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['result']['preflight_id'],confirmed=True,**common))
        context=core.business_scenarios.context(project)
        action=next(item for item in context['actions'] if item['action_id']==harness.action.action_id)
        case=next(item for item in action['cases'] if item['permission']['expectation']=='ALLOW')
        item=dict(id='item',permission={name:case['permission'][name] for name in ('intent_id','revision','intent_hash')},subject_identity_id=case['subject_test_identity_id'],resource_id=case['resource_id'])
        document=BusinessScenarioRevision.model_validate_json(json.dumps(dict(id='bsc_'+uuid4().hex,project_id=project,revision=1,label='两步发布取消',experiments=[dict(
            id='normal',label='完整正常流程',kind='NORMAL',invocations=[dict(id='first',label='第一次发布',items=[item]),dict(id='second',label='后续业务动作',items=[item],depends_on=['first'])]) ])))
        core.business_scenarios.save(project,document)
        scope=dict(scenario_reference=ScenarioReference(scenario_id=document.id,revision=1))
        preview=core.checks.preview(project,**scope);assert preview.can_execute,preview.gaps
        submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,**scope)
        runtime=core.node_runtime.reference(project)
        with httpx.Client(base_url=f'http://127.0.0.1:{runtime.port}',trust_env=False) as client:
            assert client.post('/api/login',json={'account':'alice'}).status_code==200
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                if client.get('/__counts').json()['count']==1:break
                time.sleep(.04)
            else:pytest.fail('真实写入未到达')
            if interruption=='CANCEL':core.checks.cancel(project,submitted.run.run_id)
            elif interruption=='REVOKE':
                proofs.revoke_scope(project,RevokeProofScope(operation_id=uuid4().hex,scope_id=granted['result']['scope_id']))
            elif interruption=='SOURCE_REVISION':
                proofs.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=proofs.context(project)['basis_id'],
                    source_id=common['source_id'],expected_revision=1,
                    config=source_configuration(harness).model_copy(update=dict(timeout_us=4_000_000))))
            else:
                with (harness.source_root/'policy.mjs').open('a',encoding='utf8') as stream:stream.write('\n// source revision changed during execution\n')
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                status=core.check_results.status(submitted.run.run_id,project_id=project)
                if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
                time.sleep(.1)
            assert client.get('/__counts').json()==dict(count=1,state='draft')
        assert status.run.lifecycle.value=='CANCELLED',status
        progress=status.scenario_execution
        assert progress[0].request in {'RECEIVED','UNCONFIRMED'} and progress[0].recovered_cases
        assert progress[1].request=='NOT_STARTED'
        # 取消不发布完整权限结论；独立读取实际状态和逐节点恢复账本核对收尾。
        assert status.run.verdict is None
        if interruption!='CANCEL':return
        var=core.var_dir;core.close()
        # 重建 ApplicationCore 和监督器；只读原题，不提交新操作，也不靠取消后重试制造结果。
        replacement=ApplicationCore(var,secret_store=MemorySecrets(),environ=runtime_identity_environment(var))
        replacement.worker.start()
        old=replacement.check_results.status(submitted.run.run_id,project_id=project)
        assert old.run.lifecycle.value=='CANCELLED' and old.job.attempt==1
        assert old.scenario_execution==progress
        understanding=replacement.application_understanding.get(project)
        preparation=replacement.node_runtime.preview(project,entry='app.mjs',port=runtime.port,revision=understanding.revision,consent_source_read=True)
        operation=uuid4().hex
        replacement.node_runtime.start(project,entry='app.mjs',port=runtime.port,revision=preparation.revision,
            preview_fingerprint=preparation.preview_fingerprint,operation_id=operation,consent_execute=True)
        replacement.runtime_worker.start()
        assert wait_for(lambda:replacement.node_runtime.operation(project,operation))['state']=='SUCCEEDED'
        with httpx.Client(base_url=f'http://127.0.0.1:{runtime.port}',trust_env=False) as client:
            assert client.post('/api/login',json={'account':'alice'}).status_code==200
            assert client.get('/__counts').json()==dict(count=1,state='draft')
        assert replacement.check_results.status(submitted.run.run_id,project_id=project).job.attempt==1
    finally:
        if replacement is not None:replacement.close()
        else:harness.close()


pytestmark=pytest.mark.level4
