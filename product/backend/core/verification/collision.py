# =============================================================================
# 并发碰撞实验的安全事实
#
# 定位
#   独立于普通串行 Runner，描述 TOCTOU 碰撞预算、观察与三态结论。
#
# 职责
#   约束实验预算｜区分真实业务异常与弱线索｜按跨轮复现生成结论
#
# 边界
#   不发送请求、不解释 HTTP 表面状态，也不改写 Permission Verification。
# =============================================================================

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.lifecycle import RunVerdict


class CollisionModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["1"] = "1"


class CollisionAnomaly(StrEnum):
    UNAUTHORIZED_EFFECT = "UNAUTHORIZED_EFFECT"
    DUPLICATE_EFFECT = "DUPLICATE_EFFECT"
    INVALID_STATE = "INVALID_STATE"
    QUOTA_BYPASS = "QUOTA_BYPASS"
    REVOKED_ACCESS_SUCCEEDED = "REVOKED_ACCESS_SUCCEEDED"


class CollisionClue(StrEnum):
    LATENCY_VARIATION = "LATENCY_VARIATION"
    RESPONSE_ORDER_VARIATION = "RESPONSE_ORDER_VARIATION"
    TRANSIENT_SERVER_ERROR = "TRANSIENT_SERVER_ERROR"
    SINGLE_FASTER_RESPONSE = "SINGLE_FASTER_RESPONSE"
    REQUEST_FAILURE = "REQUEST_FAILURE"
    OBSERVER_INCOMPLETE = "OBSERVER_INCOMPLETE"


class CollisionBudget(CollisionModel):
    max_requests: int = Field(ge=4, le=256)
    repetitions: int = Field(ge=2, le=32)
    request_timeout_ms: int = Field(ge=1, le=30_000)
    experiment_timeout_ms: int = Field(ge=1, le=300_000)
    synchronization_timeout_ms: int = Field(ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_time_budget(self) -> CollisionBudget:
        if self.synchronization_timeout_ms > self.request_timeout_ms:
            raise ValueError("synchronization timeout cannot exceed request timeout")
        if self.request_timeout_ms > self.experiment_timeout_ms:
            raise ValueError("request timeout cannot exceed experiment timeout")
        return self


class CollisionObservation(CollisionModel):
    anomalies: tuple[CollisionAnomaly, ...] = Field(default=(), max_length=5)
    clues: tuple[CollisionClue, ...] = Field(default=(), max_length=6)
    invariants_complete: bool
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_unique_facts(self) -> CollisionObservation:
        if len(set(self.anomalies)) != len(self.anomalies):
            raise ValueError("collision anomalies must be unique within a repetition")
        if len(set(self.clues)) != len(self.clues):
            raise ValueError("collision clues must be unique within a repetition")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("collision reason codes must be unique")
        return self


class CollisionTrial(CollisionModel):
    repetition: int = Field(ge=1, le=32)
    baseline_fingerprint: str = Field(min_length=1, max_length=256)
    request_count: int = Field(ge=2, le=64)
    responses_complete: bool
    observation: CollisionObservation


class CollisionExperimentResult(CollisionModel):
    verdict: RunVerdict
    sequential_semantics_valid: bool
    baseline_consistent: bool
    repeatable_anomalies: tuple[CollisionAnomaly, ...] = Field(default=(), max_length=5)
    trials: tuple[CollisionTrial, ...] = Field(default=(), max_length=32)
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)


def classify_collision_trials(
    *,
    sequential_semantics_valid: bool,
    expected_repetitions: int,
    trials: tuple[CollisionTrial, ...],
) -> CollisionExperimentResult:
    """只有相同基线下跨轮复现的真实业务异常能够形成 BLOCK。"""

    baseline_consistent = bool(trials) and len({trial.baseline_fingerprint for trial in trials}) == 1
    counts = Counter(
        anomaly
        for trial in trials
        if trial.responses_complete and trial.observation.invariants_complete
        for anomaly in trial.observation.anomalies
    )
    repeatable = tuple(sorted((item for item, count in counts.items() if count >= 2), key=str))
    complete = (
        len(trials) == expected_repetitions
        and all(trial.responses_complete and trial.observation.invariants_complete for trial in trials)
    )
    clues = {clue for trial in trials for clue in trial.observation.clues}
    if sequential_semantics_valid and baseline_consistent and repeatable:
        verdict = RunVerdict.BLOCK
        reasons = ("COLLISION_ANOMALY_REPEATED",)
    elif sequential_semantics_valid and baseline_consistent and complete and not counts and not clues:
        verdict = RunVerdict.PASS
        reasons = ("COLLISION_INVARIANTS_PRESERVED",)
    else:
        verdict = RunVerdict.INCONCLUSIVE
        reasons = tuple(
            code
            for condition, code in (
                (not sequential_semantics_valid, "COLLISION_SEQUENTIAL_SEMANTICS_INVALID"),
                (not baseline_consistent, "COLLISION_BASELINE_MISMATCH"),
                (not complete, "COLLISION_EXPERIMENT_INCOMPLETE"),
                (bool(counts) and not repeatable, "COLLISION_ANOMALY_NOT_REPEATED"),
                (bool(clues), "COLLISION_CLUE_ONLY"),
            )
            if condition
        ) or ("COLLISION_EVIDENCE_INSUFFICIENT",)
    return CollisionExperimentResult(
        verdict=verdict,
        sequential_semantics_valid=sequential_semantics_valid,
        baseline_consistent=baseline_consistent,
        repeatable_anomalies=repeatable,
        trials=trials,
        reason_codes=reasons,
    )
