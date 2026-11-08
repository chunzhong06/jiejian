"""连续观察的边界：缺执行、换题和部署未知均不能被归为已验证修复。"""
from types import SimpleNamespace

import pytest

from product.backend.application.checks.reading.comparison import classify_change,_proof_method
from product.backend.domain.lifecycle import CaseVerdict
from product.protocols.checks.execution_request import RecordedProofReference,ObserverProofReference,OperationProofReference


def observed(verdict, *, signature='same', control='SAFE'):
    return dict(signature=signature,result=None if verdict is None else SimpleNamespace(verdict=CaseVerdict(verdict)),
        control=None if control is None else SimpleNamespace(verdict=CaseVerdict(control)))


@pytest.mark.parametrize('candidate,control,deployment,expected', [
    ('SAFE','SAFE','MATCHED','FIXED'), ('SAFE','SAFE','UNKNOWN','NO_LONGER_OBSERVED'),
    ('SAFE','SAFE','UNCONFIRMED','NO_LONGER_OBSERVED'), ('SAFE',None,'MATCHED','INSUFFICIENT'),
    ('SAFE','ERROR','MATCHED','INSUFFICIENT'), ('SKIPPED','SAFE','MATCHED','INSUFFICIENT'),
    ('ERROR','SAFE','MATCHED','INSUFFICIENT'), ('INCONCLUSIVE','SAFE','MATCHED','INSUFFICIENT'),
    (None,'SAFE','MATCHED','INSUFFICIENT'), ('VULNERABLE','SAFE','UNKNOWN','PERSISTING')])
def test_original_issue_disappearance_requires_complete_control_and_verified_deployment(candidate,control,deployment,expected):
    state,_=classify_change(observed('VULNERABLE'),observed(candidate,control=control),deployment=deployment)
    assert state==expected


def test_changed_requirement_is_not_a_fix_and_missing_coverage_is_not_a_new_issue():
    assert classify_change(observed('VULNERABLE'),observed('SAFE',signature='new-rule'),deployment='MATCHED') == (
        'INCOMPARABLE',('CHECK_CONTRACT_CHANGED',))
    assert classify_change(observed('VULNERABLE'),None,deployment='MATCHED') == ('INSUFFICIENT',('CURRENT_NOT_COVERED',))
    assert classify_change(None,observed('VULNERABLE'),deployment='MATCHED') == ('INSUFFICIENT',('BASELINE_NOT_COVERED',))


def test_recurrence_requires_the_same_earlier_issue_and_a_safe_baseline():
    before,after=observed('SAFE'),observed('VULNERABLE')
    assert classify_change(before,after,deployment='UNKNOWN',earlier=observed('VULNERABLE'))[0]=='RECURRED'
    assert classify_change(before,after,deployment='UNKNOWN',earlier=observed('VULNERABLE',signature='different'))[0]=='NEW'
    assert classify_change(before,after,deployment='UNKNOWN',earlier=observed('INCONCLUSIVE'))[0]=='NEW'
    assert classify_change(observed('SAFE'),observed('SAFE'),deployment='UNKNOWN')[0]=='UNCHANGED'


def test_each_proof_origin_uses_its_actual_method_identity():
    methods=[RecordedProofReference(recording_id='rec_'+'a'*32,draft_revision=1,draft_sha256='b'*64,step_id='read',request_template_fingerprint='c'*64),
        ObserverProofReference(descriptor_id='exp_'+'d'*32,descriptor_fingerprint='e'*64,observer_id='query'),
        OperationProofReference(flow_id='ofl_'+'f'*32,revision=1,query_fingerprint='1'*64)]
    assert [_proof_method(item) for item in methods]==['RECORDED_OBSERVATION:'+'c'*64,'REGISTERED_OBSERVER:'+'e'*64,'OPERATION_HTTP_ENTITY:'+'1'*64]


pytestmark=[pytest.mark.level3]
