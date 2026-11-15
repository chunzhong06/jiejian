"""保护规则适用集合与具体样本结论分离，未知条件不由计划补值。"""
from types import SimpleNamespace as NS
from product.backend.application.checks.reading.coverage import sample_coverage
from product.protocols.checks.conditions import ObservedPermissionConditions


def package(*, observed='APPROVED', verdict='SAFE', expected=('APPROVED', 'WAITING')):
    permission=NS(intent_id='pin_'+'a'*32,revision=2,intent_hash='a'*64,
        conditions=NS(resource_states=expected))
    case=NS(case_id='case_a',resource_id='loan-1042',subject_test_identity_id='tid_'+'b'*32,permission=permission)
    conditions=() if observed is None else (ObservedPermissionConditions(proof_fingerprint='a'*64,
        source_id='psr_'+'b'*32,source_fingerprint='c'*64,principal='AUTHENTICATED',resource_state=observed),)
    result=NS(case_id=case.case_id,verdict=NS(value=verdict),evidence_ids=('ev_a',),outcome=NS(condition_observations=conditions))
    document=NS(evidence_id='ev_a',effective_case=case,business_facts=())
    return NS(request=NS(actions=(NS(cases=(case,)),)),result=NS(case_results=(result,)),evidence=(document,))


def test_success_keeps_unexecuted_state_explicit_without_changing_verdict():
    value=package()
    coverage,=sample_coverage(value)
    assert coverage.applicable_states==('APPROVED','WAITING')
    assert coverage.concluded_states==('APPROVED',)
    assert coverage.unchecked_states==('WAITING',)
    assert coverage.samples[0].resource_id=='loan-1042'
    assert value.result.case_results[0].verdict.value=='SAFE'


def test_observation_without_conclusion_is_not_completed_coverage():
    coverage,=sample_coverage(package(observed='WAITING',verdict='INCONCLUSIVE'))
    assert coverage.observed_states==('WAITING',)
    assert coverage.concluded_states==()
    assert coverage.unchecked_states==('APPROVED','WAITING')


def test_missing_observation_is_unknown_and_never_filled_from_rule():
    coverage,=sample_coverage(package(observed=None,verdict='INCONCLUSIVE'))
    assert coverage.observed_states==()
    assert coverage.unknown_case_ids==('case_a',)
    assert coverage.samples[0].conditions==()


def test_unconditional_sample_does_not_invent_an_all_conditions_percentage():
    coverage,=sample_coverage(package(observed=None,expected=()))
    assert coverage.unchecked_states==coverage.unknown_case_ids==()
    assert len(coverage.samples)==1
