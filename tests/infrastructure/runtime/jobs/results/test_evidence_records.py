# 固定证据阅读模板覆盖真实封存值、未知原因及旧记录；投影期间禁止重新裁决或目标I/O。
from dataclasses import replace
import json
import pytest
from product.backend.domain.lifecycle import CaseVerdict
from product.backend.domain.errors import JiejianError
from product.backend.infrastructure.artifacts.checks.check_packages import validate_check_package
from product.backend.application.checks.reading.records import record_index, record_view
from product.protocols.checks.business_facts import seal_business_fact, FactProofReference, CommittedStateFact, CommittedFieldChange, ObservationFactReference, RecordObservationWindow
from product.protocols.checks.check_result import CheckObservation, seal_check_evidence, check_request_marker
from tests.support.builders.checks.check_publication import package_parts


def detailed_package(parts,verdict='VULNERABLE',reasons=('ORPHAN_EFFECT_CONFIRMED',)):
    _,_,_,directory,_=parts
    package=validate_check_package(directory,published=False)
    original=next(document for document in package.evidence if document.case.permission.expectation=='DENY')
    case=original.case;proof=case.proof_requirements[0]
    reference=FactProofReference(effect_id=proof.effect_id,proof_fingerprint=proof.proof_fingerprint,source_id='psr_'+'1'*32,source_revision=1,source_fingerprint='a'*64)
    fact=seal_business_fact(case_id=case.case_id,request_ref=check_request_marker(original.run_id,original.job_id,original.attempt,case.case_id),
        observed_at_us=10,collector_kind='CONTROLLED_RECORDS',proofs=(reference,),complete=True,
        data=CommittedStateFact(generation='g',operation_id='commit-1',scope_ordinal=0,before_version=0,after_version=1,
            subject_identity_id=case.subject_test_identity_id,owner_identity_id=case.resource_owner_test_identity_id,resource_id=case.resource_id,
            changes=(CommittedFieldChange(proof_fingerprint=proof.proof_fingerprint,path=('state',),before='private',after='public'),)))
    observation=CheckObservation(effect_id=proof.effect_id,proof_fingerprint=proof.proof_fingerprint,observer_id='source',level='VERDICT_REQUIRED',
        phase='AFTER',state='CONFIRMED',closure='CLOSED',complete=True,reliable=True,correlated=True,authoritative=True,window_start_us=9,window_end_us=11)
    ref=ObservationFactReference(proof_fingerprint=proof.proof_fingerprint,observer_id='source',phase='AFTER',fact_ids=(fact.fact_id,),source=reference,
        method='ATOMIC_STATE',complete=True,record_window=RecordObservationWindow(generation='g',before_version=0,after_version=1,before_value='private',after_value='public',
            scope_state='COMPLETE',operation_count=1,request_matched=True,source_complete=True,field_path=('state',)))
    document=seal_check_evidence(**original.model_dump(exclude={'schema_version','evidence_id','observations','case','outcome','trace','business_facts','fact_references'}),
        case=case,outcome=original.outcome,observations=(observation,),business_facts=(fact,),fact_references=(ref,))
    results=tuple(result.model_copy(update={'evidence_ids':(document.evidence_id,),'verdict':CaseVerdict(verdict),'reason_codes':reasons}) if result.case_id==case.case_id else result for result in package.result.case_results)
    return replace(package,evidence=(document,),result=package.result.model_copy(update={'case_results':results})),document


@pytest.mark.parametrize('verdict,reasons,word',[('VULNERABLE',('ORPHAN_EFFECT_CONFIRMED',),'禁止'),('SAFE',(),'符合'),
    ('INCONCLUSIVE',('ACTUAL_IDENTITY_UNKNOWN',),'无法'),('INCONCLUSIVE',('FUTURE_REASON',),'无法')])
def test_detailed_record_reads_exact_values_and_published_reason(package_parts,monkeypatch,verdict,reasons,word):
    package,document=detailed_package(package_parts,verdict,reasons)
    def forbidden(*args,**kwargs):raise AssertionError('read must not evaluate')
    monkeypatch.setattr('product.backend.domain.verification.checks.evaluate_check_case',forbidden)
    index=record_index(package,document.evidence_id,document.case.case_id)
    observation=next(item for item in index.records if item.kind=='OBSERVATION')
    view=record_view(package,document.evidence_id,document.case.case_id,observation.record_id)
    assert word in view.published_judgement
    assert view.values[0]==dict(label='state',before='private',after='public')
    assert view.verification[2].status=='CONFIRMED' and '每一次已保存的数据修改' in view.verification[2].text
    if reasons==('FUTURE_REASON',):assert view.verification[4].status=='UNKNOWN' and '尚无对应说明' in view.verification[4].text
    fact_link=next(item for item in view.related_records if item.kind=='FACT')
    fact=record_view(package,document.evidence_id,document.case.case_id,fact_link.record_id)
    assert fact.fragment['data']['operation_id']=='commit-1'
    assert fact.location['pointer']=='/business_facts/0'
    serialized=fact.model_dump_json()
    assert 'request_ref' not in serialized and 'lease_owner' not in serialized
    assert fact.verification[4].source['pointer'].endswith('/reason_codes')
    with pytest.raises(JiejianError):record_view(package,document.evidence_id,'other',fact_link.record_id)
    with pytest.raises(JiejianError):record_view(package,document.evidence_id,document.case.case_id,'missing')


def test_legacy_outcome_remains_limited_without_inventing_collection_steps(package_parts):
    package=validate_check_package(package_parts[3],published=False);document=package.evidence[0]
    record=record_index(package,document.evidence_id,document.case.case_id).records[0]
    view=record_view(package,document.evidence_id,document.case.case_id,record.record_id)
    assert view.role=='SUPPORTING' and not view.values
    assert any('不能单独证明' in text for text in view.limitations)
    assert not any('旧证据' in text for text in view.limitations)
    assert 'UNKNOWN' in json.dumps(view.fragment)


def test_automatic_activity_is_published_addressed_and_read_as_supporting(package_parts):
    from product.protocols.runtime.request_activity import RequestActivity
    from product.protocols.checks.check_result import canonical_check_document, parse_check_document, CheckEvidence
    from product.backend.application.checks.reading.story import _request_activity, _activity_error
    package=validate_check_package(package_parts[3],published=False)
    original=package.evidence[0]
    original_bytes=canonical_check_document(original)
    assert b'"activity"' not in original_bytes
    assert b'"activity_error"' not in original_bytes
    assert canonical_check_document(parse_check_document(original_bytes,CheckEvidence))==original_bytes
    capture=RequestActivity.model_validate_json(json.dumps(dict(request_nonce='a'*64,request_digest='b'*64,
        adapters=['node:http','node:sqlite'],complete=True,events=[
            dict(event_id='call_'+'1'*32,parent_event_id=None,kind='HTTP_SERVER',operation='REQUEST',started_at_us=10,duration_us=50,outcome='OK',http_method='POST',http_status=403),
            dict(event_id='call_'+'2'*32,parent_event_id='call_'+'1'*32,kind='SQLITE',operation='GET',started_at_us=12,duration_us=2,outcome='OK',source_location='app.mjs:20')])))
    fields={name:getattr(original,name) for name in CheckEvidence.model_fields if name not in {'evidence_id','activity'}}
    document=seal_check_evidence(**fields,activity=capture)
    result=next(item for item in package.result.case_results if item.case_id==document.case.case_id)
    package=replace(package,evidence=(document,),result=package.result.model_copy(update={'case_results':(
        result.model_copy(update={'evidence_ids':(document.evidence_id,)}),)}))
    assert document.evidence_id!=original.evidence_id
    raw=canonical_check_document(document)
    assert parse_check_document(raw,CheckEvidence).activity==capture
    path=_request_activity((document,))
    assert path.capture==capture and path.evidence_refs==(document.evidence_id,)
    assert _activity_error((document,)) is None
    missing=seal_check_evidence(**{**fields,'activity_error':'ACTIVITY_SOURCE_UNAVAILABLE'})
    assert _request_activity((missing,)) is None
    assert _activity_error((missing,))=='ACTIVITY_SOURCE_UNAVAILABLE'
    assert _activity_error((document,missing))=='ACTIVITY_RECORDS_CONFLICT'
    link=next(item for item in record_index(package,document.evidence_id,document.case.case_id).records if item.event_id==capture.events[1].event_id)
    view=record_view(package,document.evidence_id,document.case.case_id,link.record_id)
    assert view.role=='SUPPORTING' and view.location['pointer']=='/activity/events/1'
    assert view.fragment['source_location']=='app.mjs:20'
    assert view.verification[3].source['pointer']=='/activity'
    assert view.verification[3].status=='LIMITED' and '关联到实际请求' in view.verification[3].text
    assert not any('旧证据' in item for item in view.limitations)
    assert 'SQLITE' in view.fragment.values()
    changed=raw.replace(b'"duration_us":2,',b'"duration_us":3,')
    with pytest.raises(ValueError):parse_check_document(changed,CheckEvidence)

@pytest.mark.parametrize('state,complete,correlated,word',[
    ('SUCCESS',True,True,'服务声明已完成'),('RUNNING',True,True,'仍在运行'),
    ('FAILED',True,True,'服务声明失败'),('CANCELLED',True,True,'服务声明已取消'),
    ('SUCCESS',False,True,'尚未完整对应'),('SUCCESS',True,False,'尚未完整对应')])
def test_async_task_reading_explains_frozen_state_without_replacing_file_or_verdict(package_parts,monkeypatch,state,complete,correlated,word):
    from product.protocols.checks.business_facts import AsyncTaskFact
    from product.protocols.checks.check_result import canonical_check_document
    package,original=detailed_package(package_parts)
    prior=original.business_facts[0]
    fact=seal_business_fact(case_id=prior.case_id,request_ref=prior.request_ref,observed_at_us=10,
        collector_kind='ASYNC_STATUS',proofs=prior.proofs,complete=complete,
        data=AsyncTaskFact(task_fingerprint='a'*64,mapping_fingerprint='b'*64,dispatch_request_digest='c'*64,
            state=state,subject_identity_id=original.case.subject_test_identity_id,owner_identity_id=original.case.resource_owner_test_identity_id,
            resource_id=original.case.resource_id,correlated=correlated,polls_used=2))
    fields={key:getattr(original,key) for key in type(original).model_fields if key not in {'evidence_id','business_facts','fact_references'}}
    reference=original.fact_references[0].model_copy(update={'fact_ids':tuple(sorted((prior.fact_id,fact.fact_id)))})
    document=seal_check_evidence(**fields,business_facts=tuple(sorted((prior,fact),key=lambda item:item.fact_id)),fact_references=(reference,))
    results=tuple(item.model_copy(update={'evidence_ids':(document.evidence_id,)}) if item.case_id==document.case.case_id else item for item in package.result.case_results)
    package=replace(package,evidence=(document,),result=package.result.model_copy(update={'case_results':results}))
    raw=canonical_check_document(document)
    def forbidden(*args,**kwargs):raise AssertionError('reading must not evaluate')
    monkeypatch.setattr('product.backend.domain.verification.checks.evaluate_check_case',forbidden)
    view=record_view(package,document.evidence_id,document.case.case_id,fact.fact_id)
    assert word in view.summary and view.role=='SUPPORTING'
    assert '禁止' in view.published_judgement
    assert view.fragment['data']['state']==state
    method=next(item.text for item in view.verification if item.key=='method')
    assert '状态接口' in method and '独立的文件接收记录' in method
    assert 'SHA-256' not in method
    assert canonical_check_document(document)==raw
    if complete and correlated:assert '文件接收记录' in view.summary


def test_identity_fact_does_not_inherit_the_methods_of_business_observations(package_parts,monkeypatch):
    from product.protocols.checks.business_facts import IdentityCheckFact
    from product.protocols.checks.check_result import canonical_check_document
    package,original=detailed_package(package_parts)
    prior=original.business_facts[0]
    identity=seal_business_fact(case_id=prior.case_id,request_ref=prior.request_ref,observed_at_us=10,
        collector_kind='IDENTITY_READER',proofs=prior.proofs,complete=True,
        data=IdentityCheckFact(identity_id=original.case.subject_test_identity_id,subject_match='MATCH',role_match='MATCH'))
    fields={key:getattr(original,key) for key in type(original).model_fields if key not in {'evidence_id','business_facts','fact_references'}}
    reference=original.fact_references[0].model_copy(update={'fact_ids':tuple(sorted((prior.fact_id,identity.fact_id)))})
    document=seal_check_evidence(**fields,business_facts=tuple(sorted((prior,identity),key=lambda item:item.fact_id)),fact_references=(reference,))
    results=tuple(item.model_copy(update={'evidence_ids':(document.evidence_id,)}) if item.case_id==document.case.case_id else item for item in package.result.case_results)
    package=replace(package,evidence=(document,),result=package.result.model_copy(update={'case_results':results}))
    raw=canonical_check_document(document)
    def forbidden(*args,**kwargs):raise AssertionError('reading must not evaluate')
    monkeypatch.setattr('product.backend.domain.verification.checks.evaluate_check_case',forbidden)
    view=record_view(package,document.evidence_id,document.case.case_id,identity.fact_id)
    link=next(item for item in record_index(package,document.evidence_id,document.case.case_id).records if item.record_id==identity.fact_id)
    assert '操作账号' in link.label
    assert '资源所有者' in link.label if document.effective_case.subject_test_identity_id==document.effective_case.resource_owner_test_identity_id else '资源所有者' not in link.label
    method=next(item.text for item in view.verification if item.key=='method')
    assert '独立读取实际账号与角色' in method and '数据修改' not in method
    explanation=next(item for item in view.verification if item.key=='method')
    assert explanation.source['pointer']==view.location['pointer']
    assert explanation.fragment['data']['kind']=='IDENTITY_CHECK'
    assert '禁止' in view.published_judgement and canonical_check_document(document)==raw


pytestmark = [pytest.mark.level3]
