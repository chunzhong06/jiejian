# =============================================================================
# Verification V2 纯判定核心
#
# 定位：只把已脱敏、已校验的请求和观察事实归约为单个 V2 case 结论。
# 本模块不依赖公共 wire DTO、Runner 或观察器适配器，也不执行目标请求。
# =============================================================================

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..domain.lifecycle import CaseVerdict
from .permission_coverage import PermissionMutationCaseV2
from .permissions import ActionDefinition, BatchAuthorizationMode, PermissionExpectation


_HEX = r"^[0-9a-f]{64}$"
_REASON = r"^[A-Z][A-Z0-9_]{0,127}$"
_ID = r"^[a-z][a-z0-9_.:-]{0,127}$"
_SENSITIVE_KEY = re.compile(r"authorization|cookie|credential|password|passwd|secret|token|api[_-]?key", re.I)
_URL = re.compile(r"(?:https?://|javascript:|data:|\\\\|\benv:)", re.I)


class EvaluationV2Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal["2"] = "2"


class RequestDecisionFact(EvaluationV2Model):
    status_code: int | None = Field(default=None, ge=100, le=599)
    failure_code: str | None = Field(default=None, pattern=_REASON)

    @model_validator(mode="after")
    def validate_response_or_failure(self) -> RequestDecisionFact:
        if (self.status_code is None) == (self.failure_code is None):
            raise ValueError("request fact requires exactly one response status or failure code")
        return self


class ObserverKindV2(StrEnum):
    OWNER_API = "OWNER_API"
    READ_ONLY_SQLITE = "READ_ONLY_SQLITE"
    STRUCTURED_AUDIT_LOG = "STRUCTURED_AUDIT_LOG"
    ASYNC_TASK_STATUS = "ASYNC_TASK_STATUS"
    AZURE_QUEUE_PEEK = "AZURE_QUEUE_PEEK"
    AZURE_BLOB_OBJECT = "AZURE_BLOB_OBJECT"


class DecisionPhaseV2(StrEnum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    EVENTUAL = "EVENTUAL"


def _validate_json_value(value: Any, *, depth: int = 0) -> None:
    if depth > 6:
        raise ValueError("canonical_data is too deeply nested")
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and (_URL.search(value) or len(value) > 2048):
            raise ValueError("canonical_data contains forbidden or unbounded text")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical_data must contain finite numbers")
        return
    if isinstance(value, Mapping):
        if len(value) > 64:
            raise ValueError("canonical_data contains too many keys")
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 128:
                raise ValueError("canonical_data keys must be bounded strings")
            if _SENSITIVE_KEY.search(key):
                raise ValueError("canonical_data contains a forbidden sensitive key")
            _validate_json_value(child, depth=depth + 1)
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        if len(value) > 256:
            raise ValueError("canonical_data contains too many items")
        for child in value:
            _validate_json_value(child, depth=depth + 1)
        return
    raise ValueError("canonical_data must be finite JSON")


class ObservationDecisionFact(EvaluationV2Model):
    requirement_id: str = Field(pattern=_ID)
    observer_kind: ObserverKindV2
    resource_id: str = Field(pattern=_ID)
    phase: DecisionPhaseV2
    available: bool
    complete: bool
    correlated: bool
    canonical_sha256: str | None = Field(default=None, pattern=_HEX)
    canonical_data: Any = None

    @model_validator(mode="after")
    def validate_observation(self) -> ObservationDecisionFact:
        if self.complete:
            if not self.available or not self.correlated or self.canonical_sha256 is None or self.canonical_data is None:
                raise ValueError("complete observation requires availability, correlation, hash, and data")
            _validate_json_value(self.canonical_data)
            if len(json.dumps(self.canonical_data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")) > 262_144:
                raise ValueError("canonical_data exceeds its bounded size")
        elif self.canonical_sha256 is not None or self.canonical_data is not None:
            raise ValueError("incomplete observation must not carry canonical state")
        return self


class CaseDecisionInput(EvaluationV2Model):
    case: PermissionMutationCaseV2
    action: ActionDefinition
    expected_statuses: tuple[int, ...] = Field(min_length=1, max_length=32)
    request: RequestDecisionFact
    required_observations: tuple[ObservationDecisionFact, ...] = Field(default=(), max_length=19_200)

    @model_validator(mode="after")
    def validate_case_input(self) -> CaseDecisionInput:
        if self.action.action_id != self.case.action_id:
            raise ValueError("action does not match the permission case")
        if len(set(self.expected_statuses)) != len(self.expected_statuses):
            raise ValueError("expected statuses must be unique")
        required = set(self.case.required_observers)
        if "http" not in required:
            raise ValueError("V2 cases require the fixed http request requirement")
        keys = set()
        kinds: dict[str, ObserverKindV2] = {}
        for fact in self.required_observations:
            key = (fact.requirement_id, fact.resource_id, fact.phase)
            if key in keys:
                raise ValueError("required observations must have unique requirement/resource/phase keys")
            keys.add(key)
            if fact.requirement_id not in required or fact.requirement_id == "http":
                raise ValueError("observation requirement is not bound to this case")
            if fact.resource_id not in self.case.resource_ids:
                raise ValueError("observation resource is outside the case")
            allowed_phases = {
                ObserverKindV2.OWNER_API: {DecisionPhaseV2.BEFORE, DecisionPhaseV2.AFTER},
                ObserverKindV2.READ_ONLY_SQLITE: {DecisionPhaseV2.BEFORE, DecisionPhaseV2.AFTER},
                ObserverKindV2.AZURE_BLOB_OBJECT: {DecisionPhaseV2.BEFORE, DecisionPhaseV2.AFTER},
                ObserverKindV2.STRUCTURED_AUDIT_LOG: {DecisionPhaseV2.AFTER, DecisionPhaseV2.EVENTUAL},
                ObserverKindV2.ASYNC_TASK_STATUS: {DecisionPhaseV2.EVENTUAL},
                ObserverKindV2.AZURE_QUEUE_PEEK: {DecisionPhaseV2.EVENTUAL},
            }[fact.observer_kind]
            if fact.phase not in allowed_phases:
                raise ValueError("observation phase is not valid for its observer kind")
            previous = kinds.setdefault(fact.requirement_id, fact.observer_kind)
            if previous is not fact.observer_kind:
                raise ValueError("one requirement cannot change observer kind")
        return self


class EffectV2(StrEnum):
    CONFIRMED = "CONFIRMED"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


class EvaluationReasonCodeV2(StrEnum):
    REQUIRED_OBSERVER_INCOMPLETE = "V2_REQUIRED_OBSERVER_INCOMPLETE"
    REQUEST_FAILED = "V2_REQUEST_FAILED"
    UNEXPECTED_HTTP_RESPONSE = "V2_UNEXPECTED_HTTP_RESPONSE"
    ALLOW_BASELINE_REJECTED = "V2_ALLOW_BASELINE_REJECTED"
    ALLOW_EFFECT_UNCONFIRMED = "V2_ALLOW_EFFECT_UNCONFIRMED"
    UNAUTHORIZED_REQUEST_ACCEPTED = "V2_UNAUTHORIZED_REQUEST_ACCEPTED"
    UNAUTHORIZED_SIDE_EFFECT = "V2_UNAUTHORIZED_SIDE_EFFECT"
    MIXED_BATCH_ATOMIC_ACCEPTED = "V2_MIXED_BATCH_ATOMIC_ACCEPTED"


def _reasons(*values: EvaluationReasonCodeV2) -> tuple[str, ...]:
    return tuple(sorted({value.value for value in values}))


def _required_phases(kind: ObserverKindV2) -> tuple[DecisionPhaseV2, ...]:
    if kind in {ObserverKindV2.OWNER_API, ObserverKindV2.READ_ONLY_SQLITE, ObserverKindV2.AZURE_BLOB_OBJECT}:
        return (DecisionPhaseV2.BEFORE, DecisionPhaseV2.AFTER)
    if kind is ObserverKindV2.STRUCTURED_AUDIT_LOG:
        return (DecisionPhaseV2.AFTER, DecisionPhaseV2.EVENTUAL)
    return (DecisionPhaseV2.EVENTUAL,)


def _facts_by_requirement(input_data: CaseDecisionInput) -> dict[str, tuple[ObservationDecisionFact, ...]]:
    grouped: dict[str, list[ObservationDecisionFact]] = {}
    for fact in input_data.required_observations:
        grouped.setdefault(fact.requirement_id, []).append(fact)
    return {key: tuple(value) for key, value in grouped.items()}


def _effects(input_data: CaseDecisionInput) -> tuple[dict[str, EffectV2], bool]:
    grouped = _facts_by_requirement(input_data)
    effects: dict[str, EffectV2] = {resource_id: EffectV2.ABSENT for resource_id in input_data.case.resource_ids}
    complete = True
    for requirement in input_data.case.required_observers:
        if requirement == "http":
            continue
        facts = grouped.get(requirement, ())
        if not facts:
            return {resource_id: EffectV2.UNKNOWN for resource_id in input_data.case.resource_ids}, False
        kind = facts[0].observer_kind
        by_key = {(fact.resource_id, fact.phase): fact for fact in facts}
        for resource_id in input_data.case.resource_ids:
            if kind in {ObserverKindV2.OWNER_API, ObserverKindV2.READ_ONLY_SQLITE, ObserverKindV2.AZURE_BLOB_OBJECT}:
                expected = tuple((resource_id, phase) for phase in _required_phases(kind))
                selected = [by_key.get(key) for key in expected]
                if any(fact is None or not fact.complete for fact in selected):
                    effects[resource_id] = EffectV2.UNKNOWN
                    complete = False
                    continue
            else:
                selected = [fact for fact in facts if fact.resource_id == resource_id and fact.phase in _required_phases(kind)]
                if kind is ObserverKindV2.STRUCTURED_AUDIT_LOG:
                    selected = [fact for fact in selected if fact.complete]
                if not selected or any(not fact.complete for fact in selected):
                    effects[resource_id] = EffectV2.UNKNOWN
                    complete = False
                    continue
            local_effect = EffectV2.ABSENT
            if kind in {ObserverKindV2.OWNER_API, ObserverKindV2.READ_ONLY_SQLITE, ObserverKindV2.AZURE_BLOB_OBJECT}:
                local_effect = EffectV2.CONFIRMED if selected[0].canonical_sha256 != selected[1].canonical_sha256 else EffectV2.ABSENT
            elif kind is ObserverKindV2.STRUCTURED_AUDIT_LOG:
                records = []
                for fact in selected:
                    data = fact.canonical_data
                    records.extend(data.get("records", []) if isinstance(data, Mapping) else [])
                if any(isinstance(record, Mapping) and record.get("event_type") == "SIDE_EFFECT" and record.get("effect") == "APPLIED" for record in records):
                    local_effect = EffectV2.CONFIRMED
            elif kind is ObserverKindV2.ASYNC_TASK_STATUS:
                data = selected[-1].canonical_data
                if isinstance(data, Mapping) and data.get("task_state") == "SUCCESS" and isinstance(data.get("final_result"), Mapping) and data["final_result"].get("effect") == "APPLIED":
                    local_effect = EffectV2.CONFIRMED
                elif isinstance(data, Mapping) and data.get("task_state") == "NOT_CREATED" and selected[-1].phase is DecisionPhaseV2.EVENTUAL:
                    local_effect = EffectV2.ABSENT
                else:
                    local_effect = EffectV2.UNKNOWN
                    complete = False
            elif kind is ObserverKindV2.AZURE_QUEUE_PEEK:
                data = selected[-1].canonical_data
                if isinstance(data, Mapping) and data.get("window_complete") is True and data.get("matched_count") == 0 and data.get("messages") == []:
                    local_effect = EffectV2.ABSENT
                elif isinstance(data, Mapping) and data.get("matched_count", 0) > 0 and data.get("messages"):
                    local_effect = EffectV2.CONFIRMED
                else:
                    local_effect = EffectV2.UNKNOWN
                    complete = False
            if local_effect is EffectV2.CONFIRMED or effects[resource_id] is EffectV2.ABSENT and local_effect is EffectV2.UNKNOWN:
                effects[resource_id] = local_effect
    if any(resource_id not in effects for resource_id in input_data.case.resource_ids):
        complete = False
    return effects, complete


def evaluate_permission_case_v2(input_data: CaseDecisionInput) -> tuple[CaseVerdict, tuple[str, ...]]:
    effects, observations_complete = _effects(input_data)
    if not observations_complete:
        return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.REQUIRED_OBSERVER_INCOMPLETE)
    if input_data.request.status_code is None:
        return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.REQUEST_FAILED)
    accepted = input_data.request.status_code in input_data.expected_statuses
    denied = input_data.request.status_code in {401, 403, 404}
    if not accepted and not denied:
        return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.UNEXPECTED_HTTP_RESPONSE)
    case = input_data.case
    side_effect = input_data.action.side_effect
    expectations = case.expectations
    if case.batch_mode is None:
        effect = effects[case.resource_ids[0]]
        expected = expectations[0]
        if expected is PermissionExpectation.DENY:
            if effect is EffectV2.CONFIRMED:
                return CaseVerdict.VULNERABLE, _reasons(EvaluationReasonCodeV2.UNAUTHORIZED_SIDE_EFFECT)
            if accepted:
                return CaseVerdict.VULNERABLE, _reasons(EvaluationReasonCodeV2.UNAUTHORIZED_REQUEST_ACCEPTED)
            if denied and (not side_effect or effect is EffectV2.ABSENT):
                return CaseVerdict.SAFE, ()
            return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.REQUIRED_OBSERVER_INCOMPLETE)
        if denied:
            return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.ALLOW_BASELINE_REJECTED)
        if side_effect and effect is not EffectV2.CONFIRMED:
            return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.ALLOW_EFFECT_UNCONFIRMED)
        return (CaseVerdict.SAFE, ()) if accepted else (CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.UNEXPECTED_HTTP_RESPONSE))
    deny_effects = [effect for effect, expected in zip(effects.values(), expectations) if expected is PermissionExpectation.DENY]
    allow_effects = [effect for effect, expected in zip(effects.values(), expectations) if expected is PermissionExpectation.ALLOW]
    if case.batch_mode is BatchAuthorizationMode.ALL_DENY:
        if EffectV2.CONFIRMED in deny_effects:
            return CaseVerdict.VULNERABLE, _reasons(EvaluationReasonCodeV2.UNAUTHORIZED_SIDE_EFFECT)
        if accepted:
            return CaseVerdict.VULNERABLE, _reasons(EvaluationReasonCodeV2.UNAUTHORIZED_REQUEST_ACCEPTED)
        if denied and all(effect is EffectV2.ABSENT for effect in deny_effects):
            return CaseVerdict.SAFE, ()
        return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.REQUIRED_OBSERVER_INCOMPLETE)
    if case.batch_mode is BatchAuthorizationMode.ALL_ALLOW:
        if denied:
            return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.ALLOW_BASELINE_REJECTED)
        if side_effect and any(effect is not EffectV2.CONFIRMED for effect in allow_effects):
            return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.ALLOW_EFFECT_UNCONFIRMED)
        return (CaseVerdict.SAFE, ()) if accepted else (CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.UNEXPECTED_HTTP_RESPONSE))
    if EffectV2.CONFIRMED in deny_effects:
        return CaseVerdict.VULNERABLE, _reasons(EvaluationReasonCodeV2.UNAUTHORIZED_SIDE_EFFECT)
    if case.atomic:
        if accepted:
            return CaseVerdict.VULNERABLE, _reasons(EvaluationReasonCodeV2.MIXED_BATCH_ATOMIC_ACCEPTED)
        if denied and all(effect is EffectV2.ABSENT for effect in deny_effects):
            return CaseVerdict.SAFE, ()
        return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.REQUIRED_OBSERVER_INCOMPLETE)
    if denied:
        return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.ALLOW_BASELINE_REJECTED)
    if side_effect and any(effect is not EffectV2.CONFIRMED for effect in allow_effects):
        return CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.ALLOW_EFFECT_UNCONFIRMED)
    return (CaseVerdict.SAFE, ()) if accepted and all(effect is EffectV2.ABSENT for effect in deny_effects) else (CaseVerdict.INCONCLUSIVE, _reasons(EvaluationReasonCodeV2.REQUIRED_OBSERVER_INCOMPLETE))
