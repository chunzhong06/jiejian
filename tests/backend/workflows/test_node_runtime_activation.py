# 两批真实Node交付通过同一持久加载Job接续；回执事务失败不留下可被Worker领取的任务。
import socket
import time
from uuid import uuid4

import pytest
from sqlalchemy import func,select

from product.backend.composition import ApplicationCore
from product.backend.infra.storage.development import DevelopmentRepository
from product.backend.infra.storage.runtime_loads import RuntimeLoadRow
from tests.fixtures.action_preparation import build_preparation_harness,MemorySecretStore
from tests.fixtures.runtime_environment import runtime_identity_environment


def _wait(runtime,project,key):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        value=runtime.operation(project,key)
        if value['state'] in {'SUCCEEDED','FAILED','CANCELLED'}:
            assert value['state']=='SUCCEEDED',value
            return value
        time.sleep(.05)
    pytest.fail('runtime load did not finish')


def test_two_node_deliveries_and_atomic_runtime_receipt(tmp_path,monkeypatch):
    var=tmp_path/'var'
    core=ApplicationCore(var,secret_store=MemorySecretStore(),environ=runtime_identity_environment(var))
    harness=build_preparation_harness(tmp_path,core=core)
    project=harness.project_id
    # 替换测试自建目录中的Python占位源码，以生产扫描和受控Node链核对真实修改。
    (harness.source_root/'routes.py').unlink()
    entry=harness.source_root/'app.mjs'
    source="import http from 'node:http'; http.createServer((q,r)=>r.end('VERSION')).listen(Number(process.env.PORT),'127.0.0.1');"
    entry.write_text(source.replace('VERSION','start'),encoding='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    try:
        understanding=core.application_understanding.get(project)
        core.application_understanding.analyze_source_for_change(project,revision=understanding.revision)
        understanding=core.application_understanding.get(project)
        preview=core.node_runtime.preview(project,entry='app.mjs',port=port,revision=understanding.revision)
        key=uuid4().hex
        core.node_runtime.start(project,entry=preview.entry,port=port,revision=preview.revision,
            preview_fingerprint=preview.preview_fingerprint,operation_id=key,consent_execute=True)
        core.runtime_worker.start();first=_wait(core.node_runtime,project,key)
        task=core.development.create(project,operation_id=uuid4().hex,title='调整页面说明',goal='保持权限规则')
        accepted=core.development.accept(project,task.task_id,operation_id=uuid4().hex,
            expected_version=task.task_version,context_id=task.context_id,client_name='test')
        previous_instance=first['instance_id']
        for index in (1,2):
            entry.write_text(source.replace('VERSION',f'change-{index}'),encoding='utf-8')
            active=core.development.view(project,task.task_id)
            delivered=core.development.deliver(project,task.task_id,operation_id=uuid4().hex,
                expected_version=active['task']['version'],context_id=accepted.context_id,reason=f'修改{index}',submitted_by='test')
            active=core.development.view(project,task.task_id)
            operation_id=uuid4().hex
            arguments=dict(operation_id=operation_id,expected_version=active['task']['version'])
            if index==1:
                original=DevelopmentRepository.add_receipt
                def fail_receipt(self,value):
                    if value.kind=='LOAD_RUNTIME':raise OSError('injected receipt failure')
                    return original(self,value)
                monkeypatch.setattr(DevelopmentRepository,'add_receipt',fail_receipt)
                with pytest.raises(OSError):core.runtime_activation.activate(project,delivered.delivery_id,**arguments)
                with core.uow_factory() as work:
                    assert work.runtime_loads.operation(project,operation_id) is None
                    assert work.development.runtime_receipt(project,operation_id) is None
                monkeypatch.setattr(DevelopmentRepository,'add_receipt',original)
            pending=core.runtime_activation.activate(project,delivered.delivery_id,**arguments)
            assert pending.schema_version=='2' and pending.status=='PENDING'
            loaded=_wait(core.node_runtime,project,operation_id)
            completed=core.runtime_activation.receipt(project,operation_id)
            assert completed.status=='SUCCEEDED'
            assert loaded['instance_id']!=previous_instance
            assert completed.runtime_reference==core.runtime_ports.reference(project)
            assert core.runtime_activation.activate(project,delivered.delivery_id,**arguments)==completed
            assert core.development.view(project,task.task_id)['runtime_state']=='MATCHED'
            previous_instance=loaded['instance_id']
        # 只有初始加载和两批交付，不会因查询、失败回滚或幂等重放多启动一批。
        with core.uow_factory() as work:
            assert work._session.scalar(select(func.count()).select_from(RuntimeLoadRow))==3
    finally:
        core.close()
