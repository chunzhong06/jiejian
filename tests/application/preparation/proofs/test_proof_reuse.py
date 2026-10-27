# 验证同一规则两次真实改码：受支持纯策略变更保留录制，运行/会话变化重做预检查，旧Run不改写。
import pytest
from uuid import uuid4
import time
from product.backend.application.preparation.proofs.commands import SaveProofSource, GrantProofScope, StartProofPreflight, AdoptProofSource
from tests.support.builders.runtime.managed_records import ordinary_application, source_configuration, wait_for, refresh_ordinary_sessions


def test_two_source_changes_reuse_materials_and_keep_original_results(tmp_path):
    harness = ordinary_application(tmp_path)
    core,project,service = harness.core,harness.project_id,harness.core.proof_preparation
    try:
        basis = service.context(project)['basis_id']
        source = service.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=source_configuration(harness)))['result']['source_id']
        service.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=1,confirmed=True))
        with core.uow_factory() as work:
            original_execution = work.action_preparation.execution(harness.action.action_id,1)
            original_resource = work.action_preparation.resources(harness.action.action_id,1)
            original_recovery = work.action_preparation.recovery(harness.action.action_id,1)
        core.worker.start()
        old_runs = [];repair_reference=None;source_revision=1
        for stage,expected in [(0,'PASS'),(1,'BLOCK'),(2,'PASS')]:
            change_id=None
            if stage:
                previous = core.node_runtime.reference(project)
                core.node_runtime.stop(project,instance_id=previous.instance_id)
                policy = 'true' if stage==1 else "actor.role === 'owner' && actor.id === ownerId"
                (harness.source_root/'policy.mjs').write_text(f'export function mayPublish(actor, ownerId) {{ return {policy}; }}',encoding='utf8')
                registration=core.development.registration_preview(project)
                receipt=core.development.register_change(project,operation_id=uuid4().hex,expected_registration_fingerprint=registration['fingerprint'],
                    reason='修改实际业务权限实现',claimed_paths=('policy.mjs',),repair_reference=repair_reference if stage==2 else None)
                change_id=receipt.change_id
                understanding = core.application_understanding.get(project)
                preview = core.node_runtime.preview(project,entry='app.mjs',port=previous.port,revision=understanding.revision,consent_source_read=True)
                operation = uuid4().hex
                core.node_runtime.start(project,entry='app.mjs',port=previous.port,revision=preview.revision,
                    preview_fingerprint=preview.preview_fingerprint,operation_id=operation,consent_execute=True)
                assert wait_for(lambda:core.node_runtime.operation(project,operation))['state']=='SUCCEEDED'
                understanding = core.application_understanding.get(project)
                core.application_understanding.analyze_source(project,revision=understanding.revision)
                refresh_ordinary_sessions(harness)
                assert service.active_sources(project)==()
                assert not core.checks.preview(project,change_id=change_id).can_execute
                if stage==2:
                    # 同一含义重新保存与采用不换题；revision和preflight_id不是证明标准。
                    updated=service.context(project)
                    service.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=updated['basis_id'],source_id=source,expected_revision=1,config=source_configuration(harness)))
                    source_revision=2
            basis = service.context(project)['basis_id']
            started = service.start(project,StartProofPreflight(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=source_revision))
            preflight = started['result']['preflight_id']
            assert wait_for(lambda:service.status(project,preflight))['report']['assessment']=='USABLE'
            if stage in {0,2}:
                service.adopt(project,AdoptProofSource(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=source_revision,
                    preflight_id=preflight,confirmed=True))
            preview = core.checks.preview(project,change_id=change_id)
            assert not preview.gaps,preview
            submitted = core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,change_id=change_id)
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
            if stage==2:
                assert story.repair_verification.status=='VERIFIED',story.repair_verification
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
