# 验证权限模型基础不变量与观察要求结构。

import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from product.backend.domain.verification.permissions.models import ActionDefinition, PermissionContext, PermissionRule, CoverageDimension, RelationEndpoint, RelationFact, RelationType, ResourceDefinition, SecurityEffectDefinition, SubjectDefinition
from product.backend.domain.verification.permissions.contract import NormalizedPermissionPlan, PermissionContract, canonical_json_bytes, permission_model_sha256, compile_permission_plan, parse_permission_contract
from product.backend.domain.boundaries.semantics import PermissionExpectation, BusinessEffectKind as SecurityEffectKind
pytestmark = pytest.mark.level2
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


@pytest.mark.parametrize('batch',[False,True])
def test_single_and_batch_rules_preserve_observation_validation(batch):
    from product.backend.domain.verification.permissions.models import BatchPermissionRule, BatchResourceExpectation

    if batch:
        model=BatchPermissionRule
        payload=dict(rule_id='batch',subject_id='viewer',action_id='read',coverage_dimensions=(CoverageDimension.BULK,),resource_expectations=(
            BatchResourceExpectation(resource_id='first',expectation=PermissionExpectation.ALLOW),
            BatchResourceExpectation(resource_id='second',expectation=PermissionExpectation.DENY),
        ))
    else:
        model=PermissionRule
        payload=_contract().rules[0].model_dump(mode='python')
    valid=model.model_validate({**payload,'required_observations':('z_state','a_state')})
    assert valid.required_observations==('a_state','z_state')
    with pytest.raises(ValidationError,match='required_observations must be unique'):
        model.model_validate({**payload,'required_observations':('same','same')})
    with pytest.raises(ValidationError,match='bounded requirement IDs'):
        model.model_validate({**payload,'required_observations':('bad id',)})
