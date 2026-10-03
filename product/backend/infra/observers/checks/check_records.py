# 普通来源的正式观察桥：核对实际身份、独立请求边界与资源历史，只输出事实和缺口。
from product.backend.infra.observers.adapters.json_source import strict_json, SourceReadError
from product.backend.infra.observers.records.source_contracts import audit_source_contract
from product.backend.infra.observers.records.record_source import read_record_source
from product.backend.infra.observers.records.record_facts import record_value, request_fact
from product.backend.infra.observers.checks.check_disclosure import disclosure_proof
from product.protocols.checks.check_result import CheckObservation
from product.protocols.preparation.proof_sources import ManagedProofSourceConfig
from product.protocols.web.request import HttpRequestTemplate


def observe_records(owner, *, source, case, action_id, requirement, proof, phase, baseline_trusted,
                    cleanup, common, source_identity):
    from product.backend.infra.observers.checks.check_runtime import CheckObservedSource
    config = source.config
    if not isinstance(config,ManagedProofSourceConfig):
        return owner._unknown(common,'SOURCE_REQUIRES_MIGRATION')
    if source_identity != 'MATCH' or audit_source_contract(owner.var_dir,owner.bundle.runtime_reference,config) != source.contract:
        return owner._unknown(common,'RECORD_PROVIDER_UNAVAILABLE')
    claims = {item.identity_id:item for item in config.identity_claims}
    subject = claims.get(case.subject_test_identity_id)
    resource_owner = claims.get(case.resource_owner_test_identity_id)
    if subject is None or resource_owner is None:
        return owner._unknown(common,'RESOURCE_OWNER_UNCONFIRMED')
    try:
        # 预检查不代替正式执行时的身份事实；接口与角色字段均来自用户采用的配置。
        for identity_id in dict.fromkeys((case.subject_test_identity_id,case.resource_owner_test_identity_id,proof.observation_identity_id)):
            claim = claims[identity_id]
            response = owner.web.request(HttpRequestTemplate(method='GET',path=claim.request_path),
                case=case,action_id=action_id,identity_id=identity_id,cleanup=cleanup)
            data = strict_json(response.body,config.max_response_bytes)
            if (response.status_code != 200 or record_value(data,claim.subject_path) != claim.application_subject_id
                    or record_value(data,claim.role_path) != source.identity_roles[identity_id]):
                return owner._unknown(common,'ACTUAL_IDENTITY_MISMATCH')
        target = owner.web.target_response(case.case_id) if phase in {'AFTER','EVENTUAL'} else None
        view = read_record_source(owner.var_dir,owner.bundle.runtime_reference,config,case.resource_id,
            request_nonce=target.request_nonce if target is not None else None,
            cancelled=lambda:owner.cancelled() and not cleanup)
        snapshot = view.snapshot
        if snapshot.owner_id != resource_owner.application_subject_id:
            return owner._unknown(common,'RESOURCE_OWNER_UNCONFIRMED')
        key = (case.case_id,proof.binding_fingerprint)
        if phase in {'BASELINE','BEFORE'}:
            owner._json_histories[key] = snapshot
        before = owner._json_histories.get(key)
        complete, projection, reasons = False, None, ()
        state,closure = 'UNKNOWN','OPEN'
        if config.source_contract_id == 'TRANSACTION_HISTORY_V1':
            path = config.mappings['state'][1:]
            value = record_value(snapshot.data,path)
            projection = (case.resource_id,snapshot.owner_id,value)
            if phase in {'BASELINE','BEFORE','RECOVERY'}:
                state = 'CONFIRMED' if value == proof.expected_state else 'ABSENT'
                complete,closure = True,'CLOSED'
            elif target is not None and baseline_trusted:
                fact = request_fact(before,view,path=path,expected_state=proof.expected_state,
                    request_nonce=target.request_nonce,request_digest=target.request_digest,
                    subject_id=subject.application_subject_id,resource_id=case.resource_id,
                    owner_id=resource_owner.application_subject_id,collection=config.collection)
                state,closure,reasons = fact.state,fact.closure,fact.reason_codes
                complete = state != 'UNKNOWN'
        else:
            initial = disclosure_proof(owner=snapshot.data,response=snapshot.data,fields=proof.protected_projection,
                key=owner._disclosure_key,marker=owner.web.request_marker(case.case_id))
            projection = (case.resource_id,snapshot.owner_id,initial.owner_digest) if initial.projection_complete else None
            if phase in {'BASELINE','BEFORE','RECOVERY'}:
                complete = projection is not None
                state,closure = ('CONFIRMED','CLOSED') if complete else ('UNKNOWN','OPEN')
            elif target is not None and before is not None and baseline_trusted:
                scope = view.scope
                if (scope is not None and scope.request_nonce == target.request_nonce
                        and scope.request_digest == target.request_digest and scope.generation == before.generation == snapshot.generation):
                    data = strict_json(target.body,config.max_response_bytes)
                    state,complete,reasons = _disclosure(owner,config,proof,case,before,snapshot,data,target.status_code)
                    complete = complete and (state == 'CONFIRMED' or scope.state == 'COMPLETE')
                    closure = 'CLOSED' if complete else 'OPEN'
        terminal = bool(complete and view.scope is not None and view.scope.state == 'COMPLETE')
        if not complete and not reasons:
            reasons = ('RECORD_REQUEST_INCOMPLETE',)
        observation = CheckObservation(**common,state=state,closure=closure,complete=complete,
            reliable=complete,correlated=complete,authoritative=complete,window_end_us=owner.clock(),
            correlation_refs=(case.case_id,owner.web.request_marker(case.case_id)),reason_codes=reasons)
        return CheckObservedSource(observation,projection if complete else None,terminal,
            case.case_id if terminal else None,case.resource_id if terminal else None,proof.binding_fingerprint if terminal else None)
    except (SourceReadError,KeyError) as error:
        return owner._unknown(common,error.code if isinstance(error,SourceReadError) else 'ACTUAL_IDENTITY_MISMATCH')


def _disclosure(owner,config,proof,case,before,after,data,status):
    """有限 JSON 字段证明；禁止读取时任一受保护字段泄露都保留，未知响应不能推成未泄露。"""
    if before.data != after.data or before.version != after.version:
        return 'UNKNOWN',False,('RECORD_HISTORY_INCOMPLETE',)
    if status in {401,403} and isinstance(data,dict) and set(data) <= {'error'}:
        return 'ABSENT',True,()
    try:
        content = record_value(data,config.target_data_path)
        if (record_value(data,config.target_resource_path)!=case.resource_id
                or record_value(data,config.target_owner_path)!=before.owner_id):
            return 'UNKNOWN',False,('OPERATION_CORRELATION_INVALID',)
    except SourceReadError:
        return 'UNKNOWN',False,('DISCLOSURE_PROJECTION_INCOMPLETE',)
    results = [disclosure_proof(owner=before.data,response=content,fields=(field,),key=owner._disclosure_key,
        marker=owner.web.request_marker(case.case_id)) for field in proof.protected_projection]
    if case.permission.expectation=='DENY' and any(item.matched for item in results):
        return 'CONFIRMED',True,()
    if all(item.matched for item in results):
        return 'CONFIRMED',True,()
    return 'UNKNOWN',False,('DISCLOSURE_PROJECTION_INCOMPLETE',)
