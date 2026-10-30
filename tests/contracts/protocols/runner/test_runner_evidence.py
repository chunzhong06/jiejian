# 验证 Runner Evidence 语义载荷、观察完整性与秘密边界。

from __future__ import annotations
import pytest
from product.backend.domain.lifecycle import CaseVerdict
from product.backend.domain.verification.facts import ExecutionOutcome, ObservedEffect
from product.protocols.runner.evidence import build_evidence
from tests.support.builders.runtime.runner import evidence
pytestmark = pytest.mark.level2

def test_current_evidence_carries_execution_and_observation_facts() -> None:
    current_evidence = evidence()
    assert current_evidence.execution_fact.outcome is ExecutionOutcome.ACCEPTED
    assert current_evidence.observation_facts[0].effect is ObservedEffect.CONFIRMED

def test_incomplete_observation_requires_inconclusive_verdict() -> None:
    current_evidence = evidence(available=False, verdict=CaseVerdict.INCONCLUSIVE)
    assert current_evidence.verdict is CaseVerdict.INCONCLUSIVE

def test_evidence_rejects_missing_observation_fact_coverage() -> None:
    raw = evidence().model_dump(mode="python")
    raw.pop("evidence_id")
    raw.pop("evidence_hash")
    raw["observation_facts"] = ()
    with pytest.raises(ValueError, match="exactly cover"):
        build_evidence(**raw)


def test_evidence_builder_hashes_normalized_fact_and_reason_order() -> None:
    raw = evidence(resource_ids=("resource-a", "resource-z")).model_dump(mode="python")
    raw.pop("evidence_id")
    raw.pop("evidence_hash")
    raw["observation_facts"] = tuple(reversed(raw["observation_facts"]))
    raw["reason_codes"] = ("Z_REASON", "A_REASON")

    rebuilt = build_evidence(**raw)

    assert [item.resource_id for item in rebuilt.observation_facts] == [
        "resource-a",
        "resource-z",
    ]
    assert rebuilt.reason_codes == ("A_REASON", "Z_REASON")
