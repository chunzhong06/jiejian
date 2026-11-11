"""工单适配使用内存HTTP传输；重点验证未知结果不重发及人工审阅的准确正文。"""
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from product.backend.application.agent_access.github_issues import IssueSource,IssueDelivery
from product.backend.application.agent_access.tasks import CreateCollaboration,CollaborationAction
from product.backend.domain.errors import JiejianError
from product.backend.infrastructure.integrations.github import GitHubIssues
from product.backend.infrastructure.secrets.refs import credential_ref
from tests.support.builders.preparation.action_preparation import build_preparation_harness


@pytest.fixture
def harness(tmp_path,monkeypatch):
    value=build_preparation_harness(tmp_path)
    item=SimpleNamespace(case_id='case_'+'a'*32,display_name='读取工单',judgement='已发现规则禁止的实际结果')
    monkeypatch.setattr(value.core.github_issues.stories,'build',lambda *args,**kwargs:SimpleNamespace(actions=[item]))
    value.core.secret_store.write(credential_ref('github','fixture'),'private-fixture-value')
    try:yield value
    finally:value.close()


def command(harness):
    service=harness.core.github_issues
    source=IssueSource(run_id='run_'+'1'*32,case_id='case_'+'a'*32)
    draft=service.draft(harness.project_id,source)
    return CollaborationAction(operation_id=uuid4().hex,capability='github.issue_create',arguments={
        **source.model_dump(),'repository':'fixture/testing','credential_profile':'fixture',
        'expected_draft_fingerprint':draft['draft_fingerprint']})


def task(harness):
    return harness.core.collaboration.create(harness.project_id,CreateCollaboration(
        operation_id=uuid4().hex,goal='核对这张测试工单',purpose='UNDERSTAND'))['task_id']


def test_unknown_send_can_only_reconcile_original_issue_and_cross_task_replay_is_rejected(harness):
    requests=[]
    posted={}
    def transport(request):
        requests.append(request.method)
        if request.method=='POST':
            posted.update(json.loads(request.content))
            raise httpx.ReadTimeout('fixture-disconnected')
        return httpx.Response(200,json=[{'number':12,'html_url':'https://github.com/fixture/testing/issues/12',
            'body':posted['body'],'state':'closed'}])
    harness.core.github_issues.adapter=GitHubIssues(transport=httpx.MockTransport(transport))
    service,project=harness.core.collaboration,harness.project_id
    identity=task(harness);action=command(harness)
    pending=service.act(project,identity,action)
    assert pending['state']=='WAITING_USER' and not requests
    assert any('将发送的正文'==row['label'] for row in pending['summary'])
    with pytest.raises(JiejianError):service.decide(project,identity,action.operation_id,True)
    assert service.act(project,identity,action)['state']=='UNKNOWN'
    assert requests==['POST']
    result=service.reconcile(project,identity,action.operation_id)
    assert result['state']=='SUCCEEDED' and result['result']['number']==12
    assert result['result']['remote_state']=='closed'
    assert requests==['POST','GET']
    with pytest.raises(JiejianError):service.act(project,task(harness),action)
    with harness.core.uow_factory() as work:stored=work.collaboration.get(project,identity)
    assert 'private-fixture-value' not in json.dumps(stored)


def test_no_matching_association_remains_unknown_without_second_post(harness):
    requests=[]
    def transport(request):
        requests.append(request.method)
        if request.method=='POST':return httpx.Response(503,json={'message':'fixture'})
        return httpx.Response(200,json=[])
    harness.core.github_issues.adapter=GitHubIssues(transport=httpx.MockTransport(transport))
    service,project=harness.core.collaboration,harness.project_id
    identity=task(harness);action=command(harness)
    service.act(project,identity,action)
    with pytest.raises(JiejianError):service.decide(project,identity,action.operation_id,True)
    assert service.reconcile(project,identity,action.operation_id)['state']=='UNKNOWN'
    assert service.act(project,identity,action)['state']=='UNKNOWN'
    assert requests==['POST','GET']


def test_changed_draft_or_unsafe_repository_never_reaches_transport(harness):
    action=command(harness)
    changed=IssueDelivery.model_validate({**action.arguments,'expected_draft_fingerprint':'0'*64})
    with pytest.raises(JiejianError):harness.core.github_issues.describe(harness.project_id,changed)
    with pytest.raises(ValidationError):IssueDelivery.model_validate({**action.arguments,'repository':'fixture/..'})


def test_remote_metadata_cannot_forge_an_external_url():
    with pytest.raises(RuntimeError):GitHubIssues.receipt('fixture/testing',{
        'number':12,'body':'exact-marker','html_url':'https://other.invalid/12'},'exact-marker')


@pytest.mark.parametrize('status',[403,429])
def test_permission_or_rate_limit_rejection_keeps_original_failed_operation(harness,status):
    """已知拒绝保留原操作；重复确认不能再次发出创建请求或保存上游正文。"""
    requests=[]
    def transport(request):
        requests.append(request.method)
        return httpx.Response(status,json={'message':'private-upstream-canary'})
    harness.core.github_issues.adapter=GitHubIssues(transport=httpx.MockTransport(transport))
    service,project=harness.core.collaboration,harness.project_id
    identity=task(harness);action=command(harness)
    assert service.act(project,identity,action)['state']=='WAITING_USER'
    with pytest.raises(JiejianError) as rejected:
        service.decide(project,identity,action.operation_id,True)
    assert rejected.value.to_dict()['details']=={'upstream_status':status,'request_outcome':'NOT_ACCEPTED'}
    assert service.decide(project,identity,action.operation_id,True)['state']=='FAILED'
    assert service.reconcile(project,identity,action.operation_id)['state']=='FAILED'
    assert requests==['POST']
    with harness.core.uow_factory() as work:stored=work.collaboration.get(project,identity)
    assert 'private-upstream-canary' not in json.dumps(stored)


def test_declined_issue_delivery_never_reaches_github(harness):
    requests=[]
    def transport(request):
        requests.append(request.method)
        raise AssertionError('撤回的工单不应访问GitHub')
    harness.core.github_issues.adapter=GitHubIssues(transport=httpx.MockTransport(transport))
    service,project=harness.core.collaboration,harness.project_id
    identity=task(harness);action=command(harness)
    assert service.act(project,identity,action)['state']=='WAITING_USER'
    assert service.decide(project,identity,action.operation_id,False)['state']=='DECLINED'
    assert service.act(project,identity,action)['state']=='DECLINED'
    assert service.decide(project,identity,action.operation_id,True)['state']=='DECLINED'
    assert requests==[]
