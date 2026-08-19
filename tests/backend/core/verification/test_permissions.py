import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from product.backend.core.verification.permissions import (
    ActionDefinition,
    NormalizedPermissionPlan,
    PermissionContract,
    PermissionContext,
    PermissionExpectation,
    PermissionRule,
    CoverageDimension,
    RelationEndpoint,
    RelationFact,
    RelationType,
    ResourceDefinition,
    SubjectDefinition,
    canonical_json_bytes,
    canonical_sha256,
    compile_permission_plan,
)


pytestmark = pytest.mark.essential


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _contract(*, expectation: PermissionExpectation = PermissionExpectation.ALLOW, observers=("resource_state",)) -> PermissionContract:
    return PermissionContract(
        contract_id="permissions",
        version=1,
        role_ids=("admin", "user"),
        workflow_states=("active", "archived"),
        subjects=(
            SubjectDefinition(subject_id="admin", roles=("admin",), tenant_id="tenant-a", department_id="dept-a", admin_level=2),
            SubjectDefinition(subject_id="owner", roles=("user",), tenant_id="tenant-a", department_id="dept-a", admin_level=0),
        ),
        actions=(ActionDefinition(action_id="read", ),),
        resources=(
            ResourceDefinition(
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
            PermissionRule(
                rule_id="read-document",
                subject_id="admin",
                action_id="read",
                resource_id="document",
                relation_path=("manages-owner", "owns-document"),
                context=PermissionContext(workflow_states=("active",), resource_ids=("document",)),
                expectation=expectation,
                required_observations=observers,
                coverage_dimensions=(CoverageDimension.RELATION,),
            ),
        ),
    )


def test_v2_contract_has_strict_six_dimensions_and_stable_plan() -> None:
    contract = _contract()
    plan = compile_permission_plan(contract, engine_version="permissions", seed=7, )
    assert plan.cases[0].expected is PermissionExpectation.ALLOW
    assert len(plan.cases) == 1
    assert canonical_json_bytes(contract) == canonical_json_bytes(
        PermissionContract.model_validate_json(canonical_json_bytes(contract))
    )
    reordered_data = contract.model_dump(mode="python")
    reordered_data.update(
        subjects=tuple(reversed(contract.subjects)),
        resources=tuple(reversed(contract.resources)),
        relations=tuple(reversed(contract.relations)),
        rules=tuple(reversed(contract.rules)),
    )
    reordered = PermissionContract(**reordered_data)
    assert canonical_sha256(contract) == canonical_sha256(reordered)
    assert plan.model_dump(mode="python")["schema_version"] == "2"


@pytest.mark.parametrize(
    "change",
    [
        {"subjects": (SubjectDefinition(subject_id="other", roles=("user",), tenant_id="tenant-b"),)},
        {"resources": (ResourceDefinition(resource_id="document", resource_type="document", tenant_id="tenant-b", workflow_state="active"),)},
        {"workflow_states": ("unknown",)},
    ],
)
def test_v2_rejects_undeclared_or_cross_boundary_facts(change: dict) -> None:
    data = _contract().model_dump(mode="python")
    data.update(change)
    with pytest.raises(ValidationError):
        PermissionContract.model_validate(data)


def test_v2_rejects_undeclared_role_action_and_state() -> None:
    data = _contract().model_dump(mode="python")
    data["subjects"] = (
        {**data["subjects"][0], "roles": ("root",)},
        data["subjects"][1],
    )
    with pytest.raises(ValidationError, match="subject role must be declared"):
        PermissionContract.model_validate(data)

    data = _contract().model_dump(mode="python")
    data["rules"] = (
        {**data["rules"][0], "action_id": "delete"},
    )
    with pytest.raises(ValidationError, match="action reference is invalid"):
        PermissionContract.model_validate(data)

    data = _contract().model_dump(mode="python")
    data["rules"] = (
        {
            **data["rules"][0],
            "context": PermissionContext(workflow_states=("unknown",)),
        },
    )
    with pytest.raises(ValidationError, match="undeclared workflow state"):
        PermissionContract.model_validate(data)


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
        PermissionContract.model_validate(data)


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
        ResourceDefinition(
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
        PermissionContract.model_validate(data)


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
        PermissionContract.model_validate(data)

    data = _contract().model_dump(mode="python")
    data["rules"] = (
        data["rules"][0],
        PermissionRule(
            rule_id="deny-same",
            subject_id="admin",
            action_id="read",
            resource_id="document",
            relation_path=("manages-owner", "owns-document"),
            context=PermissionContext(workflow_states=("active",), resource_ids=("document",)),
            expectation=PermissionExpectation.DENY,
            required_observations=("resource_state",),
            coverage_dimensions=(CoverageDimension.RELATION,),
        ),
    )
    with pytest.raises(ValidationError):
        PermissionContract.model_validate(data)


def test_permission_rules_use_semantic_observation_requirements() -> None:
    contract = _contract(expectation=PermissionExpectation.DENY, observers=("resource_state",))
    assert contract.rules[0].required_observations == ("resource_state",)


@pytest.mark.parametrize("schema_name, model", [("permission-contract.schema.json", PermissionContract), ("normalized-permission-plan.schema.json", NormalizedPermissionPlan)])
def test_checked_in_v2_schema_has_no_drift(schema_name: str, model: type) -> None:
    checked_in = json.loads((PROJECT_ROOT / "product" / "protocols" / "schemas" / "contracts" / schema_name).read_text(encoding="utf-8"))
    assert checked_in == model.model_json_schema()


def test_checked_in_permission_mutation_plan_schema_has_no_drift() -> None:
    from product.backend.core.verification.permission_coverage import PermissionMutationPlan

    checked_in = json.loads((PROJECT_ROOT / "product" / "protocols" / "schemas" / "contracts" / "permission-mutation-plan.schema.json").read_text(encoding="utf-8"))
    assert checked_in == PermissionMutationPlan.model_json_schema()


def test_permission_coverage_is_deterministic_and_records_neighborhoods() -> None:
    from product.backend.core.verification.permission_coverage import (
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
        ResourceDefinition(resource_id="pending-document", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="owner", workflow_state="archived"),
    )
    data["actions"] = (
        ActionDefinition(action_id="read", side_effect=True, workflow_transition={"allowed_from_states": ("active",), "target_state": "archived"}),
    )
    data["rules"] = ({**data["rules"][0], "coverage_dimensions": (CoverageDimension.ROLE, CoverageDimension.TENANT, CoverageDimension.DEPARTMENT, CoverageDimension.WORKFLOW)},)
    contract = PermissionContract(**data)
    first = build_permission_coverage_plan(contract, engine_version="coverage-v2", seed=7, case_budget=16, max_relation_depth=4)
    second = build_permission_coverage_plan(contract, engine_version="coverage-v2", seed=7, case_budget=16, max_relation_depth=4)
    assert first == second
    assert first.plan_fingerprint == second.plan_fingerprint
    assert any(CoverageStatus.COVERED is record.status for record in first.coverage)
    assert all(CoverageGapCode.RELATION_UNPROVABLE is not gap.code for gap in first.gaps)
    assert first.cases[0].finding_pre_identity


def test_permission_coverage_records_gaps_and_budget_eliminations() -> None:
    from product.backend.core.verification.permission_coverage import CoverageGapCode, build_permission_coverage_plan

    data = _contract().model_dump(mode="python")
    data["rules"] = ({**data["rules"][0], "coverage_dimensions": (CoverageDimension.ROLE, CoverageDimension.TENANT)},)
    contract = PermissionContract(**data)
    plan = build_permission_coverage_plan(contract, engine_version="coverage-v2", seed=7, case_budget=1, available_subject_ids=("admin",), available_observations=())
    assert any(gap.code is CoverageGapCode.MISSING_OBSERVER for gap in plan.gaps)
    assert plan.candidate_count >= plan.retained_count


def test_batch_rule_requires_batch_action_and_preserves_per_resource_expectations() -> None:
    from product.backend.core.verification.permission_coverage import BatchAuthorizationMode, build_permission_coverage_plan
    from product.backend.core.verification.permissions import BatchPermissionRule, BatchResourceExpectation

    data = _contract().model_dump(mode="python")
    data["subjects"] = (*data["subjects"], SubjectDefinition(subject_id="child", roles=("user",), tenant_id="tenant-a", department_id="dept-a"))
    data["resources"] = (*data["resources"], ResourceDefinition(resource_id="child-document", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="child", workflow_state="active"))
    data["actions"] = (*data["actions"], ActionDefinition(action_id="batch-read", is_batch=True))
    data["batch_rules"] = (BatchPermissionRule(
        rule_id="batch-read-rule", subject_id="admin", action_id="batch-read",
        resource_expectations=(
            BatchResourceExpectation(resource_id="document", expectation=PermissionExpectation.ALLOW, relation_path=("manages-owner", "owns-document")),
            BatchResourceExpectation(resource_id="child-document", expectation=PermissionExpectation.DENY),
        ),
        required_observations=("resource_state",), context=PermissionContext(resource_ids=("child-document", "document")),
        coverage_dimensions=(CoverageDimension.BULK,), atomic=True,
    ),)
    contract = PermissionContract(**data)
    plan = build_permission_coverage_plan(contract, engine_version="coverage-v2", seed=7, case_budget=8)
    batch = next(case for case in plan.cases if case.batch_mode is not None)
    assert batch.batch_mode is BatchAuthorizationMode.MIXED_AUTHORIZATION
    assert batch.atomic is True
    assert batch.expectations == (PermissionExpectation.DENY, PermissionExpectation.ALLOW)
