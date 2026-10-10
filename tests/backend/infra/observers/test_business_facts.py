# 核对真实提交的有限证据、阶段去重和请求归属，避免仅凭最终状态推断安全。
from types import SimpleNamespace as NS
from contextlib import closing
import pytest
from product.backend.infra.observers.records.transaction_store import TransactionRecordStore
from product.backend.infra.observers.checks.record_evidence import collect_record_evidence
from product.backend.infra.observers.checks.sealed_facts import finalize_facts
from product.backend.core.verification.business_facts import reduce_record_facts
from product.protocols.runtime.transaction_records import RecordSeed,RecordTransaction,RecordChange
from product.protocols.checks.check_result import (CheckObservation,check_request_marker,seal_check_evidence,
    canonical_check_document,parse_check_document,CheckEvidence,DetailedCheckEvidence,CheckCaseOutcome)
from product.protocols.checks.execution_request import ExecutionCase
from tests.fixtures.checks.check_plan import plan


def collected(tmp_path,commits,*,closed=True):
    action=plan().actions[0]
    case=ExecutionCase.model_validate_json(next(item for item in action.cases if item.permission.expectation=='DENY').model_dump_json())
    requirement=case.proof_requirements[0]
    source=NS(source_id='psr_'+'1'*32,revision=1,source_fingerprint='a'*64,
        config=NS(mappings={'state':('data','state')},collection='items'))
    proof=NS(observation_identity_id=case.resource_owner_test_identity_id,observer_id='json_'+'1'*32,expected_state='open')
    marker=check_request_marker('run_'+'1'*32,'job_'+'2'*32,1,case.case_id)
    target=NS(request_nonce='a'*64,request_digest='b'*64)
    claims={case.subject_test_identity_id:NS(application_subject_id='user'),case.resource_owner_test_identity_id:NS(application_subject_id='owner')}
    with closing(TransactionRecordStore(tmp_path/'journal')) as store:
        before=store.seed(RecordSeed(collection='items',resource_id=case.resource_id,owner_id='owner',data={'state':'closed'}))
        scope=store.open_scope(target.request_nonce,target.request_digest)
        for index,changes in enumerate(commits):
            store.transact(RecordTransaction(collection='items',resource_id=case.resource_id,subject_id='user',
                scope_id=scope.scope_id,request_key=f'command-{index}',expected_version=index,
                changes=tuple(RecordChange(path=('state',),value=value) for value in changes)))
        if closed:store.close_scope(scope.scope_id,True)
        view=store.proof_view('items',case.resource_id,request_nonce=target.request_nonce)
    facts,ref=collect_record_evidence(source=source,case=case,requirement=requirement,proof=proof,phase='AFTER',
        before=before,view=view,target=target,clock=10,marker=marker,claims=claims)
    state,closure,complete=reduce_record_facts(ref,facts,case=case,expected_state=proof.expected_state)
    observation=CheckObservation(effect_id=requirement.effect_id,proof_fingerprint=requirement.proof_fingerprint,
        observer_id=proof.observer_id,level=requirement.level,phase='AFTER',state=state,closure=closure,
        complete=complete,reliable=complete,correlated=complete,authoritative=complete,
        window_start_us=9,window_end_us=11,correlation_refs=(case.case_id,marker))
    return action,case,facts,ref,observation


@pytest.mark.parametrize('commits,expected',[((), 'ABSENT'),((('open','closed'),),'ABSENT'),((('open',),('closed',)),'CONFIRMED'),(((),),'ABSENT')])
def test_only_independent_commits_prove_occurrence(tmp_path,commits,expected):
    _,case,facts,ref,observation=collected(tmp_path,commits)
    assert observation.state==expected
    broken=ref.model_copy(update={'record_window':ref.record_window.model_copy(update={'request_matched':False})})
    assert reduce_record_facts(broken,facts,case=case,expected_state='open')[0]=='UNKNOWN'


def test_open_scope_cannot_prove_absence_but_keeps_committed_occurrence(tmp_path):
    _,_,_,_,observation=collected(tmp_path/'empty',(),closed=False)
    assert observation.state=='UNKNOWN'
    _,_,_,_,observation=collected(tmp_path/'changed',(('open',),),closed=False)
    assert observation.state=='CONFIRMED'


def test_after_and_eventual_share_one_committed_fact_and_strict_root(tmp_path):
    action,case,facts,ref,observation=collected(tmp_path,(('open',),('closed',)))
    later=observation.model_copy(update={'phase':'EVENTUAL','window_start_us':12,'window_end_us':13})
    observations,sealed,references=finalize_facts((observation,later),{
        observation.model_dump_json():(facts,ref),later.model_dump_json():(facts,ref.model_copy(update={'phase':'EVENTUAL'}))})
    assert len([fact for fact in sealed if fact.data.kind=='COMMITTED_STATE'])==2
    assert references[0].fact_ids==references[1].fact_ids
    evidence=seal_check_evidence(detailed=True,run_id='run_'+'1'*32,job_id='job_'+'2'*32,attempt=1,
        action_id=action.action_id,action_revision=1,request_hash='a'*64,config_hash='b'*64,case=case,
        outcome=CheckCaseOutcome(execution_outcome='DENIED',actual_identity_status='MATCH',baseline_trusted=True,
            recovery_verified=True,run_correlated=True,resource_correlated=True),
        observations=observations,business_facts=sealed,fact_references=references)
    raw=canonical_check_document(evidence)
    assert isinstance(parse_check_document(raw,CheckEvidence),DetailedCheckEvidence)
    with pytest.raises(ValueError):CheckEvidence.model_validate_json(raw)


def test_publisher_rejects_recomputed_outer_hash_when_facts_disagree(tmp_path):
    from product.backend.infra.artifacts.checks.fact_validation import validate_frozen_facts
    action,case,facts,ref,observation=collected(tmp_path,(('open',),))
    requirement=case.proof_requirements[0]
    source=NS(source_id=ref.source.source_id,revision=1,source_fingerprint=ref.source.source_fingerprint,
        config=NS(effect_id=requirement.effect_id,source_contract_id='TRANSACTION_HISTORY_V2',mappings={'state':('data','state')}))
    bundle=NS(schema_version='6',json_sources=(source,),actions=(NS(action_id=action.action_id,
        proofs=(NS(binding_fingerprint=requirement.binding_fingerprint,expected_state='open'),)),))
    def seal(observation):
        return seal_check_evidence(detailed=True,run_id='run_'+'1'*32,job_id='job_'+'2'*32,attempt=1,
            action_id=action.action_id,action_revision=1,request_hash='a'*64,config_hash='b'*64,case=case,
            outcome=CheckCaseOutcome(execution_outcome='DENIED',actual_identity_status='MATCH',baseline_trusted=True,
                recovery_verified=True,run_correlated=True,resource_correlated=True),
            observations=(observation,),business_facts=facts,fact_references=(ref,))
    validate_frozen_facts(seal(observation),bundle,0,20)
    tampered=seal(observation.model_copy(update={'state':'ABSENT'}))
    with pytest.raises(ValueError,match='differs from sealed facts'):validate_frozen_facts(tampered,bundle,0,20)
    with pytest.raises(ValueError,match='outside run window'):validate_frozen_facts(seal(observation),bundle,12,20)


@pytest.mark.parametrize('matched,refused,scope,expected',[(True,False,'COMPLETE','CONFIRMED'),(True,True,'OPEN','CONFIRMED'),
    (False,False,'COMPLETE','UNKNOWN'),(False,True,'COMPLETE','ABSENT'),(False,True,'OPEN','UNKNOWN')])
def test_file_fact_comparison_requires_real_bytes_and_closed_refusal(matched,refused,scope,expected):
    from product.backend.infra.observers.checks.file_evidence import collect_file_evidence
    from product.backend.core.verification.business_facts import reduce_file_facts
    from product.protocols.checks.business_facts import ArtifactManifestReference
    action=plan().actions[0];case=ExecutionCase.model_validate_json(next(item for item in action.cases if item.permission.expectation=='DENY').model_dump_json())
    requirement=case.proof_requirements[0];manifest=ArtifactManifestReference(asset_id='pai_'+'1'*32,size=3,sha256='a'*64)
    source=NS(source_id='psr_'+'1'*32,revision=1,source_fingerprint='a'*64,adoption_preflight_id='pfc_'+'1'*32,
        config=NS(reference_artifact=manifest,reference_origin='UPLOAD',reference_resource_id=case.resource_id,reference_owner_identity_id=case.resource_owner_test_identity_id))
    proof=NS(observation_identity_id=case.resource_owner_test_identity_id,observer_id='json_'+'1'*32)
    target=NS(request_nonce='n',request_digest='d',entity_receipt=NS(actual_size=3,actual_sha256='a'*64 if matched else 'b'*64,complete=True,refused=refused,reason_codes=()))
    view=NS(snapshot=NS(generation='g'),scope=NS(generation='g',request_nonce='n',request_digest='d',state=scope))
    facts,reference=collect_file_evidence(source=source,case=case,requirement=requirement,proof=proof,phase='AFTER',
        before=NS(generation='g'),view=view,target=target,clock=10,marker=check_request_marker('run_'+'1'*32,'job_'+'2'*32,1,case.case_id))
    assert reduce_file_facts(reference,facts,case=case)[0]==expected
    other=case.model_copy(update={'resource_id':'another-resource'})
    assert reduce_file_facts(reference,facts,case=other)[0]=='UNKNOWN'
