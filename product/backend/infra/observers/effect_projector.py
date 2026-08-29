# =============================================================================
# 确定性业务效果投影器
#
# 定位
#   在规范化 ObservationEnvelope 与 Verification 事实之间解释冻结业务效果。
#
# 职责
#   按 effect identity/projector version 选择目标投影｜形成 ObservationFact｜聚合 SecurityEffectFact
#
# 边界
#   不读取 live Target、数据库或 Sample；不使用 whole-state hash，也不产生 Verdict/Finding。
# =============================================================================

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from product.backend.core.verification.facts import (
    DisclosureProof,
    ObservationFact,
    ObservedEffect,
    SecurityEffectFact,
    TemporalClosure,
    aggregate_security_effect,
)
from product.backend.core.verification.permissions import (
    SecurityEffectDefinition,
    SecurityEffectKind,
)
from product.protocols import (
    CausalityStatus,
    ObservationCompleteness,
    ObservationEnvelope,
    ObservationPhase,
    ObserverType,
)


_PHASE_ORDER = {
    ObservationPhase.BASELINE: 0,
    ObservationPhase.BEFORE: 1,
    ObservationPhase.AFTER: 2,
    ObservationPhase.EVENTUAL: 3,
}
_ABSENT_STATES = frozenset(
    {"ABSENT", "DELETED", "MISSING", "NOT_CREATED", "REVOKED"}
)


@dataclass(frozen=True)
class EffectProjection:
    observation_facts: tuple[ObservationFact, ...]
    security_effect_fact: SecurityEffectFact


class EffectProjector:
    """只依据冻结 Effect、Binding 与已发布观察形成确定性业务事实。"""

    def __init__(self, *, observer_bindings: Mapping[str, Any]) -> None:
        self._observer_bindings = observer_bindings

    def project(
        self,
        *,
        case_id: str,
        resource_id: str,
        effect: SecurityEffectDefinition,
        effect_binding: Any,
        envelopes: tuple[ObservationEnvelope, ...],
        baseline_integrity: bool,
        disclosure_proof: DisclosureProof | None = None,
    ) -> EffectProjection:
        """按单个业务效果和资源形成观察事实及其唯一聚合事实。"""

        requirement_ids = tuple(
            dict.fromkeys(
                (
                    *effect_binding.required_channels,
                    *effect_binding.corroborating_channels,
                )
            )
        )
        observations = tuple(
            self._project_requirement(
                case_id=case_id,
                resource_id=resource_id,
                effect=effect,
                projection_version=effect_binding.projection_version,
                requirement_id=requirement_id,
                envelopes=envelopes,
                required=requirement_id in effect_binding.required_channels,
                disclosure_proof=disclosure_proof,
            )
            for requirement_id in requirement_ids
        )
        security_effect = aggregate_security_effect(
            effect,
            resource_id=resource_id,
            required_requirement_ids=effect_binding.required_channels,
            corroborating_requirement_ids=effect_binding.corroborating_channels,
            observations=observations,
            baseline_integrity=baseline_integrity,
            disclosure_proof=disclosure_proof,
        )
        return EffectProjection(
            observation_facts=observations,
            security_effect_fact=security_effect,
        )

    def _project_requirement(
        self,
        *,
        case_id: str,
        resource_id: str,
        effect: SecurityEffectDefinition,
        projection_version: str,
        requirement_id: str,
        envelopes: tuple[ObservationEnvelope, ...],
        required: bool,
        disclosure_proof: DisclosureProof | None,
    ) -> ObservationFact:
        binding = self._observer_bindings[requirement_id]
        selected = tuple(
            sorted(
                (
                    item
                    for item in envelopes
                    if item.observer_id == binding.observer_id
                    and item.observer_type is binding.observer_type
                    and item.correlation.case_id == case_id
                    and item.correlation.resource_id == resource_id
                ),
                key=lambda item: _PHASE_ORDER[item.phase],
            )
        )
        if projection_version != "v1":
            return _unknown_fact(
                effect.effect_id,
                requirement_id,
                resource_id,
                reason="EFFECT_PROJECTOR_UNSUPPORTED",
            )
        trustworthy = bool(selected) and all(
            item.completeness is ObservationCompleteness.COMPLETE
            and item.causality is CausalityStatus.CORRELATED
            and item.state is not None
            for item in selected
        )
        if not trustworthy:
            return _unknown_fact(
                effect.effect_id,
                requirement_id,
                resource_id,
                reason=(
                    "REQUIRED_OBSERVER_INCOMPLETE"
                    if required
                    else "SUPPORTING_OBSERVER_INCOMPLETE"
                ),
            )

        closure = _temporal_closure(binding.phases, selected)
        if effect.kind is SecurityEffectKind.DATA_DISCLOSURE:
            return _project_disclosure(
                effect.effect_id,
                requirement_id,
                resource_id,
                closure,
                disclosure_proof,
            )
        states = tuple(item.state.canonical_data for item in selected if item.state)
        if binding.observer_type in {
            ObserverType.OWNER_API,
            ObserverType.READ_ONLY_SQLITE,
            ObserverType.AZURE_BLOB_OBJECT,
        }:
            return _project_target_state(
                effect,
                requirement_id,
                resource_id,
                binding.observer_type,
                states,
                closure,
            )
        if binding.observer_type is ObserverType.STRUCTURED_AUDIT_LOG:
            return _project_audit(
                effect,
                requirement_id,
                resource_id,
                states,
                closure,
            )
        if binding.observer_type is ObserverType.ASYNC_TASK_STATUS:
            return _project_task(
                effect,
                requirement_id,
                resource_id,
                states[-1],
                closure,
            )
        if binding.observer_type is ObserverType.AZURE_QUEUE_PEEK:
            return _project_queue(
                effect,
                requirement_id,
                resource_id,
                states[-1],
                closure,
            )
        return _unknown_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            reason="EFFECT_PROJECTOR_UNSUPPORTED",
            closure=closure,
            reliable=True,
            correlated=True,
        )


def _temporal_closure(
    phases: tuple[ObservationPhase, ...],
    selected: tuple[ObservationEnvelope, ...],
) -> TemporalClosure:
    present = {item.phase for item in selected}
    if set(phases) == {ObservationPhase.EVENTUAL}:
        closed = ObservationPhase.EVENTUAL in present
    else:
        closed = ObservationPhase.AFTER in present and (
            ObservationPhase.EVENTUAL not in phases
            or ObservationPhase.EVENTUAL in present
        )
    return TemporalClosure.CLOSED if closed else TemporalClosure.OPEN


def _project_target_state(
    effect: SecurityEffectDefinition,
    requirement_id: str,
    resource_id: str,
    observer_type: ObserverType,
    states: tuple[Mapping[str, Any], ...],
    closure: TemporalClosure,
) -> ObservationFact:
    projections = tuple(
        _target_projection(observer_type, state, resource_id) for state in states
    )
    if len(projections) < 2 or any(item is None for item in projections):
        return _unknown_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            reason="OBSERVATION_UNINTERPRETED",
            closure=closure,
            reliable=True,
            correlated=True,
        )
    before = projections[0]
    after = projections[-1]
    assert before is not None and after is not None
    if effect.kind is SecurityEffectKind.OBJECT_CREATION:
        if not before[0] and after[0]:
            return _known_fact(
                effect.effect_id,
                requirement_id,
                resource_id,
                ObservedEffect.CONFIRMED,
                closure,
            )
        if closure is TemporalClosure.CLOSED:
            return _known_fact(
                effect.effect_id,
                requirement_id,
                resource_id,
                ObservedEffect.ABSENT,
                closure,
            )
    elif effect.kind is SecurityEffectKind.STATE_MUTATION:
        before_value = _mutation_value(before, effect.expected_state)
        after_value = _mutation_value(after, effect.expected_state)
        if before[0] and after[0] and before_value != after_value:
            if effect.expected_state is None or after[1] == effect.expected_state:
                return _known_fact(
                    effect.effect_id,
                    requirement_id,
                    resource_id,
                    ObservedEffect.CONFIRMED,
                    closure,
                )
        if closure is TemporalClosure.CLOSED:
            return _known_fact(
                effect.effect_id,
                requirement_id,
                resource_id,
                ObservedEffect.ABSENT,
                closure,
            )
    return _unknown_fact(
        effect.effect_id,
        requirement_id,
        resource_id,
        reason=(
            "TEMPORAL_WINDOW_OPEN"
            if closure is TemporalClosure.OPEN
            else "EFFECT_PROJECTOR_UNSUPPORTED"
        ),
        closure=closure,
        reliable=True,
        correlated=True,
    )


def _target_projection(
    observer_type: ObserverType,
    data: Mapping[str, Any],
    resource_id: str,
) -> tuple[bool, str | None, str | None] | None:
    if observer_type is ObserverType.OWNER_API:
        candidate: Mapping[str, Any] | None = data
    elif observer_type is ObserverType.READ_ONLY_SQLITE:
        rows = data.get("rows")
        candidate = next(
            (
                row
                for row in rows
                if isinstance(row, Mapping) and row.get("resource_id") == resource_id
            ),
            None,
        ) if isinstance(rows, list) else None
        if candidate is None and data.get("row_count") == 0:
            return False, None, None
    elif observer_type is ObserverType.AZURE_BLOB_OBJECT:
        objects = data.get("objects")
        if not isinstance(objects, list):
            return None
        candidate = next(
            (
                item
                for item in objects
                if isinstance(item, Mapping)
                and isinstance(item.get("metadata"), Mapping)
                and item["metadata"].get("resource_id") == resource_id
            ),
            None,
        )
        return (
            (False, None, None)
            if candidate is None
            else (
                True,
                None,
                str(
                    candidate.get("content_sha256")
                    or candidate.get("etag")
                    or candidate.get("name")
                    or ""
                ),
            )
        )
    else:
        return None
    if not isinstance(candidate, Mapping) or candidate.get("resource_id") != resource_id:
        return None
    workflow_state = candidate.get("workflow_state")
    value = candidate.get("value")
    state_text = str(workflow_state) if workflow_state is not None else None
    value_text = str(value) if value is not None else None
    exists = state_text is not None and state_text.upper() not in _ABSENT_STATES
    return exists, state_text, value_text


def _mutation_value(
    projection: tuple[bool, str | None, str | None],
    expected_state: str | None,
) -> tuple[str | None, ...]:
    return (projection[1],) if expected_state is not None else (projection[1], projection[2])


def _project_audit(
    effect: SecurityEffectDefinition,
    requirement_id: str,
    resource_id: str,
    states: tuple[Mapping[str, Any], ...],
    closure: TemporalClosure,
) -> ObservationFact:
    supported = effect.kind in {
        SecurityEffectKind.EXTERNAL_DISPATCH,
        SecurityEffectKind.RESTRICTED_FUNCTION_INVOCATION,
    }
    if not supported:
        return _unknown_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            reason="EFFECT_PROJECTOR_UNSUPPORTED",
            closure=closure,
            reliable=True,
            correlated=True,
        )
    groups = tuple(state.get("records") for state in states)
    if not all(
        isinstance(group, (list, tuple))
        and all(isinstance(record, Mapping) for record in group)
        for group in groups
    ):
        return _unknown_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            reason="OBSERVATION_UNINTERPRETED",
            closure=closure,
            correlated=True,
        )
    records = tuple(record for group in groups for record in group)
    applied = any(
        record.get("event_type") == "SIDE_EFFECT"
        and record.get("effect") == "APPLIED"
        and record.get("effect_id") == effect.effect_id
        for record in records
    )
    if applied:
        return _known_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            ObservedEffect.CONFIRMED,
            closure,
        )
    if closure is TemporalClosure.CLOSED:
        return _known_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            ObservedEffect.ABSENT,
            closure,
        )
    return _unknown_fact(
        effect.effect_id,
        requirement_id,
        resource_id,
        reason="TEMPORAL_WINDOW_OPEN",
        closure=closure,
        reliable=True,
        correlated=True,
    )


def _project_task(
    effect: SecurityEffectDefinition,
    requirement_id: str,
    resource_id: str,
    data: Mapping[str, Any],
    closure: TemporalClosure,
) -> ObservationFact:
    if effect.kind not in {
        SecurityEffectKind.OBJECT_CREATION,
        SecurityEffectKind.RESTRICTED_FUNCTION_INVOCATION,
    }:
        return _unknown_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            reason="EFFECT_PROJECTOR_UNSUPPORTED",
            closure=closure,
            reliable=True,
            correlated=True,
        )
    if closure is not TemporalClosure.CLOSED:
        return _unknown_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            reason="TEMPORAL_WINDOW_OPEN",
            closure=closure,
            reliable=True,
            correlated=True,
        )
    final_result = data.get("final_result")
    confirmed = (
        data.get("task_state") == "SUCCESS"
        and isinstance(final_result, Mapping)
        and (
            final_result.get("effect") == "APPLIED"
            or (
                effect.kind is SecurityEffectKind.OBJECT_CREATION
                and bool(final_result.get("artifact_id"))
            )
        )
    )
    if confirmed:
        return _known_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            ObservedEffect.CONFIRMED,
            closure,
        )
    if data.get("task_state") == "NOT_CREATED":
        return _known_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            ObservedEffect.ABSENT,
            closure,
        )
    return _unknown_fact(
        effect.effect_id,
        requirement_id,
        resource_id,
        reason="OBSERVATION_UNINTERPRETED",
        closure=closure,
        reliable=True,
        correlated=True,
    )


def _project_queue(
    effect: SecurityEffectDefinition,
    requirement_id: str,
    resource_id: str,
    data: Mapping[str, Any],
    closure: TemporalClosure,
) -> ObservationFact:
    messages = data.get("messages")
    matched_count = data.get("matched_count")
    if (
        effect.kind is SecurityEffectKind.EXTERNAL_DISPATCH
        and isinstance(matched_count, int)
        and not isinstance(matched_count, bool)
        and matched_count > 0
        and isinstance(messages, list)
        and bool(messages)
    ):
        return _known_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            ObservedEffect.CONFIRMED,
            closure,
        )
    if (
        effect.kind is SecurityEffectKind.EXTERNAL_DISPATCH
        and closure is TemporalClosure.CLOSED
        and data.get("window_complete") is True
        and matched_count == 0
        and messages == []
    ):
        return _known_fact(
            effect.effect_id,
            requirement_id,
            resource_id,
            ObservedEffect.ABSENT,
            closure,
        )
    return _unknown_fact(
        effect.effect_id,
        requirement_id,
        resource_id,
        reason=(
            "EFFECT_PROJECTOR_UNSUPPORTED"
            if effect.kind is not SecurityEffectKind.EXTERNAL_DISPATCH
            else "OBSERVATION_WINDOW_INCOMPLETE"
        ),
        closure=(
            TemporalClosure.OPEN
            if data.get("window_complete") is not True
            else closure
        ),
        reliable=True,
        correlated=True,
    )


def _project_disclosure(
    effect_id: str,
    requirement_id: str,
    resource_id: str,
    closure: TemporalClosure,
    proof: DisclosureProof | None,
) -> ObservationFact:
    if proof is not None and proof.projection_complete:
        return _known_fact(
            effect_id,
            requirement_id,
            resource_id,
            ObservedEffect.CONFIRMED if proof.matched else ObservedEffect.ABSENT,
            closure,
        )
    return _unknown_fact(
        effect_id,
        requirement_id,
        resource_id,
        reason="DISCLOSURE_PROJECTION_INCOMPLETE",
        closure=closure,
        reliable=True,
        correlated=True,
    )


def _known_fact(
    effect_id: str,
    requirement_id: str,
    resource_id: str,
    effect: ObservedEffect,
    closure: TemporalClosure,
) -> ObservationFact:
    return ObservationFact(
        effect_id=effect_id,
        requirement_id=requirement_id,
        resource_id=resource_id,
        effect=effect,
        complete=True,
        reliable=True,
        correlated=True,
        temporal_closure=closure,
        reason_codes=()
        if closure is TemporalClosure.CLOSED
        else ("TEMPORAL_WINDOW_OPEN",),
    )


def _unknown_fact(
    effect_id: str,
    requirement_id: str,
    resource_id: str,
    *,
    reason: str,
    closure: TemporalClosure = TemporalClosure.UNKNOWN,
    reliable: bool = False,
    correlated: bool = False,
) -> ObservationFact:
    return ObservationFact(
        effect_id=effect_id,
        requirement_id=requirement_id,
        resource_id=resource_id,
        effect=ObservedEffect.UNKNOWN,
        complete=False,
        reliable=reliable,
        correlated=correlated,
        temporal_closure=closure,
        reason_codes=(reason,),
    )


__all__ = ["EffectProjection", "EffectProjector"]
