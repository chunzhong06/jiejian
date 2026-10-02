# 实机验证加载Job结束后应用仍运行，控制面退出回收拥有树，旧会话请求不重放。
from functools import partial
import os
import socket
import time

import httpx
import pytest

from product.backend.core.lifecycle import JobState, ProjectStatus
from product.backend.infra.runtime.process.node_owned import node_reference_matches
from product.backend.infra.runtime.worker.runtime_supervisor import LocalRuntimeSupervisor
from product.backend.infra.storage import (ProjectRecord,StorageUnitOfWork,create_session_factory,
    create_sqlite_engine,default_database_path,upgrade_database)
from product.backend.workflows.runtime_load_jobs import RuntimeLoadJobs
from tests.fixtures.node_runtime import node_runtime_input
from tests.fixtures.runtime_environment import runtime_identity_environment

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Windows runtime ownership boundary')


def _setup(tmp_path):
    var=tmp_path/'var';var.mkdir()
    upgrade_database(default_database_path(var))
    engine=create_sqlite_engine(default_database_path(var))
    factory=partial(StorageUnitOfWork,create_session_factory(engine))
    with factory() as work:
        work.projects.add(ProjectRecord(project_id='owned-node-project',name='运行监督测试',
            status=ProjectStatus.READY,created_at_us=1,updated_at_us=1));work.commit()
    return var,engine,factory


def _port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def test_successful_load_keeps_target_alive_until_owned_supervisor_stops(tmp_path):
    var,engine,factory=_setup(tmp_path)
    holder={}
    supervisor=LocalRuntimeSupervisor(var,factory,node_executable_provider=lambda:holder['node'],
        environment_provider=lambda:runtime_identity_environment(var))
    node,_,request=node_runtime_input(tmp_path,_port(),control_session_id=supervisor.control_session_id)
    holder['node']=node
    service=RuntimeLoadJobs(factory);submitted=service.submit(request)
    try:
        supervisor.start()
        deadline=time.monotonic()+20
        result=None
        while time.monotonic()<deadline:
            result=service.operation(request.project_id,request.operation_id)
            if result['job'].state in {JobState.SUCCEEDED,JobState.FAILED,JobState.CANCELLED}: break
            time.sleep(.05)
        assert result['job'].state is JobState.SUCCEEDED, result['job']
        reference=result['receipt'].reference
        assert node_reference_matches(var,request,reference,node)
        with httpx.Client(trust_env=False) as client:
            assert client.get(f'http://127.0.0.1:{reference.port}').text=='frozen source'
        supervisor.stop()
        assert not node_reference_matches(var,request,reference,node)
        # 已发布的是启动事实，关闭进程不改写这条历史回执。
        assert service.operation(request.project_id,request.operation_id)['receipt']==result['receipt']
        with factory() as work: assert work.runs.list_for_project(request.project_id)==()
    finally:
        supervisor.stop();engine.dispose()


def test_prior_control_session_pending_request_is_closed_without_start(tmp_path):
    var,engine,factory=_setup(tmp_path)
    node,artifact,request=node_runtime_input(tmp_path,_port())
    service=RuntimeLoadJobs(factory);service.submit(request)
    supervisor=LocalRuntimeSupervisor(var,factory,node_executable_provider=lambda:node,
        environment_provider=lambda:runtime_identity_environment(var))
    try:
        supervisor.tick()
        result=service.operation(request.project_id,request.operation_id)
        assert result['job'].state is JobState.FAILED
        assert result['receipt'] is None
        assert not (artifact/'start.gate').exists()
        with factory() as work:
            assert work.job_events.list_for_job(result['job'].job_id)[-1].metadata['error_code']=='RUNTIME_SESSION_EXPIRED'
    finally:
        supervisor.stop();engine.dispose()
