# 验证同一规则两次真实改码：受支持纯策略变更保留录制，运行/会话变化重做预检查，旧Run不改写。
import pytest
from uuid import uuid4
import time
import json
from product.backend.application.preparation.proofs.commands import SaveProofSource, GrantProofScope, StartProofPreflight, AdoptProofSource
from tests.support.builders.runtime.managed_records import ordinary_application, source_configuration, wait_for, reload_ordinary_policy


@pytest.mark.parametrize('complex_flow',[False,True])
def test_two_source_changes_reuse_materials_and_keep_original_results(tmp_path,complex_flow):
    def driver(text):
        return text.replace("{id:'bob',role:roles[1]}","{id:'bob',role:roles[1],organizations:['team']}").replace(
            "{state:'draft',title:'unit-a',summary:'value-a'}","{state:'draft',title:'unit-a',summary:'value-a',organization:'team',scope_complete:true}")
    def proposal(command,selected):
        command['proposed_permissions'][1]['conditions']=dict(relationships=[dict(kind='ORGANIZATION')])
        command['proposed_actions'][0]['effect_catalog'][0].update(expected_state=None,
            field_mutation=dict(path=['state'],operation='ASSIGN',expected_value='published'))
    harness = ordinary_application(tmp_path,edit_driver=driver if complex_flow else None,edit_proposal=proposal if complex_flow else None)
    core,project,service = harness.core,harness.project_id,harness.core.proof_preparation
    def configuration():
        config=source_configuration(harness).model_dump(mode='json')
        if complex_flow:config['relationship_mapping']=dict(application_action='publish',scope_complete_path=['scope_complete'],
            subject_organizations_path=['organizations'],resource_organization_path=['organization'])
        from product.protocols.preparation.proof_sources import AtomicProofSourceConfig
        return AtomicProofSourceConfig.model_validate_json(json.dumps(config))
    try:
        basis = service.context(project)['basis_id']
        source = service.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=configuration()))['result']['source_id']
        service.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=1,confirmed=True))
        with core.uow_factory() as work:
            original_execution = work.action_preparation.execution(harness.action.action_id,1)
            original_resource = work.action_preparation.resources(harness.action.action_id,1)
            original_recovery = work.action_preparation.recovery(harness.action.action_id,1)
        core.worker.start()
        old_runs = [];repair_reference=None;source_revision=1;scenario_reference=None
        stages=[(0,'PASS'),(1,'BLOCK'),(2,'BLOCK'),(3,'PASS')] if complex_flow else [(0,'PASS'),(1,'BLOCK'),(2,'PASS')]
        for stage,expected in stages:
            change_id=None
            if stage:
                policy = 'true' if stage==1 or complex_flow and stage==2 else "actor.role === 'owner' && actor.id === ownerId"
                change_id=reload_ordinary_policy(harness,policy,repair_reference=repair_reference if stage>=2 else None)
                assert service.active_sources(project)==()
                assert not core.checks.preview(project,change_id=change_id).can_execute
                if stage>=2:
                    # 同一含义重新保存与采用不换题；revision和preflight_id不是证明标准。
                    updated=service.context(project)
                    retained=service.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=updated['basis_id'],source_id=source,expected_revision=1,config=configuration()))
                    assert retained['result']['state']=='UNCHANGED'
                    source_revision=retained['result']['revision']
            basis = service.context(project)['basis_id']
            started = service.start(project,StartProofPreflight(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=source_revision))
            preflight = started['result']['preflight_id']
            assert wait_for(lambda:service.status(project,preflight))['report']['assessment']=='USABLE'
            if stage==0 or stage>=2:
                service.adopt(project,AdoptProofSource(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=source_revision,
                    preflight_id=preflight,confirmed=True))
            if complex_flow and stage==0:
                from product.protocols.checks.scenarios import BusinessScenarioRevision,ScenarioReference
                current=core.checks.preview(project)
                def invocation(expectation):
                    case=next(case for item in current.actions for case in item.cases if case.permission.expectation==expectation)
                    return dict(id='publish',label='发布资料',items=[dict(id='resource',resource_id=case.resource_id,
                        subject_identity_id=case.subject_test_identity_id,permission={key:getattr(case.permission,key) for key in ('intent_id','revision','intent_hash')})])
                document=BusinessScenarioRevision.model_validate_json(json.dumps(dict(id='bsc_'+uuid4().hex,project_id=project,
                    revision=1,label='组织条件下的发布流程',experiments=[dict(id='normal',label='负责人发布',kind='NORMAL',invocations=[invocation('ALLOW')]),
                        dict(id='member',label='换成组织成员',kind='CHANGE_SUBJECT',control_experiment_id='normal',invocations=[invocation('DENY')])])))
                core.business_scenarios.save(project,document)
                scenario_reference=ScenarioReference(scenario_id=document.id,revision=1)
            scope=dict(scenario_reference=scenario_reference) if complex_flow and stage<2 else dict(change_id=change_id)
            preview = core.checks.preview(project,**scope)
            assert not preview.gaps,preview
            with core.uow_factory() as work:
                adoption = work.proof_sources.adoption(project,source)
            frozen = service.frozen_sources(project)
            assert frozen[0].adoption_preflight_id == adoption.preflight_id
            if stage == 1:
                # 新实例已重核，但本次未要求人重新采用；运行引用仍绑定原确认。
                assert frozen[0].adoption_preflight_id != preflight
            submitted = core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,**scope)
            deadline = time.monotonic()+40
            while time.monotonic()<deadline:
                status = core.check_results.status(submitted.run.run_id,project_id=project)
                if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:
                    break
                time.sleep(.1)
            assert status.run.verdict is not None and status.run.verdict.value==expected,status
            story=core.check_story.build(submitted.run.run_id)
            assert story.verdict.value==expected
            if stage==1:
                repair_reference=core.check_repairs.contracts(submitted.run.run_id)[0].reference()
                package=core.check_results.package(submitted.run.run_id)
                document=next(item for item in package.evidence if item.case.permission.expectation=='DENY')
                records=core.check_results.evidence_records(submitted.run.run_id,document.evidence_id,document.case.case_id,project_id=project)
                observed=next(item for item in records.records if item.kind=='OBSERVATION' and item.phase=='AFTER')
                detail=core.check_results.evidence_records(submitted.run.run_id,document.evidence_id,document.case.case_id,project_id=project,record_id=observed.record_id)
                assert detail.values and detail.verification[2].status=='CONFIRMED'
            if stage>=2:
                assert story.repair_verification.status==('NOT_VERIFIED' if expected=='BLOCK' else 'VERIFIED'),story.repair_verification
                assert story.repair_verification.source_run_id==old_runs[1][0]
            old_runs.append((submitted.run.run_id,status.run.verdict))
            with core.uow_factory() as work:
                assert work.action_preparation.execution(harness.action.action_id,1)==original_execution
                assert work.action_preparation.resources(harness.action.action_id,1)==original_resource
                assert work.action_preparation.recovery(harness.action.action_id,1)==original_recovery
            for run_id,verdict in old_runs:
                assert core.check_results.status(run_id,project_id=project).run.verdict==verdict
    finally:
        harness.close()


def test_correcting_missing_field_keeps_recordings_and_reuses_read_scope(tmp_path):
    harness=ordinary_application(tmp_path)
    core,project,service=harness.core,harness.project_id,harness.core.proof_preparation
    try:
        config=source_configuration(harness);basis=service.context(project)['basis_id']
        source=service.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=config))['result']['source_id']
        service.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=1,confirmed=True))
        core.worker.start()
        def preflight(revision):
            basis=service.context(project)['basis_id']
            queued=service.start(project,StartProofPreflight(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=revision))['result']
            return queued['preflight_id'],wait_for(lambda:service.status(project,queued['preflight_id']))
        first,result=preflight(1);assert result['report']['assessment']=='USABLE'
        service.adopt(project,AdoptProofSource(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=1,preflight_id=first,confirmed=True))
        original=core.preparation.get(project).actions[0]
        # 映射引用的业务字段不存在时只影响来源准备，录制与权限不被重建。
        basis=service.context(project)['basis_id']
        invalid=config.model_copy(update={'mappings':dict(config.mappings,state=('data','missing_state'))})
        service.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,source_id=source,expected_revision=1,config=invalid))
        assert service.active_sources(project)==()
        _,missing=preflight(2)
        assert missing['report']['assessment']!='USABLE'
        assert any(v['mapping_key']=='state' for v in missing['report']['checks'])
        basis=service.context(project)['basis_id']
        updated=config
        service.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,source_id=source,expected_revision=2,config=updated))
        second,result=preflight(3);assert result['report']['assessment']=='USABLE'
        assert service.active_sources(project)==()
        service.adopt(project,AdoptProofSource(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=3,preflight_id=second,confirmed=True))
        assert not core.checks.preview(project).gaps
        assert len(service.context(project)['read_scopes'])==1
        assert core.business_boundaries.view(project).policy_epoch==1
    finally:harness.close()


# 该模块启动真实 Node、Worker 与 Runner，不进入普通 L2。
pytestmark = [pytest.mark.level4, pytest.mark.process, pytest.mark.slow]
