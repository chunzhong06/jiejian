# 验证唯一官方数字展馆的真实业务、受控运行、资源恢复和秘密边界。
from pathlib import Path
from uuid import uuid4
import io
import zipfile
import httpx
import pytest
from product.backend.composition import ApplicationCore
from product.backend.core.errors import JiejianError
from tests.fixtures.preparation.action_preparation import MemorySecretStore
from tests.fixtures.runtime.runtime_environment import runtime_identity_environment

ROOT=Path(__file__).resolve().parents[3]
SAMPLE=ROOT/'samples/web/digital_gallery'


@pytest.mark.process
@pytest.mark.slow
def test_node_sample_start_human_choice_real_assets_and_exit(tmp_path):
    var=tmp_path/'var'
    core=ApplicationCore(var,official_sample_root=SAMPLE,secret_store=MemorySecretStore(),environ=runtime_identity_environment(var))
    try:
        key=str(uuid4());started=core.official_experience.start(consent=True,operation_id=key)
        assert started.active and started.runtime_kind=='NODE_ESM'
        project=started.project_id
        assert core.official_experience.start(consent=True,operation_id=key).project_id==project
        revision=core.application_understanding.get(project).revision
        core.official_experience.reconcile()
        assert core.application_understanding.get(project).revision==revision
        source=Path(core.application_understanding.get(project).source_root)
        assert source != SAMPLE/'source' and source.is_relative_to(var.resolve())
        assert not list(source.glob('*.zip')) and not list(source.glob('*.pdf'))
        reference=core.node_runtime.reference(project)
        assert core.runtime_ports.reference(project)==reference
        with pytest.raises(JiejianError):core.official_experience.boundary_proposal()
        proposed=core.official_experience.boundary_proposal(exhibition_download=False)
        permissions=proposed.proposal.proposed_permissions
        assert len(permissions)==5
        with httpx.Client(base_url=started.origin,trust_env=False) as target:
            assert target.get('/health').status_code==200
            assert target.get('/api/galleries/campus').status_code==401
            assert target.post('/api/login',json={'account':'curator'}).status_code==200
            assert target.get('/api/galleries/campus').status_code==404
            assert target.post('/api/galleries').status_code==201
            assert target.post('/api/galleries/unknown/internal').status_code==404
            nonce=uuid4().hex+uuid4().hex
            response=target.post('/api/galleries/campus/internal',headers={'X-Jiejian-Request-Nonce':nonce})
            assert response.status_code==200
            assert 'internal-notes.txt' in zipfile.ZipFile(io.BytesIO(response.content)).namelist()
            # 穿过真实 Node 写入回执和只读来源端口，核对协议版本与实际父引用。
            from product.backend.infra.observers.records.record_source import record_provider
            from product.backend.infra.runtime.process.records.record_capabilities import read_record_capability
            from product.protocols.runtime.record_trace import RecordTraceLog
            provider=record_provider(var,reference)
            trace_response=httpx.get(f'http://127.0.0.1:{provider.port}/trace/read/galleries/campus/{nonce}',
                headers={'Authorization':'Bearer '+read_record_capability(var,reference.instance_id)},trust_env=False)
            assert trace_response.status_code==200
            log=RecordTraceLog.model_validate_json(__import__('json').dumps(trace_response.json()['data']))
            assert log.scope_state=='COMPLETE' and log.events[-1].semantic_key=='response_prepared'
            assert [event.kind for event in log.events]==['ENTRY','IDENTITY','AUTHORIZATION','PERSISTENT_EFFECT','MESSAGE']
            assert all(event.parent_event_id==previous.event_id for previous,event in zip(log.events,log.events[1:]))
            assert target.post('/api/login',json={'account':'judge'}).status_code==200
            assert target.post('/api/galleries/campus/internal').status_code==403
            assert target.get('/api/galleries/campus/internal-file').status_code==403
            assert target.post('/api/galleries/campus/withdraw').status_code==403
            assert target.post('/api/galleries').status_code==403
            assert target.get('/api/galleries/campus/preview').json()['data']['title']=='校园数字展馆'
            assert target.get('/api/galleries/campus/exhibition').content.startswith(b'%PDF-1.4')
            assert target.post('/api/login',json={'account':'curator'}).status_code==200
            assert target.post('/api/galleries/campus/withdraw').status_code==200
            assert target.get('/api/galleries/campus/internal-file').status_code==200
            secrets=[cookie.value.encode() for cookie in target.cookies.jar]
            for path in var.rglob('*'):
                if path.is_file() and path.suffix in {'.json','.jsonl','.mjs','.log'}:
                    assert not any(secret in path.read_bytes() for secret in secrets),path
        stopped=core.official_experience.stop(operation_id=str(uuid4()))
        assert not stopped.active and stopped.recovery_state=='EXITED'
        assert core.check_results.history(project).items==()
        restarted=core.official_experience.start(consent=True,operation_id=str(uuid4()))
        assert restarted.project_id!=project and restarted.active
        replay=core.official_experience.start(consent=True,operation_id=key)
        assert replay.project_id==project and not replay.active and replay.origin is None
        assert replay.scenario_version is None
        core.official_experience.stop()
    finally:core.close()
