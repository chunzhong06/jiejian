# 普通来源的正式观察桥：核对实际身份、独立请求边界与资源历史，只输出事实和缺口。
from product.backend.infrastructure.observers.adapters.json_source import strict_json, SourceReadError
from product.backend.infrastructure.observers.records.source_contracts import audit_source_contract
from product.backend.infrastructure.observers.records.record_source import read_record_source
from product.backend.infrastructure.observers.records.record_facts import record_value
from product.backend.infrastructure.observers.checks.check_disclosure import disclosure_proof
from product.protocols.checks.check_result import CheckObservation
from product.protocols.preparation.proof_sources import AtomicProofSourceConfig,FileProofSourceConfig
from product.protocols.web.request import HttpRequestTemplate


def observe_records(owner, *, source, case, action_id, requirement, proof, phase, baseline_trusted,
                    cleanup, common):
    from product.backend.infrastructure.observers.checks.models import CheckObservedSource
    config = source.config
    if not isinstance(config,AtomicProofSourceConfig):
        return owner._unknown(common,'SOURCE_REQUIRES_MIGRATION')
    if audit_source_contract(owner.var_dir,owner.bundle.runtime.reference,config) != source.contract:
        return owner._unknown(common,'RECORD_PROVIDER_UNAVAILABLE')
    claims = {item.identity_id:item for item in config.identity_claims}
    subject = claims.get(case.subject_test_identity_id)
    resource_owner = claims.get(case.resource_owner_test_identity_id)
    anonymous = case.subject_test_identity_id is None
    if (subject is None and not anonymous) or resource_owner is None:
        return owner._unknown(common,'RESOURCE_OWNER_UNCONFIRMED')
    try:
        if anonymous and owner.web.verify_identity(None, case, cleanup=cleanup) != 'MATCH':
            return owner._unknown(common, 'ANONYMOUS_PRINCIPAL_UNCONFIRMED')
        actual_identities = {}
        # 预检查不代替正式执行时的身份事实；接口与角色字段均来自用户采用的配置。
        for identity_id in dict.fromkeys((case.subject_test_identity_id,case.resource_owner_test_identity_id,proof.observation_identity_id)):
            if identity_id is None:
                continue
            claim = claims[identity_id]
            response = owner.web.request(HttpRequestTemplate(method='GET',path=claim.request_path),
                case=case,action_id=action_id,identity_id=identity_id,cleanup=cleanup)
            data = strict_json(response.body,config.max_response_bytes)
            if (response.status_code != 200 or record_value(data,claim.subject_path) != claim.application_subject_id
                    or record_value(data,claim.role_path) != source.identity_roles[identity_id]):
                return owner._unknown(common,'ACTUAL_IDENTITY_MISMATCH')
            actual_identities[identity_id] = data
        if config.source_kind in {'CREATED_OBJECT_RECORDS','SQLITE_OBJECTS'}:
            if case.permission.conditions is not None and phase in {'BASELINE', 'BEFORE'}:
                from product.protocols.checks.conditions import ObservedPermissionConditions
                owner.condition_observations[(case.case_id, requirement.proof_fingerprint)] = ObservedPermissionConditions(
                    proof_fingerprint=requirement.proof_fingerprint, source_id=source.source_id,
                    source_fingerprint=source.source_fingerprint,
                    principal='ANONYMOUS' if anonymous else 'AUTHENTICATED')
            from product.backend.infrastructure.observers.checks.creation_evidence import observe_creation
            return observe_creation(owner,source=source,case=case,action_id=action_id,requirement=requirement,
                proof=proof,phase=phase,cleanup=cleanup,common=common,claims=claims)
        target = owner.web.target_response(case.case_id) if phase in {'AFTER','EVENTUAL'} else None
        view = read_record_source(owner.var_dir,owner.bundle.runtime.reference,config,case.resource_id,
            request_nonce=target.request_nonce if target is not None else None,
            cancelled=lambda:owner.cancelled() and not cleanup,verified_subject='anonymous' if anonymous else subject.application_subject_id)
        snapshot = view.snapshot
        if snapshot.owner_id != resource_owner.application_subject_id:
            return owner._unknown(common,'RESOURCE_OWNER_UNCONFIRMED')
        if case.permission.conditions is not None and phase in {'BASELINE','BEFORE'}:
            from product.protocols.checks.conditions import ObservedPermissionConditions
            def field(data, path):
                if path is None:
                    return None
                try:
                    value = record_value(data, path)
                    return value if isinstance(value, str) else None
                except SourceReadError:
                    return None
            expected = case.permission.conditions
            supported = ((not expected.resource_states or 'condition_state' in config.mappings)
                and (expected.tenant is None or ('tenant' in config.mappings and resource_owner.tenant_path is not None
                    and subject is not None and subject.tenant_path is not None)))
            context = ObservedPermissionConditions(proof_fingerprint=requirement.proof_fingerprint,
                source_id=source.source_id, source_fingerprint=source.source_fingerprint,
                principal='ANONYMOUS' if anonymous else 'AUTHENTICATED',
                subject_tenant=None if anonymous else field(actual_identities[case.subject_test_identity_id], subject.tenant_path),
                owner_tenant=field(actual_identities[case.resource_owner_test_identity_id], resource_owner.tenant_path),
                resource_tenant=field(snapshot.data, config.mappings.get('tenant', ())[1:] or None),
                resource_state=field(snapshot.data, config.mappings.get('condition_state', ())[1:] or None))
            if supported:
                owner.condition_observations[(case.case_id, requirement.proof_fingerprint)] = context
        key = (case.case_id,proof.binding_fingerprint)
        if phase in {'BASELINE','BEFORE'}:
            owner._json_histories[key] = snapshot
        before = owner._json_histories.get(key)
        complete, projection, reasons = False, None, ()
        state,closure = 'UNKNOWN','OPEN'
        facts,reference=(),None
        if isinstance(config,FileProofSourceConfig):
            from product.backend.domain.boundaries.entities import boundary_sha256
            from product.backend.infrastructure.observers.checks.file_evidence import collect_file_evidence
            from product.backend.domain.verification.business_facts import reduce_file_facts
            projection=(case.resource_id,snapshot.owner_id,boundary_sha256(snapshot.data))
            if phase in {'BASELINE','BEFORE','RECOVERY'} or target is not None and baseline_trusted:
                facts,reference=collect_file_evidence(source=source,case=case,requirement=requirement,proof=proof,
                    phase=phase,before=before,view=view,target=target,clock=owner.clock(),marker=owner.web.request_marker(case.case_id))
                state,closure,complete=reduce_file_facts(reference,facts,case=case)
                reasons=reference.reason_codes
        elif config.source_contract_id == 'TRANSACTION_HISTORY_V2':
            path = config.mappings['state'][1:]
            value = record_value(snapshot.data,path)
            projection = (case.resource_id,snapshot.owner_id,value)
            if phase in {'BASELINE','BEFORE','RECOVERY'} or target is not None and baseline_trusted:
                from product.backend.infrastructure.observers.checks.record_evidence import collect_record_evidence
                from product.backend.domain.verification.business_facts import reduce_record_facts
                facts,reference=collect_record_evidence(source=source,case=case,requirement=requirement,proof=proof,
                    phase=phase,before=before,view=view,target=target,clock=owner.clock(),
                    marker=owner.web.request_marker(case.case_id),claims=claims)
                state,closure,complete=reduce_record_facts(reference,facts,case=case,expected_state=proof.expected_state)
                if phase in {'AFTER','EVENTUAL'} and complete:
                    reasons=('BUSINESS_EFFECT_RECORDED' if state=='CONFIRMED' else 'COMPLETE_HISTORY_UNCHANGED',)
        else:
            initial = disclosure_proof(owner=snapshot.data,response=snapshot.data,fields=proof.protected_projection,
                key=owner._disclosure_key,marker=owner.web.request_marker(case.case_id))
            projection = (case.resource_id,snapshot.owner_id,initial.owner_digest) if initial.projection_complete else None
            if phase in {'BASELINE','BEFORE','RECOVERY'} or target is not None and before is not None and baseline_trusted:
                from product.backend.infrastructure.observers.checks.disclosure_evidence import collect_disclosure_evidence
                from product.backend.domain.verification.business_facts import reduce_disclosure_facts
                facts,reference=collect_disclosure_evidence(source=source,case=case,requirement=requirement,proof=proof,
                    phase=phase,before=before,view=view,target=target,clock=owner.clock(),
                    marker=owner.web.request_marker(case.case_id),key=owner._disclosure_key)
                state,closure,complete=reduce_disclosure_facts(reference,facts,case=case)
                if not complete:reasons=reference.reason_codes or ('DISCLOSURE_PROJECTION_INCOMPLETE',)
        terminal = bool(complete and view.scope is not None and view.scope.state == 'COMPLETE')
        if not complete and not reasons:
            reasons = ('RECORD_REQUEST_INCOMPLETE',)
        observation = CheckObservation(**common,state=state,closure=closure,complete=complete,
            reliable=complete,correlated=complete,authoritative=complete,window_end_us=owner.clock(),
            correlation_refs=(case.case_id,owner.web.request_marker(case.case_id)),reason_codes=reasons)
        if reference is not None:
            owner._evidence_sources[observation.model_dump_json()]=(facts,reference)
        return CheckObservedSource(observation,projection if complete else None,terminal,
            case.case_id if terminal else None,case.resource_id if terminal else None,proof.binding_fingerprint if terminal else None)
    except (SourceReadError,KeyError) as error:
        return owner._unknown(common,error.code if isinstance(error,SourceReadError) else 'ACTUAL_IDENTITY_MISMATCH')
    except ValueError:
        return owner._unknown(common,'FACT_PROJECTION_UNAVAILABLE')
