from __future__ import annotations

import pytest

from jiejian.contracts.analysis.drift import (
    DriftEntry,
    DriftReport,
    DriftType,
    VerifiedBehaviorFingerprint,
    build_drift_report,
)
from jiejian.contracts.analysis.models import AnalysisReasonCode
from jiejian.contracts.analysis.sources.requirement import parse_requirement
from jiejian.contracts.models import (
    ContractAuditAction,
    ContractAuditEntry,
    ContractProvenance,
    ContractSourceType,
    ContractVersion,
    Requirement,
    SourceReference,
)
from jiejian.domain.lifecycle import ContractStatus
from jiejian.verification.models import ContractRule, RuleKind, SecurityContract
from jiejian.errors import ErrorCode, JiejianError


def _source(locator: str) -> SourceReference:
    return SourceReference(
        source_type=ContractSourceType.REQUIREMENT_TEXT,
        locator=locator,
        content_sha256="a" * 64,
    )


def _contract() -> ContractVersion:
    rules = (
        ContractRule(id="foreign-read", kind=RuleKind.FOREIGN_READ, required_observers=("http",)),
        ContractRule(
            id="side-effect",
            kind=RuleKind.UNAUTHORIZED_SIDE_EFFECT,
            required_observers=("http", "owner_api"),
            severity="critical",
        ),
    )
    return ContractVersion(
        project_id="drift-project",
        contract_id="drift-contract",
        version=1,
        status=ContractStatus.DRAFT,
        snapshot=SecurityContract(
            id="drift-contract",
            version=1,
            status=ContractStatus.DRAFT,
            rules=rules,
        ),
        provenance=ContractProvenance(sources=(_source("contract.md"),)),
        audit=(ContractAuditEntry(action=ContractAuditAction.CREATED, actor="analyst", occurred_at_us=1),),
        created_at_us=1,
        updated_at_us=1,
    )


def test_all_six_drift_types_are_representable_without_verdict_changes() -> None:
    contract = _contract()
    requirement = Requirement(
        requirement_id="req_" + "1" * 32,
        project_id="drift-project",
        source=_source("new-requirement.md"),
        text="rule id=privileged-field kind=privileged_field observers=http,owner_api severity=critical",
        created_by="analyst",
        created_at_us=1,
    )
    explicit = parse_requirement(requirement).candidates[0]
    llm = explicit.model_copy(
        update={
            "candidate_id": "cand_" + "2" * 32,
            "source": SourceReference(
                source_type=ContractSourceType.LLM,
                locator="offline-llm-candidate",
                content_sha256="b" * 64,
            ),
            "rule": ContractRule(
                id="privileged-field-llm",
                kind=RuleKind.FOREIGN_READ,
                required_observers=("http",),
                severity="high",
            ),
        }
    )
    capability_changed = explicit.model_copy(
        update={
            "candidate_id": "cand_" + "3" * 32,
            "rule": ContractRule(
                id="foreign-read",
                kind=RuleKind.UNAUTHORIZED_SIDE_EFFECT,
                required_observers=("http", "owner_api"),
                severity="critical",
            ),
        }
    )
    accepted = VerifiedBehaviorFingerprint(
        run_id="run_" + "1" * 32,
        project_id="drift-project",
        contract_id="drift-contract",
        contract_version=1,
        fingerprint_sha256="c" * 64,
        summary_sha256="d" * 64,
    )
    current = accepted.model_copy(
        update={
            "run_id": "run_" + "2" * 32,
            "fingerprint_sha256": "e" * 64,
        }
    )
    report = build_drift_report(
        contract,
        requirements=(requirement,),
        requirement_candidates=(explicit,),
        available_rule_ids=("foreign-read",),
        capability_candidates=(capability_changed,),
        unexecutable_rule_ids=("side-effect",),
        available_observers=("http",),
        accepted_behavior=accepted,
        current_behavior=current,
        llm_candidates=(llm,),
    )
    types = {entry.drift_type.value for entry in report.entries}
    assert types == {
        "REQUIREMENT_UNCOVERED",
        "CONTRACT_RULE_DISAPPEARED",
        "ROUTE_CHANGED",
        "OBSERVER_UNAVAILABLE",
        "BEHAVIOR_CHANGED",
        "LLM_REQUIREMENT_CONFLICT",
    }
    assert report == build_drift_report(
        contract,
        requirements=(requirement,),
        requirement_candidates=(explicit,),
        available_rule_ids=("foreign-read",),
        capability_candidates=(capability_changed,),
        unexecutable_rule_ids=("side-effect",),
        available_observers=("http",),
        accepted_behavior=accepted,
        current_behavior=current,
        llm_candidates=(llm,),
    )


def test_behavior_drift_requires_both_verified_inputs() -> None:
    with pytest.raises(JiejianError) as captured:
        build_drift_report(_contract(), accepted_behavior=VerifiedBehaviorFingerprint(
            run_id="run_" + "1" * 32,
            project_id="drift-project",
            contract_id="drift-contract",
            contract_version=1,
            fingerprint_sha256="a" * 64,
            summary_sha256="b" * 64,
        ))
    assert captured.value.code == ErrorCode.CONTRACT_ANALYSIS_INVALID.value


@pytest.mark.parametrize(
    "field,value",
    [
        ("project_id", "other-project"),
        ("contract_id", "other-contract"),
    ],
)
def test_behavior_drift_rejects_cross_context_fingerprints(field: str, value: str) -> None:
    accepted = VerifiedBehaviorFingerprint(
        run_id="run_" + "1" * 32,
        project_id="drift-project",
        contract_id="drift-contract",
        contract_version=1,
        fingerprint_sha256="a" * 64,
        summary_sha256="b" * 64,
    ).model_copy(update={field: value})
    current = accepted.model_copy(update={field: "drift-project" if field == "project_id" else "drift-contract", "run_id": "run_" + "2" * 32})
    with pytest.raises(JiejianError) as captured:
        build_drift_report(_contract(), accepted_behavior=accepted, current_behavior=current)
    assert captured.value.code == ErrorCode.CONTRACT_ANALYSIS_INVALID.value


def test_behavior_drift_rejects_current_version_mismatch() -> None:
    accepted = VerifiedBehaviorFingerprint(
        run_id="run_" + "1" * 32,
        project_id="drift-project",
        contract_id="drift-contract",
        contract_version=1,
        fingerprint_sha256="a" * 64,
        summary_sha256="b" * 64,
    )
    current = accepted.model_copy(update={"run_id": "run_" + "2" * 32, "contract_version": 2})
    with pytest.raises(JiejianError) as captured:
        build_drift_report(_contract(), accepted_behavior=accepted, current_behavior=current)
    assert captured.value.code == ErrorCode.CONTRACT_ANALYSIS_INVALID.value


def test_explicit_empty_capability_set_reports_all_rules_disappeared() -> None:
    report = build_drift_report(_contract(), available_rule_ids=())
    disappeared = {
        entry.subject_id
        for entry in report.entries
        if entry.drift_type.value == "CONTRACT_RULE_DISAPPEARED"
    }
    assert disappeared == {"foreign-read", "side-effect"}


@pytest.mark.parametrize("input_kind", ("requirement", "requirement_candidate", "capability_candidate", "llm_candidate"))
def test_drift_rejects_cross_project_inputs(input_kind: str) -> None:
    requirement = Requirement(
        requirement_id="req_" + "9" * 32,
        project_id="other-project",
        source=_source("other.md"),
        text="rule id=foreign-read kind=foreign_read observers=http severity=high",
        created_by="analyst",
        created_at_us=1,
    )
    candidate = parse_requirement(requirement).candidates[0]
    kwargs = {
        "requirements": (requirement,),
    } if input_kind == "requirement" else {
        "requirement_candidates": (candidate,),
    } if input_kind == "requirement_candidate" else {
        "capability_candidates": (candidate,),
    } if input_kind == "capability_candidate" else {
        "llm_candidates": (candidate,),
    }
    with pytest.raises(JiejianError) as captured:
        build_drift_report(_contract(), **kwargs)
    assert captured.value.code == ErrorCode.CONTRACT_ANALYSIS_INVALID.value
