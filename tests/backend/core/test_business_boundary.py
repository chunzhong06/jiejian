# 验证 Business Boundary 领域哈希、Effect 规范化与本机审批真源。

from __future__ import annotations

import pytest
from pydantic import ValidationError

from product.backend.core.approval import HumanApproval, HumanApprovalChannel
from product.backend.core.boundary_proposal import BoundarySourceSnapshot
from product.backend.core.business_boundary import (
    ActorImplementationBinding,
    BusinessActionOperationKind,
    BusinessActionRevision,
    BusinessEffectDefinition,
    BusinessRevisionState,
    ImplementationCandidateSnapshot,
    boundary_sha256,
)
from product.backend.core.verification.permissions import SecurityEffectKind


ACTION_ID = "bac_" + "1" * 32
PROJECT_ID = "sample-project"


def _approval() -> HumanApproval:
    return HumanApproval(
        channel=HumanApprovalChannel.LOCAL_GUI,
        approved_by="本机界鉴用户",
        approved_at_us=10,
        reason="确认业务动作边界",
    )


def _effect(effect_id: str, label: str, kind: SecurityEffectKind) -> BusinessEffectDefinition:
    return BusinessEffectDefinition(
        effect_id=effect_id,
        business_label=label,
        effect_kind=kind,
        resource_concept="document",
        description=f"{label}的业务效果",
    )


def _action_fingerprint(effects: tuple[BusinessEffectDefinition, ...]) -> str:
    return boundary_sha256(
        {
            "action_id": ACTION_ID,
            "project_id": PROJECT_ID,
            "display_name": "更新文档",
            "description": "修改文档内容并形成新状态",
            "primary_resource_concept": "document",
            "operation_kind": BusinessActionOperationKind.CHANGE.value,
            "state_changing": True,
            "effect_catalog": [item.model_dump(mode="json") for item in effects],
            "effective_state": BusinessRevisionState.ACTIVE.value,
        }
    )


def test_action_effect_catalog_has_canonical_order_and_stable_hash() -> None:
    first = _effect(
        "bef_" + "1" * 32,
        "创建修订记录",
        SecurityEffectKind.OBJECT_CREATION,
    )
    second = _effect(
        "bef_" + "2" * 32,
        "更新文档内容",
        SecurityEffectKind.STATE_MUTATION,
    )
    canonical = (first, second)

    revision = BusinessActionRevision(
        action_id=ACTION_ID,
        project_id=PROJECT_ID,
        revision=1,
        display_name="更新文档",
        description="修改文档内容并形成新状态",
        primary_resource_concept="document",
        operation_kind=BusinessActionOperationKind.CHANGE,
        state_changing=True,
        effect_catalog=(second, first),
        semantic_fingerprint=_action_fingerprint(canonical),
        effective_state=BusinessRevisionState.ACTIVE,
        approval=_approval(),
        created_at_us=10,
    )

    assert revision.effect_catalog == canonical
    assert revision.semantic_fingerprint == boundary_sha256(revision.semantic_payload())


def test_action_effect_catalog_rejects_duplicate_business_semantics() -> None:
    first = _effect(
        "bef_" + "1" * 32,
        "更新文档内容",
        SecurityEffectKind.STATE_MUTATION,
    )
    duplicate = first.model_copy(update={"effect_id": "bef_" + "2" * 32})

    with pytest.raises(ValidationError, match="business semantics must be unique"):
        BusinessActionRevision(
            action_id=ACTION_ID,
            project_id=PROJECT_ID,
            revision=1,
            display_name="更新文档",
            description="修改文档内容并形成新状态",
            primary_resource_concept="document",
            operation_kind=BusinessActionOperationKind.CHANGE,
            state_changing=True,
            effect_catalog=(first, duplicate),
            semantic_fingerprint="0" * 64,
            effective_state=BusinessRevisionState.ACTIVE,
            approval=_approval(),
            created_at_us=10,
        )


def test_human_approval_identity_is_server_controlled() -> None:
    with pytest.raises(ValidationError, match="identity is server controlled"):
        HumanApproval(
            channel=HumanApprovalChannel.LOCAL_GUI,
            approved_by="客户端自述用户",
            approved_at_us=10,
            reason="尝试自述身份",
        )


def test_legacy_source_snapshot_defaults_to_basis_one() -> None:
    snapshot = BoundarySourceSnapshot.model_validate_json(
        '{"application_understanding_revision":1,"source_fingerprint":"'
        + "a" * 64
        + '","candidates":[]}'
    )

    assert snapshot.basis_version == 1


def test_binding_basis_preserves_legacy_hash_and_requires_exact_v2_snapshots() -> None:
    actor_id = "bar_" + "2" * 32
    candidate_id = "role_" + "3" * 32
    legacy_payload = {
        "actor_id": actor_id,
        "actor_revision": 1,
        "understanding_revision": 2,
        "source_fingerprint": "b" * 64,
        "role_candidate_ids": [candidate_id],
    }
    legacy = ActorImplementationBinding(
        actor_id=actor_id,
        actor_revision=1,
        understanding_revision=2,
        source_fingerprint="b" * 64,
        basis_version=1,
        role_candidate_ids=(candidate_id,),
        binding_fingerprint=boundary_sha256(legacy_payload),
        updated_at_us=10,
    )
    assert legacy.candidate_snapshots == ()
    assert legacy.source_proposal_id is None
    assert legacy.confirmed_at_us is None

    snapshot = ImplementationCandidateSnapshot(
        candidate_id=candidate_id,
        candidate_fingerprint="c" * 64,
        evidence_fingerprint="d" * 64,
    )
    v2_payload = legacy_payload | {
        "basis_version": 2,
        "source_proposal_id": "bpr_" + "4" * 32,
        "confirmed_at_us": 10,
        "candidate_snapshots": [snapshot.model_dump(mode="json")],
    }
    current = legacy.model_copy(
        update={
            "basis_version": 2,
            "source_proposal_id": "bpr_" + "4" * 32,
            "confirmed_at_us": 10,
            "candidate_snapshots": (snapshot,),
            "binding_fingerprint": boundary_sha256(v2_payload),
        }
    )
    current = ActorImplementationBinding.model_validate(current.model_dump())
    assert current.basis_version == 2

    with pytest.raises(ValidationError, match="snapshots must match"):
        ActorImplementationBinding.model_validate(
            current.model_dump() | {"candidate_snapshots": ()}
        )

    with pytest.raises(ValidationError, match="approval provenance"):
        ActorImplementationBinding.model_validate(
            current.model_dump() | {"source_proposal_id": None}
        )
