# 验证权限模型基础不变量与观察要求结构。

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
    SecurityEffectDefinition,
    SecurityEffectKind,
    SubjectDefinition,
    canonical_json_bytes,
    permission_model_sha256,
    compile_permission_plan,
    parse_permission_contract,
)
pytestmark = pytest.mark.essential
PROJECT_ROOT = Path(__file__).resolve().parents[5]

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
        effects=(SecurityEffectDefinition(effect_id="document-mutated", kind=SecurityEffectKind.STATE_MUTATION, resource_type="document"),),
        actions=(ActionDefinition(action_id="read", effect_ids=("document-mutated",)),),
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

def test_contract_has_strict_six_dimensions_and_stable_plan() -> None:
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
    assert permission_model_sha256(contract) == permission_model_sha256(reordered)
    assert plan.schema_version == "1"

def test_permission_rules_use_semantic_observation_requirements() -> None:
    contract = _contract(expectation=PermissionExpectation.DENY, observers=("resource_state",))
    assert contract.rules[0].required_observations == ("resource_state",)
