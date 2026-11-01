from uuid import uuid4

import pytest

from product.backend.application.agent_access.capabilities import Capability, Empty
from product.backend.application.agent_access.tasks import CreateCollaboration, CollaborationAction, CollaborationQuestion
from product.backend.domain.errors import JiejianError
from tests.support.builders.preparation.action_preparation import build_preparation_harness


@pytest.fixture
def harness(tmp_path):
    value = build_preparation_harness(tmp_path)
    try:
        yield value
    finally:
        value.close()


def task(harness):
    return harness.core.collaboration.create(harness.project_id, CreateCollaboration(
        operation_id=uuid4().hex, goal='准备账号并核对工单权限', purpose='CHECK'))


def test_task_is_persistent_and_questions_resume_the_same_goal(harness):
    service, project = harness.core.collaboration, harness.project_id
    value = task(harness)
    question = CollaborationQuestion(question_id=uuid4().hex, question='成员是否可以修改其他成员的工单？', options=['允许', '禁止'])
    service.ask(project, value['task_id'], question)
    assert service.show(project, value['task_id'])['state'] == 'WAITING_USER'
    service.answer(project, value['task_id'], question.question_id, '禁止')
    with harness.core.uow_factory() as work:
        stored = work.collaboration.get(project, value['task_id'])
    assert stored['goal'] == value['goal']
    assert stored['questions'][0]['answer'] == '禁止'
    assert stored['state'] == 'WAITING_AGENT'


def test_native_write_waits_for_gui_and_repeated_request_returns_receipt(harness):
    calls = []
    capability = Capability('fixture.write', '写入虚构资源', '测试', 'EXECUTE', Empty,
        lambda p, a, o: calls.append(o) or {'resource_id':'ticket1'}, True)
    harness.core.agent_capabilities.items[capability.key] = capability
    service, project, value = harness.core.collaboration, harness.project_id, task(harness)
    command = CollaborationAction(operation_id=uuid4().hex, capability=capability.key)
    assert service.act(project, value['task_id'], command)['state'] == 'WAITING_USER'
    assert calls == []
    assert service.decide(project, value['task_id'], command.operation_id, True)['state'] == 'SUCCEEDED'
    assert service.act(project, value['task_id'], command)['result'] == {'resource_id':'ticket1'}
    assert calls == [command.operation_id]
    with pytest.raises(JiejianError): service.decide(project, value['task_id'], command.operation_id, False)


def test_unknown_write_is_not_replayed_and_can_only_be_reconciled(harness, monkeypatch):
    calls = []
    def disconnected(p, a, operation):
        calls.append(operation)
        raise OSError('fixture-connection-lost')
    harness.core.agent_capabilities.items['fixture.unknown'] = Capability('fixture.unknown', '保存结果', '测试', 'PREPARE', Empty, disconnected)
    service, project, value = harness.core.collaboration, harness.project_id, task(harness)
    command = CollaborationAction(operation_id=uuid4().hex, capability='fixture.unknown')
    with pytest.raises(JiejianError): service.act(project, value['task_id'], command)
    assert service.act(project, value['task_id'], command)['state'] == 'UNKNOWN'
    assert calls == [command.operation_id]
    monkeypatch.setattr(harness.core.agent_capabilities, 'receipt', lambda p, op: {'saved':True})
    assert service.reconcile(project, value['task_id'], command.operation_id)['result'] == {'saved':True}
    assert calls == [command.operation_id]


def test_capabilities_use_existing_identity_owner_and_reject_other_project(harness):
    service, project, value = harness.core.collaboration, harness.project_id, task(harness)
    existing = harness.core.test_identities.list(project)[0]
    result = service.act(project, value['task_id'], CollaborationAction(operation_id=uuid4().hex,
        capability='identities.options', arguments={'identity_id':existing.identity_id}))
    assert result['state'] == 'READ'
    with pytest.raises(JiejianError):
        service.act(project, value['task_id'], CollaborationAction(operation_id=uuid4().hex,
            capability='identities.options', arguments={'identity_id':'tid_'+'0'*32}))


def test_paused_task_rejects_new_work_and_secret_text_is_not_persisted(harness):
    service, project, value = harness.core.collaboration, harness.project_id, task(harness)
    service.control(project, value['task_id'], 'pause')
    with pytest.raises(JiejianError): service.ask(project, value['task_id'], CollaborationQuestion(question_id=uuid4().hex, question='继续吗'))
    with pytest.raises(JiejianError):
        service.create(project, CreateCollaboration(operation_id=uuid4().hex, goal='password=fixture-sensitive', purpose='CHECK'))
    assert len(service.list(project)) == 1


def test_answering_one_question_keeps_other_decisions_visible(harness):
    service, project, value = harness.core.collaboration, harness.project_id, task(harness)
    first = CollaborationQuestion(question_id=uuid4().hex, question='成员是否可查看？')
    second = CollaborationQuestion(question_id=uuid4().hex, question='成员是否可修改？')
    service.ask(project, value['task_id'], first)
    service.ask(project, value['task_id'], second)
    assert service.answer(project, value['task_id'], first.question_id, '允许')['state'] == 'WAITING_USER'
    service.control(project, value['task_id'], 'cancel')
    with pytest.raises(JiejianError): service.answer(project, value['task_id'], second.question_id, '禁止')


def test_execution_messages_cannot_revive_paused_task_or_replace_new_turn(harness):
    service, project, value = harness.core.collaboration, harness.project_id, task(harness)
    first, second = uuid4().hex, uuid4().hex
    service.execution_started(project, value['task_id'], dict(operation_id=first, state='RUNNING'))
    service.control(project, value['task_id'], 'pause')
    assert service.execution_progress(project, value['task_id'], first, state='FINISHED')['state'] == 'PAUSED'
    service.control(project, value['task_id'], 'resume')
    service.execution_started(project, value['task_id'], dict(operation_id=second, state='RUNNING'))
    current = service.execution_progress(project, value['task_id'], first, state='FAILED')
    assert current['execution'] == dict(operation_id=second, state='RUNNING')
    service.recover_executions()
    assert service.show(project, value['task_id'])['execution']['state'] == 'UNKNOWN'


def test_read_query_keeps_original_business_operation_independent_of_transport(harness):
    from product.backend.application.agent_access.capabilities import parameters
    original = uuid4().hex
    harness.core.agent_capabilities.items['fixture.receipt'] = Capability('fixture.receipt', '查询原请求', '测试', 'READ',
        parameters('OriginalRequest', operation_id=(str, ...)), lambda p, a, o: {'queried': a.operation_id})
    service, project, value = harness.core.collaboration, harness.project_id, task(harness)
    result = service.act(project, value['task_id'], CollaborationAction(operation_id=uuid4().hex,
        capability='fixture.receipt', arguments={'operation_id': original}))
    assert result['result'] == {'queried': original}
    assert service.show(project, value['task_id'])['operations'] == []


def test_finish_waits_for_agent_and_cancel_retries_only_native_cleanup(harness, monkeypatch):
    service, project, value = harness.core.collaboration, harness.project_id, task(harness)
    operation = uuid4().hex
    service.execution_started(project, value['task_id'], dict(operation_id=operation, state='RUNNING'))
    with pytest.raises(JiejianError):
        service.control(project, value['task_id'], 'finish')
    calls = []
    def interrupted_cleanup(p, operations):
        calls.append(p)
        if len(calls) == 1:
            raise OSError('fixture interrupted while closing owned job')
    monkeypatch.setattr(harness.core.agent_capabilities, 'cancel_owned', interrupted_cleanup)
    with pytest.raises(OSError):
        service.control(project, value['task_id'], 'cancel')
    assert service.show(project, value['task_id'])['state'] == 'CANCELLED'
    assert service.control(project, value['task_id'], 'cancel')['state'] == 'CANCELLED'
    assert calls == [project, project]


def test_unknown_persistent_task_format_is_rejected_without_rewriting(harness):
    import json
    from product.backend.infrastructure.storage.runtime.collaboration import CollaborationRow
    value = task(harness)
    with harness.core.uow_factory() as work:
        row = work.collaboration.session.get(CollaborationRow, value['task_id'])
        payload = json.loads(row.payload)
        payload['schema_version'] = 'unsupported'
        row.payload = json.dumps(payload)
        work.commit()
    with pytest.raises(JiejianError):
        harness.core.collaboration.show(harness.project_id, value['task_id'])
    with harness.core.uow_factory() as work:
        assert json.loads(work.collaboration.session.get(CollaborationRow, value['task_id']).payload)['schema_version'] == 'unsupported'


def test_global_entry_returns_only_current_summary_and_keeps_paused_work(harness):
    service, project = harness.core.collaboration, harness.project_id
    assert service.current(project) is None
    first = task(harness)
    service.control(project, first['task_id'], 'pause')
    second = task(harness)
    service.control(project, second['task_id'], 'finish')
    current = service.current(project)
    assert current['task_id'] == first['task_id']
    assert current['state'] == 'PAUSED'
    assert 'operations' not in current and 'events' not in current


def test_cancel_intent_also_closes_business_job_returning_after_cancel(harness, monkeypatch):
    service, project, value = harness.core.collaboration, harness.project_id, task(harness)
    cleanup = []
    monkeypatch.setattr(harness.core.agent_capabilities, 'cancel_owned',
        lambda p, operations: cleanup.extend(item['result'] for item in operations if item['result']))
    def delayed_receipt(p, a, operation):
        # 确定性插入“取消已保存、业务回执尚未返回”的窗口，不依赖线程计时。
        service.control(project, value['task_id'], 'cancel')
        return {'job_id': 'owned-late-job'}
    harness.core.agent_capabilities.items['fixture.delayed'] = Capability('fixture.delayed', '提交后台执行', '测试', 'PREPARE', Empty, delayed_receipt)
    result = service.act(project, value['task_id'], CollaborationAction(operation_id=uuid4().hex, capability='fixture.delayed'))
    assert result['state'] == 'SUCCEEDED'
    assert cleanup == [{'job_id': 'owned-late-job'}]
    assert service.show(project, value['task_id'])['state'] == 'CANCELLED'


def test_agent_can_locate_authorized_source_without_receiving_secret_references(harness, monkeypatch):
    owner = harness.core.application_understanding
    current = owner.get(harness.project_id)
    monkeypatch.setattr(owner, 'get', lambda p: current.model_copy(update={'source_analysis_authorized': False}))
    assert 'source_root' not in harness.core.agent_capabilities.read_application(harness.project_id)
    monkeypatch.setattr(owner, 'get', lambda p: current.model_copy(update={'source_analysis_authorized': True}))
    assert harness.core.agent_capabilities.read_application(harness.project_id)['source_root'] == str(current.source_root)
    assert harness.core.agent_capabilities.public({'source_root': 'selected-app', 'bearer_secret_ref': 'private', 'token': 'private'}) == {'source_root': 'selected-app'}


def test_portable_executor_uses_declared_client_without_host_path(tmp_path,monkeypatch):
    from product.backend.application.agent_access import execution
    installed=tmp_path/'codex.exe';installed.write_bytes(b'fixture')
    monkeypatch.setenv('JIEJIAN_CODEX_EXECUTABLE',str(installed))
    monkeypatch.setattr(execution.shutil,'which',lambda _:None)
    assert execution._codex_executable()==str(installed)
    installed.unlink()
    assert execution._codex_executable() is None


def test_read_only_executor_can_read_results_but_cannot_request_source_writes(harness, monkeypatch):
    from types import SimpleNamespace
    from product.backend.application.agent_access import execution
    from product.backend.application.agent_access.service import MCPAccessLevel
    monkeypatch.setattr(execution.shutil,'which',lambda _: 'installed-codex')
    current=harness.core.application_understanding.get(harness.project_id)
    monkeypatch.setattr(harness.core.application_understanding,'get',lambda _:current.model_copy(update={'source_analysis_authorized':True}))
    access=SimpleNamespace(view=lambda:SimpleNamespace(paired=True),level_for=lambda _:MCPAccessLevel.READ)
    calls=[]
    def runner(**arguments):
        calls.append(arguments)
        return dict(state='FINISHED',session_id='read-only-session')
    executor=execution.AgentExecution(harness.core,access,SimpleNamespace(prepare_managed_profile=lambda _: 'protected-profile'),runner=runner)
    value=task(harness)
    assert executor.capabilities(harness.project_id)['read_only'] is True
    with pytest.raises(JiejianError,match='当前协作为只读'):
        executor.start(harness.project_id,value['task_id'],execution.StartAgent(operation_id=uuid4().hex,allow_changes=True))
    executor.start(harness.project_id,value['task_id'],execution.StartAgent(operation_id=uuid4().hex))
    executor.close()
    assert len(calls)==1 and calls[0]['allow_changes'] is False


def test_local_executor_does_not_read_project_before_source_authorization(harness, monkeypatch):
    from types import SimpleNamespace
    from product.backend.application.agent_access import execution
    from product.backend.application.agent_access.service import MCPAccessLevel
    current = harness.core.application_understanding.get(harness.project_id)
    monkeypatch.setattr(harness.core.application_understanding, 'get', lambda p: current.model_copy(update={'source_analysis_authorized':False}))
    monkeypatch.setattr(execution.shutil, 'which', lambda name: 'installed-codex')
    access = SimpleNamespace(view=lambda:SimpleNamespace(paired=True), level_for=lambda p:MCPAccessLevel.PREPARE)
    executor = execution.AgentExecution(harness.core, access, None)
    value = task(harness)
    assert executor.capabilities(harness.project_id)['setup_path'] == '/application'
    with pytest.raises(JiejianError, match='先明确允许读取'):
        executor.start(harness.project_id, value['task_id'], execution.StartAgent(operation_id=uuid4().hex))
    assert executor.active == {}
