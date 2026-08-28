# Runner Evidence 语义载荷与不可变构造。

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from product.backend.core.identifiers import RUN_ID_PATTERN
from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.differential import PermissionTwin, TwinExecutionRole
from product.backend.core.verification.permissions.coverage import PermissionMutationCase
from product.backend.core.verification.facts import ExecutionFact, ExecutionOutcome, ObservationFact, ObservedEffect, SecurityEffectFact
from product.protocols.execution import ObserverRequirementBinding, ObserverRequirementKind, ProtocolModel
from product.protocols.observer import ObservationCompleteness, ObservationEnvelope, ObserverOutcome
from .input import _HEX, _validate_reason_codes

def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="python"))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _evidence_semantic_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


class Evidence(ProtocolModel):
    schema_version: Literal["1"] = "1"
    evidence_id: str = Field(pattern=r"^ev_[0-9a-f]{20}$")
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    case_snapshot: PermissionMutationCase
    twin_snapshot: PermissionTwin | None = None
    twin_role: TwinExecutionRole | None = None
    allow_control_valid: bool
    baseline_integrity: bool
    finding_pre_identity: str = Field(pattern=_HEX)
    execution_fact: ExecutionFact
    requirement_bindings: tuple[ObserverRequirementBinding, ...] = Field(default=(), max_length=16)
    observation_facts: tuple[ObservationFact, ...] = Field(default=(), max_length=19_200)
    security_effect_facts: tuple[SecurityEffectFact, ...] = Field(min_length=1, max_length=19_200)
    observations: tuple[ObservationEnvelope, ...] = Field(default=(), max_length=19_200)
    outcomes: tuple[ObserverOutcome, ...] = Field(default=(), max_length=64)
    verdict: CaseVerdict
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)
    evidence_hash: str = Field(pattern=_HEX)

    @model_validator(mode="after")
    def validate_evidence(self) -> Evidence:
        observations = tuple(sorted(self.observations, key=lambda item: (item.observer_id, item.phase.value, item.correlation.resource_id)))
        outcomes = tuple(sorted(self.outcomes, key=lambda item: item.observer_id))
        if len({(item.observer_id, item.phase, item.correlation.resource_id) for item in observations}) != len(observations):
            raise ValueError("evidence observations must have unique observer, phase, and resource")
        if len({item.observer_id for item in outcomes}) != len(outcomes):
            raise ValueError("evidence outcomes must have unique observer IDs")
        binding_map = {item.requirement_id: item for item in self.requirement_bindings}
        case_requirements = set(self.case_snapshot.required_observations)
        if len(binding_map) != len(self.requirement_bindings) or not case_requirements.issubset(binding_map):
            raise ValueError("evidence bindings must cover this case requirements")
        if (self.twin_snapshot is None) != (self.twin_role is None):
            raise ValueError("twin snapshot and role must be present together")
        if self.twin_snapshot is not None:
            expected_case = self.twin_snapshot.allow_case if self.twin_role is TwinExecutionRole.ALLOW_CONTROL else self.twin_snapshot.deny_case
            if expected_case != self.case_snapshot:
                raise ValueError("evidence case does not match its twin role")
        observer_bindings = {
            item.requirement_id: item
            for item in self.requirement_bindings
            if item.kind is ObserverRequirementKind.OBSERVER_SPEC
        }
        required_observer_ids = {
            item.observer_id
            for requirement, item in observer_bindings.items()
            if requirement in case_requirements
        }
        if any(
            item.required is not (item.observer_id in required_observer_ids)
            for item in outcomes
        ):
            raise ValueError("evidence outcomes must preserve observer roles")
        if len(observer_bindings) != len({item.observer_id for item in observer_bindings.values()}):
            raise ValueError("evidence bindings must have unique observer IDs")
        if {item.observer_id for item in observer_bindings.values()} != {item.observer_id for item in outcomes}:
            raise ValueError("evidence outcomes must exactly cover bound observers")
        bound_observer_ids = {item.observer_id for item in observer_bindings.values()}
        if any(item.observer_id not in bound_observer_ids for item in observations):
            raise ValueError("evidence observation references an unbound observer")
        outcome_map = {item.observer_id: item for item in outcomes}
        for requirement, binding in observer_bindings.items():
            assert binding.observer_id is not None
            bound_observations = tuple(item for item in observations if item.observer_id == binding.observer_id)
            expected_keys = {
                (binding.observer_id, phase, resource_id)
                for resource_id in self.case_snapshot.resource_ids
                for phase in binding.phases
            }
            actual_keys = {
                (item.observer_id, item.phase, item.correlation.resource_id)
                for item in bound_observations
            }
            if any(item.phase not in binding.phases for item in bound_observations):
                raise ValueError("evidence contains an observer phase outside its binding")
            if any(item.observer_type is not binding.observer_type for item in bound_observations):
                raise ValueError("evidence observer type does not match its binding")
            if outcome_map[binding.observer_id].status.value == "AVAILABLE" and actual_keys != expected_keys:
                raise ValueError("available observer outcome requires every resource and phase")
            if outcome_map[binding.observer_id].status.value == "AVAILABLE" and not bound_observations:
                raise ValueError("available outcome requires an observation envelope")
        for envelope in observations:
            correlation = envelope.correlation
            if correlation.case_id != self.case_snapshot.case_id or correlation.resource_id not in self.case_snapshot.resource_ids:
                raise ValueError("observation correlation does not match the case snapshot")
            if envelope.completeness is ObservationCompleteness.COMPLETE and envelope.causality.value != "CORRELATED":
                raise ValueError("complete evidence observation must be correlated")
        confirmed_effect = any(item.state is ObservedEffect.CONFIRMED for item in self.security_effect_facts)
        unavailable_required = any(
            item.observer_id in required_observer_ids
            and item.status.value != "AVAILABLE"
            for item in outcomes
        )
        failed_request = self.execution_fact.outcome in {ExecutionOutcome.FAILED, ExecutionOutcome.UNKNOWN}
        if (unavailable_required or failed_request) and self.verdict is not CaseVerdict.INCONCLUSIVE and not (self.verdict is CaseVerdict.VULNERABLE and confirmed_effect):
            raise ValueError("incomplete required observation can only produce INCONCLUSIVE evidence")
        if self.verdict not in {CaseVerdict.SAFE, CaseVerdict.VULNERABLE, CaseVerdict.INCONCLUSIVE}:
            raise ValueError(" evidence verdict must be SAFE, VULNERABLE, or INCONCLUSIVE")
        expected_fact_keys = {
            (requirement, resource_id)
            for requirement in binding_map
            for resource_id in self.case_snapshot.resource_ids
        }
        actual_fact_keys = {
            (item.requirement_id, item.resource_id)
            for item in self.observation_facts
        }
        if len(actual_fact_keys) != len(self.observation_facts) or actual_fact_keys != expected_fact_keys:
            raise ValueError("evidence observation facts must exactly cover every requirement and resource")
        effect_keys = {(item.effect_id, item.resource_id) for item in self.security_effect_facts}
        expected_effect_keys = {
            (effect_id, resource_id)
            for effect_id in {
                effect_id
                for action_id in {self.case_snapshot.action_id}
                for effect_id in (
                    item.effect_id
                    for item in self.security_effect_facts
                    if item.effect_id
                )
            }
            for resource_id in self.case_snapshot.resource_ids
        }
        if len(effect_keys) != len(self.security_effect_facts) or effect_keys != expected_effect_keys:
            raise ValueError("evidence effect facts must uniquely cover every effect and resource")
        safe_effect_state = (
            ObservedEffect.CONFIRMED
            if self.twin_role is TwinExecutionRole.ALLOW_CONTROL
            or all(item.value == "ALLOW" for item in self.case_snapshot.expectations)
            else ObservedEffect.ABSENT
        )
        if self.verdict is CaseVerdict.SAFE and (
            failed_request
            or not self.baseline_integrity
            or not self.allow_control_valid
            or any(item.state is not safe_effect_state for item in self.security_effect_facts)
        ):
            raise ValueError("safe evidence requires a valid control, baseline, and role-appropriate effects")
        if self.verdict is CaseVerdict.VULNERABLE and not confirmed_effect and self.execution_fact.outcome is not ExecutionOutcome.ACCEPTED:
            raise ValueError("vulnerable evidence requires accepted execution or a confirmed effect")
        if self.finding_pre_identity != self.case_snapshot.finding_pre_identity:
            raise ValueError("finding_pre_identity must match the case snapshot")
        normalized_reasons = _validate_reason_codes(self.reason_codes, "evidence reason_codes")
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "outcomes", outcomes)
        object.__setattr__(self, "observation_facts", tuple(sorted(self.observation_facts, key=lambda item: (item.requirement_id, item.resource_id))))
        object.__setattr__(self, "reason_codes", normalized_reasons)
        expected = _evidence_semantic_sha256(_evidence_semantic_payload(self))
        if self.evidence_id != f"ev_{expected[:20]}" or self.evidence_hash != expected:
            raise ValueError("evidence_hash does not match the evidence semantic payload")
        return self


def _evidence_semantic_payload(evidence: Evidence) -> dict[str, Any]:
    payload = evidence.model_dump(mode="json")
    payload.pop("evidence_id", None)
    payload.pop("evidence_hash", None)
    payload["observations"] = sorted(
        payload.get("observations", ()),
        key=lambda item: (item["observer_id"], item["phase"], item["correlation"]["resource_id"]),
    )
    payload["outcomes"] = sorted(payload.get("outcomes", ()), key=lambda item: item["observer_id"])
    return payload


def build_evidence(**fields: Any) -> Evidence:
    """构造内容寻址 Evidence，统一计算语义 hash 和 evidence_id。"""

    if "evidence_id" in fields or "evidence_hash" in fields:
        raise TypeError("build_evidence computes evidence_id and evidence_hash")
    semantic_payload = _jsonable(fields)
    semantic_payload["observations"] = sorted(
        semantic_payload.get("observations", ()),
        key=lambda item: (item["observer_id"], item["phase"], item["correlation"]["resource_id"]),
    )
    semantic_payload["outcomes"] = sorted(semantic_payload.get("outcomes", ()), key=lambda item: item["observer_id"])
    semantic_payload["observation_facts"] = sorted(
        semantic_payload.get("observation_facts", ()),
        key=lambda item: (item["requirement_id"], item["resource_id"]),
    )
    semantic_payload["reason_codes"] = sorted(semantic_payload.get("reason_codes", ()))
    expected = _evidence_semantic_sha256(semantic_payload)
    return Evidence(
        **fields,
        evidence_id=f"ev_{expected[:20]}",
        evidence_hash=expected,
    )
