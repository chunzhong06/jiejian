from __future__ import annotations

import hashlib
from pathlib import Path

from product.backend.core.contracts.analysis.assessment import assess_contract
from product.backend.core.contracts.analysis.diff import diff_contract_versions
from product.backend.core.contracts.analysis.merge import merge_candidates
from product.backend.core.contracts.analysis.models import AnalysisReasonCode, AnalysisSeverity
from product.backend.core.contracts.analysis.sources.fastapi_ast import parse_fastapi_source_candidates
from product.backend.workflows.contracts.flow_candidates import build_flow_candidates
from product.backend.core.contracts.analysis.sources.openapi import build_openapi_candidates
from product.backend.core.contracts.analysis.sources.requirement import parse_requirement
from product.backend.core.contracts.models import CandidateRiskKind, CandidateSuggestion, ContractAuditAction, ContractAuditEntry, ContractProvenance, ContractSourceType, ContractVersion, Requirement, SourceReference
from product.backend.core.lifecycle import ContractStatus
from product.protocols.recording_flow import Flow, FlowStep
from product.protocols.web.workflow import HttpOutcomeClassifier, HttpRequestTemplate, ValueSlot, ValueSlotConsumer, ValueSlotSource
from product.backend.core.verification.permissions import ActionDefinition, CoverageDimension, PermissionContract, PermissionContext, PermissionExpectation, PermissionRule, RelationEndpoint, RelationFact, RelationType, ResourceDefinition, SecurityEffectDefinition, SecurityEffectKind, SubjectDefinition

SHA256 = "a" * 64


def _source(locator: str = "requirements.md") -> SourceReference:
    return SourceReference(source_type=ContractSourceType.REQUIREMENT_TEXT, locator=locator, content_sha256=SHA256)


def _requirement(text: str) -> Requirement:
    return Requirement(requirement_id="req_" + "1" * 32, project_id="analysis-project", source=_source(), text=text, created_by="analyst", created_at_us=1)


def _suggestion(suggestion_id: str = "foreign-read", kind: CandidateRiskKind = CandidateRiskKind.FOREIGN_READ, severity: str = "high") -> CandidateSuggestion:
    return CandidateSuggestion(id=suggestion_id, kind=kind, required_observations=("resource_state",), severity=severity)


def _permission_rule(rule_id: str = "foreign-read") -> PermissionRule:
    return PermissionRule(rule_id=rule_id, subject_id="member", action_id="view", resource_id="document", relation_path=("owns-document",), context=PermissionContext(resource_ids=("document",)), expectation=PermissionExpectation.DENY, required_observations=("resource_state",), coverage_dimensions=(CoverageDimension.RELATION,))


def _permission_contract(version: int = 1, rule_id: str = "foreign-read") -> PermissionContract:
    return PermissionContract(contract_id="analysis-contract", version=version, role_ids=("member",), workflow_states=("DRAFT",), subjects=(SubjectDefinition(subject_id="member", roles=("member",), tenant_id="tenant"),), effects=(SecurityEffectDefinition(effect_id="document-read", kind=SecurityEffectKind.DATA_DISCLOSURE, resource_type="document", protected_fields=("content",)),), actions=(ActionDefinition(action_id="view", effect_ids=("document-read",)),), resources=(ResourceDefinition(resource_id="document", resource_type="document", owner_subject_id="member", tenant_id="tenant", workflow_state="DRAFT"),), relations=(RelationFact(relation_id="owns-document", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document")),), rules=(_permission_rule(rule_id),))


def _version(version: int = 1, *, rule_id: str = "foreign-read") -> ContractVersion:
    return ContractVersion(project_id="analysis-project", contract_id="analysis-contract", version=version, status=ContractStatus.DRAFT, snapshot=_permission_contract(version, rule_id), provenance=ContractProvenance(sources=(_source(),)), supersedes_version=None if version == 1 else version - 1, audit=(ContractAuditEntry(action=ContractAuditAction.CREATED, actor="analyst", occurred_at_us=1),), created_at_us=1, updated_at_us=1)


def test_requirement_template_is_deterministic_and_candidate_is_non_authoritative() -> None:
    requirement = _requirement("# controlled\nsuggestion id=foreign-read kind=FOREIGN_READ observations=resource_state severity=high")
    first = parse_requirement(requirement)
    assert first == parse_requirement(requirement)
    assert first.candidates[0].suggestion.kind is CandidateRiskKind.FOREIGN_READ
    assert first.candidates[0].source.locator.endswith("#line:2")
    assert not assess_contract(_version(), candidates=first.candidates).blocking_issues
    ambiguous = parse_requirement(_requirement("用户只能访问自己的资源"))
    assert not ambiguous.candidates
    assert ambiguous.issues[0].code is AnalysisReasonCode.AMBIGUOUS_SOURCE
    assert ambiguous.issues[0].severity is AnalysisSeverity.BLOCKING


def test_flow_and_openapi_adapters_produce_suggestions() -> None:
    resource_slot = ValueSlot(slot_id="resource_id", source=ValueSlotSource.CASE_RESOURCE_ID, consumer=ValueSlotConsumer.PATH)
    flow = Flow(id="analysis-flow", steps=(FlowStep(id="read-resource", request_template=HttpRequestTemplate(method="GET", path="/resources/{resource_id}", input_slots=(resource_slot,)), classifier=HttpOutcomeClassifier(), identity_id="owner", resource_id="resource", alternate_identity_id="attacker", alternate_resource_id="foreign-resource"), FlowStep(id="update-resource", request_template=HttpRequestTemplate(method="PATCH", path="/resources/{resource_id}", input_slots=(resource_slot,)), classifier=HttpOutcomeClassifier(), identity_id="owner", resource_id="resource", alternate_identity_id="attacker", alternate_resource_id="foreign-resource", sensitive_fields=("email",))))
    flow_batch = build_flow_candidates("analysis-project", flow)
    assert {item.suggestion.kind for item in flow_batch.candidates} == {CandidateRiskKind.FOREIGN_READ, CandidateRiskKind.PRIVILEGED_FIELD, CandidateRiskKind.UNAUTHORIZED_SIDE_EFFECT}
    assert all(item.source.locator.startswith("flow:analysis-flow/step:") for item in flow_batch.candidates)
    openapi = {"openapi": "3.0.0", "paths": {"/resources/{resource_id}": {"get": {}, "patch": {"requestBody": {"content": {"application/json": {"schema": {"properties": {"email": {"type": "string"}}}}}}}}}}
    openapi_batch = build_openapi_candidates("analysis-project", openapi)
    assert len(openapi_batch.candidates) == 3
    assert all(item.source.locator.startswith("openapi:") for item in openapi_batch.candidates)
    external = build_openapi_candidates("analysis-project", {"openapi": "3.0.0", "paths": {"/x": {"get": {"$ref": "https://example.test/op"}}}})
    assert external.issues[0].code is AnalysisReasonCode.INVALID_OPENAPI


def test_fastapi_ast_adapter_is_bounded_and_never_imports_source(tmp_path: Path) -> None:
    source = tmp_path / "routes.py"
    source.write_text("from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/resources/{resource_id}')\ndef read(resource_id: str): ...\n", encoding="utf-8")
    source_bytes = source.read_bytes()
    batch = parse_fastapi_source_candidates("analysis-project", source_bytes, source_locator="routes.py", content_sha256=hashlib.sha256(source_bytes).hexdigest())
    assert batch.candidates
    assert all(item.source.source_type is ContractSourceType.STATIC_ANALYSIS for item in batch.candidates)


def test_merge_diff_and_assessment_are_stable() -> None:
    requirement = _requirement("suggestion id=foreign-read kind=FOREIGN_READ observations=resource_state severity=high")
    candidate = parse_requirement(requirement).candidates[0]
    duplicate = candidate.model_copy(update={"candidate_id": "cand_" + "2" * 32, "source": _source("routes.py:10")})
    merged = merge_candidates((candidate, duplicate))
    assert merged == merge_candidates((duplicate, candidate))
    assert any(issue.code is AnalysisReasonCode.DUPLICATE_CANDIDATE for issue in merged.issues)
    before = _version()
    after = _version(2, rule_id="new-rule")
    diff = diff_contract_versions(before, after)
    assert diff.added and diff.removed
    assert diff == diff_contract_versions(before, after)


def test_fastapi_source_hash_mismatch_is_blocking() -> None:
    source = "@router.get('/x')\ndef read(): ...\n"
    batch = parse_fastapi_source_candidates("analysis-project", source, source_locator="routes.py", content_sha256="0" * 64)
    assert not batch.candidates
    assert batch.issues[0].code is AnalysisReasonCode.SOURCE_HASH_MISMATCH
    assert batch.issues[0].severity is AnalysisSeverity.BLOCKING
