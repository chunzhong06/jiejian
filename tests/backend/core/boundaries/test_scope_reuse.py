# 范围同意只沿用未变的要求；正式规则依据变化不能替人同意新要求或解除暂缓。
from types import SimpleNamespace

from product.backend.core.boundaries.candidate_scope import RequirementSource, ScopeDecision, scope_items
from product.backend.core.boundaries.entities import boundary_sha256


def candidate(source, decisions=(), basis='rb_'+'a'*64):
    return SimpleNamespace(candidate_id='rcd_'+'1'*32, basis_id=basis,
        content=SimpleNamespace(requirement_sources=(source,)), scope_decisions=decisions, scope_references=())


def test_legacy_scope_survives_other_rule_revision_without_rewriting_receipt():
    source = RequirementSource(requirement_id='req_'+'1'*16, title='内部包', origin='USER',
        source_excerpt='评审不能取得内部包', interpretation='检查本次过程中的内部包交付')
    original = candidate(source)
    decision = ScopeDecision(operation_id='2'*32, expected_basis_id=original.basis_id,
        expected_revision=1, requirement_id=source.requirement_id,
        requirement_fingerprint=boundary_sha256([original.candidate_id, original.basis_id, source.model_dump(mode='json', exclude={'permission_item_ids'})]),
        disposition='IN_SCOPE', requirement=source.interpretation, reason='确认原意', time_scope='CHECK_WINDOW',
        output_revision=2, created_at_us=1)
    updated = candidate(source, (decision,), 'rb_'+'b'*64)
    assert scope_items(updated)[0]['status'] == 'CONFIRMED'
    assert scope_items(updated)[0]['decision'] is decision
    changed = source.model_copy(update={'interpretation':'检查任意历史中的内部包交付'})
    assert scope_items(candidate(changed, (decision,), updated.basis_id))[0]['status'] == 'STALE'
    assert scope_items(candidate(source.model_copy(update={'requirement_id':'req_'+'3'*16}), (decision,)))[0]['status'] == 'NEEDS_DECISION'
    assert scope_items(candidate(source, (decision.model_copy(update={'disposition':'DEFER'}),), updated.basis_id))[0]['status'] == 'DEFER'


def test_new_scope_fingerprint_is_stable_only_for_same_requirement_meaning():
    source = RequirementSource(requirement_id='req_'+'1'*16, title='公开预览', origin='USER',
        source_excerpt='评审可以预览', interpretation='保留正常预览对照')
    before = scope_items(candidate(source))[0]['fingerprint']
    mapped = source.model_copy(update={'permission_item_ids':('pperm_'+'2'*16,)})
    assert scope_items(candidate(mapped, basis='rb_'+'b'*64))[0]['fingerprint'] == before
    changed = source.model_copy(update={'source_excerpt':'评审不可以预览'})
    assert scope_items(candidate(changed))[0]['fingerprint'] != before
