# 验证 Runner Evidence 语义载荷、观察完整性与秘密边界。

from __future__ import annotations
import json
from pathlib import Path
import pytest
from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.backend.core.errors import JiejianError
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect, TargetType
from product.protocols import (
    CleanupResult,
    CleanupIssue,
    CleanupIssueCode,
    CleanupStatus,
    Evidence,
    PreparedCookieCredential,
    PreparedCookieSessionIdentityBinding,
    RunnerInput,
    RunnerFailurePhase,
    RunnerResult,
    RunnerResultType,
    WebExecutionIdentity,
    build_evidence,
    canonical_runner_json_bytes,
    canonical_runner_sha256,
    parse_runner_result,
    parse_runner_input,
)
from product.protocols.runner.result import _reject_secret_material
from tests.fixtures.runner import evidence, runner_input
pytestmark = pytest.mark.essential

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
