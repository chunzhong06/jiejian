import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from jiejian.verification.models import (
    ContractRule,
    Flow,
    FlowStep,
    Identity,
    MutationCase,
    MutationKind,
    MutationPlan,
    ResourceDefinition,
    RuleKind,
    SecurityContract,
)
from jiejian.verification.permissions import (
    ActionDefinition,
    NormalizedPermissionPlan,
    PermissionContractV2,
    PermissionContext,
    PermissionExpectation,
    PermissionRuleV2,
    CoverageDimension,
    RelationEndpoint,
    RelationFact,
    RelationType,
    ResourceDefinitionV2,
    SubjectDefinition,
    adapt_v1_ownership_plan,
    canonical_json_bytes,
    canonical_sha256,
    compile_permission_plan,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _contract(*, expectation: PermissionExpectation = PermissionExpectation.ALLOW, observers=("http", "owner_api")) -> PermissionContractV2:
    return PermissionContractV2(
        contract_id="permissions",
        version=1,
        role_ids=("admin", "user"),
        workflow_states=("active", "archived"),
        subjects=(
            SubjectDefinition(subject_id="admin", roles=("admin",), tenant_id="tenant-a", department_id="dept-a", admin_level=2),
            SubjectDefinition(subject_id="owner", roles=("user",), tenant_id="tenant-a", department_id="dept-a", admin_level=0),
        ),
        actions=(ActionDefinition(action_id="read", flow_step_ids=("read-step",)),),
        resources=(
            ResourceDefinitionV2(
                resource_id="document",
                resource_type="document",
                tenant_id="tenant-a",
                department_id="dept-a",
                owner_subject_id="owner",
                workflow_state="active",
            ),
        ),
        relations=(
            RelationFact(
                relation_id="manages-owner",
                relation=RelationType.MANAGES,
                source=RelationEndpoint(endpoint_type="subject", endpoint_id="admin"),
                target=RelationEndpoint(endpoint_type="subject", endpoint_id="owner"),
            ),
            RelationFact(
                relation_id="owns-document",
                relation=RelationType.OWNS,
                source=RelationEndpoint(endpoint_type="subject", endpoint_id="owner"),
                target=RelationEndpoint(endpoint_type="resource", endpoint_id="document"),
            ),
        ),
        rules=(
            PermissionRuleV2(
                rule_id="read-document",
                subject_id="admin",
                action_id="read",
                resource_id="document",
                relation_path=("manages-owner", "owns-document"),
                context=PermissionContext(workflow_states=("active",), resource_ids=("document",)),
                expectation=expectation,
                required_observers=observers,
                coverage_dimensions=(CoverageDimension.RELATION,),
            ),
        ),
    )


def test_v2_contract_has_strict_six_dimensions_and_stable_plan() -> None:
    contract = _contract()
    plan = compile_permission_plan(contract, engine_version="permissions-v2", seed=7, flow_step_ids=("read-step",))
    assert plan.cases[0].expected is PermissionExpectation.ALLOW
    assert len(plan.cases) == 1
    assert canonical_json_bytes(contract) == canonical_json_bytes(
        PermissionContractV2.model_validate_json(canonical_json_bytes(contract))
    )
    reordered_data = contract.model_dump(mode="python")
    reordered_data.update(
        subjects=tuple(reversed(contract.subjects)),
        resources=tuple(reversed(contract.resources)),
        relations=tuple(reversed(contract.relations)),
        rules=tuple(reversed(contract.rules)),
    )
    reordered = PermissionContractV2(**reordered_data)
    assert canonical_sha256(contract) == canonical_sha256(reordered)
    assert plan.model_dump(mode="python")["schema_version"] == "2"


@pytest.mark.parametrize(
    "change",
    [
        {"subjects": (SubjectDefinition(subject_id="other", roles=("user",), tenant_id="tenant-b"),)},
        {"resources": (ResourceDefinitionV2(resource_id="document", resource_type="document", tenant_id="tenant-b", workflow_state="active"),)},
        {"workflow_states": ("unknown",)},
    ],
)
def test_v2_rejects_undeclared_or_cross_boundary_facts(change: dict) -> None:
    data = _contract().model_dump(mode="python")
    data.update(change)
    with pytest.raises(ValidationError):
        PermissionContractV2.model_validate(data)


def test_v2_rejects_undeclared_role_action_and_state() -> None:
    data = _contract().model_dump(mode="python")
    data["subjects"] = (
        {**data["subjects"][0], "roles": ("root",)},
        data["subjects"][1],
    )
    with pytest.raises(ValidationError, match="subject role must be declared"):
        PermissionContractV2.model_validate(data)

    data = _contract().model_dump(mode="python")
    data["rules"] = (
        {**data["rules"][0], "action_id": "delete"},
    )
    with pytest.raises(ValidationError, match="action reference is invalid"):
        PermissionContractV2.model_validate(data)

    data = _contract().model_dump(mode="python")
    data["rules"] = (
        {
            **data["rules"][0],
            "context": PermissionContext(workflow_states=("unknown",)),
        },
    )
    with pytest.raises(ValidationError, match="undeclared workflow state"):
        PermissionContractV2.model_validate(data)


@pytest.mark.parametrize(
    "relation_path",
    [
        ("owns-document",),
        ("manages-owner",),
        ("manages-owner", "manages-owner"),
    ],
)
def test_v2_rejects_disconnected_or_incomplete_relation_paths(
    relation_path: tuple[str, ...],
) -> None:
    data = _contract().model_dump(mode="python")
    data["rules"] = (
        {**data["rules"][0], "relation_path": relation_path},
    )
    with pytest.raises(ValidationError, match="relation_path"):
        PermissionContractV2.model_validate(data)


@pytest.mark.parametrize(
    "context",
    [
        PermissionContext(workflow_states=("archived",)),
        PermissionContext(resource_ids=("other-document",)),
    ],
)
def test_v2_rejects_context_that_does_not_describe_the_rule_resource(
    context: PermissionContext,
) -> None:
    data = _contract().model_dump(mode="python")
    data["resources"] = (
        *data["resources"],
        ResourceDefinitionV2(
            resource_id="other-document",
            resource_type="document",
            tenant_id="tenant-a",
            department_id="dept-a",
            owner_subject_id="owner",
            workflow_state="active",
        ),
    )
    data["rules"] = ({**data["rules"][0], "context": context},)
    with pytest.raises(ValidationError, match="context"):
        PermissionContractV2.model_validate(data)


def test_v2_rejects_bad_relation_endpoints_cycles_and_conflicts() -> None:
    data = _contract().model_dump(mode="python")
    data["relations"] = (
        RelationFact(
            relation_id="bad",
            relation=RelationType.OWNS,
            source=RelationEndpoint(endpoint_type="resource", endpoint_id="document"),
            target=RelationEndpoint(endpoint_type="subject", endpoint_id="owner"),
        ),
    )
    with pytest.raises(ValidationError):
        PermissionContractV2.model_validate(data)

    data = _contract().model_dump(mode="python")
    data["rules"] = (
        data["rules"][0],
        PermissionRuleV2(
            rule_id="deny-same",
            subject_id="admin",
            action_id="read",
            resource_id="document",
            relation_path=("manages-owner", "owns-document"),
            context=PermissionContext(workflow_states=("active",), resource_ids=("document",)),
            expectation=PermissionExpectation.DENY,
            required_observers=("http", "owner_api"),
            coverage_dimensions=(CoverageDimension.RELATION,),
        ),
    )
    with pytest.raises(ValidationError):
        PermissionContractV2.model_validate(data)


def test_v2_requires_observers_for_deny_and_stateful_rules() -> None:
    with pytest.raises(ValidationError):
        _contract(expectation=PermissionExpectation.DENY, observers=("http",))


def test_v1_adapter_is_deterministic_and_preserves_original_case_metadata() -> None:
    identity = (Identity(id="owner", role="user", secret_ref="env:OWNER"), Identity(id="attacker", role="user", secret_ref="env:ATTACKER"))
    resources = (ResourceDefinition(id="resource", owner_identity_id="owner"), ResourceDefinition(id="foreign", owner_identity_id="attacker"))
    flow = Flow(
        id="flow",
        steps=(FlowStep(
            id="read-step", method="GET", path="/resources/{resource_id}", identity_id="owner", resource_id="resource",
            alternate_identity_id="attacker", alternate_resource_id="foreign",
        ),),
    )
    contract = SecurityContract(
        id="ownership", rules=(ContractRule(id="foreign-read", kind=RuleKind.FOREIGN_READ, required_observers=("http",)),)
    )
    original = MutationPlan(seed=7, engine_version="v1", cases=(MutationCase(
        case_id="case-old", fingerprint="a" * 64, step_id="read-step", rule_id="foreign-read",
        mutation=MutationKind.IDENTITY_SWAP, method="GET", path="/resources/resource", identity_id="attacker",
        resource_id="resource", owner_identity_id="owner",
    ),))
    first = adapt_v1_ownership_plan(original, contract, flow, identity, resources)
    second = adapt_v1_ownership_plan(original, contract, flow, identity, resources)
    assert first == second
    assert first.cases[0].source_case_id == "case-old"
    assert first.cases[0].fingerprint == "a" * 64
    assert first.cases[0].source_step_id == "read-step"


@pytest.mark.parametrize("schema_name, model", [("permission-contract-v2.schema.json", PermissionContractV2), ("normalized-permission-plan-v2.schema.json", NormalizedPermissionPlan)])
def test_checked_in_v2_schema_has_no_drift(schema_name: str, model: type) -> None:
    checked_in = json.loads((PROJECT_ROOT / "schemas" / "contracts" / schema_name).read_text(encoding="utf-8"))
    assert checked_in == model.model_json_schema()


def test_checked_in_permission_mutation_plan_schema_has_no_drift() -> None:
    from jiejian.verification.permission_coverage import PermissionMutationPlanV2

    checked_in = json.loads((PROJECT_ROOT / "schemas" / "contracts" / "permission-mutation-plan-v2.schema.json").read_text(encoding="utf-8"))
    assert checked_in == PermissionMutationPlanV2.model_json_schema()


def test_permission_coverage_is_deterministic_and_records_neighborhoods() -> None:
    from jiejian.verification.permission_coverage import (
        CoverageGapCode,
        CoverageStatus,
        build_permission_coverage_plan,
    )

    base = _contract()
    data = base.model_dump(mode="python")
    data["subjects"] = (
        *data["subjects"],
        SubjectDefinition(subject_id="tenant-peer", roles=("admin",), tenant_id="tenant-b", department_id="dept-b", admin_level=2),
        SubjectDefinition(subject_id="dept-peer", roles=("admin",), tenant_id="tenant-a", department_id="dept-b", admin_level=2),
    )
    data["resources"] = (
        *data["resources"],
        ResourceDefinitionV2(resource_id="pending-document", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="owner", workflow_state="archived"),
    )
    data["actions"] = (
        ActionDefinition(action_id="read", flow_step_ids=("read-step",), side_effect=True, workflow_transition={"allowed_from_states": ("active",), "target_state": "archived"}),
    )
    data["rules"] = ({**data["rules"][0], "coverage_dimensions": (CoverageDimension.ROLE, CoverageDimension.TENANT, CoverageDimension.DEPARTMENT, CoverageDimension.WORKFLOW)},)
    contract = PermissionContractV2(**data)
    first = build_permission_coverage_plan(contract, engine_version="coverage-v2", seed=7, case_budget=16, max_relation_depth=4)
    second = build_permission_coverage_plan(contract, engine_version="coverage-v2", seed=7, case_budget=16, max_relation_depth=4)
    assert first == second
    assert first.plan_fingerprint == second.plan_fingerprint
    assert any(CoverageStatus.COVERED is record.status for record in first.coverage)
    assert all(CoverageGapCode.RELATION_UNPROVABLE is not gap.code for gap in first.gaps)
    assert first.cases[0].finding_pre_identity


def test_permission_coverage_records_gaps_and_budget_eliminations() -> None:
    from jiejian.verification.permission_coverage import CoverageGapCode, build_permission_coverage_plan

    data = _contract().model_dump(mode="python")
    data["rules"] = ({**data["rules"][0], "coverage_dimensions": (CoverageDimension.ROLE, CoverageDimension.TENANT)},)
    contract = PermissionContractV2(**data)
    plan = build_permission_coverage_plan(contract, engine_version="coverage-v2", seed=7, case_budget=1, available_subject_ids=("admin",), available_observers=("http",))
    assert any(gap.code is CoverageGapCode.MISSING_OBSERVER for gap in plan.gaps)
    assert plan.candidate_count >= plan.retained_count


def test_batch_rule_requires_batch_action_and_preserves_per_resource_expectations() -> None:
    from jiejian.verification.permission_coverage import BatchAuthorizationMode, build_permission_coverage_plan
    from jiejian.verification.permissions import BatchPermissionRuleV2, BatchResourceExpectation

    data = _contract().model_dump(mode="python")
    data["subjects"] = (*data["subjects"], SubjectDefinition(subject_id="child", roles=("user",), tenant_id="tenant-a", department_id="dept-a"))
    data["resources"] = (*data["resources"], ResourceDefinitionV2(resource_id="child-document", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="child", workflow_state="active"))
    data["actions"] = (*data["actions"], ActionDefinition(action_id="batch-read", flow_step_ids=("read-step",), is_batch=True))
    data["batch_rules"] = (BatchPermissionRuleV2(
        rule_id="batch-read-rule", subject_id="admin", action_id="batch-read",
        resource_expectations=(
            BatchResourceExpectation(resource_id="document", expectation=PermissionExpectation.ALLOW, relation_path=("manages-owner", "owns-document")),
            BatchResourceExpectation(resource_id="child-document", expectation=PermissionExpectation.DENY),
        ),
        required_observers=("http", "owner_api"), context=PermissionContext(resource_ids=("child-document", "document")),
        coverage_dimensions=(CoverageDimension.BULK,), atomic=True,
    ),)
    contract = PermissionContractV2(**data)
    plan = build_permission_coverage_plan(contract, engine_version="coverage-v2", seed=7, case_budget=8)
    batch = next(case for case in plan.cases if case.batch_mode is not None)
    assert batch.batch_mode is BatchAuthorizationMode.MIXED_AUTHORIZATION
    assert batch.atomic is True
    assert batch.expectations == (PermissionExpectation.DENY, PermissionExpectation.ALLOW)
