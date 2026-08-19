from __future__ import annotations

from jiejian.domain.lifecycle import CaseVerdict, RunLifecycle, RunVerdict
from jiejian.verification.gating import (
    BaselineFindingRef,
    GateFacts,
    GateFinding,
    GatePolicy,
    RegressionBaseline,
    canonical_sha256,
    evaluate_gate,
)


BASELINE_ID = "baseline_" + "a" * 32
FINDING_ID = "finding_" + "b" * 32
OCCURRENCE_ID = "occ_" + "c" * 32
RUN_ID = "run_" + "d" * 32


def _baseline() -> RegressionBaseline:
    return RegressionBaseline(
        baseline_id=BASELINE_ID,
        project_id="project-gate",
        accepted_run_id="run_" + "e" * 32,
        finding_refs=(
            BaselineFindingRef(
                finding_id=FINDING_ID,
                occurrence_id=OCCURRENCE_ID,
                evidence_ids=("ev_" + "f" * 20,),
            ),
        ),
        coverage_ids=("case:case-a:fingerprint-a", "case:case-b:fingerprint-b"),
        coverage_digest=canonical_sha256(("case:case-a:fingerprint-a", "case:case-b:fingerprint-b")),
        request_snapshot_sha256="1" * 64,
        engine_version="runner-v2",
        protocol_versions=("observer-v2", "runner-result-v2"),
        actor="operator",
        reason="fixed run accepted",
        accepted_at_us=1,
    )


def _facts(**updates) -> GateFacts:
    values = dict(
        run_id=RUN_ID,
        project_id="project-gate",
        lifecycle=RunLifecycle.COMPLETED,
        verdict=RunVerdict.PASS,
        publication_validated=True,
        findings=(),
        coverage_ids=("case:case-a:fingerprint-a", "case:case-b:fingerprint-b"),
        coverage_gap_count=0,
        required_observer_issues=(),
        inconclusive_reasons=(),
        execution_errors=(),
        request_snapshot_sha256="2" * 64,
        engine_version="runner-v2",
        protocol_versions=("observer-v2", "runner-result-v2"),
    )
    values.update(updates)
    return GateFacts(**values)


def test_reappeared_vulnerable_finding_blocks_deterministically() -> None:
    baseline = _baseline()
    facts = _facts(
        verdict=RunVerdict.BLOCK,
        findings=(GateFinding(
            finding_id=FINDING_ID,
            occurrence_id="occ_" + "1" * 32,
            status="REAPPEARED",
            verdict=CaseVerdict.VULNERABLE,
            severity="high",
        ),),
    )
    result = evaluate_gate(baseline, facts, GatePolicy())
    assert result.decision.value == "BLOCK"
    assert {item.code for item in result.reasons} >= {"FINDING_REAPPEARED", "RUN_VERDICT_BLOCK"}
    assert result.input_hash == evaluate_gate(baseline, facts, GatePolicy()).input_hash


def test_required_observer_and_coverage_degradation_block() -> None:
    baseline = _baseline()
    result = evaluate_gate(
        baseline,
        _facts(
            coverage_ids=("case:case-a:fingerprint-a",),
            required_observer_issues=("case-a:owner_api:INCONCLUSIVE",),
        ),
        GatePolicy(),
    )
    assert result.decision.value == "BLOCK"
    assert {item.code for item in result.reasons} >= {"BASELINE_COVERAGE_MISSING", "REQUIRED_OBSERVER_INCOMPLETE"}


def test_publication_error_is_independent_gate_error() -> None:
    result = evaluate_gate(
        _baseline(),
        _facts(publication_validated=False, execution_errors=("ARTIFACT_MANIFEST",)),
        GatePolicy(),
    )
    assert result.decision.value == "ERROR"
    assert {item.code for item in result.reasons} >= {"PUBLICATION_NOT_VALIDATED", "EXECUTION_ERROR"}
