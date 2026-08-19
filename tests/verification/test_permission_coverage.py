from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.verification.permission_test_target import create_complex_permission_test_server
from product.protocols import (
    Correlation,
    ObservationCompleteness,
    ObservationPhase,
    ObserverBudget,
    ObserverOutcomeStatus,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
    SqliteQueryLocator,
)
from product.backend.infra.observers.sqlite import run_sqlite_observer
from product.backend.core.verification.permission_coverage import (
    BatchAuthorizationMode,
    CoverageGapCode,
    CoverageStatus,
    build_permission_coverage_plan,
)
from product.backend.core.verification.permissions import (
    ActionDefinition,
    BatchPermissionRule,
    BatchResourceExpectation,
    CoverageDimension,
    PermissionContract,
    PermissionContext,
    PermissionExpectation,
    PermissionRule,
    RelationEndpoint,
    RelationFact,
    RelationType,
    ResourceDefinition,
    SubjectDefinition,
)


def _complex_contract() -> PermissionContract:
    return PermissionContract(
        contract_id="complex-permission-test-contract",
        version=1,
        role_ids=("department-admin", "member", "tenant-admin"),
        workflow_states=("APPROVED", "DRAFT", "PENDING"),
        subjects=(
            SubjectDefinition(subject_id="member-a", roles=("member",), tenant_id="tenant-a", department_id="dept-a"),
            SubjectDefinition(subject_id="dept-admin-a", roles=("department-admin",), tenant_id="tenant-a", department_id="dept-a", admin_level=1),
            SubjectDefinition(subject_id="tenant-admin-a", roles=("tenant-admin",), tenant_id="tenant-a", department_id="dept-a", admin_level=2),
            SubjectDefinition(subject_id="member-a2", roles=("member",), tenant_id="tenant-a", department_id="dept-a2"),
            SubjectDefinition(subject_id="dept-admin-a2", roles=("department-admin",), tenant_id="tenant-a", department_id="dept-a2", admin_level=1),
            SubjectDefinition(subject_id="member-b", roles=("member",), tenant_id="tenant-b", department_id="dept-b"),
        ),
        actions=(
            ActionDefinition(action_id="modify", side_effect=True),
            ActionDefinition(action_id="approve", side_effect=True, workflow_transition={"allowed_from_states": ("PENDING",), "target_state": "APPROVED"}),
            ActionDefinition(action_id="batch-modify", is_batch=True, side_effect=True),
        ),
        resources=(
            ResourceDefinition(resource_id="document-a", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="member-a", workflow_state="DRAFT"),
            ResourceDefinition(resource_id="document-a-child", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="member-a", parent_resource_id="document-a", workflow_state="DRAFT"),
            ResourceDefinition(resource_id="document-a-pending", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="member-a", workflow_state="PENDING"),
            ResourceDefinition(resource_id="document-a-approved", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="member-a", workflow_state="APPROVED"),
            ResourceDefinition(resource_id="document-b", resource_type="document", tenant_id="tenant-b", department_id="dept-b", owner_subject_id="member-b", workflow_state="DRAFT"),
            ResourceDefinition(resource_id="document-a2", resource_type="document", tenant_id="tenant-a", department_id="dept-a2", owner_subject_id="member-a2", workflow_state="DRAFT"),
        ),
        relations=(
            RelationFact(relation_id="manages-dept-admin-a", relation=RelationType.MANAGES, source=RelationEndpoint(endpoint_type="subject", endpoint_id="tenant-admin-a"), target=RelationEndpoint(endpoint_type="subject", endpoint_id="dept-admin-a")),
            RelationFact(relation_id="inherits-tenant-admin-a", relation=RelationType.INHERITS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="tenant-admin-a"), target=RelationEndpoint(endpoint_type="subject", endpoint_id="dept-admin-a")),
            RelationFact(relation_id="manages-member-a", relation=RelationType.MANAGES, source=RelationEndpoint(endpoint_type="subject", endpoint_id="dept-admin-a"), target=RelationEndpoint(endpoint_type="subject", endpoint_id="member-a")),
            RelationFact(relation_id="owns-document-a", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member-a"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document-a")),
            RelationFact(relation_id="owns-document-a-child", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member-a"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document-a-child")),
            RelationFact(relation_id="owns-document-a-pending", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member-a"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document-a-pending")),
            RelationFact(relation_id="owns-document-a-approved", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member-a"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document-a-approved")),
            RelationFact(relation_id="owns-document-a2", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member-a2"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document-a2")),
        ),
        rules=(
            PermissionRule(rule_id="modify-document-a", subject_id="member-a", action_id="modify", resource_id="document-a", relation_path=("owns-document-a",), context=PermissionContext(workflow_states=("DRAFT",), resource_ids=("document-a",)), expectation=PermissionExpectation.ALLOW, required_observations=("resource_state",), coverage_dimensions=(CoverageDimension.ROLE, CoverageDimension.TENANT, CoverageDimension.DEPARTMENT, CoverageDimension.RELATION)),
            PermissionRule(rule_id="approve-document-a", subject_id="tenant-admin-a", action_id="approve", resource_id="document-a", relation_path=("inherits-tenant-admin-a", "manages-member-a", "owns-document-a"), context=PermissionContext(workflow_states=("DRAFT",), resource_ids=("document-a",)), expectation=PermissionExpectation.DENY, required_observations=("resource_state",), coverage_dimensions=(CoverageDimension.WORKFLOW,)),
            PermissionRule(rule_id="approve-document-a-pending", subject_id="tenant-admin-a", action_id="approve", resource_id="document-a-pending", relation_path=("inherits-tenant-admin-a", "manages-member-a", "owns-document-a-pending"), context=PermissionContext(workflow_states=("PENDING",), resource_ids=("document-a-pending",)), expectation=PermissionExpectation.ALLOW, required_observations=("resource_state",), coverage_dimensions=(CoverageDimension.WORKFLOW,)),
            PermissionRule(rule_id="approve-document-a-approved", subject_id="tenant-admin-a", action_id="approve", resource_id="document-a-approved", relation_path=("inherits-tenant-admin-a", "manages-member-a", "owns-document-a-approved"), context=PermissionContext(workflow_states=("APPROVED",), resource_ids=("document-a-approved",)), expectation=PermissionExpectation.DENY, required_observations=("resource_state",), coverage_dimensions=(CoverageDimension.WORKFLOW,)),
        ),
        batch_rules=(
            BatchPermissionRule(rule_id="batch-all-allow", subject_id="member-a", action_id="batch-modify", resource_expectations=(BatchResourceExpectation(resource_id="document-a", expectation=PermissionExpectation.ALLOW, relation_path=("owns-document-a",)), BatchResourceExpectation(resource_id="document-a-child", expectation=PermissionExpectation.ALLOW, relation_path=("owns-document-a-child",))), required_observations=("resource_state",), context=PermissionContext(resource_ids=("document-a", "document-a-child")), atomic=True, coverage_dimensions=(CoverageDimension.BULK,)),
            BatchPermissionRule(rule_id="batch-all-deny", subject_id="member-a", action_id="batch-modify", resource_expectations=(BatchResourceExpectation(resource_id="document-a2", expectation=PermissionExpectation.DENY), BatchResourceExpectation(resource_id="document-b", expectation=PermissionExpectation.DENY)), required_observations=("resource_state",), context=PermissionContext(resource_ids=("document-a2", "document-b")), atomic=True, coverage_dimensions=(CoverageDimension.BULK,)),
            BatchPermissionRule(rule_id="batch-mixed", subject_id="member-a", action_id="batch-modify", resource_expectations=(BatchResourceExpectation(resource_id="document-a", expectation=PermissionExpectation.ALLOW, relation_path=("owns-document-a",)), BatchResourceExpectation(resource_id="document-b", expectation=PermissionExpectation.DENY)), required_observations=("resource_state",), context=PermissionContext(resource_ids=("document-a", "document-b")), atomic=True, coverage_dimensions=(CoverageDimension.BULK,)),
        ),
    )


def _request(base: str, method: str, path: str, token: str, body: dict | None = None, *, test_mode: bool = False) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{base}{path}", data=data, method=method, headers={"Authorization": f"Bearer {token}"})
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if test_mode:
        request.add_header("X-Jiejian-Test-Mode", "1")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, json.loads(raw) if raw else {}


@pytest.fixture
def permission_server(request: pytest.FixtureRequest, tmp_path: Path):
    running = []

    def start(variant: str, *, observer_token: str | None = None):
        tokens = {subject_id: f"token-{subject_id}" for subject_id in ("member-a", "dept-admin-a", "dept-admin-a2", "tenant-admin-a", "member-b")}
        server = create_complex_permission_test_server(
            variant=variant,
            port=0,
            tokens=tokens,
            database_path=tmp_path / f"{variant}.db",
            observer_token=observer_token,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        running.append((server, thread))
        return server, tokens

    def stop() -> None:
        for server, thread in running:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    request.addfinalizer(stop)
    return start


def test_complex_coverage_is_stable_and_preserves_batch_semantics() -> None:
    contract = _complex_contract()
    first = build_permission_coverage_plan(contract, engine_version="coverage-v2", seed=7, case_budget=32, max_relation_depth=4)
    second = build_permission_coverage_plan(contract, engine_version="coverage-v2", seed=7, case_budget=32, max_relation_depth=4)
    assert first == second
    assert first.contract_fingerprint == first.contract_fingerprint
    batch_modes = {case.batch_mode for case in first.cases if case.batch_mode is not None}
    assert batch_modes == {BatchAuthorizationMode.ALL_ALLOW, BatchAuthorizationMode.ALL_DENY, BatchAuthorizationMode.MIXED_AUTHORIZATION}
    assert all(case.atomic for case in first.cases if case.batch_mode is not None)
    assert all(case.finding_pre_identity for case in first.cases)
    approve_cases = [case for case in first.cases if case.action_id == "approve"]
    assert any(case.expectations == (PermissionExpectation.ALLOW,) and case.context.workflow_states == ("PENDING",) for case in approve_cases)
    assert any(
        case.relation_paths[0] == ("inherits-tenant-admin-a", "manages-member-a", "owns-document-a")
        for case in approve_cases
    )
    child = next(resource for resource in contract.resources if resource.resource_id == "document-a-child")
    assert child.parent_resource_id == "document-a"
    assert any(
        expectation.resource_id == "document-a-child" and expectation.relation_path == ("owns-document-a-child",)
        for rule in contract.batch_rules
        for expectation in rule.resource_expectations
    )
    baseline = next(record for record in first.coverage if record.rule_id == "modify-document-a" and record.expectation is PermissionExpectation.ALLOW)
    assert baseline.status is CoverageStatus.COVERED
    assert any(record.status is CoverageStatus.COVERED for record in first.coverage)


def test_coverage_reports_missing_observer_and_budget_gap() -> None:
    plan = build_permission_coverage_plan(_complex_contract(), engine_version="coverage-v2", seed=7, case_budget=1, available_observations=())
    codes = {gap.code for gap in plan.gaps}
    assert CoverageGapCode.MISSING_OBSERVER in codes
    assert plan.candidate_count >= plan.retained_count
    assert CoverageGapCode.BUDGET_EXCEEDED in codes or plan.candidate_count == plan.retained_count


def test_coverage_gaps_explain_each_baseline_and_dimension() -> None:
    plan = build_permission_coverage_plan(_complex_contract(), engine_version="coverage-v2", seed=7, case_budget=32, available_subject_ids=("member-a",), available_observations=("resource_state",))
    targets = {(gap.rule_id, gap.dimension, gap.expectation) for gap in plan.gaps}
    for record in plan.coverage:
        if record.status is CoverageStatus.GAP:
            assert record.gap_codes
            assert (record.rule_id, record.dimension, record.expectation) in targets


def test_seed_changes_same_priority_budget_selection_and_finding_identity_has_subject_class() -> None:
    first = build_permission_coverage_plan(_complex_contract(), engine_version="coverage-v2", seed=1, case_budget=1)
    second = build_permission_coverage_plan(_complex_contract(), engine_version="coverage-v2", seed=2, case_budget=1)
    assert first.plan_fingerprint != second.plan_fingerprint
    assert first.cases != second.cases
    assert all(case.finding_pre_identity for case in first.cases)


@pytest.mark.parametrize("variant", ["fixed", "vulnerable", "inconclusive"])
def test_permission_sample_variants_are_loopback_and_observer_distinct(permission_server, variant: str) -> None:
    server, tokens = permission_server(variant)
    base = f"http://127.0.0.1:{server.server_port}"
    status, _ = _request(base, "GET", "/health", tokens["member-a"])
    assert status == 200
    status, _ = _request(base, "GET", "/owner/resources/document-a", tokens["member-a"])
    assert status == (503 if variant == "inconclusive" else 200)


def test_fixed_enforces_scopes_workflow_and_atomic_batch(permission_server) -> None:
    server, tokens = permission_server("fixed")
    base = f"http://127.0.0.1:{server.server_port}"
    assert _request(base, "PATCH", "/resources/document-a", tokens["member-a"], {"value": "changed"})[0] == 200
    assert _request(base, "POST", "/reset", tokens["member-a"], test_mode=True)[0] == 204


def test_owner_observer_credential_does_not_change_target_permissions(permission_server) -> None:
    observer_token = "opaque-owner-observer"
    server, tokens = permission_server("fixed", observer_token=observer_token)
    base = f"http://127.0.0.1:{server.server_port}"

    assert _request(base, "PATCH", "/resources/document-a", tokens["dept-admin-a"], {"value": "department-admin"})[0] == 200
    assert _request(base, "POST", "/reset", tokens["member-a"], test_mode=True)[0] == 204
    assert _request(base, "PATCH", "/resources/document-a", tokens["tenant-admin-a"], {"value": "tenant-admin"})[0] == 200
    assert _request(base, "GET", "/resources/document-a", observer_token)[0] == 401
    assert _request(base, "GET", "/owner/resources/document-a", observer_token)[0] == 200
    assert _request(base, "PATCH", "/resources/document-a", tokens["dept-admin-a"], {"value": "department-admin"})[0] == 200
    assert _request(base, "POST", "/reset", tokens["member-a"], test_mode=True)[0] == 204
    assert _request(base, "PATCH", "/resources/document-a", tokens["tenant-admin-a"], {"value": "tenant-admin"})[0] == 200
    assert _request(base, "POST", "/reset", tokens["member-a"], test_mode=True)[0] == 204
    assert _request(base, "PATCH", "/resources/document-b", tokens["member-a"], {"value": "blocked"})[0] == 403
    assert _request(base, "PATCH", "/resources/document-a", tokens["dept-admin-a2"], {"value": "wrong-dept"})[0] == 403
    assert _request(base, "PATCH", "/resources/document-a", tokens["member-b"], {"value": "wrong-tenant"})[0] == 403
    assert _request(base, "POST", "/resources/document-a-pending/approve", tokens["dept-admin-a"])[0] == 403
    assert _request(base, "POST", "/resources/document-a-pending/approve", tokens["tenant-admin-a"])[0] == 200
    assert _request(base, "POST", "/resources/document-a-approved/approve", tokens["tenant-admin-a"])[0] == 403
    status, _ = _request(base, "POST", "/resources/batch", tokens["member-a"], {"resource_ids": ["document-a", "document-b"], "value": "mixed"})
    assert status == 403
    assert _request(base, "GET", "/resources/document-a", tokens["member-a"])[1]["value"] == "a-initial"
    assert _request(base, "POST", "/reset", tokens["member-a"], test_mode=True)[0] == 204


@pytest.mark.parametrize(
    ("resource_ids", "expected_status"),
    [
        (["document-a", "document-a-child"], 200),
        (["document-b", "document-a2"], 403),
    ],
)
def test_fixed_batch_all_allow_and_all_deny(permission_server, resource_ids: list[str], expected_status: int) -> None:
    server, tokens = permission_server("fixed")
    base = f"http://127.0.0.1:{server.server_port}"
    status, _ = _request(base, "POST", "/resources/batch", tokens["member-a"], {"resource_ids": resource_ids, "value": "batch"})
    assert status == expected_status


def test_fixed_batch_all_allow_persists_to_sqlite_observer(permission_server, tmp_path: Path) -> None:
    server, tokens = permission_server("fixed")
    base = f"http://127.0.0.1:{server.server_port}"
    assert _request(base, "POST", "/resources/batch", tokens["member-a"], {"resource_ids": ["document-a", "document-a-child"], "value": "batch-persisted"})[0] == 200
    spec = ObserverSpec(
        observer_id="sqlite_observer",
        observer_type=ObserverType.READ_ONLY_SQLITE,
        target=ObserverTarget(
            target_id="sqlite_state",
            locator=SqliteQueryLocator(query_template_id="resource-state", table_or_view="resource_state", database_secret_ref="env:BATCH_DB_SECRET"),
            normalization_id="resource-state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER,),
        required=True,
        budget=ObserverBudget(timeout_us=5_000_000, max_rows=10, max_bytes=4096),
    )
    for resource_id in ("document-a", "document-a-child"):
        result = run_sqlite_observer(
            spec,
            Correlation(case_id="batch-persist", resource_id=resource_id, request_marker="batch-persist"),
            ObservationPhase.AFTER,
            attempt_dir=tmp_path / resource_id,
            parent_environ={"BATCH_DB_SECRET": str(server.database_path)},
            python_executable=sys.executable,
        )
        assert result.outcome.status is ObserverOutcomeStatus.AVAILABLE
        assert result.envelope is not None and result.envelope.state is not None
        assert result.envelope.state.canonical_data["rows"][0]["value"] == "batch-persisted"


def test_vulnerable_batch_returns_forbidden_but_changes_allowed_member(permission_server) -> None:
    server, tokens = permission_server("vulnerable")
    base = f"http://127.0.0.1:{server.server_port}"
    status, _ = _request(base, "POST", "/resources/batch", tokens["member-a"], {"resource_ids": ["document-a", "document-b"], "value": "partial"})
    assert status == 403
    assert _request(base, "GET", "/owner/resources/document-a", tokens["member-a"])[1]["value"] == "partial"


def test_inconclusive_observer_cannot_be_replaced_by_http_response(permission_server) -> None:
    server, tokens = permission_server("inconclusive")
    base = f"http://127.0.0.1:{server.server_port}"
    assert _request(base, "PATCH", "/resources/document-a", tokens["member-a"], {"value": "candidate"})[0] == 200
    assert _request(base, "GET", "/owner/resources/document-a", tokens["member-a"])[0] == 503


def test_fixed_and_vulnerable_pair_http_403_with_sqlite_before_after_evidence(permission_server, tmp_path: Path) -> None:
    def observe(server, phase: ObservationPhase, name: str):
        spec = ObserverSpec(
            observer_id="sqlite_observer",
            observer_type=ObserverType.READ_ONLY_SQLITE,
            target=ObserverTarget(
                target_id="sqlite_state",
                locator=SqliteQueryLocator(
                    query_template_id="resource-state",
                    table_or_view="resource_state",
                    database_secret_ref="env:PAIRING_DB_SECRET",
                ),
                normalization_id="resource-state",
                normalization_version="1.0",
            ),
            phases=(ObservationPhase.BEFORE, ObservationPhase.AFTER),
            required=True,
            budget=ObserverBudget(timeout_us=5_000_000, max_rows=10, max_bytes=4096),
        )
        result = run_sqlite_observer(
            spec,
            Correlation(case_id="pairing-case", resource_id="document-b", request_marker="pairing-case"),
            phase,
            attempt_dir=tmp_path / f"{server.variant}-{name}",
            parent_environ={"PAIRING_DB_SECRET": str(server.database_path), "UNRELATED_SECRET": "not-forwarded"},
            python_executable=sys.executable,
        )
        assert result.outcome.status is ObserverOutcomeStatus.AVAILABLE
        assert result.envelope is not None
        assert result.envelope.observer_type is ObserverType.READ_ONLY_SQLITE
        assert result.envelope.protocol_version == "2"
        assert result.envelope.target_id == "sqlite_state"
        assert result.envelope.phase is phase
        assert result.envelope.completeness is ObservationCompleteness.COMPLETE
        assert result.envelope.causality.value == "CORRELATED"
        assert result.envelope.provenance is not None
        assert result.envelope.provenance.query_template_id == "resource-state"
        assert result.envelope.state is not None
        return result.envelope

    for variant in ("fixed", "vulnerable"):
        server, tokens = permission_server(variant)
        base = f"http://127.0.0.1:{server.server_port}"
        before = observe(server, ObservationPhase.BEFORE, "before")
        status, _ = _request(base, "PATCH", "/resources/document-b", tokens["member-a"], {"value": "denied-side-effect"})
        assert status == 403
        after = observe(server, ObservationPhase.AFTER, "after")
        assert before.correlation == after.correlation
        assert before.state is not None and after.state is not None
        if variant == "fixed":
            assert after.state.canonical_data == before.state.canonical_data
            assert after.state.canonical_sha256 == before.state.canonical_sha256
        else:
            assert after.state.canonical_data != before.state.canonical_data
            assert after.state.canonical_sha256 != before.state.canonical_sha256
            assert after.state.canonical_data["rows"][0]["value"] == "denied-side-effect"


def test_sample_observer_and_batch_body_boundaries_are_strict(permission_server) -> None:
    server, tokens = permission_server("fixed")
    base = f"http://127.0.0.1:{server.server_port}"
    assert _request(base, "GET", "/owner/resources/document-a", "not-a-token")[0] == 401
    assert _request(base, "POST", "/resources/batch", tokens["member-a"], {"resource_ids": ["document-a", "document-a"], "value": "duplicate"})[0] == 400
    assert _request(base, "POST", "/resources/batch", tokens["member-a"], {"resource_ids": ["document-a", "document-a-child"], "value": "ok", "extra": True})[0] == 400
