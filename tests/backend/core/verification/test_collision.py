# 验证验证领域中的并发碰撞判定。

from __future__ import annotations

from product.backend.core.lifecycle import RunVerdict
from product.backend.core.verification.collision import (
    CollisionAnomaly,
    CollisionClue,
    CollisionObservation,
    CollisionTrial,
    classify_collision_trials,
)


def _trial(
    repetition: int,
    *,
    baseline: str = "baseline-v1",
    anomalies: tuple[CollisionAnomaly, ...] = (),
    clues: tuple[CollisionClue, ...] = (),
    complete: bool = True,
) -> CollisionTrial:
    return CollisionTrial(
        repetition=repetition,
        baseline_fingerprint=baseline,
        request_count=2,
        responses_complete=complete,
        observation=CollisionObservation(
            anomalies=anomalies,
            clues=clues,
            invariants_complete=complete,
        ),
    )


def test_repeatable_business_anomaly_blocks_even_with_auxiliary_clue() -> None:
    anomaly = (CollisionAnomaly.QUOTA_BYPASS,)
    result = classify_collision_trials(
        sequential_semantics_valid=True,
        expected_repetitions=2,
        trials=(
            _trial(1, anomalies=anomaly, clues=(CollisionClue.LATENCY_VARIATION,)),
            _trial(2, anomalies=anomaly),
        ),
    )

    assert result.verdict is RunVerdict.BLOCK
    assert result.repeatable_anomalies == anomaly
    assert result.reason_codes == ("COLLISION_ANOMALY_REPEATED",)


def test_single_anomaly_or_clue_never_blocks() -> None:
    result = classify_collision_trials(
        sequential_semantics_valid=True,
        expected_repetitions=2,
        trials=(
            _trial(1, anomalies=(CollisionAnomaly.DUPLICATE_EFFECT,)),
            _trial(2, clues=(CollisionClue.TRANSIENT_SERVER_ERROR,)),
        ),
    )

    assert result.verdict is RunVerdict.INCONCLUSIVE
    assert "COLLISION_ANOMALY_NOT_REPEATED" in result.reason_codes
    assert "COLLISION_CLUE_ONLY" in result.reason_codes


def test_incomplete_observer_anomaly_never_blocks() -> None:
    anomaly = (CollisionAnomaly.UNAUTHORIZED_EFFECT,)
    incomplete = CollisionTrial(
        repetition=2,
        baseline_fingerprint="baseline-v1",
        request_count=2,
        responses_complete=True,
        observation=CollisionObservation(
            anomalies=anomaly,
            invariants_complete=False,
        ),
    )
    result = classify_collision_trials(
        sequential_semantics_valid=True,
        expected_repetitions=2,
        trials=(_trial(1, anomalies=anomaly), incomplete),
    )

    assert result.verdict is RunVerdict.INCONCLUSIVE
    assert "COLLISION_EXPERIMENT_INCOMPLETE" in result.reason_codes
    assert "COLLISION_ANOMALY_NOT_REPEATED" in result.reason_codes


def test_clean_complete_repetitions_pass() -> None:
    result = classify_collision_trials(
        sequential_semantics_valid=True,
        expected_repetitions=2,
        trials=(_trial(1), _trial(2)),
    )

    assert result.verdict is RunVerdict.PASS
    assert result.reason_codes == ("COLLISION_INVARIANTS_PRESERVED",)


def test_baseline_mismatch_is_inconclusive() -> None:
    anomaly = (CollisionAnomaly.INVALID_STATE,)
    result = classify_collision_trials(
        sequential_semantics_valid=True,
        expected_repetitions=2,
        trials=(
            _trial(1, baseline="baseline-a", anomalies=anomaly),
            _trial(2, baseline="baseline-b", anomalies=anomaly),
        ),
    )

    assert result.verdict is RunVerdict.INCONCLUSIVE
    assert result.baseline_consistent is False
    assert "COLLISION_BASELINE_MISMATCH" in result.reason_codes
