# 动态创建对象的独立观察：完整集合基线、宿主请求回执、实际新对象与恢复投影分别保存。
import hashlib
import json
from product.backend.domain.verification.business_facts import reduce_creation_facts
from product.backend.infrastructure.observers.records.record_source import read_record_source
from product.backend.infrastructure.observers.checks.record_evidence import identity_facts
from product.protocols.checks.business_facts import (FactProofReference, ObjectCreationFact,
    CreationObservationWindow, CreationFactReference, seal_business_fact)
from product.protocols.checks.check_result import CheckObservation
from product.protocols.recording.created_resource import response_object_candidates


def collection_digest(view):
    raw=json.dumps([item.model_dump(mode='json') for item in view.members],sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(raw).hexdigest()


def response_resource(action, response):
    if response is None or action.created_resource is None:
        return None
    extractor=action.created_resource
    selector='$location' if extractor.kind=='LOCATION' else extractor.json_path
    candidates=response_object_candidates(response.body,tuple(response.headers.items()),response.url)
    values=[value for kind,path,value in candidates if path==selector
        and kind==('RESPONSE_LOCATION' if extractor.kind=='LOCATION' else 'RESPONSE_JSON')]
    return values[0] if len(values)==1 else None


def observe_creation(owner, *, source, case, action_id, requirement, proof, phase, cleanup, common, claims):
    from product.backend.infrastructure.observers.checks.models import CheckObservedSource
    config=source.config
    action=next(item for item in owner.bundle.actions if item.action_id==action_id)
    if getattr(action,'created_resource',None) is None:
        return owner._unknown(common,'CREATED_RESOURCE_CONTRACT_REQUIRED')
    request=owner.web.target_request(case.case_id)
    view=read_record_source(owner.var_dir,owner.bundle.runtime.reference,config,case.resource_id,
        request_nonce=request[0] if request is not None and phase not in {'BASELINE','BEFORE'} else None,
        cancelled=lambda:owner.cancelled() and not cleanup)
    key=(case.case_id,proof.binding_fingerprint)
    histories=owner._creation_histories
    if phase in {'BASELINE','BEFORE'}:
        histories[key]={'before':view,'last':view,'created':(), 'closed':False}
    entry=histories.get(key)
    if entry is None:
        return owner._unknown(common,'CREATION_BASELINE_MISSING')
    before=entry['before']
    same=view.generation==before.generation and view.collection==before.collection and view.watermark>=before.watermark
    snapshot=phase in {'BASELINE','BEFORE','RECOVERY'}
    matched=same and (phase in {'BASELINE','BEFORE'} or request is not None and view.scope is not None
        and (view.scope.request_nonce,view.scope.request_digest)==request)
    old={item.resource_id:item for item in before.members}
    fresh=tuple(event for event in view.events if event.kind=='CREATE'
        and event.sequence>before.watermark and event.member.resource_id not in old)
    # 所有新对象都取自独立提交。响应只能协助定位，不能增补不存在的创建记录。
    owned=tuple(event for event in fresh if event.member.owner_id==claims[case.resource_owner_test_identity_id].application_subject_id)
    current={item.resource_id:item for item in view.members}
    scope_ids={event.member.resource_id for event in fresh}
    unchanged=all(current.get(key)==member for key,member in old.items()) and not (set(current)-set(old)-scope_ids)
    complete=matched and not view.foreign_mutations and unchanged
    if phase in {'AFTER','EVENTUAL'}:
        # 全局水位覆盖范围比所选集合更大：并发创建会明确留下缺口，不凭时间接近归因。
        complete=complete and view.watermark-before.watermark==len(view.events) and view.scope.state=='COMPLETE'
        entry.update(last=view,created=owned,closed=complete and len(fresh)==len(owned))
    elif phase=='RECOVERY':
        complete=complete and entry['closed'] and collection_digest(view)==collection_digest(before)
    response_id=response_resource(action,owner.web.target_response(case.case_id))
    response_matched=bool(matched and len(fresh)==len(owned)==1 and response_id==owned[0].member.resource_id)
    source_ref=FactProofReference(effect_id=requirement.effect_id,proof_fingerprint=requirement.proof_fingerprint,
        source_id=source.source_id,source_revision=source.revision,source_fingerprint=source.source_fingerprint)
    shared=dict(case_id=case.case_id,request_ref=owner.web.request_marker(case.case_id),observed_at_us=owner.clock(),
        proofs=(source_ref,),complete=True)
    facts=identity_facts(shared,case,proof)
    if not snapshot and matched:
        facts.extend(seal_business_fact(**shared,collector_kind='CONTROLLED_RECORDS',data=ObjectCreationFact(
            generation=view.generation,sequence=event.sequence,resource_id=event.member.resource_id,
            incarnation=event.member.incarnation,subject_identity_id=case.subject_test_identity_id,
            owner_identity_id=case.resource_owner_test_identity_id)) for event in owned)
    reasons=() if complete else ('CREATION_WINDOW_INCOMPLETE',)
    if not snapshot and matched and owned and not response_matched:
        reasons=tuple(dict.fromkeys((*reasons,'CREATION_RESPONSE_MISMATCH')))
    window=CreationObservationWindow(generation=view.generation,baseline_watermark=before.watermark,
        current_watermark=view.watermark,baseline_digest=collection_digest(before),current_digest=collection_digest(view),
        scope_state='MISSING' if view.scope is None else view.scope.state,request_matched=matched,
        source_complete=complete,created_count=len(fresh),response_resource_id=response_id,response_matched=response_matched)
    reference=CreationFactReference(proof_fingerprint=requirement.proof_fingerprint,observer_id=proof.observer_id,
        phase=phase,fact_ids=tuple(fact.fact_id for fact in facts),source=source_ref,
        method='CREATION_SNAPSHOT' if snapshot else 'OBJECT_CREATION',creation_window=window,complete=matched,reason_codes=reasons)
    state,closure,proven=reduce_creation_facts(reference,facts,case=case)
    observation=CheckObservation(**common,state=state,closure=closure,complete=proven,reliable=proven,correlated=proven,
        authoritative=proven,window_end_us=owner.clock(),correlation_refs=(case.case_id,owner.web.request_marker(case.case_id)),reason_codes=reasons)
    owner._evidence_sources[observation.model_dump_json()]=(tuple(facts),reference)
    projection=(view.generation,collection_digest(view)) if complete else None
    return CheckObservedSource(observation,projection)
