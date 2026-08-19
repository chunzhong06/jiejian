from __future__ import annotations

import pytest

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect, TargetType
from product.protocols import (
    build_evidence,
    canonical_runner_json_bytes,
    canonical_runner_sha256,
    parse_runner_input,
)
from tests.fixtures.runner import evidence, runner_input


pytestmark = pytest.mark.essential


def test_current_runner_input_round_trips_with_web_target_and_execution_binding() -> None:
    document = runner_input()
    raw = canonical_runner_json_bytes(document)
    assert parse_runner_input(raw) == document
    assert document.project_snapshot.target_type is TargetType.WEB
    assert canonical_runner_sha256(document) == canonical_runner_sha256(parse_runner_input(raw))


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
