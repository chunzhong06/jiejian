# 将封存的有限提交事实归约为观察；执行与发布读取共用，不访问目标、不裁决Verdict。
from product.protocols.checks.business_facts import CommittedStateFact,IdentityCheckFact,FieldDisclosureFact,ReferenceArtifactFact,FileReceiptFact


def reduce_creation_facts(reference,facts,*,case):
    """肯定事实保留历史创建；未创建必须有独立完整请求窗，响应编号本身不能证明业务结果。"""
    from product.protocols.checks.business_facts import ObjectCreationFact
    window=reference.creation_window
    selected=[fact for fact in facts if fact.fact_id in reference.fact_ids]
    if not reference.complete or not window.request_matched or len(selected)!=len(reference.fact_ids):
        return 'UNKNOWN','OPEN',False
    identities={fact.data.identity_id for fact in selected if isinstance(fact.data,IdentityCheckFact)
        and fact.complete and fact.data.subject_match==fact.data.role_match=='MATCH'}
    if not {case.subject_test_identity_id,case.resource_owner_test_identity_id}<=identities:
        return 'UNKNOWN','OPEN',False
    if reference.method=='CREATION_SNAPSHOT':
        return ('ABSENT','CLOSED',True) if window.source_complete else ('UNKNOWN','OPEN',False)
    created=[fact for fact in selected if isinstance(fact.data,ObjectCreationFact)]
    for fact in created:
        data=fact.data
        if (not fact.complete or data.generation!=window.generation
            or not window.baseline_watermark<data.sequence<=window.current_watermark
            or (data.subject_identity_id,data.owner_identity_id)!=(case.subject_test_identity_id,case.resource_owner_test_identity_id)):
            return 'UNKNOWN','OPEN',False
    if created:
        return 'CONFIRMED','CLOSED',True
    if window.source_complete and window.scope_state=='COMPLETE' and window.created_count==0:
        return 'ABSENT','CLOSED',True
    return 'UNKNOWN','OPEN',False


def reduce_record_facts(reference,facts,*,case,expected_state):
    """只有完整关联事实能证明发生；未发生另需完整请求窗及连续版本。"""
    window=reference.record_window
    if not reference.complete or window is None or not window.request_matched:
        return 'UNKNOWN','OPEN',False
    records=[fact for fact in facts if fact.fact_id in reference.fact_ids]
    if len(records)!=len(reference.fact_ids):return 'UNKNOWN','OPEN',False
    identities={fact.data.identity_id for fact in records if isinstance(fact.data,IdentityCheckFact)
        and fact.complete and fact.data.subject_match==fact.data.role_match=='MATCH'}
    if not {case.subject_test_identity_id,case.resource_owner_test_identity_id}<=identities:
        return 'UNKNOWN','OPEN',False
    if reference.method=='STATE_SNAPSHOT':
        if not window.source_complete:return 'UNKNOWN','OPEN',False
        return ('CONFIRMED' if window.after_value==expected_state else 'ABSENT'),'CLOSED',True
    commits=sorted((fact for fact in records if isinstance(fact.data,CommittedStateFact)),key=lambda fact:fact.data.scope_ordinal)
    value,version,happened=window.before_value,window.before_version,False
    for ordinal,fact in enumerate(commits):
        data=fact.data
        changes=[item for item in data.changes if item.proof_fingerprint==reference.proof_fingerprint and item.path==window.field_path]
        if (not fact.complete or len(changes)!=1 or data.scope_ordinal!=ordinal
            or data.generation!=window.generation or data.before_version!=version
            or (data.subject_identity_id,data.owner_identity_id,data.resource_id)!=(case.subject_test_identity_id,
                case.resource_owner_test_identity_id,case.resource_id) or changes[0].before!=value):
            return 'UNKNOWN','OPEN',False
        after=changes[0].after
        happened=happened or (value!=after and (expected_state is None or after==expected_state))
        value,version=after,data.after_version
    if happened:return 'CONFIRMED','CLOSED',True
    last=commits[-1].data.operation_id if commits else window.before_operation
    if (not window.source_complete or window.scope_state!='COMPLETE' or len(commits)!=window.operation_count
        or value!=window.after_value or version!=window.after_version or last!=window.after_operation):
        return 'UNKNOWN','OPEN',False
    return 'ABSENT','CLOSED',True


def reduce_disclosure_facts(reference,facts,*,case):
    """只比较采集器封存的逐字段摘要；任一泄露可证明禁止后果，正常读取须覆盖全部字段。"""
    window=reference.disclosure_window
    selected=[fact for fact in facts if fact.fact_id in reference.fact_ids]
    if not reference.complete or window is None or not window.request_matched or len(selected)!=len(reference.fact_ids):
        return 'UNKNOWN','OPEN',False
    identities={fact.data.identity_id for fact in selected if isinstance(fact.data,IdentityCheckFact)
        and fact.complete and fact.data.subject_match==fact.data.role_match=='MATCH'}
    if not {case.subject_test_identity_id,case.resource_owner_test_identity_id}<=identities:
        return 'UNKNOWN','OPEN',False
    if reference.method=='FIELD_SNAPSHOT':
        return ('CONFIRMED','CLOSED',True) if window.current_digest is not None else ('UNKNOWN','OPEN',False)
    if not window.source_unchanged or window.baseline_digest is None or window.baseline_digest!=window.current_digest:
        return 'UNKNOWN','OPEN',False
    if window.rejected_empty_response:
        return ('ABSENT','CLOSED',True) if window.scope_state=='COMPLETE' else ('UNKNOWN','OPEN',False)
    if not window.resource_matched:return 'UNKNOWN','OPEN',False
    fields={}
    for fact in selected:
        data=fact.data
        if not isinstance(data,FieldDisclosureFact):continue
        if (data.subject_identity_id,data.owner_identity_id,data.resource_id)!=(case.subject_test_identity_id,
            case.resource_owner_test_identity_id,case.resource_id):return 'UNKNOWN','OPEN',False
        for field in data.fields:
            if field.path in fields and fields[field.path]!=field:return 'UNKNOWN','OPEN',False
            fields[field.path]=field
    matches=[fields[path].matched for path in window.protected_paths if path in fields]
    confirmed=any(matches) if case.permission.expectation=='DENY' else len(matches)==len(window.protected_paths) and all(matches)
    return ('CONFIRMED','CLOSED',True) if confirmed else ('UNKNOWN','OPEN',False)


def reduce_file_facts(reference,facts,*,case):
    """完整实体匹配优先于HTTP状态；只有可靠拒绝和闭合才能支持未交付。"""
    window=reference.file_window
    selected=[fact for fact in facts if fact.fact_id in reference.fact_ids]
    if not reference.complete or window is None or not window.request_matched or not window.resource_matched or len(selected)!=len(reference.fact_ids):
        return 'UNKNOWN','OPEN',False
    identities={fact.data.identity_id for fact in selected if isinstance(fact.data,IdentityCheckFact)
        and fact.complete and fact.data.subject_match==fact.data.role_match=='MATCH'}
    if not {case.subject_test_identity_id,case.resource_owner_test_identity_id}<=identities or not any(
        isinstance(fact.data,ReferenceArtifactFact) and fact.data.manifest==window.expected and fact.complete for fact in selected):
        return 'UNKNOWN','OPEN',False
    if reference.method=='FILE_SNAPSHOT':return 'CONFIRMED','CLOSED',True
    receipts=[fact.data for fact in selected if isinstance(fact.data,FileReceiptFact) and fact.complete]
    if len(receipts)!=1:return 'UNKNOWN','OPEN',False
    receipt=receipts[0]
    if (receipt.subject_identity_id,receipt.owner_identity_id,receipt.resource_id,receipt.expected)!=(
        case.subject_test_identity_id,case.resource_owner_test_identity_id,case.resource_id,window.expected):
        return 'UNKNOWN','OPEN',False
    if receipt.complete and receipt.comparison=='MATCH':return 'CONFIRMED','CLOSED',True
    if receipt.complete and window.refused and window.scope_state=='COMPLETE':return 'ABSENT','CLOSED',True
    return 'UNKNOWN','OPEN',False
