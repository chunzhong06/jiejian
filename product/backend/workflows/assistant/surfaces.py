# =============================================================================
# AI surface 服务端事实构造
#
# 定位
#   从正式 workflow View 构造九类短事实，隔离页面输入与模型输入。
#
# 边界
#   只读现有实体和确定性状态；不读取秘密、源码正文、Evidence 正文或日志。
# =============================================================================

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from product.backend.core.application_understanding import CandidateDecision
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.assistant.diagnosis import ErrorDiagnosis
from product.backend.workflows.assistant.templates import (
    AssistantEntity,
    AssistantEntityType,
    AssistantFact,
    AssistantSurfaceInput,
    AssistantTemplateId,
    SafeFactValue,
    build_surface_input,
)


PROJECT_ASSISTANT_TEMPLATES = frozenset(
    {
        AssistantTemplateId.NEXT_STEP,
        AssistantTemplateId.CANDIDATE_REVIEW,
        AssistantTemplateId.IDENTITY_PREPARATION,
        AssistantTemplateId.RECORDING_REVIEW,
        AssistantTemplateId.PERMISSION_REVIEW,
        AssistantTemplateId.OBSERVATION_RECOVERY,
        AssistantTemplateId.CHECK_PREVIEW_EXPLANATION,
    }
)


@dataclass(frozen=True, slots=True)
class ResolvedAssistantSurface:
    subject_id: str
    state_fingerprint: str
    surface_input: AssistantSurfaceInput


class AssistantSurfaceResolver:
    """九类 surface 只组合正式只读 View，不接受客户端提交任意事实。"""

    def __init__(
        self,
        *,
        guidance,
        application_understanding,
        test_identities,
        project_readiness,
        product_flows,
        recording_lifecycle,
        permission_intents,
        check_preview,
        result_presentation,
    ) -> None:
        self._guidance = guidance
        self._application_understanding = application_understanding
        self._test_identities = test_identities
        self._project_readiness = project_readiness
        self._product_flows = product_flows
        self._recording_lifecycle = recording_lifecycle
        self._permission_intents = permission_intents
        self._check_preview = check_preview
        self._result_presentation = result_presentation

    def resolve_project(
        self,
        project_id: str,
        template_id: AssistantTemplateId,
    ) -> ResolvedAssistantSurface:
        if template_id not in PROJECT_ASSISTANT_TEMPLATES:
            raise JiejianError(ErrorCode.INPUT_INVALID, "当前 AI 辅助类型不属于项目主流程")
        builder = {
            AssistantTemplateId.NEXT_STEP: self._next_step,
            AssistantTemplateId.CANDIDATE_REVIEW: self._candidate_review,
            AssistantTemplateId.IDENTITY_PREPARATION: self._identity_preparation,
            AssistantTemplateId.RECORDING_REVIEW: self._recording_review,
            AssistantTemplateId.PERMISSION_REVIEW: self._permission_review,
            AssistantTemplateId.OBSERVATION_RECOVERY: self._observation_recovery,
            AssistantTemplateId.CHECK_PREVIEW_EXPLANATION: self._check_preview_explanation,
        }[template_id]
        return builder(project_id)

    def resolve_result(self, run_id: str) -> ResolvedAssistantSurface:
        presentation = self._result_presentation.build(run_id)
        entities = tuple(
            _entity(
                item.finding_id,
                AssistantEntityType.RESULT_ITEM,
                item.title,
                {
                    "expectation": item.expectation,
                    "surface_result": item.surface_result,
                    "actual_result": item.actual_result,
                    "conclusion": item.conclusion,
                    "verdict": item.verdict.value,
                    "evidence_sources": tuple(
                        f"{source.role}:{source.status}:{source.label}" for source in item.evidence_sources[:16]
                    ),
                },
            )
            for item in presentation.issues[:128]
        ) or (
            _entity(
                presentation.run_id,
                AssistantEntityType.RESULT_ITEM,
                presentation.headline,
                {
                    "expectation": presentation.scope_statement,
                    "surface_result": presentation.execution_problem or "检查已形成发布结果",
                    "actual_result": presentation.scope_statement,
                    "conclusion": presentation.headline,
                    "verdict": _enum_value(presentation.verdict) if presentation.verdict is not None else "UNAVAILABLE",
                    "evidence_sources": (),
                },
            ),
        )
        return _resolved(
            AssistantTemplateId.RESULT_EXPLANATION,
            presentation.run_id,
            {
                "run_lifecycle": presentation.run_lifecycle.value,
                "verdict": _enum_value(presentation.verdict) if presentation.verdict is not None else "UNAVAILABLE",
                "headline": presentation.headline,
                "scope_statement": presentation.scope_statement,
                "checked_count": presentation.checked_count,
                "safe_count": presentation.safe_count,
                "problem_count": presentation.problem_count,
                "inconclusive_count": presentation.inconclusive_count,
                "uncovered_count": presentation.uncovered_count,
                "limitations": tuple(_short(item) for item in presentation.limitations[:32]),
            },
            entities,
        )

    def resolve_error(self, error_code: str, diagnosis: ErrorDiagnosis) -> ResolvedAssistantSurface:
        subject_hash = hashlib.sha256(
            json.dumps(
                {"error_code": error_code, "diagnosis": diagnosis.model_dump(mode="json")},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        subject_id = f"error:{subject_hash}"
        facts = {
            "area": diagnosis.area.value,
            "phase": diagnosis.phase.value,
            "error_code": _short(error_code, 96),
            "cause": diagnosis.cause,
            "recovery_action": diagnosis.recovery_action.value,
            "headline": diagnosis.headline,
            "short_message": diagnosis.short_message,
        }
        return _resolved(
            AssistantTemplateId.ERROR_EXPLANATION,
            subject_id,
            facts,
            (
                _entity(
                    subject_id,
                    AssistantEntityType.ERROR,
                    diagnosis.headline,
                    {key: facts[key] for key in ("area", "phase", "error_code", "cause", "recovery_action")},
                ),
            ),
        )

    def _next_step(self, project_id: str) -> ResolvedAssistantSurface:
        guidance = self._guidance.get(project_id)
        entities = tuple(
            _entity(
                option.option_id,
                AssistantEntityType.OPTION,
                option.title,
                {
                    "kind": option.kind.value,
                    "reason_codes": option.reason_codes,
                    "priority_tier": option.priority_tier.value,
                    "route": option.route,
                },
            )
            for option in guidance.options[:32]
        )
        return _resolved(
            AssistantTemplateId.NEXT_STEP,
            project_id,
            {
                "phase": guidance.phase.value,
                "current_scope_runnable": guidance.current_scope_runnable,
                "remaining_gap_count": guidance.remaining_gap_count,
            },
            entities,
        )

    def _candidate_review(self, project_id: str) -> ResolvedAssistantSurface:
        understanding = self._application_understanding.get(project_id)
        rows = tuple(("ROLE", item) for item in understanding.role_candidates) + tuple(
            ("ACTION", item) for item in understanding.action_candidates
        )
        entities = tuple(
            _entity(
                item.candidate_id,
                AssistantEntityType.CANDIDATE,
                item.display_name,
                {
                    "candidate_type": candidate_type,
                    "canonical_key": item.canonical_key,
                    "confidence": item.confidence.value,
                    "decision": item.decision.value,
                    "origin": item.origin.value,
                    "stale": item.stale,
                    "detectors": _unique_short(evidence.detector for evidence in item.evidence),
                    "relative_paths": _unique_short(evidence.relative_path for evidence in item.evidence),
                    "symbols": _unique_short(evidence.symbol for evidence in item.evidence if evidence.symbol),
                },
            )
            for candidate_type, item in rows[:128]
        )
        return _resolved(
            AssistantTemplateId.CANDIDATE_REVIEW,
            project_id,
            {"revision": understanding.revision, "candidate_count": len(rows)},
            entities,
        )

    def _identity_preparation(self, project_id: str) -> ResolvedAssistantSurface:
        understanding = self._application_understanding.get(project_id)
        identities = self._test_identities.list(project_id)
        readiness = self._project_readiness.get(project_id)
        entities: list[AssistantEntity] = []
        for role in understanding.role_candidates:
            if role.decision is not CandidateDecision.CONFIRMED or role.stale:
                continue
            matching = tuple(item for item in identities if item.role_candidate_id == role.candidate_id)
            entities.append(
                _entity(
                    role.candidate_id,
                    AssistantEntityType.ROLE,
                    role.display_name,
                    {
                        "role_candidate_id": role.candidate_id,
                        "role_canonical_key": role.canonical_key,
                        "status": "HAS_IDENTITY" if matching else "MISSING_IDENTITY",
                        "identity_count": len(matching),
                    },
                )
            )
        for identity in identities:
            entities.append(
                _entity(
                    identity.identity_id,
                    AssistantEntityType.IDENTITY,
                    identity.label,
                    {
                        "role_candidate_id": identity.role_candidate_id,
                        "role_canonical_key": identity.role_canonical_key,
                        "status": identity.status.value,
                        "review_reasons": identity.review_reasons,
                    },
                )
            )
        action_ids: list[str] = []
        for action in readiness.permission_actions:
            action_ids.append(action.action_candidate_id)
            entities.append(
                _entity(
                    action.action_candidate_id,
                    AssistantEntityType.ACTION,
                    action.action_display_name,
                    {"gap_codes": action.gaps},
                )
            )
        return _resolved(
            AssistantTemplateId.IDENTITY_PREPARATION,
            project_id,
            {
                "remaining_gap_count": readiness.remaining_gap_count,
                "action_ids": tuple(action_ids[:64]),
            },
            tuple(entities[:128]),
        )

    def _recording_review(self, project_id: str) -> ResolvedAssistantSurface:
        recordings = sorted(
            self._product_flows.list(project_id),
            key=lambda item: int(item.get("created_at_us", 0)),
            reverse=True,
        )
        selected = None
        for item in recordings:
            view = self._recording_lifecycle.status(str(item["recording_id"]))
            if view.draft is not None:
                selected = view
                break
        if selected is None or selected.draft is None:
            raise JiejianError(ErrorCode.INPUT_INVALID, "当前还没有可供 AI 解读的录制草稿")
        draft = selected.draft
        entities = tuple(
            _entity(
                step.id,
                AssistantEntityType.RECORDING_STEP,
                step.name,
                {
                    "method": step.method or "UI",
                    "path": _short(step.path or "无 HTTP 请求"),
                    "depends_on_step_ids": step.depends_on_step_ids,
                    "is_current_target": step.id == draft.target_step_id,
                    "is_recommended_target": step.id == draft.recommended_target_step_id,
                },
            )
            for step in draft.steps[:128]
        )
        return _resolved(
            AssistantTemplateId.RECORDING_REVIEW,
            draft.recording_id,
            {
                "recording_id": draft.recording_id,
                "recording_state": selected.recording.state.value,
                "target_step_id": draft.target_step_id or "UNCONFIRMED",
            },
            entities,
        )

    def _permission_review(self, project_id: str) -> ResolvedAssistantSurface:
        matrix = self._permission_intents.matrix(project_id)
        entities: list[AssistantEntity] = []
        for action in matrix.actions:
            if not action.cells:
                entities.append(
                    _entity(
                        action.action_candidate_id,
                        AssistantEntityType.ACTION,
                        action.action_display_name,
                        {"action_id": action.action_candidate_id, "gap_codes": action.gaps},
                    )
                )
            for cell in action.cells:
                cell_id = _stable_id(
                    "permission",
                    action.action_candidate_id,
                    cell.subject_role_candidate_id,
                    cell.resource_owner_role_candidate_id,
                    cell.relation.value,
                )
                entities.append(
                    _entity(
                        cell_id,
                        AssistantEntityType.PERMISSION_CELL,
                        f"{cell.subject_role_display_name} · {action.action_display_name}",
                        {
                            "action_id": action.action_candidate_id,
                            "subject_role": cell.subject_role_display_name,
                            "resource_owner_role": cell.resource_owner_role_display_name,
                            "relation": cell.relation.value,
                            "expectation": _enum_value(cell.expectation) if cell.expectation is not None else "UNCONFIRMED",
                            "status": cell.status.value,
                            "review_reasons": cell.review_reasons,
                            "execution_gap": cell.execution_gap or "NONE",
                        },
                    )
                )
        return _resolved(
            AssistantTemplateId.PERMISSION_REVIEW,
            project_id,
            {
                "unconfirmed_count": matrix.unconfirmed_count,
                "review_required_count": matrix.review_required_count,
                "representative_gap_count": matrix.representative_gap_count,
                "compilable_action_count": matrix.compilable_action_count,
            },
            tuple(entities[:128]),
        )

    def _observation_recovery(self, project_id: str) -> ResolvedAssistantSurface:
        preview = self._check_preview(project_id)
        entities = tuple(
            _entity(
                action.action_candidate_id,
                AssistantEntityType.ACTION,
                action.action_display_name,
                {
                    "observation_gap_codes": tuple(gap.code for gap in action.gaps if "OBSERVATION" in gap.code),
                    "recovery_gap_codes": tuple(gap.code for gap in action.gaps if "RECOVERY" in gap.code),
                    "other_gap_codes": tuple(gap.code for gap in action.gaps if "OBSERVATION" not in gap.code and "RECOVERY" not in gap.code),
                },
            )
            for action in preview.actions[:128]
        )
        return _resolved(
            AssistantTemplateId.OBSERVATION_RECOVERY,
            project_id,
            {"ready": preview.ready, "gap_codes": tuple(gap.code for gap in preview.gaps[:64])},
            entities,
        )

    def _check_preview_explanation(self, project_id: str) -> ResolvedAssistantSurface:
        preview = self._check_preview(project_id)
        entities = tuple(
            _entity(
                action.action_candidate_id,
                AssistantEntityType.CHECK_ACTION,
                action.action_display_name,
                {
                    "ready": action.ready,
                    "expectations": tuple(_enum_value(item.expectation) if item.expectation is not None else "UNCONFIRMED" for item in action.checks[:64]),
                    "subject_roles": tuple(_short(item.subject_role_display_name) for item in action.checks[:64]),
                    "gap_codes": tuple(gap.code for gap in action.gaps[:64]),
                },
            )
            for action in preview.actions[:128]
        )
        return _resolved(
            AssistantTemplateId.CHECK_PREVIEW_EXPLANATION,
            project_id,
            {
                "ready": preview.ready,
                "case_count": preview.case_count,
                "differential_pair_count": preview.differential_pair_count,
                "gap_codes": tuple(gap.code for gap in preview.gaps[:64]),
            },
            entities,
        )


def _resolved(
    template_id: AssistantTemplateId,
    subject_id: str,
    facts: Mapping[str, SafeFactValue],
    entities: Sequence[AssistantEntity],
) -> ResolvedAssistantSurface:
    surface_input = build_surface_input(
        template_id,
        subject_id=subject_id,
        facts={key: _safe_value(value) for key, value in facts.items()},
        entities=entities,
    )
    canonical = json.dumps(
        surface_input.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return ResolvedAssistantSurface(
        subject_id=subject_id,
        state_fingerprint=hashlib.sha256(canonical).hexdigest(),
        surface_input=surface_input,
    )


def _entity(
    entity_id: str,
    entity_type: AssistantEntityType,
    display_name: str,
    facts: Mapping[str, SafeFactValue],
) -> AssistantEntity:
    return AssistantEntity(
        entity_id=entity_id,
        entity_type=entity_type,
        display_name=_short(display_name),
        facts=tuple(
            AssistantFact(field=field, value=_safe_value(value))
            for field, value in sorted(facts.items())
        ),
    )


def _safe_value(value) -> SafeFactValue:
    if isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(_short(item) for item in list(value)[:64])
    return _short(value)


def _short(value, limit: int = 160) -> str:
    normalized = " ".join(str(value).split()).strip()
    return (normalized[:limit] or "未提供")


def _unique_short(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_short(value) for value in values))[:64]


def _enum_value(value) -> str:
    return str(getattr(value, "value", value))


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


__all__ = [
    "PROJECT_ASSISTANT_TEMPLATES",
    "AssistantSurfaceResolver",
    "ResolvedAssistantSurface",
]
