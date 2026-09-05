# 验证 CURRENT 三类事实投影、明确焦点、有限实体和类型化建议边界。

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from product.backend.core.application_understanding import CandidateDecision
from product.backend.core.business_boundary import BusinessRevisionState
from product.backend.core.errors import JiejianError
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.permission_semantics import PermissionExpectation
from product.backend.core.recording import RecordingState
from product.backend.infra.storage import FlowDraftRevisionRecord
from product.backend.workflows.assistant.current_surfaces import CURRENT_ASSISTANT_TEMPLATES
from product.backend.workflows.assistant.templates import AssistantEntityType as EntityType, AssistantTemplateId as Template, parse_assistant_result, render_assistant_prompt
from product.protocols.flow_draft import canonical_flow_draft_json_bytes
from tests.fixtures.action_preparation import add_recording, build_preparation_harness
from tests.fixtures.assurance import permission


@pytest.fixture
def harness(tmp_path):
    value = build_preparation_harness(tmp_path)
    yield value
    value.close()


def _candidates(h, count, *, actor=False):
    with h.core.uow_factory() as work:
        understanding = work.application_understanding.get(h.project_id)
        key = "role_candidates" if actor else "action_candidates"
        base = getattr(understanding, key)[0]
        values = tuple(base.model_copy(update={"candidate_id": ("role_" if actor else "action_") + f"{index:032x}",
            "canonical_key": f"candidate_{index}", "display_name": f"候选 {index}"}) for index in range(count))
        work.application_understanding.replace(understanding.model_copy(update={key: values}))
        work.commit()
    return values


def _mapping(h, *, actor=False):
    focus = {"business_actor_id": h.actor.actor_id} if actor else {"business_action_id": h.action.action_id}
    return h.core.assistant_surfaces.resolve_project(h.project_id, Template.IMPLEMENTATION_MAPPING, **focus)


def _ambiguous_recording(h):
    recording = add_recording(h, step_count=2)
    with h.core.uow_factory() as work:
        current = work.flow_drafts.latest(recording.recording_id)
        steps = tuple(item.model_copy(update={"path": "/docs/doc-123?view=query-private", "json_body": {"title": "body-private"}}) for item in current.draft.steps)
        draft = current.draft.model_copy(update={"revision": 2, "target_step_id": None, "resource_candidate_id": None, "steps": steps})
        raw = canonical_flow_draft_json_bytes(draft)
        work.flow_drafts.add(FlowDraftRevisionRecord(recording_id=recording.recording_id, revision=2, flow_id=recording.flow_id,
            draft=draft, draft_sha256=hashlib.sha256(raw).hexdigest(), created_at_us=4))
        work.commit()
    return recording


def _result(surface, kind, ids):
    return {"schema_version": "1", "template_id": surface.template_id.value, "template_version": "1",
        "suggestions": [{"kind": kind, "entity_ids": ids, "explanation": "根据现有事实进行人工核对。"}]}


@pytest.mark.parametrize("actor", [False, True])
@pytest.mark.parametrize("count", [0, 1, 2, 130])
def test_mapping_uses_current_business_bounded_candidates_and_deterministic_gate(harness, actor, count):
    _candidates(harness, count, actor=actor)
    resolved = _mapping(harness, actor=actor)
    assert resolved == _mapping(harness, actor=actor)
    assert resolved.can_generate is (count > 1)
    assert len(resolved.surface_input.entities) == min(count, 127) + 1
    facts = {item.field: item.value for item in resolved.surface_input.facts}
    assert facts == {"business_kind": "ACTOR" if actor else "ACTION", "business_revision": 1,
        "candidate_count": count, "candidates_truncated": count > 127}
    assert resolved.surface_input.entities[0].entity_type is (EntityType.ACTOR if actor else EntityType.ACTION)
    assert harness.project_id in resolved.subject_id
    assert (harness.actor.actor_id if actor else harness.action.action_id) in resolved.subject_id
    payload = render_assistant_prompt(resolved.surface_input)
    assert str(harness.source_root) not in payload and "def update_document" not in payload
    assert all(item.entity_type is EntityType.CANDIDATE for item in resolved.surface_input.entities[1:])


def test_mapping_filters_stale_rejected_and_fingerprint_tracks_source(harness):
    values = _candidates(harness, 3)
    before = _mapping(harness)
    with harness.core.uow_factory() as work:
        current = work.application_understanding.get(harness.project_id)
        work.application_understanding.replace(current.model_copy(update={"action_candidates": (
            values[0], values[1].model_copy(update={"stale": True}), values[2].model_copy(update={"decision": CandidateDecision.REJECTED})),
            "source_fingerprint": "f" * 64}))
        work.commit()
    changed = _mapping(harness)
    assert not changed.can_generate and len(changed.surface_input.entities) == 2
    assert changed.state_fingerprint != before.state_fingerprint


@pytest.mark.parametrize("template,focus", [(Template.IMPLEMENTATION_MAPPING, {}),
    (Template.IMPLEMENTATION_MAPPING, {"business_actor_id": "bar_" + "1" * 32, "business_action_id": "bac_" + "1" * 32}),
    (Template.BUSINESS_RECORDING_REVIEW, {}), (Template.PREPARATION_EXPLANATION, {"recording_id": "rec_" + "1" * 32}),
    (Template.NEXT_STEP, {}), (Template.IMPLEMENTATION_MAPPING, {"business_actor_id": "invalid"})])
def test_invalid_focus_or_dormant_template_is_rejected(harness, template, focus):
    with pytest.raises(JiejianError):
        harness.core.assistant_surfaces.resolve_project(harness.project_id, template, **focus)


def test_mapping_requires_active_current_project_object(harness, monkeypatch):
    boundary = harness.core.business_boundaries.view(harness.project_id)
    for updates in ({"project_id": "other-project"}, {"effective_state": BusinessRevisionState.RETIRED}):
        monkeypatch.setattr(harness.core.business_boundaries, "view", lambda _: boundary.model_copy(update={
            "actors": (boundary.actors[0].model_copy(update=updates),)}))
        with pytest.raises(JiejianError):
            _mapping(harness, actor=True)
    monkeypatch.setattr(harness.core.business_boundaries, "view", lambda _: boundary.model_copy(update={
        "actors": (boundary.actors[0].model_copy(update={"revision": 2}),)}))
    assert dict((item.field, item.value) for item in _mapping(harness, actor=True).surface_input.facts)["business_revision"] == 2


def test_recording_is_explicit_and_resource_entities_preserve_step_association(harness):
    first = _ambiguous_recording(harness)
    newer = add_recording(harness)
    resolved = harness.core.assistant_surfaces.resolve_project(harness.project_id, Template.BUSINESS_RECORDING_REVIEW, recording_id=first.recording_id)
    assert resolved.can_generate
    facts = {item.field: item.value for item in resolved.surface_input.facts}
    assert facts["recording_id"] == first.recording_id and facts["recording_id"] != newer.recording_id
    assert facts["draft_revision"] == 2 and facts["target_step_id"] == ""
    resources = [item for item in resolved.surface_input.entities if item.entity_type is EntityType.RESOURCE_CANDIDATE]
    assert len(resources) == 2 and len({item.entity_id for item in resources}) == 2
    assert all(item.entity_id.startswith(dict((fact.field, fact.value) for fact in item.facts)["step_id"] + ":") for item in resources)
    payload = render_assistant_prompt(resolved.surface_input)
    assert all(value not in payload for value in ("query-private", "body-private", "doc-123", "fixture-secret", "browser_events", "secret_ref"))
    with harness.core.uow_factory() as work:
        assert work.recordings.get(first.recording_id).state is RecordingState.PENDING_REVIEW
        assert work.flow_drafts.latest(first.recording_id).revision == 2


@pytest.mark.parametrize("problem", ["cross_project", "stale_source", "old_action"])
def test_recording_rejects_cross_project_and_stale_origin(harness, monkeypatch, problem):
    record = add_recording(harness)
    status = harness.core.recording_lifecycle.status(record.recording_id)
    updates = {"cross_project": {"project_id": "other-project"}, "stale_source": {"preparation_source_fingerprint": "f" * 64}, "old_action": {"action_revision": 2}}[problem]
    monkeypatch.setattr(harness.core.recording_lifecycle, "status", lambda _: status.model_copy(update={"recording": record.model_copy(update=updates)}))
    with pytest.raises(JiejianError):
        harness.core.assistant_surfaces.resolve_project(harness.project_id, Template.BUSINESS_RECORDING_REVIEW, recording_id=record.recording_id)


@pytest.mark.parametrize("completed", [False, True])
def test_unique_or_completed_recording_does_not_generate(harness, completed):
    record = add_recording(harness)
    if completed:
        harness.core.recording_lifecycle.finalize(record.recording_id, var_dir=harness.var_dir, now_us=100)
    resolved = harness.core.assistant_surfaces.resolve_project(harness.project_id, Template.BUSINESS_RECORDING_REVIEW, recording_id=record.recording_id)
    assert not resolved.can_generate


def test_preparation_explains_two_accounts_without_changing_requirements(harness):
    with harness.core.uow_factory() as work:
        work.permission_intents.add_revision(permission(2, relation=PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
            expectation=PermissionExpectation.DENY).model_copy(update={"project_id": harness.project_id}))
        work.commit()
    before = harness.core.preparation.get(harness.project_id)
    resolved = harness.core.assistant_surfaces.resolve_project(harness.project_id, Template.PREPARATION_EXPLANATION, business_action_id=harness.action.action_id)
    assert resolved.can_generate and harness.core.preparation.get(harness.project_id) == before
    facts = {item.field: item.value for item in resolved.surface_input.facts}
    assert set(facts) == {"action_revision", "preparation_complete", "gap_count"}
    identities = [item for item in resolved.surface_input.entities if any(fact.field == "category" and fact.value == "identity" for fact in item.facts)]
    assert len(identities) == 2
    assert {dict((fact.field, fact.value) for fact in item.facts)["ordinal"] for item in identities} == {1, 2}
    payload = render_assistant_prompt(resolved.surface_input)
    assert all(value not in payload for value in ("secret_ref", "http://", "binding_fingerprint", before.actions[0].assurance_contract_fingerprint))


@pytest.mark.parametrize("kind,entity_type,category", [("LIKELY_RESOURCE", "RECORDING_STEP", None),
    ("LIKELY_TARGET", "RESOURCE_CANDIDATE", None), ("CONFIDENCE_EXPLANATION", "ACTION", None),
    ("OBSERVATION_GAP", "PREPARATION_ITEM", "recovery"), ("RECOVERY_GAP", "PREPARATION_ITEM", "effect")])
def test_current_typed_kind_rejects_existing_but_wrong_entity(harness, kind, entity_type, category):
    if kind.startswith("LIKELY_"):
        record = _ambiguous_recording(harness)
        resolved = harness.core.assistant_surfaces.resolve_project(harness.project_id, Template.BUSINESS_RECORDING_REVIEW, recording_id=record.recording_id)
    elif kind == "CONFIDENCE_EXPLANATION":
        _candidates(harness, 2)
        resolved = _mapping(harness)
    else:
        resolved = harness.core.assistant_surfaces.resolve_project(harness.project_id, Template.PREPARATION_EXPLANATION, business_action_id=harness.action.action_id)
    entity = next(item for item in resolved.surface_input.entities if item.entity_type.value == entity_type
        and (category is None or any(fact.field == "category" and fact.value == category for fact in item.facts)))
    with pytest.raises(JiejianError):
        parse_assistant_result(_result(resolved.surface_input, kind, [entity.entity_id]), surface_input=resolved.surface_input)


def test_deterministic_post_skips_provider_and_cache(harness, monkeypatch):
    service = harness.core.assistant_service
    profiles = harness.core.llm_profiles
    monkeypatch.setattr(profiles, "get_settings", lambda: SimpleNamespace(enabled=True, default_profile_name="fake"))
    monkeypatch.setattr(profiles, "get", lambda _: SimpleNamespace(enabled=True, secret_configured=True))
    forbidden = Mock(side_effect=AssertionError("确定输入不调用模型或缓存"))
    monkeypatch.setattr(profiles, "resolve_provider", forbidden)
    monkeypatch.setattr(service._cache, "read", forbidden)
    monkeypatch.setattr(service._cache, "write_success", forbidden)
    view = service.generate_project(harness.project_id, Template.IMPLEMENTATION_MAPPING, business_action_id=harness.action.action_id)
    assert view.status.value == "READY" and not view.can_generate and view.suggestions == ()
    forbidden.assert_not_called()
    assert CURRENT_ASSISTANT_TEMPLATES == {Template.IMPLEMENTATION_MAPPING, Template.BUSINESS_RECORDING_REVIEW, Template.PREPARATION_EXPLANATION}
