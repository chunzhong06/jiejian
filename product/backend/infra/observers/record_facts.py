# 解释通用记录组件的真实事务；每一中间变化保留，最终恢复不抹去已发生事实。
from __future__ import annotations

from product.backend.infra.observers.json_source import JsonHistoryFact, SourceReadError


def record_value(data, path):
    value = data
    for part in path:
        if not isinstance(value, dict) or part not in value:
            raise SourceReadError('MAPPING_MISSING')
        value = value[part]
    return value


def transaction_fact(before, view, *, path, expected_state, request_key, subject_id, resource_id, owner_id, collection):
    if before is None or view.operation is None:
        return JsonHistoryFact('UNKNOWN','OPEN',('HISTORY_BASELINE_MISSING',))
    after, operation = view.snapshot, view.operation
    if (before.generation != after.generation or before.generation != operation.generation):
        return JsonHistoryFact('UNKNOWN','OPEN',('HISTORY_GENERATION_CHANGED',))
    if not (before.collection == after.collection == operation.collection == collection
            and before.resource_id == after.resource_id == operation.resource_id == resource_id
            and before.owner_id == after.owner_id == operation.owner_id == owner_id
            and operation.subject_id == subject_id and operation.request_key == request_key
            and operation.before_version == before.version
            and operation.after_version == after.version == before.version + 1
            and after.last_operation_id == operation.operation_id):
        return JsonHistoryFact('UNKNOWN','OPEN',('OPERATION_CORRELATION_INVALID',))
    current = before.data
    happened = False
    try:
        for ordinal, transition in enumerate(operation.transitions):
            if transition.ordinal != ordinal or transition.before != current:
                return JsonHistoryFact('UNKNOWN','OPEN',('RECORD_HISTORY_INCOMPLETE',))
            initial = record_value(transition.before,path)
            final = record_value(transition.after,path)
            if initial != final and (expected_state is None or final == expected_state):
                happened = True
            current = transition.after
        if current != after.data:
            return JsonHistoryFact('UNKNOWN','OPEN',('RECORD_HISTORY_INCOMPLETE',))
    except SourceReadError:
        return JsonHistoryFact('UNKNOWN','OPEN',('MAPPING_MISSING',))
    return JsonHistoryFact('CONFIRMED' if happened else 'ABSENT','CLOSED',
        ('BUSINESS_EFFECT_RECORDED' if happened else 'COMPLETE_HISTORY_UNCHANGED',))


def request_fact(before, view, *, path, expected_state, request_nonce, request_digest,
                 subject_id, resource_id, owner_id, collection):
    """发生可由已提交记录证明；未发生还要求整个真实请求完成且不存在遗漏、并发或后续写入。"""
    scope, after = view.scope, view.snapshot
    if before is None or scope is None:
        return JsonHistoryFact('UNKNOWN','OPEN',('HISTORY_BASELINE_MISSING',))
    if before.generation != after.generation or scope.generation != before.generation:
        return JsonHistoryFact('UNKNOWN','OPEN',('HISTORY_GENERATION_CHANGED',))
    if (scope.request_nonce != request_nonce or scope.request_digest != request_digest
            or (before.collection,before.resource_id,before.owner_id) != (collection,resource_id,owner_id)
            or (after.collection,after.resource_id,after.owner_id) != (collection,resource_id,owner_id)):
        return JsonHistoryFact('UNKNOWN','OPEN',('OPERATION_CORRELATION_INVALID',))
    current, version, happened = before.data, before.version, False
    for operation in view.operations:
        if (operation.scope_id != scope.scope_id or operation.generation != scope.generation
                or (operation.collection,operation.resource_id,operation.owner_id,operation.subject_id)
                    != (collection,resource_id,owner_id,subject_id)
                or operation.before_version != version or operation.after_version != version+1):
            return JsonHistoryFact('UNKNOWN','OPEN',('OPERATION_CORRELATION_INVALID',))
        try:
            for ordinal, transition in enumerate(operation.transitions):
                if transition.ordinal != ordinal or transition.before != current:
                    return JsonHistoryFact('UNKNOWN','OPEN',('RECORD_HISTORY_INCOMPLETE',))
                initial, final = record_value(current,path), record_value(transition.after,path)
                happened = happened or (initial != final and (expected_state is None or final == expected_state))
                current = transition.after
        except SourceReadError:
            return JsonHistoryFact('UNKNOWN','OPEN',('MAPPING_MISSING',))
        version = operation.after_version
    if happened:
        # 后续完成缺口不能抹去已经关联到本次请求的禁止变化。
        return JsonHistoryFact('CONFIRMED','CLOSED',('BUSINESS_EFFECT_RECORDED',))
    if (scope.state != 'COMPLETE' or current != after.data or version != after.version
            or (view.operations and after.last_operation_id != view.operations[-1].operation_id)):
        return JsonHistoryFact('UNKNOWN','OPEN',('RECORD_REQUEST_INCOMPLETE',))
    return JsonHistoryFact('ABSENT','CLOSED',('COMPLETE_HISTORY_UNCHANGED',))
