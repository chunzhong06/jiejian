# 验证准备任务的全局优先级、真实账号分配和严格录制来源定位。

from types import SimpleNamespace

import pytest

from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.permission_semantics import PermissionExpectation
from product.backend.core.recording import RecordingPurpose, RecordingState
from product.backend.workflows.preparation.models import PreparationStatus as Status
from tests.fixtures.action_preparation import add_recording, build_preparation_harness
from tests.fixtures.assurance import permission

pytestmark = [pytest.mark.database, pytest.mark.essential]


@pytest.fixture
def harness(tmp_path):
    value = build_preparation_harness(tmp_path)
    yield value
    value.close()


def _task(harness):
    return harness.core.workspace.get(harness.project_id).primary_task


def _finish(harness, **kwargs):
    recording = add_recording(harness, **kwargs)
    harness.core.recording_lifecycle.finalize(recording.recording_id, var_dir=harness.var_dir, now_us=100)
    return recording


def _permission(harness, number=2, **kwargs):
    item = permission(number, **kwargs).model_copy(update={"project_id": harness.project_id})
    with harness.core.uow_factory() as work:
        work.permission_intents.add_revision(item)
        work.commit()
    return item


def test_identity_creation_login_and_stale_task_context(tmp_path):
    h = build_preparation_harness(tmp_path, identity_count=0)
    try:
        first = _task(h)
        assert first.task_kind == "PREPARE_TEST_IDENTITY" and first.test_identity_id is None
        assert first.business_actor_id == h.actor.actor_id and first.action_revision == 1
        assert first.can_execute and first.route == "/tests"
        assert _task(h) == first
        identity = h.core.test_identities.create(h.project_id, actor_id=h.actor.actor_id, actor_revision=1, label="普通成员账号 1")
        second = _task(h)
        assert second.test_identity_id == identity.identity_id and second.can_execute
        assert second.task_id != first.task_id
    finally:
        h.close()


def test_stale_identity_cannot_start_login(harness):
    identity = harness.identities[0]
    harness.core.secret_store.delete(identity.bearer_secret_ref)
    task = _task(harness)
    assert task.task_kind == "PREPARE_TEST_IDENTITY"
    assert not task.can_execute
    assert task.user_responsibility == "请先在业务边界中复核账号所属的业务主体。"


def test_distinct_accounts_allow_subject_and_exact_missing_resource_owner(tmp_path):
    h = build_preparation_harness(tmp_path, identity_count=2)
    try:
        _permission(h, relation=PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT, expectation=PermissionExpectation.DENY)
        prep = h.core.preparation.get(h.project_id).actions[0]
        slots = prep.identity_requirements.slots
        assert len(slots) == 2 and len({item.test_identity_id for item in slots}) == 2
        assert {item.requirement.ordinal for item in slots} == {1, 2}
        allowed = next(item for item in prep.assurance_contract.identity_requirements.permissions
                       if item.permission.intent_id == "pin_" + f"{1:032x}")
        subject = next(item for item in slots if item.requirement.slot_id == allowed.subject_slot_id)
        task = _task(h)
        assert task.task_kind == "DEMONSTRATE_ACTION"
        assert task.test_identity_id == subject.test_identity_id and task.recording_purpose == "TARGET"
        # 先给非 owner 账号建立执行材料，才能真实形成指定 owner 的资源缺口。
        first_index = next(i for i, identity in enumerate(h.identities) if identity.identity_id != subject.test_identity_id)
        first = _finish(h, identity_index=first_index)
        task = _task(h)
        assert task.task_kind == "PREPARE_ACTION_RESOURCE"
        assert task.test_identity_id != first.test_identity_id
        resource = next(item for item in h.core.preparation.get(h.project_id).actions[0].resources
                        if item.status is not Status.SATISFIED)
        assert (task.identity_slot_id, task.test_identity_id) == (resource.owner_slot_id, resource.owner_test_identity_id)
        with h.core.uow_factory() as work:
            old_binding = work.action_preparation.resource(h.action.action_id, 1, first.test_identity_id)
        second_index = 1 - first_index
        _finish(h, identity_index=second_index)
        with h.core.uow_factory() as work:
            assert work.action_preparation.resource(h.action.action_id, 1, first.test_identity_id) == old_binding
        assert _task(h).task_kind == "COMPLETE_EFFECT_EVIDENCE"
    finally:
        h.close()


@pytest.mark.parametrize("state", [RecordingState.CREATED, RecordingState.STARTING, RecordingState.RECORDING,
    RecordingState.CLEANING, RecordingState.PROCESSING, RecordingState.PENDING_REVIEW])
def test_current_recording_is_resumed_without_duplicate_task(harness, state):
    recording = add_recording(harness)
    with harness.core.uow_factory() as work:
        work.recordings.replace(recording.model_copy(update={"state": state}))
        work.commit()
    first = _task(harness)
    assert first.task_kind == "REVIEW_RECORDING" and first.recording_id == recording.recording_id
    assert first.test_identity_id == recording.test_identity_id
    assert first.title == ("确认业务演示" if state is RecordingState.PENDING_REVIEW else "继续业务演示")
    assert _task(harness) == first
    with harness.core.uow_factory() as work:
        assert len(work.recordings.list_for_project(harness.project_id)) == 1


@pytest.mark.parametrize("history", ["FAILED", "CANCELLED", "SAFETY_STOPPED", "old_revision", "stale_source"])
def test_historical_recordings_do_not_block_new_demonstration(harness, history):
    recording = add_recording(harness)
    updates = ({"action_revision": 2} if history == "old_revision" else
               {"preparation_source_fingerprint": "f" * 64} if history == "stale_source" else
               {"state": RecordingState(history)})
    # 固定历史行作为查询输入，避免建立不存在的业务版本根；来源判断仍使用真实 UoW。
    original_factory = harness.core.workspace._uow_factory
    from contextlib import contextmanager
    @contextmanager
    def with_history():
        with original_factory() as work:
            work.recordings.list_for_project = lambda _: (recording.model_copy(update=updates),)
            yield work
    harness.core.workspace._uow_factory = with_history
    assert _task(harness).task_kind == "DEMONSTRATE_ACTION"


@pytest.mark.parametrize("state_changing", [True, False])
def test_current_parent_effect_recovery_and_complete_projection(tmp_path, state_changing):
    h = build_preparation_harness(tmp_path, state_changing=state_changing)
    try:
        target = _finish(h)
        task = _task(h)
        assert task.task_kind == "COMPLETE_EFFECT_EVIDENCE"
        assert (task.parent_recording_id, task.test_identity_id, task.recording_purpose, task.effect_id) == (
            target.recording_id, target.test_identity_id, "OBSERVATION", h.effect_id)
        _finish(h, purpose=RecordingPurpose.OBSERVATION, parent_recording_id=target.recording_id,
                effect_id=h.effect_id, target_step_id="first")
        task = _task(h)
        if state_changing:
            assert task.task_kind == "COMPLETE_RECOVERY"
            assert (task.parent_recording_id, task.test_identity_id, task.recording_purpose, task.effect_id) == (
                target.recording_id, target.test_identity_id, "RECOVERY", None)
            _finish(h, purpose=RecordingPurpose.RECOVERY, parent_recording_id=target.recording_id, target_step_id="first")
        else:
            assert task is None
        workspace = h.core.workspace.get(h.project_id)
        assert workspace.primary_task is None
        tests = next(item for item in workspace.areas if item.key == "tests")
        assert (tests.status, tests.status_label) == ("READY", "材料已准备")
        assert "正式检查尚未接入" in tests.description
        assert next(item for item in workspace.areas if item.key == "changes").status == "BLOCKED"
        assert h.core.preparation.get(h.project_id).preparation_complete
    finally:
        h.close()


def test_parent_comes_from_current_resource_not_latest_history(harness):
    target = _finish(harness)
    newer = add_recording(harness)
    with harness.core.uow_factory() as work:
        work.recordings.replace(newer.model_copy(update={"state": RecordingState.COMPLETED, "finished_at_us": 4}))
        work.commit()
    task = _task(harness)
    assert task.parent_recording_id == target.recording_id
    assert task.parent_recording_id != newer.recording_id


def _complete_projection(item):
    def satisfied(value):
        return value.model_copy(update={"status": Status.SATISFIED, "reason_codes": ()})
    return item.model_copy(update={"execution": satisfied(item.execution),
        "resources": tuple(satisfied(value) for value in item.resources),
        "effect_evidence": tuple(satisfied(value) for value in item.effect_evidence),
        "recovery": satisfied(item.recovery), "preparation_complete": True})


def _gap(item, kind):
    updates = {"preparation_complete": False}
    if kind == "PREPARE_TEST_IDENTITY":
        identity = item.identity_requirements
        updates["identity_requirements"] = identity.model_copy(update={"slots": (
            identity.slots[0].model_copy(update={"status": Status.NEEDS_USER}),)})
    else:
        key = {"DEMONSTRATE_ACTION": "execution", "PREPARE_ACTION_RESOURCE": "resources",
               "COMPLETE_EFFECT_EVIDENCE": "effect_evidence", "COMPLETE_RECOVERY": "recovery"}[kind]
        value = getattr(item, key)
        updates[key] = (value[0].model_copy(update={"status": Status.NEEDS_USER}),) if isinstance(value, tuple) else value.model_copy(update={"status": Status.NEEDS_USER})
    return item.model_copy(update=updates)


@pytest.mark.parametrize("higher,lower", [("PREPARE_TEST_IDENTITY", "DEMONSTRATE_ACTION"),
    ("DEMONSTRATE_ACTION", "PREPARE_ACTION_RESOURCE"), ("PREPARE_ACTION_RESOURCE", "COMPLETE_EFFECT_EVIDENCE"),
    ("COMPLETE_EFFECT_EVIDENCE", "COMPLETE_RECOVERY")])
def test_category_priority_applies_across_actions(harness, higher, lower):
    preparation = harness.core.preparation.get(harness.project_id)
    complete = _complete_projection(preparation.actions[0])
    earlier = _gap(complete.model_copy(update={"action_id": "bac_" + "0" * 32}), lower)
    later = _gap(complete, higher)
    harness.core.workspace._preparation = SimpleNamespace(get=lambda _: preparation.model_copy(update={"actions": (earlier, later)}))
    task = _task(harness)
    assert (task.task_kind, task.business_action_id) == (higher, later.action_id)


def test_recording_review_precedes_other_action_identity_and_source_review_still_wins(harness):
    preparation = harness.core.preparation.get(harness.project_id)
    extra = _gap(preparation.actions[0].model_copy(update={"action_id": "bac_" + "0" * 32}), "PREPARE_TEST_IDENTITY")
    harness.core.workspace._preparation = SimpleNamespace(get=lambda _: preparation.model_copy(update={"actions": (extra, *preparation.actions)}))
    recording = add_recording(harness)
    assert _task(harness).recording_id == recording.recording_id
    with harness.core.uow_factory() as work:
        current = work.application_understanding.get(harness.project_id)
        work.application_understanding.replace(current.model_copy(update={"endpoint_reachable": False}))
        work.commit()
    assert _task(harness).task_kind == "CONFIRM_APPLICATION_ENDPOINT"


def test_missing_parent_is_not_fabricated_and_fingerprint_tracks_facts(harness):
    preparation = harness.core.preparation.get(harness.project_id)
    projection = _gap(_complete_projection(preparation.actions[0]), "COMPLETE_EFFECT_EVIDENCE")
    harness.core.workspace._preparation = SimpleNamespace(get=lambda _: preparation.model_copy(update={"actions": (projection,)}))
    task = _task(harness)
    assert not task.can_execute and task.parent_recording_id is None and task.test_identity_id is None
    assert _task(harness) == task
    projection = projection.model_copy(update={"assurance_contract_fingerprint": "f" * 64})
    changed = _task(harness)
    assert changed.task_id != task.task_id
    projection = projection.model_copy(update={"action_revision": 2})
    assert _task(harness).task_id != changed.task_id


def test_deny_only_moves_to_identity_only_after_real_allow_is_added(tmp_path):
    h = build_preparation_harness(tmp_path, identity_count=0)
    try:
        _permission(h, number=1, revision=2, expectation=PermissionExpectation.DENY)
        assert _task(h).task_kind == "COMPLETE_ALLOW_CONTROL"
        _permission(h, number=2, expectation=PermissionExpectation.ALLOW)
        assert _task(h).task_kind == "PREPARE_TEST_IDENTITY"
    finally:
        h.close()


def test_second_slot_selects_distinct_recorded_account_for_login(harness):
    _permission(harness, relation=PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT, expectation=PermissionExpectation.DENY)
    first = _task(harness)
    assert first.task_kind == "PREPARE_TEST_IDENTITY" and first.test_identity_id is None
    prep = harness.core.preparation.get(harness.project_id).actions[0]
    assert next(item for item in prep.identity_requirements.slots if item.requirement.slot_id == first.identity_slot_id).requirement.ordinal == 2
    created = harness.core.test_identities.create(harness.project_id, actor_id=harness.actor.actor_id,
        actor_revision=1, label="普通成员账号 2")
    task = _task(harness)
    assert task.identity_slot_id == first.identity_slot_id
    assert task.test_identity_id == created.identity_id
    assert task.test_identity_id != harness.identities[0].identity_id
    assert task.can_execute and task.task_id != first.task_id


@pytest.mark.parametrize("change", ["failed", "wrong_identity", "stale_source", "wrong_purpose"])
def test_unusable_resource_parent_is_never_offered(harness, change):
    target = _finish(harness)
    original_factory = harness.core.workspace._uow_factory
    from contextlib import contextmanager
    updates = {"failed": {"state": RecordingState.FAILED},
        "wrong_identity": {"test_identity_id": "tid_" + "f" * 32},
        "stale_source": {"preparation_source_fingerprint": "f" * 64},
        "wrong_purpose": {"purpose": RecordingPurpose.OBSERVATION}}[change]
    @contextmanager
    def factory():
        with original_factory() as work:
            original_get = work.recordings.get
            work.recordings.get = lambda recording_id: original_get(recording_id).model_copy(update=updates) if recording_id == target.recording_id else original_get(recording_id)
            yield work
    harness.core.workspace._uow_factory = factory
    task = _task(harness)
    assert task.task_kind == "COMPLETE_EFFECT_EVIDENCE"
    assert task.parent_recording_id is None and task.test_identity_id is None and not task.can_execute


def test_same_category_orders_action_slot_and_effect_stably(harness):
    preparation = harness.core.preparation.get(harness.project_id)
    item = preparation.actions[0]
    # 以只读投影输入验证顺序，不为排序测试建立额外业务持久根。
    earlier = item.model_copy(update={"action_id": "bac_" + "0" * 32})
    harness.core.workspace._preparation = SimpleNamespace(get=lambda _: preparation.model_copy(update={"actions": (item, earlier)}))
    assert _task(harness).business_action_id == earlier.action_id
    slots = item.identity_requirements.slots
    second = slots[0].model_copy(update={"requirement": slots[0].requirement.model_copy(update={"slot_id": "slot-second", "ordinal": 2}), "status": Status.NEEDS_USER})
    first = slots[0].model_copy(update={"status": Status.NEEDS_USER})
    item = item.model_copy(update={"identity_requirements": item.identity_requirements.model_copy(update={"slots": (second, first)})})
    harness.core.workspace._preparation = SimpleNamespace(get=lambda _: preparation.model_copy(update={"actions": (item,)}))
    assert _task(harness).identity_slot_id == first.requirement.slot_id
    item = _complete_projection(preparation.actions[0])
    first_effect = item.effect_evidence[0].model_copy(update={"status": Status.NEEDS_USER})
    second_effect = first_effect.model_copy(update={"effect_id": "bef_" + "f" * 32})
    item = item.model_copy(update={"effect_evidence": (second_effect, first_effect)})
    assert _task(harness).effect_id == first_effect.effect_id


def test_task_fingerprint_changes_for_endpoint_source_and_recording_state(harness):
    first = _task(harness)
    with harness.core.uow_factory() as work:
        understanding = work.application_understanding.get(harness.project_id)
        work.application_understanding.replace(understanding.model_copy(update={"endpoint_source_fingerprint": "f" * 64}))
        work.commit()
    second = _task(harness)
    assert second.task_kind == first.task_kind and second.task_id != first.task_id
    recording = add_recording(harness)
    pending = _task(harness)
    assert pending.task_id != second.task_id
    with harness.core.uow_factory() as work:
        work.recordings.replace(recording.model_copy(update={"state": RecordingState.PROCESSING}))
        work.commit()
    active = _task(harness)
    assert active.recording_id == pending.recording_id and active.task_id != pending.task_id
