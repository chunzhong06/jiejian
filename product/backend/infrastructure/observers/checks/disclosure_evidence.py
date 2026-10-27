# 有限字段读取的同源证明：网络正文只在内存比较，Evidence仅保存逐字段一次性密钥摘要。
from product.backend.infrastructure.observers.adapters.json_source import strict_json,SourceReadError
from product.backend.infrastructure.observers.records.record_facts import record_value
from product.backend.infrastructure.observers.checks.check_disclosure import disclosure_proof
from product.backend.infrastructure.observers.checks.record_evidence import identity_facts
from product.protocols.checks.business_facts import (FactProofReference,FieldContentComparison,FieldDisclosureFact,
    DisclosureObservationWindow,ObservationFactReference,seal_business_fact)


def collect_disclosure_evidence(*,source,case,requirement,proof,phase,before,view,target,clock,marker,key):
    config=source.config
    source_ref=FactProofReference(effect_id=requirement.effect_id,proof_fingerprint=requirement.proof_fingerprint,
        source_id=source.source_id,source_revision=source.revision,source_fingerprint=source.source_fingerprint)
    common=dict(case_id=case.case_id,request_ref=marker,observed_at_us=clock,proofs=(source_ref,),complete=True)
    facts=identity_facts(common,case,proof)
    snapshot=view.snapshot
    snapshot_only=phase in {'BASELINE','BEFORE','RECOVERY'}
    before=snapshot if snapshot_only else before
    if before is None:raise ValueError('missing disclosure baseline')
    def projection(value):
        return disclosure_proof(owner=value,response=value,fields=proof.protected_projection,key=key,marker=marker)
    initial,current=projection(before.data),projection(snapshot.data)
    matched,rejected,resource_matched=snapshot_only,False,snapshot_only
    if not snapshot_only and target is not None and view.scope is not None:
        matched=(view.scope.request_nonce==target.request_nonce and view.scope.request_digest==target.request_digest
            and view.scope.generation==before.generation==snapshot.generation)
        if matched:
            response=strict_json(target.body,config.max_response_bytes)
            rejected=target.status_code in {401,403} and isinstance(response,dict) and set(response)<={'error'}
            if not rejected:
                try:
                    content=record_value(response,config.target_data_path)
                    resource_matched=(record_value(response,config.target_resource_path)==case.resource_id
                        and record_value(response,config.target_owner_path)==before.owner_id)
                except SourceReadError:
                    resource_matched=False
                if resource_matched:
                    # 每项只封存一个字段摘要，避免长字段集合突破单事实预算；整体仍受64项上限控制。
                    for path in proof.protected_projection:
                        comparison=disclosure_proof(owner=before.data,response=content,fields=(path,),key=key,marker=marker)
                        field=FieldContentComparison(path=path,
                            expected_digest=comparison.owner_digest if comparison.projection_complete else None,
                            received_digest=comparison.response_digest,matched=comparison.matched)
                        facts.append(seal_business_fact(**common,collector_kind='HTTP_ENTITY',data=FieldDisclosureFact(
                            subject_identity_id=case.subject_test_identity_id,owner_identity_id=case.resource_owner_test_identity_id,
                            resource_id=case.resource_id,fields=(field,))))
    window=DisclosureObservationWindow(protected_paths=proof.protected_projection,
        baseline_digest=initial.owner_digest if initial.projection_complete else None,
        current_digest=current.owner_digest if current.projection_complete else None,
        source_unchanged=before.data==snapshot.data and before.version==snapshot.version,
        resource_matched=resource_matched,rejected_empty_response=rejected,request_matched=matched,
        scope_state='MISSING' if snapshot_only or view.scope is None else view.scope.state)
    budget_exceeded=len(facts)>64
    if budget_exceeded:
        facts.sort(key=lambda fact:(fact.data.kind!='IDENTITY_CHECK',
            not any(item.matched for item in getattr(fact.data,'fields',()))))
        facts=facts[:64]
    reference=ObservationFactReference(proof_fingerprint=requirement.proof_fingerprint,observer_id=proof.observer_id,
        phase=phase,source=source_ref,fact_ids=tuple(fact.fact_id for fact in facts),complete=matched,
        method='FIELD_SNAPSHOT' if snapshot_only else 'FIELD_DISCLOSURE',disclosure_window=window,
        reason_codes=('FACT_BUDGET_EXCEEDED',) if budget_exceeded else ())
    return tuple(facts),reference
