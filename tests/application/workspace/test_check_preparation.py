"""同动作的范围裁剪不能混入另一结果，原槽位和合法对照必须保留。"""
from types import SimpleNamespace
import pytest
from tests.support.builders.preparation.action_preparation import build_preparation_harness
from tests.support.builders.checks.assurance import permission, SECOND_EFFECT
from product.backend.application.preparation.scope import check_preparation
from product.backend.application.preparation.models import PreparationStatus as Status
from product.backend.application.workspace.preparation import preparation_task
from product.backend.domain.errors import JiejianError

pytestmark = [pytest.mark.level3, pytest.mark.database]


def test_same_action_unselected_effect_never_becomes_the_next_task(tmp_path):
    h = build_preparation_harness(tmp_path, state_changing=False)
    try:
        other = permission(2, effects=(SECOND_EFFECT,)).model_copy(update={'project_id': h.project_id})
        with h.core.uow_factory() as work:
            work.permission_intents.add_revision(other)
            work.commit()
        boundary = h.core.business_boundaries.view(h.project_id)
        full = h.core.preparation.get(h.project_id)
        action = full.actions[0]
        def ready(item):
            return item.model_copy(update={'status': Status.SATISFIED, 'reason_codes': ()})
        # 仅替代只读检查结果；规则和依赖仍来自正式数据库，不伪造执行成功。
        action = action.model_copy(update={'execution': ready(action.execution),
            'resources': tuple(ready(item) for item in action.resources),
            'effect_evidence': tuple(ready(item) if item.effect_id != SECOND_EFFECT else item for item in action.effect_evidence)})
        original = next(item for item in boundary.permission_intents if item.intent_id != other.intent_id)
        scoped = check_preparation(boundary, full.model_copy(update={'actions': (action,)}), (original,))
        assert scoped.preparation_complete
        assert SECOND_EFFECT not in {item.effect_id for item in scoped.actions[0].effect_evidence}
        identity_keys=lambda slots: [(item.requirement.slot_id,item.requirement.ordinal,item.test_identity_id) for item in slots]
        assert identity_keys(scoped.actions[0].identity_requirements.slots) == identity_keys(action.identity_requirements.slots)
        assert scoped.actions[0].identity_requirements.slots[0].requirement.required_by_intent_ids == (original.intent_id,)
        assert all(other.intent_id not in item.permission_ids for item in scoped.impacts)
        reading = SimpleNamespace(recordings=(), parent_for=lambda _: None)
        understanding = h.core.application_understanding.get(h.project_id)
        assert preparation_task(boundary, scoped, understanding, reading) is None
        assert preparation_task(boundary, full.model_copy(update={'actions': (action,)}), understanding, reading).effect_id == SECOND_EFFECT
        missing = action.model_copy(update={'effect_evidence': full.actions[0].effect_evidence})
        selected_second = check_preparation(boundary, full.model_copy(update={'actions': (missing,)}), (other,))
        assert preparation_task(boundary, selected_second, understanding, reading).effect_id == SECOND_EFFECT
        assert preparation_task(boundary, full.model_copy(update={'actions': (missing,)}), understanding, reading).effect_id == h.effect_id
    finally:
        h.close()


def test_preview_guidance_is_bound_to_the_preview_and_never_creates_a_run(tmp_path):
    h = build_preparation_harness(tmp_path)
    try:
        preview = h.core.checks.preview(h.project_id)
        assert preview.preparation_work.plan_fingerprint == preview.plan_fingerprint
        assert preview.preparation_work.project_id == h.project_id
        assert preview.preparation_work.actions[0].action_revision == 1
        assert preview.preparation_work.primary_task.business_action_id == h.action.action_id
        with h.core.uow_factory() as work:
            assert not work.runs.list_for_project(h.project_id)
    finally:
        h.close()


def test_stale_rule_is_not_replaced_by_another_revision(tmp_path):
    h = build_preparation_harness(tmp_path)
    try:
        boundary = h.core.business_boundaries.view(h.project_id)
        reference = boundary.permission_intents[0].model_copy(update={'revision': 99})
        with pytest.raises(JiejianError):
            check_preparation(boundary, h.core.preparation.get(h.project_id), (reference,))
    finally:
        h.close()
