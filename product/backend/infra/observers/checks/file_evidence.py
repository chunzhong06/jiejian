# 以原受控资源、实际身份和单次TARGET接收摘要形成文件证明；不读取目标自报hash或下载正文。
from product.backend.infra.observers.checks.record_evidence import identity_facts
from product.protocols.checks.business_facts import (FactProofReference,ReferenceArtifactFact,FileReceiptFact,
    FileObservationWindow,ObservationFactReference,seal_business_fact)


def collect_file_evidence(*,source,case,requirement,proof,phase,before,view,target,clock,marker):
    config=source.config
    source_ref=FactProofReference(effect_id=requirement.effect_id,proof_fingerprint=requirement.proof_fingerprint,
        source_id=source.source_id,source_revision=source.revision,source_fingerprint=source.source_fingerprint)
    common=dict(case_id=case.case_id,request_ref=marker,observed_at_us=clock,proofs=(source_ref,),complete=True)
    facts=identity_facts(common,case,proof)
    facts.append(seal_business_fact(**common,collector_kind='REFERENCE_STORE',data=ReferenceArtifactFact(
        manifest=config.reference_artifact,origin=config.reference_origin,adoption_ref=source.adoption_preflight_id)))
    snapshot_only=phase in {'BASELINE','BEFORE','RECOVERY'}
    resource_matched=(case.resource_id==config.reference_resource_id and case.resource_owner_test_identity_id==config.reference_owner_identity_id)
    request_matched=snapshot_only
    receipt=None if target is None else target.entity_receipt
    reasons=()
    if not snapshot_only:
        scope=view.scope
        request_matched=(target is not None and scope is not None and before is not None
            and scope.request_nonce==target.request_nonce and scope.request_digest==target.request_digest
            and before.generation==view.snapshot.generation==scope.generation)
        if receipt is not None:
            comparison='INCOMPLETE' if not receipt.complete else 'MATCH' if (
                receipt.actual_size,receipt.actual_sha256)==(config.reference_artifact.size,config.reference_artifact.sha256) else 'DIFFERENT'
            facts.append(seal_business_fact(**common,collector_kind='HTTP_ENTITY',data=FileReceiptFact(
                actual_size=receipt.actual_size,actual_sha256=receipt.actual_sha256,complete=receipt.complete,
                expected=config.reference_artifact,comparison=comparison,subject_identity_id=case.subject_test_identity_id,
                owner_identity_id=case.resource_owner_test_identity_id,resource_id=case.resource_id)))
            reasons=receipt.reason_codes
            if comparison=='DIFFERENT' and not receipt.refused:reasons=('FILE_CONTENT_DIFFERENT',)
        else:reasons=('FILE_RECEIPT_UNAVAILABLE',)
    if not resource_matched:reasons=('REFERENCE_RESOURCE_MISMATCH',)
    window=FileObservationWindow(expected=config.reference_artifact,resource_matched=resource_matched,request_matched=request_matched,
        scope_state='MISSING' if snapshot_only or view.scope is None else view.scope.state,refused=receipt is not None and receipt.refused)
    reference=ObservationFactReference(proof_fingerprint=requirement.proof_fingerprint,observer_id=proof.observer_id,phase=phase,
        source=source_ref,fact_ids=tuple(fact.fact_id for fact in facts),complete=request_matched and resource_matched,
        method='FILE_SNAPSHOT' if snapshot_only else 'FILE_DELIVERY',file_window=window,reason_codes=reasons)
    return tuple(facts),reference
