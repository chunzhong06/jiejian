# 将受控记录投影为已采用字段、身份核对和请求窗；受保护正文与原始nonce不进入Evidence。
from product.backend.infra.observers.records.record_facts import record_value,request_fact
from product.protocols.checks.business_facts import (FactProofReference,CommittedFieldChange,CommittedStateFact,
    IdentityCheckFact,RecordObservationWindow,ObservationFactReference,seal_business_fact)


def collect_record_evidence(*,source,case,requirement,proof,phase,before,view,target,clock,marker,claims):
    """先核对完整私有记录，再封存有限投影；独立提交中的内部步骤不另算业务事实。"""
    config=source.config
    path=config.mappings['state'][1:]
    source_ref=FactProofReference(effect_id=requirement.effect_id,proof_fingerprint=requirement.proof_fingerprint,
        source_id=source.source_id,source_revision=source.revision,source_fingerprint=source.source_fingerprint)
    common=dict(case_id=case.case_id,request_ref=marker,observed_at_us=clock,
        proofs=(source_ref,),complete=True)
    facts=identity_facts(common,case,proof)
    snapshot=view.snapshot
    snapshot_only=phase in {'BASELINE','BEFORE','RECOVERY'}
    before=snapshot if snapshot_only else before
    if before is None:raise ValueError('missing record baseline')
    matched=snapshot_only
    source_complete=True
    if not snapshot_only:
        if target is None:raise ValueError('missing target receipt')
        checked=request_fact(before,view,path=path,expected_state=proof.expected_state,
            request_nonce=target.request_nonce,request_digest=target.request_digest,
            subject_id=claims[case.subject_test_identity_id].application_subject_id,resource_id=case.resource_id,
            owner_id=claims[case.resource_owner_test_identity_id].application_subject_id,collection=config.collection)
        # 不能为失配/不连续记录封装肯定事实；单纯未闭合仍可保存已采集的关联片段。
        matched=checked.state!='UNKNOWN' or checked.reason_codes==('RECORD_REQUEST_INCOMPLETE',)
        source_complete=(checked.state=='ABSENT' or (checked.state=='CONFIRMED' and view.scope.state=='COMPLETE'))
        if matched:
            current=before.data
            for operation in view.operations:
                final=operation.transitions[-1].after if operation.transitions else current
                change=CommittedFieldChange(proof_fingerprint=requirement.proof_fingerprint,path=path,
                    before=record_value(current,path),after=record_value(final,path))
                facts.append(seal_business_fact(**common,collector_kind='CONTROLLED_RECORDS',data=CommittedStateFact(
                    generation=operation.generation,operation_id=operation.operation_id,scope_ordinal=operation.scope_ordinal,
                    before_version=operation.before_version,after_version=operation.after_version,
                    subject_identity_id=case.subject_test_identity_id,owner_identity_id=case.resource_owner_test_identity_id,
                    resource_id=case.resource_id,changes=(change,))))
                current=final
            source_complete=source_complete and current==snapshot.data
    window=RecordObservationWindow(generation=snapshot.generation,before_version=before.version,
        after_version=snapshot.version,before_value=record_value(before.data,path),after_value=record_value(snapshot.data,path),
        before_operation=before.last_operation_id,after_operation=snapshot.last_operation_id,
        scope_state='MISSING' if snapshot_only or view.scope is None else view.scope.state,
        operation_count=0 if snapshot_only else len(view.operations),request_matched=matched,
        source_complete=source_complete,field_path=path)
    reference=ObservationFactReference(proof_fingerprint=requirement.proof_fingerprint,observer_id=proof.observer_id,
        phase=phase,fact_ids=tuple(fact.fact_id for fact in facts),source=source_ref,
        method='STATE_SNAPSHOT' if snapshot_only else 'ATOMIC_STATE',record_window=window,complete=matched)
    return tuple(facts),reference


def identity_facts(common,case,proof):
    return [seal_business_fact(**common,collector_kind='IDENTITY_READER',
        data=IdentityCheckFact(identity_id=identity_id,subject_match='MATCH',role_match='MATCH'))
        for identity_id in sorted({case.subject_test_identity_id,case.resource_owner_test_identity_id,proof.observation_identity_id})]
