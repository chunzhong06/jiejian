from __future__ import annotations

import pytest

from product.backend.core.contracts.analysis.drift import DriftType, VerifiedBehaviorFingerprint, build_drift_report
from product.backend.core.contracts.analysis.models import AnalysisReasonCode
from product.backend.core.contracts.analysis.sources.requirement import parse_requirement
from product.backend.core.contracts.models import ContractAuditAction, ContractAuditEntry, ContractProvenance, ContractSourceType, ContractVersion, Requirement, SourceReference
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.verification.permissions import ActionDefinition, CoverageDimension, PermissionContract, PermissionContext, PermissionExpectation, PermissionRule, RelationEndpoint, RelationFact, RelationType, ResourceDefinition, SecurityEffectDefinition, SecurityEffectKind, SubjectDefinition


def _source(locator: str) -> SourceReference:
    return SourceReference(source_type=ContractSourceType.REQUIREMENT_TEXT, locator=locator, content_sha256="a" * 64)


def _contract() -> ContractVersion:
    permission = PermissionContract(
        contract_id="drift-contract",
        version=1,
        role_ids=("member",),
        workflow_states=("DRAFT",),
        subjects=(SubjectDefinition(subject_id="member", roles=("member",), tenant_id="tenant"),),
        effects=(SecurityEffectDefinition(effect_id="document-read", kind=SecurityEffectKind.DATA_DISCLOSURE, resource_type="document", protected_fields=("content",)),),
        actions=(ActionDefinition(action_id="view", effect_ids=("document-read",)),),
        resources=(ResourceDefinition(resource_id="document", resource_type="document", owner_subject_id="member", tenant_id="tenant", workflow_state="DRAFT"),),
        relations=(RelationFact(relation_id="owns-document", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document")),),
        rules=(PermissionRule(rule_id="foreign-read", subject_id="member", action_id="view", resource_id="document", relation_path=("owns-document",), context=PermissionContext(resource_ids=("document",)), expectation=PermissionExpectation.DENY, required_observations=("resource_state",), coverage_dimensions=(CoverageDimension.RELATION,)),),
    )
    return ContractVersion(project_id="drift-project", contract_id="drift-contract", version=1, status=ContractStatus.DRAFT, snapshot=permission, provenance=ContractProvenance(sources=(_source("contract.md"),)), audit=(ContractAuditEntry(action=ContractAuditAction.CREATED, actor="analyst", occurred_at_us=1),), created_at_us=1, updated_at_us=1)


def test_drift_reports_requirement_and_behavior_changes_without_verdict_logic() -> None:
    contract = _contract()
    requirement = Requirement(requirement_id="req_" + "1" * 32, project_id="drift-project", source=_source("new-requirement.md"), text="suggestion id=new-risk kind=UNAUTHORIZED_SIDE_EFFECT observations=resource_state severity=critical", created_by="analyst", created_at_us=1)
    candidate = parse_requirement(requirement).candidates[0]
    accepted = VerifiedBehaviorFingerprint(run_id="run_" + "1" * 32, project_id="drift-project", contract_id="drift-contract", contract_version=1, fingerprint_sha256="c" * 64, summary_sha256="d" * 64)
    current = accepted.model_copy(update={"run_id": "run_" + "2" * 32, "fingerprint_sha256": "e" * 64})
    report = build_drift_report(contract, requirements=(requirement,), requirement_candidates=(candidate,), available_rule_ids=(), available_observations=("resource_state",), accepted_behavior=accepted, current_behavior=current)
    assert {entry.drift_type for entry in report.entries} == {DriftType.REQUIREMENT_UNCOVERED, DriftType.CONTRACT_RULE_DISAPPEARED, DriftType.BEHAVIOR_CHANGED}
    assert report == build_drift_report(contract, requirements=(requirement,), requirement_candidates=(candidate,), available_rule_ids=(), available_observations=("resource_state",), accepted_behavior=accepted, current_behavior=current)
    assert all(entry.reason_code is not AnalysisReasonCode.BEHAVIOR_CHANGED or entry.blocking for entry in report.entries)


def test_behavior_drift_requires_both_verified_inputs() -> None:
    with pytest.raises(JiejianError) as captured:
        build_drift_report(_contract(), accepted_behavior=VerifiedBehaviorFingerprint(run_id="run_" + "1" * 32, project_id="drift-project", contract_id="drift-contract", contract_version=1, fingerprint_sha256="a" * 64, summary_sha256="b" * 64))
    assert captured.value.code == ErrorCode.CONTRACT_ANALYSIS_INVALID.value


def test_behavior_drift_rejects_cross_context_fingerprints() -> None:
    accepted = VerifiedBehaviorFingerprint(run_id="run_" + "1" * 32, project_id="other-project", contract_id="drift-contract", contract_version=1, fingerprint_sha256="a" * 64, summary_sha256="b" * 64)
    current = accepted.model_copy(update={"project_id": "drift-project", "run_id": "run_" + "2" * 32})
    with pytest.raises(JiejianError) as captured:
        build_drift_report(_contract(), accepted_behavior=accepted, current_behavior=current)
    assert captured.value.code == ErrorCode.CONTRACT_ANALYSIS_INVALID.value
