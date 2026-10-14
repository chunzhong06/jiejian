# 将Agent修正提议绑定当前问题；保留修订审计，人的决定只由原GUI事务生成。
from product.backend.core.boundaries.candidate_corrections import dependency_payload, SavedReviewSuggestion, suggestion_dependency_fingerprint
from product.backend.core.boundaries.candidate_reviews import boundary_review_items
from product.backend.core.errors import ErrorCode, JiejianError


def carry_assistance(current, value, command):
    old = {item['issue_id']: item for item in boundary_review_items(current)} if current else {}
    new = {item['issue_id']: item for item in boundary_review_items(value)}
    suggestions = {item.issue_id: item for item in getattr(current, 'review_suggestions', ())}
    if len({item.issue_id for item in command.review_suggestions}) != len(command.review_suggestions):
        raise JiejianError(ErrorCode.INPUT_INVALID, '同一问题只能提交一条纠正建议')
    for suggestion in command.review_suggestions:
        item = old.get(suggestion.issue_id)
        target = new.get(suggestion.issue_id)
        if item is None or target is None or item['issue_fingerprint'] != suggestion.issue_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '请读取已有问题及最新指纹后提交纠正建议', details={'reason':'CONFLICT'})
        if target['source'] == 'unsupported_constraints' and suggestion.outcome in {'NOT_SEPARATE_ACTION', 'REPRESENTED_BY_RULES'}:
            raise JiejianError(ErrorCode.INPUT_INVALID, '能力限制不能通过合并接口或不建模来消除')
        if not set(suggestion.permission_item_ids) <= {item.item_id for item in value.content.permissions}:
            raise JiejianError(ErrorCode.INPUT_INVALID, '纠正建议引用了不存在的权限')
        if suggestion.dependencies is not None:
            try:
                dependency_payload(value, suggestion.dependencies)
            except ValueError:
                raise JiejianError(ErrorCode.INPUT_INVALID, '请补齐纠正建议关联的要求、权限、动作与角色') from None
        data = suggestion.model_dump()
        data['issue_fingerprint'] = target['issue_fingerprint']
        suggestions[suggestion.issue_id] = SavedReviewSuggestion(**data,
            dependency_fingerprint=suggestion_dependency_fingerprint(value, suggestion))
    notes = {item.note_id: item for item in getattr(current, 'supporting_notes', ())}
    if len({item.note_id for item in command.supporting_notes}) != len(command.supporting_notes):
        raise JiejianError(ErrorCode.INPUT_INVALID, '辅助说明标识不能重复')
    for note in command.supporting_notes:
        if not set(note.related_requirement_ids) <= {item.requirement_id for item in value.content.requirement_sources}:
            raise JiejianError(ErrorCode.INPUT_INVALID, '辅助说明只能关联已有要求')
        if note.state == 'WITHDRAWN' and (note.note_id not in notes or note.text != notes[note.note_id].text):
            raise JiejianError(ErrorCode.INPUT_INVALID, '撤回辅助说明时必须保留已保存原文')
        notes[note.note_id] = note
    if len(suggestions) > 20 or len(notes) > 100:
        raise JiejianError(ErrorCode.INPUT_INVALID, '本候选辅助记录已达上限；请沿用稳定标识修订，不能重复创建相同说明')
    # 原问题和要求由既有protect_*强制保留；将文字抄入辅助说明不能清除它们。
    return value.model_copy(update={'review_suggestions':tuple(suggestions.values()), 'supporting_notes':tuple(notes.values())})
