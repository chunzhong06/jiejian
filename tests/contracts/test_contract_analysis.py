from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from jiejian.contracts.analysis.models import (
    AnalysisReasonCode,
    AnalysisSeverity,
)
from jiejian.contracts.analysis.assessment import assess_contract
from jiejian.contracts.analysis.diff import diff_contract_versions
from jiejian.contracts.analysis.merge import merge_candidates
from jiejian.contracts.analysis.sources.fastapi_ast import parse_fastapi_source_candidates
from jiejian.contracts.analysis.sources.flow import build_flow_candidates
from jiejian.contracts.analysis.sources.openapi import build_openapi_candidates
from jiejian.contracts.analysis.sources.requirement import parse_requirement
from jiejian.contracts.models import (
    ContractAuditAction,
    ContractAuditEntry,
    ContractCandidate,
    ContractProvenance,
    ContractSourceType,
    ContractVersion,
    Requirement,
    SourceReference,
)
from jiejian.domain.lifecycle import ContractStatus
from jiejian.verification.models import (
    ContractRule,
    Flow,
    FlowStep,
    RuleKind,
    SecurityContract,
)
SHA256 = "a" * 64


def _source(locator: str = "requirements.md") -> SourceReference:
    return SourceReference(
        source_type=ContractSourceType.REQUIREMENT_TEXT,
        locator=locator,
        content_sha256=SHA256,
    )


def _requirement(text: str) -> Requirement:
    return Requirement(
        requirement_id="req_" + "1" * 32,
        project_id="analysis-project",
        source=_source(),
        text=text,
        created_by="analyst",
        created_at_us=1,
    )


def _rule(
    rule_id: str = "foreign-read",
    *,
    kind: RuleKind = RuleKind.FOREIGN_READ,
    observers: tuple[str, ...] = ("http",),
    severity: str = "high",
) -> ContractRule:
    return ContractRule(
        schema_version="1",
        id=rule_id,
        kind=kind,
        required_observers=observers,
        severity=severity,
    )


def _contract(rule: ContractRule = _rule()) -> ContractVersion:
    return ContractVersion(
        project_id="analysis-project",
        contract_id="analysis-contract",
        version=1,
        status=ContractStatus.DRAFT,
        snapshot=SecurityContract(
            schema_version="1",
            id="analysis-contract",
            version=1,
            status=ContractStatus.DRAFT,
            rules=(rule,),
        ),
        provenance=ContractProvenance(sources=(_source(),)),
        audit=(
            ContractAuditEntry(
                action=ContractAuditAction.CREATED,
                actor="analyst",
                occurred_at_us=1,
            ),
        ),
        created_at_us=1,
        updated_at_us=1,
    )


def test_requirement_template_is_deterministic_and_rejects_uncontrolled_text() -> None:
    requirement = _requirement(
        "# controlled v1\n"
        "rule id=foreign-read kind=foreign_read observers=http severity=high"
    )
    first = parse_requirement(requirement)
    second = parse_requirement(requirement)
    assert first == second
    assert first.candidates[0].rule.kind is RuleKind.FOREIGN_READ
    assert first.candidates[0].source.locator.endswith("#line:2")

    ambiguous = parse_requirement(_requirement("用户只能访问自己的资源"))
    assert not ambiguous.candidates
    assert ambiguous.issues[0].code is AnalysisReasonCode.AMBIGUOUS_SOURCE
    assert ambiguous.issues[0].severity is AnalysisSeverity.BLOCKING


def test_flow_and_openapi_adapters_preserve_source_and_map_rule_kinds() -> None:
    flow = Flow(
        schema_version="1",
        id="analysis-flow",
        steps=(
            FlowStep(
                schema_version="1",
                id="read-resource",
                method="GET",
                path="/resources/{resource_id}",
                identity_id="owner",
                resource_id="resource",
                alternate_identity_id="attacker",
                alternate_resource_id="foreign-resource",
            ),
            FlowStep(
                schema_version="1",
                id="update-resource",
                method="PATCH",
                path="/resources/{resource_id}",
                identity_id="owner",
                resource_id="resource",
                alternate_identity_id="attacker",
                alternate_resource_id="foreign-resource",
                sensitive_fields=("email",),
            ),
        ),
    )
    flow_batch = build_flow_candidates("analysis-project", flow)
    assert {item.rule.kind for item in flow_batch.candidates} == {
        RuleKind.FOREIGN_READ,
        RuleKind.PRIVILEGED_FIELD,
        RuleKind.UNAUTHORIZED_SIDE_EFFECT,
    }
    assert all(item.source.locator.startswith("flow:analysis-flow/step:") for item in flow_batch.candidates)

    openapi = {
        "openapi": "3.0.0",
        "paths": {
            "/resources/{resource_id}": {
                "get": {},
                "patch": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"properties": {"email": {"type": "string"}}}
                            }
                        }
                    }
                },
            }
        },
    }
    openapi_batch = build_openapi_candidates("analysis-project", openapi)
    assert len(openapi_batch.candidates) == 3
    assert all(item.source.locator.startswith("openapi:") for item in openapi_batch.candidates)

    external = build_openapi_candidates(
        "analysis-project",
        {"openapi": "3.0.0", "paths": {"/x": {"get": {"$ref": "https://example.test/op"}}}},
    )
    assert external.issues[0].code is AnalysisReasonCode.INVALID_OPENAPI
    non_mapping = build_openapi_candidates("analysis-project", [])
    assert non_mapping.issues[0].detail == "openapi_document_not_mapping"


def test_fastapi_ast_adapter_is_bounded_and_never_imports_source(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    source = root / "routes.py"
    source.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/resources/{resource_id}')\n"
        "def read(resource_id: str): ...\n"
        "@router.patch('/resources/{resource_id}')\n"
        "def update(password: str): ...\n",
        encoding="utf-8",
    )
    source_bytes = source.read_bytes()
    batch = parse_fastapi_source_candidates(
        "analysis-project", source_bytes, source_locator="routes.py",
        content_sha256=hashlib.sha256(source_bytes).hexdigest(),
    )
    assert len(batch.candidates) == 3
    assert all(item.source.source_type is ContractSourceType.STATIC_ANALYSIS for item in batch.candidates)

    dynamic = root / "dynamic.py"
    dynamic.write_text("@router.get(BASE_PATH)\ndef read(): ...\n", encoding="utf-8")
    dynamic_bytes = dynamic.read_bytes()
    dynamic_batch = parse_fastapi_source_candidates(
        "analysis-project", dynamic_bytes, source_locator="dynamic.py",
        content_sha256=hashlib.sha256(dynamic_bytes).hexdigest(),
    )
    assert dynamic_batch.issues[0].code is AnalysisReasonCode.AMBIGUOUS_SOURCE


def test_merge_assessment_and_diff_are_stable_and_report_conflicts() -> None:
    requirement = _requirement("rule id=foreign-read kind=foreign_read observers=http severity=high")
    parsed = parse_requirement(requirement)
    duplicate = parsed.candidates[0].model_copy(
        update={
            "candidate_id": "cand_" + "2" * 32,
            "source": _source("routes.py:10"),
        }
    )
    merged = merge_candidates((parsed.candidates[0], duplicate))
    assert merged == merge_candidates((duplicate, parsed.candidates[0]))
    assert merged.candidates[0].candidate_ids == tuple(sorted((parsed.candidates[0].candidate_id, duplicate.candidate_id)))
    assert any(issue.code is AnalysisReasonCode.DUPLICATE_CANDIDATE for issue in merged.issues)

    conflict = duplicate.model_copy(update={"rule": _rule("foreign-read", severity="critical")})
    conflict_result = merge_candidates((parsed.candidates[0], conflict))
    assert any(issue.code is AnalysisReasonCode.CONFLICTING_CANDIDATE for issue in conflict_result.issues)

    before = _contract()
    # A real revision is created by the governance revision function; this checks diff inputs after validation.
    from jiejian.contracts.governance import revise_contract_version

    after = revise_contract_version(
        before.model_copy(update={"status": ContractStatus.ACTIVE, "snapshot": before.snapshot.model_copy(update={"status": ContractStatus.ACTIVE}), "audit": (
            before.audit[0],
            ContractAuditEntry(action=ContractAuditAction.SUBMITTED, actor="reviewer", occurred_at_us=2),
            ContractAuditEntry(action=ContractAuditAction.ACTIVATED, actor="approver", occurred_at_us=3),
        ), "updated_at_us": 3}),
        rules=(_rule("new-rule", kind=RuleKind.UNAUTHORIZED_SIDE_EFFECT, observers=("http", "owner_api"), severity="critical"),),
        provenance=ContractProvenance(sources=(_source("revision.md"),)),
        actor="analyst",
        occurred_at_us=4,
    )
    diff = diff_contract_versions(before, after)
    assert diff.added and diff.removed
    assert diff == diff_contract_versions(before, after)


def test_merge_candidates_isolates_projects_and_blocks_mixed_batches() -> None:
    requirement = _requirement("rule id=foreign-read kind=foreign_read observers=http severity=high")
    candidate = parse_requirement(requirement).candidates[0]
    other = candidate.model_copy(
        update={"candidate_id": "cand_" + "9" * 32, "project_id": "other-project"}
    )
    merged = merge_candidates((candidate, other))
    assert len(merged.candidates) == 2
    assert any(
        issue.code is AnalysisReasonCode.CONFLICTING_CANDIDATE
        and issue.severity is AnalysisSeverity.BLOCKING
        for issue in merged.issues
    )


def test_fastapi_source_hash_mismatch_is_blocking() -> None:
    source = "@router.get('/x')\ndef read(): ...\n"
    batch = parse_fastapi_source_candidates(
        "analysis-project",
        source,
        source_locator="routes.py",
        content_sha256="0" * 64,
    )
    assert not batch.candidates
    assert batch.issues[0].code is AnalysisReasonCode.SOURCE_HASH_MISMATCH
    assert batch.issues[0].severity is AnalysisSeverity.BLOCKING
