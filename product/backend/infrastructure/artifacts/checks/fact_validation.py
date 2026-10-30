# 发布和读取共用的有限事实复核；校验冻结来源和归约一致，不访问应用或重新裁决Verdict。
from product.backend.domain.verification.business_facts import reduce_record_facts,reduce_disclosure_facts,reduce_file_facts,reduce_creation_facts
from product.protocols.preparation.proof_sources import FileProofSourceConfig
from product.protocols.checks.business_facts import ReferenceArtifactFact, CreationFactReference


def validate_frozen_facts(evidence,bundle,started_at_us,completed_at_us):
    # 发布和读取都从封存事实重做有限归约，核对观察声明；不访问当前应用，也不重算安全结论。
    sources={source.source_id:source for source in bundle.proof_sources}
    configured=next(action for action in bundle.actions if action.action_id==evidence.action_id)
    runtime_proofs={proof.binding_fingerprint:proof for proof in configured.proofs}
    case_proofs={proof.proof_fingerprint:proof for proof in evidence.case.proof_requirements}
    observations={(item.proof_fingerprint,item.observer_id,item.phase):item for item in evidence.observations}
    references={(item.proof_fingerprint,item.observer_id,item.phase):item for item in evidence.fact_references}
    # 时间、来源修订和已采用参照共同限定归属；摘要有效也不能接受超出运行窗口或来源不符的事实。
    for fact in evidence.business_facts:
        if not started_at_us<=fact.observed_at_us<=completed_at_us:raise ValueError('fact outside run window')
        for ref in fact.proofs:
            source=sources.get(ref.source_id)
            if source is None or (source.revision,source.source_fingerprint,source.config.effect_id)!=(
                ref.source_revision,ref.source_fingerprint,ref.effect_id):raise ValueError('fact source differs from frozen source')
            if isinstance(fact.data,ReferenceArtifactFact) and (not isinstance(source.config,FileProofSourceConfig)
                or (fact.data.manifest,fact.data.origin,fact.data.adoption_ref)!=(source.config.reference_artifact,
                    source.config.reference_origin,source.adoption_preflight_id)):raise ValueError('reference artifact differs from adopted standard')
    for key,observation in observations.items():
        proof=runtime_proofs[case_proofs[observation.proof_fingerprint].binding_fingerprint]
        source=next((item for item in sources.values() if 'json_'+item.source_id[4:]==observation.observer_id),None)
        if source is None:continue
        reference=references.get(key)
        if reference is None:
            if observation.state!='UNKNOWN' or any((observation.complete,observation.reliable,observation.correlated,observation.authoritative)):
                raise ValueError('record observation has no collected facts')
            continue
        if (reference.source.source_id,reference.source.source_revision,reference.source.source_fingerprint)!=(
            source.source_id,source.revision,source.source_fingerprint):raise ValueError('observation source differs from frozen source')
        snapshot=observation.phase in {'BASELINE','BEFORE','RECOVERY'}
        if source.config.source_kind=='CREATED_OBJECT_RECORDS':
            if not isinstance(reference,CreationFactReference) or getattr(configured,'created_resource',None) is None:
                raise ValueError('creation facts require an adopted creation contract')
            state,closure,complete=reduce_creation_facts(reference,evidence.business_facts,case=evidence.case)
            if reference.phase=='RECOVERY' and evidence.outcome.recovery_verified and (
                    not reference.creation_window.source_complete
                    or reference.creation_window.current_digest!=reference.creation_window.baseline_digest):
                raise ValueError('creation recovery differs from original collection')
        elif isinstance(source.config,FileProofSourceConfig):
            window=reference.file_window
            if reference.method!=('FILE_SNAPSHOT' if snapshot else 'FILE_DELIVERY') or window is None or window.expected!=source.config.reference_artifact:
                raise ValueError('file method differs from adopted source')
            if window.resource_matched and (evidence.case.resource_id,evidence.case.resource_owner_test_identity_id)!=(
                source.config.reference_resource_id,source.config.reference_owner_identity_id):raise ValueError('file resource association mismatch')
            state,closure,complete=reduce_file_facts(reference,evidence.business_facts,case=evidence.case)
        elif source.config.source_contract_id=='TRANSACTION_HISTORY_V2':
            window=reference.record_window
            if reference.method!=('STATE_SNAPSHOT' if snapshot else 'ATOMIC_STATE') or window is None or window.field_path!=source.config.mappings['state'][1:]:
                raise ValueError('observation method differs from adopted source')
            state,closure,complete=reduce_record_facts(reference,evidence.business_facts,case=evidence.case,expected_state=proof.expected_state)
        else:
            window=reference.disclosure_window
            if reference.method!=('FIELD_SNAPSHOT' if snapshot else 'FIELD_DISCLOSURE') or window is None or window.protected_paths!=proof.protected_projection:
                raise ValueError('disclosure method differs from adopted source')
            state,closure,complete=reduce_disclosure_facts(reference,evidence.business_facts,case=evidence.case)
        # 标志位必须与证据归约一致，不能直接相信文件中自称 complete 或 authoritative 的值。
        if (observation.state,observation.closure,observation.complete,observation.reliable,observation.correlated,observation.authoritative)!=(
            state,closure,complete,complete,complete,complete):raise ValueError('observation differs from sealed facts')
