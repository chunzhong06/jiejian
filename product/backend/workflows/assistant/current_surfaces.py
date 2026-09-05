# 从正式业务、当前录制与准备缺口构造三个 CURRENT AI 输入；只投影短事实，不写业务状态。

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlsplit

from product.backend.core.application_understanding import CandidateDecision
from product.backend.core.business_boundary import ACTION_ID_PATTERN, ACTOR_ID_PATTERN, BusinessRevisionState, boundary_sha256
from product.backend.core.identifiers import RECORDING_ID_PATTERN
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.recording import RecordingState
from product.backend.workflows.assistant.surfaces import ResolvedAssistantSurface, _entity, _short, _unique_short
from product.backend.workflows.assistant.templates import AssistantEntityType as EntityType, AssistantFact, AssistantTemplateId as Template, build_surface_input
from product.backend.workflows.preparation.models import PreparationStatus
from product.backend.workflows.recording.source import require_recording_source


CURRENT_ASSISTANT_TEMPLATES = frozenset({Template.IMPLEMENTATION_MAPPING, Template.BUSINESS_RECORDING_REVIEW, Template.PREPARATION_EXPLANATION})


class PreparationAssistantSurfaceResolver:
    """只接受显式正式对象焦点；缓存指纹与 provider 短事实分离。"""

    def __init__(self, *, business_boundaries, application_understanding, preparation, recording_lifecycle, uow_factory):
        self._business_boundaries = business_boundaries
        self._application_understanding = application_understanding
        self._preparation = preparation
        self._recording_lifecycle = recording_lifecycle
        self._uow_factory = uow_factory

    def resolve_project(self, project_id, template_id, *, business_actor_id=None, business_action_id=None, recording_id=None):
        for value, pattern in ((business_actor_id, ACTOR_ID_PATTERN), (business_action_id, ACTION_ID_PATTERN), (recording_id, RECORDING_ID_PATTERN)):
            if value is not None and (not isinstance(value, str) or re.fullmatch(pattern, value) is None):
                self._invalid()
        if template_id is Template.IMPLEMENTATION_MAPPING and bool(business_actor_id) != bool(business_action_id) and recording_id is None:
            return self._mapping(project_id, business_actor_id, business_action_id)
        if template_id is Template.BUSINESS_RECORDING_REVIEW and recording_id and business_actor_id is None and business_action_id is None:
            return self._recording(project_id, recording_id)
        if template_id is Template.PREPARATION_EXPLANATION and business_action_id and business_actor_id is None and recording_id is None:
            return self._explanation(project_id, business_action_id)
        self._invalid()

    def _business(self, project_id, object_id, *, actor=False):
        boundary = self._business_boundaries.view(project_id)
        objects = boundary.actors if actor else boundary.actions
        value = next((item for item in objects if (item.actor_id if actor else item.action_id) == object_id
            and item.project_id == project_id and item.effective_state is BusinessRevisionState.ACTIVE), None)
        if value is None:
            self._invalid()
        return value

    def _mapping(self, project_id, actor_id, action_id):
        business = self._business(project_id, actor_id or action_id, actor=actor_id is not None)
        understanding = self._application_understanding.get(project_id)
        candidates = sorted((item for item in (understanding.role_candidates if actor_id else understanding.action_candidates)
            if not item.stale and item.decision is not CandidateDecision.REJECTED), key=lambda item: item.candidate_id)
        entities = [self._business_entity(business, actor=actor_id is not None)]
        for candidate in candidates[:127]:
            entities.append(_entity(candidate.candidate_id, EntityType.CANDIDATE, candidate.display_name, {
                "candidate_type": "ROLE" if actor_id else "ACTION", "canonical_key": candidate.canonical_key,
                "confidence": candidate.confidence.value, "decision": candidate.decision.value,
                "detectors": _unique_short(item.detector for item in candidate.evidence),
                "relative_paths": _unique_short(item.relative_path for item in candidate.evidence),
                "symbols": _unique_short(item.symbol for item in candidate.evidence if item.symbol),
            }))
        return self._resolved(project_id, actor_id or action_id, Template.IMPLEMENTATION_MAPPING,
            {"business_kind": "ACTOR" if actor_id else "ACTION", "business_revision": business.revision,
             "candidate_count": len(candidates), "candidates_truncated": len(candidates) > 127}, entities,
            can_generate=len(candidates) > 1,
            fingerprint_facts={"business": business.model_dump(mode="json"), "understanding_revision": understanding.revision,
                "source_fingerprint": understanding.source_fingerprint})

    def _recording(self, project_id, recording_id):
        status = self._recording_lifecycle.status(recording_id)
        record, draft = status.recording, status.draft
        if record.project_id != project_id or draft is None:
            self._invalid()
        business = self._business(project_id, record.business_action_id)
        if business.revision != record.action_revision:
            self._invalid()
        with self._uow_factory() as work:
            require_recording_source(work, record)
        entities = [self._business_entity(business)]
        steps = sorted(draft.steps, key=lambda item: item.id)
        for step in steps:
            if len(entities) >= 128:
                break
            entities.append(_entity(step.id, EntityType.RECORDING_STEP, step.name, {
                "method": step.method or "UNAVAILABLE", "path": _path(step),
                "depends_on_step_ids": step.depends_on_step_ids[:64],
                "is_current_target": step.id == draft.target_step_id,
                "is_recommended_target": step.id == draft.recommended_target_step_id,
            }))
        included_steps = {item.entity_id for item in entities if item.entity_type is EntityType.RECORDING_STEP}
        for step in steps:
            if step.id not in included_steps:
                continue
            for candidate in sorted(step.resource_candidates, key=lambda item: item.candidate_id):
                if len(entities) >= 128:
                    break
                # 复合实体 ID 保留原 step/candidate 定位，避免跨步骤重复 candidate ID 混淆。
                entities.append(_entity(f"{step.id}:{candidate.candidate_id}", EntityType.RESOURCE_CANDIDATE, candidate.label,
                    {"step_id": step.id, "consumer": candidate.consumer.value, "location": candidate.location}))
        target_candidates = [item for item in steps if item.method is not None]
        resource_count = sum(len(item.resource_candidates) for item in steps if draft.target_step_id is None or item.id == draft.target_step_id)
        ambiguous = (draft.target_step_id is None and len(target_candidates) > 1) or (draft.resource_candidate_id is None and resource_count > 1)
        return self._resolved(project_id, recording_id, Template.BUSINESS_RECORDING_REVIEW,
            {"business_action_id": business.action_id, "action_revision": business.revision,
             "recording_id": recording_id, "recording_state": record.state.value, "purpose": record.purpose.value,
             "target_step_id": draft.target_step_id or "", "draft_revision": draft.revision}, entities,
            can_generate=record.state is RecordingState.PENDING_REVIEW and ambiguous,
            fingerprint_facts={"source": record.preparation_source_fingerprint, "draft_revision": draft.revision,
                "selected_resource": draft.resource_candidate_id})

    def _explanation(self, project_id, action_id):
        business = self._business(project_id, action_id)
        preparation = self._preparation.get(project_id)
        action = next((item for item in preparation.actions if item.action_id == action_id and item.action_revision == business.revision), None)
        if action is None:
            self._invalid()
        entities = [self._business_entity(business)]
        actor_counts = Counter(item.requirement.actor_id for item in action.identity_requirements.slots)
        effects = {item.effect_id: item.business_label for item in business.effect_catalog}
        items = []
        for slot in action.identity_requirements.slots:
            items.append(("identity", slot.requirement.slot_id, f"{slot.actor_display_name}账号 {slot.requirement.ordinal}", slot,
                {"actor_display_name": slot.actor_display_name, "ordinal": slot.requirement.ordinal,
                 "required_count": actor_counts[slot.requirement.actor_id]}))
        items.append(("execution", "execution", "业务演示", action.execution, {}))
        for item in action.resources:
            items.append(("resource", item.owner_slot_id, "具体测试资源", item, {}))
        for item in action.effect_evidence:
            items.append(("effect", item.effect_id, effects[item.effect_id], item, {"effect_display_name": effects[item.effect_id]}))
        items.append(("recovery", "recovery", "恢复业务状态", action.recovery, {}))
        gap_count = sum(item.status not in {PreparationStatus.SATISFIED, PreparationStatus.NOT_REQUIRED} for _, _, _, item, _ in items)
        for category, identifier, name, item, facts in items[:127]:
            entity_id = "prepitem_" + boundary_sha256([action_id, category, identifier])[:32]
            entities.append(_entity(entity_id, EntityType.PREPARATION_ITEM, name,
                {"category": category, "status": item.status.value, "reason_codes": item.reason_codes[:64], **facts}))
        return self._resolved(project_id, action_id, Template.PREPARATION_EXPLANATION,
            {"action_revision": action.action_revision, "preparation_complete": action.preparation_complete, "gap_count": gap_count}, entities,
            can_generate=not action.preparation_complete and (gap_count > 1 or any(count > 1 for count in actor_counts.values())),
            fingerprint_facts=action.model_dump(mode="json"))

    @staticmethod
    def _business_entity(value, *, actor=False):
        return _entity(value.actor_id if actor else value.action_id, EntityType.ACTOR if actor else EntityType.ACTION,
            value.display_name, {"revision": value.revision, "description": _short(value.description)})

    @staticmethod
    def _resolved(project_id, focus_id, template, facts, entities, *, can_generate, fingerprint_facts):
        subject_id = f"{project_id}:{focus_id}"
        surface = build_surface_input(template, subject_id=subject_id, facts=facts, entities=entities)
        fingerprint = boundary_sha256({"input": surface.model_dump(mode="json"), "facts": fingerprint_facts, "can_generate": can_generate})
        return ResolvedAssistantSurface(subject_id, fingerprint, surface, can_generate)

    @staticmethod
    def _invalid():
        raise JiejianError(ErrorCode.INPUT_INVALID, "AI 辅助上下文不属于当前业务对象")


def _path(step):
    # 只保留路径形状；资源定位对应片段不上传实际业务值，query/fragment 完全移除。
    parts = urlsplit(step.path or "/").path.split("/")
    for candidate in step.resource_candidates:
        match = re.fullmatch(r"path\[(\d+)\]", candidate.location)
        if candidate.consumer.value == "PATH" and match:
            index = int(match[1]) + 1
            if index < len(parts):
                parts[index] = "{resource}"
    return _short("/".join(parts))
