"""真实本机域名应用：状态事实控制执行，403 回显字段仍形成 BLOCK。"""
import time
import json
from uuid import uuid4
import pytest
from tests.support.builders.preparation.external_application import external_application
from product.backend.application.business_boundaries.models import BoundaryMaintenanceCommand

pytestmark=pytest.mark.level4


def test_localhost_state_query_runs_through_worker_publication_and_delivery(tmp_path):
    with external_application(tmp_path,origin_host='localhost',resource_state=True) as app:
        core,project=app.core,app.project_id
        assert app.environment.target.base_url.startswith('http://localhost:')
        core.operation_flows.adopt(project,app.flow.id,app.flow.revision)
        validation=core.rule_candidates.validation_plan(project)
        assert all(item.conditions['resource_states']==['DRAFT'] for item in validation.requirements)
        original_refs={slot.test_identity_id for action in core.preparation.get(project).actions for slot in action.identity_requirements.slots}
        core.worker.start()
        snapshots=[]
        for vulnerable,state,expected in [(True,'DRAFT','BLOCK'),(False,'DRAFT','PASS'),(False,'APPROVED','INCONCLUSIVE'),(False,'private-unrecognized-value','INCONCLUSIVE')]:
            app.state.update(vulnerable=vulnerable,resource_state=state)
            before=app.state['target_calls']
            preview=core.checks.preview(project)
            assert preview.can_execute,preview.gaps
            submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex)
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                status=core.check_results.status(submitted.run.run_id,project_id=project)
                if status.run.lifecycle.value not in {'QUEUED','RUNNING'}:break
                time.sleep(.1)
            assert status.result_integrity=='VALID',status.model_dump_json()
            assert status.run.verdict is not None and status.run.verdict.value==expected,status
            story=core.check_story.build(submitted.run.run_id,project_id=project)
            assert story.environment.target.base_url.startswith('http://localhost:')
            assert any(item.kind=='NORMAL' for item in story.delivery_summary)
            if state!='DRAFT':assert app.state['target_calls']==before
            assert 'private-unrecognized-value' not in story.model_dump_json()
            snapshots.append((submitted.run.run_id,story.model_dump_json()))
        assert {slot.test_identity_id for action in core.preparation.get(project).actions for slot in action.identity_requirements.slots}==original_refs
        assert core.check_story.build(snapshots[0][0],project_id=project).model_dump_json()==snapshots[0][1]
        # 扩大规则适用状态时先评估原材料；配置保留不替新状态取得观察事实。
        draft=core.business_boundaries.maintenance_draft(project)
        command=draft.model_dump(mode='json',include={'actors','actions','permissions'})
        command.update(expected_boundary_state_fingerprint=draft.boundary_state_fingerprint)
        for rule in command['permissions']:
            rule['conditions']['resource_states']=['APPROVED','DRAFT']
        command=BoundaryMaintenanceCommand.model_validate_json(json.dumps(command))
        assessment=core.rule_candidates.preview_validation(project,command)
        assert all(item.current_materials and item.definition_changes for item in assessment.requirements)
        assert all(effect.configuration_present and effect.material_status=='STALE'
            for item in assessment.requirements for effect in item.effects)
        proposed=core.business_boundaries.create_maintenance_proposal(project,command).proposal
        core.business_boundaries.approve(project,proposed.proposal_id,
            expected_fingerprint=proposed.proposal_fingerprint,reason='新增批准状态，沿用兼容配置并补实际样本')
        app.state['vulnerable']=False
        for state,unchecked in [('DRAFT','APPROVED'),('APPROVED','DRAFT')]:
            app.state['resource_state']=state
            preview=core.checks.preview(project)
            assert preview.can_execute,preview.gaps
            submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex)
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                status=core.check_results.status(submitted.run.run_id,project_id=project)
                if status.run.lifecycle.value not in {'QUEUED','RUNNING'}:break
                time.sleep(.1)
            assert status.result_integrity=='VALID' and status.run.verdict.value=='PASS'
            story=core.check_story.build(submitted.run.run_id,project_id=project)
            assert story.runtime_status=='UNSUPPORTED'
            assert all(item.concluded_states==(state,) and item.unchecked_states==(unchecked,) for item in story.sample_coverage)
            workspace=core.rule_workspace.read(project)
            assert all(item['state']=='SAFE' and item['latest']['runtime_status']=='UNSUPPORTED' for item in workspace['rules'])
            assert core.agent_capabilities._check_delivery_gap(project,{'rule_id':story.actions[0].permission.intent_id},
                dict(run_id=story.run_id,verdict='PASS')) is None
        assert {slot.test_identity_id for action in core.preparation.get(project).actions for slot in action.identity_requirements.slots}==original_refs
        core.test_identities.reset(app.identities['owner'])
        prepared=core.preparation.get(project)
        assert any(item.handling=='RECHECK' and 'TEST_IDENTITY_LOGIN_REQUIRED' in item.reason_codes for item in prepared.impacts)
        assert {slot.test_identity_id for action in prepared.actions for slot in action.identity_requirements.slots}==original_refs
        assert core.operation_flows.read(project,app.flow.id,app.flow.revision).id==app.flow.id
        assert core.check_story.build(snapshots[0][0],project_id=project).model_dump_json()==snapshots[0][1]
