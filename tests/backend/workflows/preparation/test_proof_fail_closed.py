# 验证准备的修订、授权、重启与原回执边界；无效预检查不能变成采用或权限通过。
from uuid import uuid4
import pytest
from product.backend.core.errors import JiejianError
from product.backend.workflows.preparation.proof_commands import (
    SaveProofSource,GrantProofScope,StartProofPreflight,AdoptProofSource,CancelProofPreflight,
)
from tests.fixtures.managed_records import ordinary_application,source_configuration,wait_for,refresh_ordinary_sessions


def test_revision_session_and_authority_changes_invalidate_only_dependent_preparation(tmp_path):
    harness=ordinary_application(tmp_path)
    core,project,service=harness.core,harness.project_id,harness.core.proof_preparation
    try:
        basis=service.context(project)['basis_id']
        config=source_configuration(harness)
        command=SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=config)
        saved=service.save(project,command)
        source=saved['result']['source_id']
        with pytest.raises(JiejianError,match='另一份输入'):
            service.save(project,command.model_copy(update={'config':config.model_copy(update={'timeout_us':config.timeout_us-1})}))
        assert service.receipt(project,'SAVE_SOURCE',command.operation_id)==saved
        common=dict(source_id=source,revision=1,basis_id=basis)
        service.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,confirmed=True,**common))
        # 旧控制会话、撤销的MCP授权均在执行前被取消；重新授权不复活旧Job。
        for reason in ('restart','revoke','cancel'):
            service.authority_active=lambda _project,authority:authority in {'LOCAL_GUI','test-authority'}
            queued=service.start(project,StartProofPreflight(operation_id=uuid4().hex,**common),authority_id='test-authority')['result']
            if reason=='restart':service.control_session_id='pcs_'+uuid4().hex
            elif reason=='revoke':service.authority_active=lambda _project,authority:authority=='LOCAL_GUI'
            else:
                cancel=CancelProofPreflight(operation_id=uuid4().hex,preflight_id=queued['preflight_id'])
                assert service.cancel(project,cancel)==service.cancel(project,cancel)
            service.cancel_unauthorized()
            assert service.status(project,queued['preflight_id'])['state']=='CANCELLED'
        queued=service.start(project,StartProofPreflight(operation_id=uuid4().hex,**common))['result']
        core.worker.start()
        result=wait_for(lambda:service.status(project,queued['preflight_id']))
        assert result['report']['assessment']=='USABLE'
        refresh_ordinary_sessions(harness)
        assert service.context(project)['basis_id']!=basis
        with pytest.raises(JiejianError):
            service.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['preflight_id'],confirmed=True,**common))
        assert service.show(project,source)['adopted'] is False
        # 同来源错误字段得到可定位缺口；修正只增加来源修订，已授读取范围沿用。
        basis=service.context(project)['basis_id']
        wrong=config.model_copy(update={'mappings':dict(config.mappings,state=('data','missing_state'))})
        revised=SaveProofSource(operation_id=uuid4().hex,basis_id=basis,source_id=source,expected_revision=1,config=wrong)
        service.save(project,revised)
        with pytest.raises(JiejianError):service.save(project,revised.model_copy(update={'operation_id':uuid4().hex}))
        started=service.start(project,StartProofPreflight(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=2))['result']
        report=wait_for(lambda:service.status(project,started['preflight_id']))
        assert report['report']['assessment']!='USABLE'
        assert any(item['mapping_key']=='state' for item in report['report']['checks'])
        with pytest.raises(JiejianError):service.adoption_preview(project,source,started['preflight_id'])
        service.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,source_id=source,expected_revision=2,config=config))
        started=service.start(project,StartProofPreflight(operation_id=uuid4().hex,basis_id=basis,source_id=source,revision=3))['result']
        assert wait_for(lambda:service.status(project,started['preflight_id']))['report']['assessment']=='USABLE'
        assert len(service.context(project)['read_scopes'])==1
        assert service.status(project,queued['preflight_id'])==result
    finally:harness.close()


# 该模块启动真实 Node、Worker 与 Runner，不进入普通 L2。
pytestmark = [pytest.mark.process, pytest.mark.slow]
