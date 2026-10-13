# 动态创建的回归场景：真实独立存储、请求归因、创建后删除、并发与响应冒用旧编号。
import json
from types import SimpleNamespace
import pytest
from product.backend.infra.observers.records.transaction_store import TransactionRecordStore, RecordStoreError
from product.backend.infra.observers.checks import creation_evidence
from product.backend.infra.execution.web.adapter import HttpResponse
from product.backend.core.verification.checks import CheckDecisionInput, evaluate_check_case, project_check_effect_facts
from product.backend.core.lifecycle import CaseVerdict
from product.protocols.runtime.transaction_records import RecordSeed
from product.protocols.runtime.creation_records import ScopedRecordSeed, RecordRemove
from product.protocols.web.response import ResponseExtractor, ResponseExtractorKind
from product.protocols.checks.check_result import check_request_marker
from tests.fixtures.checks.check_execution import execution_pair


@pytest.fixture
def creation_case(tmp_path, monkeypatch):
    store=TransactionRecordStore(tmp_path/'records.journal')
    request,bundle=execution_pair(state_changing=True)
    case=next(case for case in request.actions[0].cases if case.permission.expectation=='DENY')
    requirement=case.proof_requirements[0]
    proof=bundle.actions[0].proofs[0]
    action=SimpleNamespace(action_id=bundle.actions[0].action_id,created_resource=ResponseExtractor(
        extractor_id='created_resource_id',kind=ResponseExtractorKind.JSON_PATH,json_path='$.id'))
    source=SimpleNamespace(source_id='psr_'+'1'*32,revision=1,source_fingerprint='2'*64,
        config=SimpleNamespace(collection='objects'))
    claims={case.resource_owner_test_identity_id:SimpleNamespace(application_subject_id='owner')}
    state={'request':None,'response':None}
    web=SimpleNamespace(target_request=lambda _case:state['request'],target_response=lambda _case:state['response'],
        request_marker=lambda _case:check_request_marker('run_'+'1'*32,'job_'+'2'*32,1,case.case_id))
    owner=SimpleNamespace(web=web,bundle=SimpleNamespace(actions=(action,),runtime_reference=None),var_dir=tmp_path,
        cancelled=lambda:False,clock=lambda:101,_creation_histories={},_evidence_sources={})
    monkeypatch.setattr(creation_evidence,'read_record_source',lambda _var,_runtime,config,_id,request_nonce=None,**_kwargs:
        store.creation_view(config.collection,request_nonce))
    store.seed(RecordSeed(collection='objects',resource_id=case.resource_id,owner_id='owner',data={'title':'existing'}))
    def observe(phase):
        return creation_evidence.observe_creation(owner,source=source,case=case,action_id=action.action_id,
            requirement=requirement,proof=proof,phase=phase,cleanup=False,claims=claims,
            common=dict(effect_id=requirement.effect_id,proof_fingerprint=requirement.proof_fingerprint,
                observer_id=proof.observer_id,level=requirement.level,phase=phase,window_start_us=100))
    baseline=observe('BASELINE')
    assert baseline.baseline_projection is not None
    scope=store.open_scope('a'*64,'b'*64)
    state['request']=(scope.request_nonce,scope.request_digest)
    try:yield SimpleNamespace(store=store,scope=scope,state=state,observe=observe,owner=owner,case=case,baseline=baseline)
    finally:store.close()


def create(fixture, identifier, scope=None):
    scope=scope or fixture.scope
    return fixture.store.seed(ScopedRecordSeed(collection='objects',resource_id=identifier,owner_id='owner',
        data={'title':'new'},scope_id=scope.scope_id))


def test_403_and_delete_do_not_erase_confirmed_creation(creation_case):
    f=creation_case
    create(f,'actual-new')
    f.store.remove(RecordRemove(collection='objects',resource_id='actual-new',scope_id=f.scope.scope_id,expected_version=0))
    f.store.close_scope(f.scope.scope_id,True)
    f.state['response']=HttpResponse(403,{},body=b'{}')
    observation=f.observe('AFTER').observation
    assert observation.state=='CONFIRMED'
    decision=evaluate_check_case(CheckDecisionInput(case=f.case,execution='DENIED',actual_identity='MATCH',
        run_correlated=True,resource_correlated=True,baseline_trusted=True,recovery_verified=False,
        effects=project_check_effect_facts(f.case,(observation,))))
    assert decision.verdict is CaseVerdict.VULNERABLE
    facts,_=f.owner._evidence_sources[observation.model_dump_json()]
    assert [fact.data.resource_id for fact in facts if fact.data.kind=='OBJECT_CREATION']==['actual-new']


@pytest.mark.parametrize('complete, expected',[(True,'ABSENT'),(False,'UNKNOWN')])
def test_no_created_object_requires_closed_independent_window(creation_case,complete,expected):
    f=creation_case
    f.store.close_scope(f.scope.scope_id,complete)
    assert f.observe('AFTER').observation.state==expected


def test_response_cannot_substitute_previous_recording_object(creation_case):
    f=creation_case
    create(f,'actual-new')
    f.store.close_scope(f.scope.scope_id,True)
    f.state['response']=HttpResponse(201,{'id':f.case.resource_id},body=json.dumps({'id':f.case.resource_id}).encode())
    observed=f.observe('AFTER')
    _,reference=f.owner._evidence_sources[observed.observation.model_dump_json()]
    assert not reference.creation_window.response_matched
    assert observed.observation.state=='CONFIRMED'
    assert f.store.read('objects',f.case.resource_id).data=={'title':'existing'}


def test_parallel_create_does_not_belong_to_target_and_blocks_absence(creation_case):
    f=creation_case
    concurrent=f.store.open_scope('c'*64,'d'*64)
    create(f,'foreign-new',concurrent)
    f.store.close_scope(concurrent.scope_id,True)
    f.store.close_scope(f.scope.scope_id,True)
    assert f.observe('AFTER').observation.state=='UNKNOWN'


def test_deleted_identifier_cannot_be_reused_by_later_create(creation_case):
    f=creation_case
    create(f,'first-new')
    f.store.remove(RecordRemove(collection='objects',resource_id='first-new',scope_id=f.scope.scope_id,expected_version=0))
    with pytest.raises(RecordStoreError,match='RECORD_RESOURCE_ID_REUSED'):
        create(f,'first-new')
    create(f,'second-new')
    f.store.close_scope(f.scope.scope_id,True)
    view=f.store.creation_view('objects',f.scope.request_nonce)
    assert [event.member.resource_id for event in view.events if event.kind=='CREATE']==['first-new','second-new']
