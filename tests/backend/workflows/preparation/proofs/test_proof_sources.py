# 验证普通来源的候选、GUI授权、真实独立预检查与采用；组件捕获fixture不替代公开接入验收。
from uuid import uuid4
import pytest
from product.backend.core.errors import JiejianError
from product.backend.workflows.preparation.proofs.commands import SaveProofSource, GrantProofScope, StartProofPreflight, AdoptProofSource, RevokeProofScope
from tests.fixtures.runtime.managed_records import ordinary_application, source_configuration, wait_for


def test_candidate_preflight_adoption_and_revocation_use_production_jobs(tmp_path):
    harness = ordinary_application(tmp_path)
    core,project = harness.core,harness.project_id
    service = core.proof_preparation
    try:
        config = source_configuration(harness)
        basis = service.context(project)['basis_id']
        save = SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=config)
        saved = service.save(project,save)
        assert service.save(project,save)==saved
        source = saved['result']['source_id']
        advice = core.preparation_guidance.context(project)['guidance']
        assert advice['sources'][0]['next_action']['kind'] == 'CONFIRM_READ_SCOPE'
        assert any(item['kind']=='execution' and item['status']=='SATISFIED' for item in advice['materials'])
        common = dict(source_id=source,revision=1,basis_id=basis)
        with pytest.raises(JiejianError,match='读取范围'):
            service.start(project,StartProofPreflight(operation_id=uuid4().hex,**common))
        scope = service.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,confirmed=True,**common))
        assert core.preparation_guidance.context(project)['guidance']['sources'][0]['next_action']['kind']=='RUN_PREFLIGHT'
        request = StartProofPreflight(operation_id=uuid4().hex,**common)
        started = service.start(project,request)
        assert service.start(project,request)==started
        core.worker.start()
        preflight = started['result']['preflight_id']
        result = wait_for(lambda:service.status(project,preflight))
        assert result['state']=='SUCCEEDED',result
        assert result['report']['assessment']=='USABLE',result
        from product.protocols.preparation.proof_sources import ProofPreflightReport
        report = ProofPreflightReport.model_validate_json(__import__('json').dumps(result['report']))
        with pytest.raises(JiejianError):
            service.jobs.publish(report.model_copy(update={'fencing_token':report.fencing_token+1}))
        with pytest.raises(JiejianError):
            service.jobs.publish(report.model_copy(update={'checks':report.checks[:1]}))
        assert service.status(project,preflight)==result
        assert service.show(project,source)['adopted'] is False
        assert core.preparation_guidance.context(project)['guidance']['sources'][0]['next_action']['kind']=='REVIEW_ADOPTION'
        with core.uow_factory() as work:
            assert work.action_preparation.evidence(harness.action.action_id,1,harness.effect_id) is None
        preview = service.adoption_preview(project,source,preflight)
        adoption_command = AdoptProofSource(operation_id=uuid4().hex,basis_id=preview['basis_id'],
            source_id=source,revision=1,preflight_id=preflight,confirmed=True)
        adopted = service.adopt(project,adoption_command)
        assert adopted['result']['state']=='ADOPTED'
        assert core.preparation_guidance.context(project)['guidance']['sources'][0]['state']=='USABLE'
        assert len(service.active_sources(project))==1
        assert core.check_registry.snapshot(project).proofs[0].reference.descriptor_id==source
        # 模拟写入已完成但前端未收到响应：回读原键和同键重试都不产生第二份采用。
        with core.uow_factory() as work:
            original_adoption = work.proof_sources.adoption(project,source)
        assert service.receipt(project,'ADOPT_SOURCE',adoption_command.operation_id)==adopted
        assert service.adopt(project,adoption_command)==adopted
        with core.uow_factory() as work:
            assert work.proof_sources.adoption(project,source)==original_adoption
        service.revoke_scope(project,RevokeProofScope(operation_id=uuid4().hex,scope_id=scope['result']['scope_id']))
        assert service.active_sources(project)==()
        assert service.status(project,preflight)==result
    finally:
        harness.close()


# 该模块启动真实 Node、Worker 与 Runner，不进入普通 L2。
pytestmark = [pytest.mark.process, pytest.mark.slow]
