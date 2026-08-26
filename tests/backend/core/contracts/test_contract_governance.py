# 验证权限契约领域中的权限契约治理。

from __future__ import annotations

import pytest

from product.backend.core.contracts.lifecycle import transition_contract_version
from product.backend.core.contracts.models import ContractAuditAction, ContractAuditEntry, ContractProvenance, ContractSourceType, ContractVersion, SourceReference
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.verification.permissions import ActionDefinition, CoverageDimension, PermissionContract, PermissionContext, PermissionExpectation, PermissionRule, RelationEndpoint, RelationFact, RelationType, ResourceDefinition, SecurityEffectDefinition, SecurityEffectKind, SubjectDefinition


def _contract(version: int = 1) -> PermissionContract:
    return PermissionContract(
        contract_id="ownership-contract", version=version, role_ids=("member",), workflow_states=("DRAFT",),
        subjects=(SubjectDefinition(subject_id="member", roles=("member",), tenant_id="tenant"),),
        effects=(SecurityEffectDefinition(effect_id="document-read", kind=SecurityEffectKind.DATA_DISCLOSURE, resource_type="document", protected_fields=("content",)),),
        actions=(ActionDefinition(action_id="view", effect_ids=("document-read",)),),
        resources=(ResourceDefinition(resource_id="document", resource_type="document", owner_subject_id="member", tenant_id="tenant", workflow_state="DRAFT"),),
        relations=(RelationFact(relation_id="owns-document", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document")),),
        rules=(PermissionRule(rule_id="foreign-read", subject_id="member", action_id="view", resource_id="document", relation_path=("owns-document",), context=PermissionContext(resource_ids=("document",)), expectation=PermissionExpectation.DENY, required_observations=("resource_state",), coverage_dimensions=(CoverageDimension.RELATION,)),),
    )


def _version() -> ContractVersion:
    return ContractVersion(
        project_id="contract-project", contract_id="ownership-contract", version=1, status=ContractStatus.DRAFT, snapshot=_contract(),
        provenance=ContractProvenance(sources=(SourceReference(source_type=ContractSourceType.PROJECT_CONFIG, locator="test", content_sha256="a" * 64),)),
        audit=(ContractAuditEntry(action=ContractAuditAction.CREATED, actor="tester", occurred_at_us=10),), created_at_us=10, updated_at_us=10,
    )


def test_contract_version_lifecycle_keeps_permission_snapshot_immutable() -> None:
    draft = _version()
    review = transition_contract_version(draft, ContractStatus.REVIEW, actor="reviewer", occurred_at_us=11)
    active = transition_contract_version(review, ContractStatus.ACTIVE, actor="approver", occurred_at_us=12)
    assert active.snapshot == draft.snapshot
    assert not hasattr(active.snapshot, "status")
    assert active.status is ContractStatus.ACTIVE


def test_active_version_cannot_be_activated_again() -> None:
    active = transition_contract_version(transition_contract_version(_version(), ContractStatus.REVIEW, actor="reviewer", occurred_at_us=11), ContractStatus.ACTIVE, actor="approver", occurred_at_us=12)
    with pytest.raises(JiejianError) as error:
        transition_contract_version(active, ContractStatus.ACTIVE, actor="approver", occurred_at_us=13)
    assert error.value.code == ErrorCode.STATE_INVALID_TRANSITION.value
