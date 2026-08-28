# Observer 结果、归一状态与 canonical/hash 边界。

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .config import (
    CausalityStatus,
    ObservationCompleteness,
    ObservationPhase,
    ObserverModel,
    ObserverOutcomeStatus,
    ObserverType,
    ProvenanceType,
    OBSERVER_STATE_MAX_BYTES,
    OBSERVER_STATE_MAX_DEPTH,
    OBSERVER_STATE_MAX_KEYS,
    _HEX_PATTERN,
    _ID_PATTERN,
    _REASON_PATTERN,
    _TEXT_PATTERN,
)
from .invocation import Correlation, ObservationWindow

def _reject_secret_values(value: Any, known_secrets: tuple[str, ...]) -> None:
    if isinstance(value, str):
        if any(secret and secret in value for secret in known_secrets):
            raise ValueError("known secret must not enter observer state")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("observer state keys must be strings")
            if any(secret and secret in key for secret in known_secrets):
                raise ValueError("known secret must not enter observer state")
            _reject_secret_values(item, known_secrets)
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            _reject_secret_values(item, known_secrets)


def _normalise_json_value(value: Any, *, depth: int, key_count: list[int]) -> Any:
    if depth > OBSERVER_STATE_MAX_DEPTH:
        raise ValueError("observer state nesting exceeds the limit")
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > 4096:
            raise ValueError("observer state string exceeds the limit")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("observer state cannot contain non-finite numbers")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str) or len(key) > 128:
                raise ValueError("observer state keys are bounded strings")
            key_count[0] += 1
            if key_count[0] > OBSERVER_STATE_MAX_KEYS:
                raise ValueError("observer state has too many keys")
            result[key] = _normalise_json_value(value[key], depth=depth + 1, key_count=key_count)
        return result
    if isinstance(value, (tuple, list)):
        if len(value) > OBSERVER_STATE_MAX_KEYS:
            raise ValueError("observer state array is too large")
        return [_normalise_json_value(item, depth=depth + 1, key_count=key_count) for item in value]
    raise ValueError("observer state contains a non-JSON value")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class NormalizedState(ObserverModel):
    canonical_data: dict[str, Any]
    canonical_sha256: str = Field(pattern=_HEX_PATTERN)
    byte_count: int = Field(ge=2, le=OBSERVER_STATE_MAX_BYTES)

    @model_validator(mode="after")
    def validate_hash(self) -> NormalizedState:
        normalized = _normalise_json_value(self.canonical_data, depth=0, key_count=[0])
        data = _json_bytes(normalized)
        if len(data) != self.byte_count or hashlib.sha256(data).hexdigest() != self.canonical_sha256:
            raise ValueError("normalized observer state hash or byte count does not match")
        object.__setattr__(self, "canonical_data", normalized)
        return self


def build_normalized_state(payload: Mapping[str, Any], *, known_secrets: tuple[str, ...] = ()) -> NormalizedState:
    """对脱敏 payload 生成确定性 canonical 状态；检测到秘密时立即拒绝。"""

    if not isinstance(payload, Mapping):
        raise ValueError("normalized observer state must be an object")
    _reject_secret_values(payload, known_secrets)
    normalized = _normalise_json_value(payload, depth=0, key_count=[0])
    data = _json_bytes(normalized)
    if len(data) > OBSERVER_STATE_MAX_BYTES:
        raise ValueError("normalized observer state exceeds the byte limit")
    return NormalizedState(
        canonical_data=normalized,
        canonical_sha256=hashlib.sha256(data).hexdigest(),
        byte_count=len(data),
    )


class ObservationProvenance(ObserverModel):
    provenance_type: ProvenanceType
    adapter_version: str = Field(pattern=_TEXT_PATTERN)
    target_id: str = Field(pattern=_ID_PATTERN)
    query_template_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    source_sha256: str = Field(pattern=_HEX_PATTERN)

    @model_validator(mode="after")
    def validate_provenance(self) -> ObservationProvenance:
        if self.provenance_type is ProvenanceType.SQLITE_QUERY and self.query_template_id is None:
            raise ValueError("sqlite provenance requires a query template")
        if self.provenance_type is ProvenanceType.AUDIT_LOG_WINDOW and self.query_template_id is not None:
            raise ValueError("audit log provenance cannot contain a query template")
        if self.provenance_type in {
            ProvenanceType.OWNER_API,
            ProvenanceType.AUDIT_LOG_WINDOW,
            ProvenanceType.ASYNC_TASK_API,
            ProvenanceType.AZURE_QUEUE_PEEK,
            ProvenanceType.AZURE_BLOB_OBJECT,
        } and self.query_template_id is not None:
            raise ValueError("this provenance type cannot contain a query template")
        return self


class ObservationEnvelope(ObserverModel):
    schema_version: Literal["1"] = "1"
    observer_id: str = Field(pattern=_ID_PATTERN)
    observer_type: ObserverType
    protocol_version: Literal["3"] = "3"
    phase: ObservationPhase
    target_id: str = Field(pattern=_ID_PATTERN)
    window: ObservationWindow
    correlation: Correlation
    causality: CausalityStatus
    completeness: ObservationCompleteness
    state: NormalizedState | None = None
    provenance: ObservationProvenance | None = None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)

    @field_validator("reason_codes")
    @classmethod
    def normalize_reasons(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(_REASON_PATTERN, value) for value in values):
            raise ValueError("observer reason codes must be stable uppercase codes")
        if len(set(values)) != len(values):
            raise ValueError("observer reason codes must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_envelope(self) -> ObservationEnvelope:
        if self.phase is not self.window.phase:
            raise ValueError("envelope phase and window phase must match")
        if self.completeness is ObservationCompleteness.COMPLETE:
            if self.state is None or self.provenance is None or self.causality is not CausalityStatus.CORRELATED or self.reason_codes:
                raise ValueError("complete observation requires correlated state and provenance without failure reasons")
        elif self.completeness is ObservationCompleteness.PARTIAL:
            if not self.reason_codes:
                raise ValueError("partial observation requires a reason")
        else:
            if self.state is not None or not self.reason_codes:
                raise ValueError("incomplete observation cannot contain state and requires a reason")
        expected_provenance = {
            ObserverType.OWNER_API: ProvenanceType.OWNER_API,
            ObserverType.READ_ONLY_SQLITE: ProvenanceType.SQLITE_QUERY,
            ObserverType.STRUCTURED_AUDIT_LOG: ProvenanceType.AUDIT_LOG_WINDOW,
            ObserverType.ASYNC_TASK_STATUS: ProvenanceType.ASYNC_TASK_API,
            ObserverType.AZURE_QUEUE_PEEK: ProvenanceType.AZURE_QUEUE_PEEK,
            ObserverType.AZURE_BLOB_OBJECT: ProvenanceType.AZURE_BLOB_OBJECT,
        }[self.observer_type]
        if self.provenance is not None and self.provenance.provenance_type is not expected_provenance:
            raise ValueError("observation provenance does not match observer type")
        if self.provenance is not None and self.provenance.target_id != self.target_id:
            raise ValueError("observation provenance target does not match envelope target")
        return self


class ObserverOutcome(ObserverModel):
    observer_id: str = Field(pattern=_ID_PATTERN)
    required: bool
    status: ObserverOutcomeStatus
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)


def evaluate_observer_outcome(
    envelope: ObservationEnvelope,
    *,
    required: bool,
    adapter_error: bool = False,
) -> ObserverOutcome:
    if adapter_error:
        status = ObserverOutcomeStatus.EXECUTION_ERROR
    elif envelope.completeness is not ObservationCompleteness.COMPLETE:
        status = ObserverOutcomeStatus.INCONCLUSIVE
    else:
        status = ObserverOutcomeStatus.AVAILABLE
    return ObserverOutcome(
        observer_id=envelope.observer_id,
        required=required,
        status=status,
        reason_codes=envelope.reason_codes,
    )
