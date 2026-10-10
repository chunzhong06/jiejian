# 固定证据阅读模板覆盖真实封存值、未知原因及旧记录；投影期间禁止重新裁决或目标I/O。
from dataclasses import replace
import json
import pytest
from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.errors import JiejianError
from product.backend.infra.artifacts.checks.check_packages import validate_check_package
from product.backend.workflows.checks.reading.records import record_index,record_view
from product.protocols.checks.business_facts import (seal_business_fact,FactProofReference,CommittedStateFact,CommittedFieldChange,
    ObservationFactReference,RecordObservationWindow)
from product.protocols.checks.check_result import CheckObservation,seal_check_evidence,check_request_marker
from tests.fixtures.checks.check_publication import package_parts


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
    document=seal_check_evidence(detailed=True,**original.model_dump(exclude={'schema_version','evidence_id','observations','case','outcome','trace'}),
        case=case,outcome=original.outcome,observations=(observation,),business_facts=(fact,),fact_references=(ref,))
    results=tuple(result.model_copy(update={'evidence_ids':(document.evidence_id,),'verdict':CaseVerdict(verdict),'reason_codes':reasons}) if result.case_id==case.case_id else result for result in package.result.case_results)
    return replace(package,evidence=(document,),result=package.result.model_copy(update={'case_results':results})),document


@pytest.mark.parametrize('verdict,reasons,word',[('VULNERABLE',('ORPHAN_EFFECT_CONFIRMED',),'禁止'),('SAFE',(),'验证'),
    ('INCONCLUSIVE',('ACTUAL_IDENTITY_UNKNOWN',),'不能'),('INCONCLUSIVE',('FUTURE_REASON',),'不能')])
def test_detailed_record_reads_exact_values_and_published_reason(package_parts,monkeypatch,verdict,reasons,word):
    package,document=detailed_package(package_parts,verdict,reasons)
    def forbidden(*args,**kwargs):raise AssertionError('read must not evaluate')
    monkeypatch.setattr('product.backend.core.verification.checks.evaluate_check_case',forbidden)
    index=record_index(package,document.evidence_id,document.case.case_id)
    observation=next(item for item in index.records if item.kind=='OBSERVATION')
    view=record_view(package,document.evidence_id,document.case.case_id,observation.record_id)
    assert word in view.published_judgement
    assert view.values[0]==dict(label='state',before='private',after='public')
    assert view.verification[2].status=='CONFIRMED' and '独立提交' in view.verification[2].text
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
    assert any('未保存' in text for text in view.limitations)
    assert 'UNKNOWN' in json.dumps(view.fragment)
