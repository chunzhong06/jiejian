# 生成有真实协议结构的展示夹具；只用于阅读布局，不作为目标执行或权限验证的证据。
from pathlib import Path
from types import SimpleNamespace
from product.backend.core.lifecycle import CaseVerdict,RunVerdict,RunLifecycle
from product.backend.core.verification.trace import ExecutionTrace,TraceEvent,TraceEventKind,TraceCorrelationKind
from product.backend.infra.artifacts.checks.check_packages import CheckPackage
from product.protocols.checks.business_facts import FactProofReference,CommittedStateFact,CommittedFieldChange,seal_business_fact,ObservationFactReference,RecordObservationWindow
from product.protocols.checks.check_result import CheckCaseOutcome,CheckObservation,CheckCaseResult,CheckRunnerResult,seal_check_evidence,check_request_marker
from tests.fixtures.checks.check_execution import execution_pair


def reading_package():
    def configure(payload):
        payload['actions'][0]['display_name']='开放项目资料'
        for i,identity in enumerate(payload['identities']):identity['label']='项目负责人' if i==0 else '评审账号'
    request,bundle=execution_pair(configure=configure)
    run='run_'+'1'*32;job='job_'+'2'*32;documents=[];results=[]
    for action in request.actions:
        for case in action.cases:
            proof=case.proof_requirements[0]
            reference=FactProofReference(effect_id=proof.effect_id,proof_fingerprint=proof.proof_fingerprint,source_id='psr_'+'1'*32,source_revision=1,source_fingerprint='a'*64)
            fact=seal_business_fact(case_id=case.case_id,request_ref=check_request_marker(run,job,1,case.case_id),observed_at_us=10,
                collector_kind='CONTROLLED_RECORDS',proofs=(reference,),complete=True,data=CommittedStateFact(generation='generation',operation_id='commit-1',scope_ordinal=0,
                before_version=0,after_version=1,subject_identity_id=case.subject_test_identity_id,owner_identity_id=case.resource_owner_test_identity_id,
                resource_id=case.resource_id,changes=(CommittedFieldChange(proof_fingerprint=proof.proof_fingerprint,path=('state',),before='仅内部可用',after='评审可访问'),)))
            outcome=CheckCaseOutcome(execution_outcome='DENIED' if case.permission.expectation=='DENY' else 'ACCEPTED',http_status=403 if case.permission.expectation=='DENY' else 200,
                actual_identity_status='MATCH',baseline_trusted=True,recovery_verified=True,run_correlated=True,resource_correlated=True)
            observation=CheckObservation(effect_id=proof.effect_id,proof_fingerprint=proof.proof_fingerprint,observer_id='owner_api',level='VERDICT_REQUIRED',phase='AFTER',
                state='CONFIRMED',closure='CLOSED',complete=True,reliable=True,correlated=True,authoritative=True,window_start_us=9,window_end_us=11)
            ref=ObservationFactReference(proof_fingerprint=proof.proof_fingerprint,observer_id=observation.observer_id,phase='AFTER',source=reference,
                fact_ids=(fact.fact_id,),method='ATOMIC_STATE',complete=True,record_window=RecordObservationWindow(generation='generation',before_version=0,after_version=1,
                before_value='仅内部可用',after_value='评审可访问',scope_state='COMPLETE',operation_count=1,request_matched=True,source_complete=True,field_path=('state',)))
            events=tuple(TraceEvent(event_id=identifier,parent_event_ids=parents,case_id=case.case_id,action_id=action.action_id,resource_ids=(case.resource_id,),
                kind=kind,semantic_key=identifier,source_component='application',source_location='handler:'+identifier,correlation_kind=TraceCorrelationKind.CASE_MARKER,recorded_at_us=stamp)
                for identifier,parents,kind,stamp in [('entry',(),TraceEventKind.ENTRY,8),('commit',('entry',),TraceEventKind.PERSISTENT_EFFECT,10)])
            trace=ExecutionTrace(case_id=case.case_id,action_id=action.action_id,planned_subject_id=case.subject_test_identity_id,events=events,complete=True,reason_codes=())
            document=seal_check_evidence(detailed=True,run_id=run,job_id=job,attempt=1,action_id=action.action_id,action_revision=action.action_revision,
                request_hash='a'*64,config_hash=request.config_fingerprint,case=case,outcome=outcome,observations=(observation,),trace=trace,business_facts=(fact,),fact_references=(ref,))
            documents.append(document)
            results.append(CheckCaseResult(case_id=case.case_id,action_id=action.action_id,verdict=CaseVerdict.VULNERABLE if case.permission.expectation=='DENY' else CaseVerdict.SAFE,
                reason_codes=('ORPHAN_EFFECT_CONFIRMED',) if case.permission.expectation=='DENY' else (),evidence_ids=(document.evidence_id,),outcome=outcome))
    result=CheckRunnerResult(run_id=run,job_id=job,attempt=1,lease_owner='reading-fixture',fencing_token=1,request_hash='a'*64,
        config_hash=request.config_fingerprint,result_type='SUCCESS',lifecycle=RunLifecycle.COMPLETED,case_results=tuple(results),verdict=RunVerdict.BLOCK,started_at_us=1,completed_at_us=20)
    return CheckPackage(directory=Path('.'),request=request,bundle=bundle,result=result,evidence=tuple(documents),files=(),manifest=SimpleNamespace(result_hash='b'*64))
