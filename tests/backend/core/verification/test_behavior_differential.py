# 验证验证领域中的行为差分。

from __future__ import annotations

import pytest

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.behavior_differential import (
    BehaviorDifferenceKind,
    BehaviorSnapshot,
    compare_behavior_snapshots,
    normalize_evidence_behavior,
)
from product.backend.core.verification.permissions import permission_model_sha256
from tests.fixtures.runner import evidence


def _snapshot() -> BehaviorSnapshot:
    return normalize_evidence_behavior(
        evidence(),
        contract_fingerprint="a" * 64,
        workflow_fingerprint="b" * 64,
        baseline_fingerprint="c" * 64,
    )


def _changed(snapshot: BehaviorSnapshot, **updates) -> BehaviorSnapshot:
    payload = snapshot.model_dump(mode="python", exclude={"behavior_fingerprint"})
    payload.update(updates)
    return BehaviorSnapshot(
        **payload,
        behavior_fingerprint=permission_model_sha256(payload),
    )


def test_behavior_normalization_filters_order_hashes_and_non_security_observation_fields() -> None:
    original = evidence()
    changed_transport = original.model_copy(
        update={
            "execution_fact": original.execution_fact.model_copy(
                update={"input_hash": "d" * 64, "output_hash": "e" * 64}
            ),
            "observations": tuple(reversed(original.observations)),
        }
    )
    fields = {
        "contract_fingerprint": "a" * 64,
        "workflow_fingerprint": "b" * 64,
        "baseline_fingerprint": "c" * 64,
    }
    assert normalize_evidence_behavior(original, **fields) == normalize_evidence_behavior(
        changed_transport, **fields
    )


def test_behavior_differential_reports_only_changed_security_dimensions() -> None:
    before = _snapshot()
    after = _changed(before, verdict=CaseVerdict.INCONCLUSIVE)
    result = compare_behavior_snapshots(before, after)
    assert result.changed is True
    assert tuple(item.kind for item in result.differences) == (
        BehaviorDifferenceKind.VERDICT,
    )


def test_behavior_differential_rejects_changed_frozen_invariant() -> None:
    before = _snapshot()
    after = _changed(before, baseline_fingerprint="f" * 64)
    with pytest.raises(ValueError, match="frozen comparison invariants"):
        compare_behavior_snapshots(before, after)
