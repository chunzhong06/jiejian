# 验证 Business Boundary Proposal 的原子批准、policy epoch、来源失效与 Actor TestIdentity。

from __future__ import annotations

from pathlib import Path

import pytest

from product.backend.composition import ApplicationCore
from product.backend.core.application_understanding import CandidateDecision
from product.backend.core.boundary_proposal import (
    ProposalWriteMode,
    ProposedActionItem,
    ProposedActorItem,
    ProposedEffectItem,
    ProposedPermissionItem,
)
from product.backend.core.business_boundary import (
    BusinessActionOperationKind,
    BusinessRevisionState,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState,
    PermissionIntentRevision,
    PermissionIntentRelation,
    PermissionIntentSemantic,
    permission_intent_sha256,
)
from product.backend.core.verification.permissions import (
    PermissionExpectation,
    SecurityEffectKind,
)
from product.backend.workflows.business_boundaries import BoundaryProposalCommand


pytestmark = [pytest.mark.database, pytest.mark.essential]


def _core(tmp_path: Path) -> tuple[ApplicationCore, str]:
    source = tmp_path / "source"
    source.mkdir()
    core = ApplicationCore(tmp_path / "var")
    connected = core.application_understanding.connect(
        str(source),
        project_name="稳定业务边界测试",
    )
    return core, connected.project.project_id


def _actors(*, member_state: BusinessRevisionState = BusinessRevisionState.ACTIVE):
    return (
        ProposedActorItem(
            item_id="pactr_1111111111111111",
            write_mode=ProposalWriteMode.CREATE,
            display_name="项目负责人",
            description="负责项目交付",
            effective_state=BusinessRevisionState.ACTIVE,
        ),
        ProposedActorItem(
            item_id="pactr_2222222222222222",
            write_mode=ProposalWriteMode.CREATE,
            display_name="普通协作成员",
            description="参与日常协作",
            effective_state=member_state,
        ),
    )


def _action():
    return ProposedActionItem(
        item_id="pactn_1111111111111111",
        write_mode=ProposalWriteMode.CREATE,
        display_name="导出完整项目交付包",
        description="形成可交付的完整项目包",
        primary_resource_concept="项目交付空间",
        operation_kind=BusinessActionOperationKind.EXPORT,
        state_changing=True,
        effect_catalog=(
            ProposedEffectItem(
                item_id="peff_1111111111111111",
                business_label="完整项目交付包真实形成",
                effect_kind=SecurityEffectKind.OBJECT_CREATION,
                resource_concept="项目交付包",
                description="交付包已经形成",
            ),
        ),
        effective_state=BusinessRevisionState.ACTIVE,
    )


def _second_action():
    return ProposedActionItem(
        item_id="pactn_2222222222222222",
        write_mode=ProposalWriteMode.CREATE,
        display_name="查看日常协作资料",
        description="读取项目的日常协作资料",
        primary_resource_concept="项目协作空间",
        operation_kind=BusinessActionOperationKind.READ,
        state_changing=False,
        effect_catalog=(
            ProposedEffectItem(
                item_id="peff_2222222222222222",
                business_label="日常协作资料已读取",
                effect_kind=SecurityEffectKind.DATA_DISCLOSURE,
                resource_concept="日常协作资料",
                protected_projection=("collaboration.summary",),
                description="返回项目日常协作资料",
            ),
        ),
        effective_state=BusinessRevisionState.ACTIVE,
    )


def _permission(item_id: str, actor_item_id: str, expectation: PermissionExpectation):
    return ProposedPermissionItem(
        item_id=item_id,
        write_mode=ProposalWriteMode.CREATE,
        effective_state=PermissionIntentEffectiveState.ACTIVE,
        subject_actor_item_id=actor_item_id,
        business_action_item_id="pactn_1111111111111111",
        resource_owner_actor_item_id="pactr_1111111111111111",
        relation=(
            PermissionIntentRelation.OWNS
            if actor_item_id == "pactr_1111111111111111"
            else PermissionIntentRelation.OTHER_ROLE
        ),
        expectation=expectation,
        protected_effect_item_ids=("peff_1111111111111111",),
    )


def _create_proposal(
    core: ApplicationCore,
    project_id: str,
    *,
    actors=None,
    permissions=None,
):
    return core.business_boundaries.create_proposal(
        project_id,
        BoundaryProposalCommand(
            proposed_actors=_actors() if actors is None else actors,
            proposed_actions=(_action(),),
            proposed_permissions=(
                (
                    _permission(
                        "pperm_1111111111111111",
                        "pactr_1111111111111111",
                        PermissionExpectation.ALLOW,
                    ),
                    _permission(
                        "pperm_2222222222222222",
                        "pactr_2222222222222222",
                        PermissionExpectation.DENY,
                    ),
                )
                if permissions is None
                else permissions
            ),
            provenance="本机用户提交业务边界",
        ),
    ).proposal


def test_bundle_approval_creates_stable_boundary_once_and_test_identity_uses_actor(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        proposal = _create_proposal(core, project_id)
        boundary = core.business_boundaries.approve(
            project_id,
            proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint,
            reason="确认稳定业务边界",
        )

        assert boundary.policy_epoch == 1
        assert len(boundary.actors) == 2
        assert len(boundary.actions) == 1
        assert len(boundary.permission_intents) == 2
        assert {item.policy_epoch for item in boundary.permission_intents} == {1}
        assert boundary.permission_statuses[0].allow_control_available is True
        assert boundary.permission_statuses[0].validation_contract_complete is False
        assert boundary.permission_statuses[0].reason_codes == (
            "VALIDATION_PIPELINE_DEFERRED_TO_1_1_3",
        )

        actor = next(item for item in boundary.actors if item.display_name == "项目负责人")
        identity = core.test_identities.create(
            project_id,
            actor_id=actor.actor_id,
            actor_revision=actor.revision,
            label="负责人账号",
        )
        assert identity.actor_id == actor.actor_id
        assert identity.actor_revision == actor.revision
        assert identity.actor_display_name == "项目负责人"
        assert "role_candidate_id" not in identity.model_dump()

        with pytest.raises(JiejianError) as error:
            core.business_boundaries.reject(
                project_id,
                proposal.proposal_id,
                expected_fingerprint=proposal.proposal_fingerprint,
                reason="重复决定",
            )
        assert error.value.code == ErrorCode.BOUNDARY_PROPOSAL_ALREADY_DECIDED.value
    finally:
        core.close()


def test_invalid_nth_permission_rolls_back_all_formal_writes(tmp_path: Path) -> None:
    core, project_id = _core(tmp_path)
    try:
        proposal = _create_proposal(
            core,
            project_id,
            actors=_actors(member_state=BusinessRevisionState.RETIRED),
        )
        with pytest.raises(JiejianError) as error:
            core.business_boundaries.approve(
                project_id,
                proposal.proposal_id,
                expected_fingerprint=proposal.proposal_fingerprint,
                reason="应当原子拒绝",
            )
        assert error.value.code == ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID.value
        boundary = core.business_boundaries.view(project_id)
        assert boundary.actors == ()
        assert boundary.actions == ()
        assert boundary.permission_intents == ()
        assert boundary.policy_epoch == 0
        assert core.business_boundaries.proposal(project_id, proposal.proposal_id).decision is None
    finally:
        core.close()


def test_source_revision_change_rejects_approval_without_formal_writes(tmp_path: Path) -> None:
    core, project_id = _core(tmp_path)
    try:
        proposal = _create_proposal(core, project_id)
        understanding = core.application_understanding.get(project_id)
        core.application_understanding.add_manual_role(
            project_id,
            revision=understanding.revision,
            display_name="后新增角色",
        )
        with pytest.raises(JiejianError) as error:
            core.business_boundaries.approve(
                project_id,
                proposal.proposal_id,
                expected_fingerprint=proposal.proposal_fingerprint,
                reason="来源已经变化",
            )
        assert error.value.code == ErrorCode.BOUNDARY_PROPOSAL_SOURCE_STALE.value
        assert core.business_boundaries.view(project_id).actors == ()
    finally:
        core.close()


def test_actor_action_only_bundle_does_not_advance_policy_epoch(tmp_path: Path) -> None:
    core, project_id = _core(tmp_path)
    try:
        proposal = _create_proposal(core, project_id, permissions=())
        boundary = core.business_boundaries.approve(
            project_id,
            proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint,
            reason="只确认业务身份",
        )
        assert boundary.policy_epoch == 0
        assert boundary.permission_intents == ()
    finally:
        core.close()


def test_current_permission_projection_excludes_noncurrent_latest_revisions(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        proposal = _create_proposal(core, project_id)
        boundary = core.business_boundaries.approve(
            project_id,
            proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint,
            reason="确认当前权限",
        )
        permission = boundary.permission_intents[0]
        action = boundary.actions[0]
        invalid_updates = (
            {"effective_state": PermissionIntentEffectiveState.RETIRED},
            {"subject_actor_revision": permission.subject_actor_revision + 1},
            {"action_revision": permission.action_revision + 1},
            {"protected_effect_ids": ("bef_ffffffffffffffffffffffffffffffff",)},
        )

        for updates in invalid_updates:
            latest = permission.model_copy(update=updates)
            current, stale = core.business_boundaries._current_permission_intents(
                (latest,), boundary.actors, boundary.actions
            )
            assert current == ()
            assert stale == (latest,)
            status = core.business_boundaries._permission_status(
                action, current, stale
            )
            assert status.permission_semantics_confirmed is False
            assert status.stale_permission_count == 1
            assert status.reason_codes == (
                "PERMISSION_REVISION_REVIEW_REQUIRED",
                "ALLOW_CONTROL_REQUIRED",
                "VALIDATION_PIPELINE_DEFERRED_TO_1_1_3",
            )
    finally:
        core.close()


def test_retired_latest_permission_stays_in_history_but_not_current_view(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        proposal = _create_proposal(core, project_id)
        boundary = core.business_boundaries.approve(
            project_id,
            proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint,
            reason="确认当前权限",
        )
        current = boundary.permission_intents[0]
        semantic_values = current.model_dump(
            include=set(PermissionIntentSemantic.model_fields),
            mode="python",
        )
        semantic_values["effective_state"] = PermissionIntentEffectiveState.RETIRED
        semantic = PermissionIntentSemantic(**semantic_values)
        retired = PermissionIntentRevision(
            **semantic.model_dump(mode="python"),
            intent_id=current.intent_id,
            project_id=current.project_id,
            revision=current.revision + 1,
            intent_hash=permission_intent_sha256(semantic.canonical_payload()),
            policy_epoch=current.policy_epoch + 1,
            approval=current.approval,
            created_at_us=current.created_at_us,
        )
        with core.uow_factory() as work:
            work.permission_intents.add_revision(retired)
            work.commit()

        current_view = core.business_boundaries.view(project_id)
        with core.uow_factory() as work:
            history = work.permission_intents.list_history(project_id)
        assert len(history) == 3
        assert retired in history
        assert all(item.intent_id != retired.intent_id for item in current_view.permission_intents)
        assert current_view.permission_statuses[0].stale_permission_count == 1
    finally:
        core.close()


def test_allow_control_uses_a_real_allow_and_covers_every_deny(tmp_path: Path) -> None:
    core, project_id = _core(tmp_path)
    try:
        proposal = _create_proposal(core, project_id)
        boundary = core.business_boundaries.approve(
            project_id,
            proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint,
            reason="确认当前权限",
        )
        action = boundary.actions[0]
        base = boundary.permission_intents[0]
        effect = base.protected_effect_ids[0]
        allow = base.model_copy(
            update={
                "intent_id": "pin_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "expectation": PermissionExpectation.ALLOW,
            }
        )
        covered_deny = base.model_copy(
            update={
                "intent_id": "pin_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "expectation": PermissionExpectation.DENY,
            }
        )
        uncovered_deny = covered_deny.model_copy(
            update={"protected_effect_ids": ("bef_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",)}
        )

        cases = (
            ((), False),
            ((allow,), True),
            ((covered_deny,), False),
            ((allow, covered_deny), True),
            ((allow, uncovered_deny), False),
        )
        for permissions, expected in cases:
            status = core.business_boundaries._permission_status(action, permissions)
            assert status.allow_control_available is expected
        assert allow.protected_effect_ids == (effect,)
    finally:
        core.close()


def test_multiple_actions_require_permission_semantics_for_every_current_action(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        first = _create_proposal(core, project_id)
        core.business_boundaries.approve(
            project_id,
            first.proposal_id,
            expected_fingerprint=first.proposal_fingerprint,
            reason="确认第一个动作",
        )
        second = core.business_boundaries.create_proposal(
            project_id,
            BoundaryProposalCommand(
                proposed_actions=(_second_action(),),
                provenance="本机用户补充第二个动作",
            ),
        ).proposal
        boundary = core.business_boundaries.approve(
            project_id,
            second.proposal_id,
            expected_fingerprint=second.proposal_fingerprint,
            reason="确认第二个动作",
        )
        status = core.product_status.get(project_id)
        permissions_area = next(item for item in status.areas if item.key == "permissions")

        assert len(boundary.actions) == 2
        assert sum(
            item.permission_semantics_confirmed
            for item in boundary.permission_statuses
        ) == 1
        assert permissions_area.status == "NEEDS_ATTENTION"
        assert permissions_area.route == "/permissions"
    finally:
        core.close()


def test_rejected_candidates_do_not_return_to_boundary_preview(tmp_path: Path) -> None:
    core, project_id = _core(tmp_path)
    try:
        understanding = core.application_understanding.get(project_id)
        understanding = core.application_understanding.add_manual_role(
            project_id,
            revision=understanding.revision,
            display_name="不适用角色",
        )
        role = understanding.role_candidates[0]
        understanding = core.application_understanding.decide_role(
            project_id,
            role.candidate_id,
            revision=understanding.revision,
            decision=CandidateDecision.REJECTED,
        )
        understanding = core.application_understanding.add_manual_action(
            project_id,
            revision=understanding.revision,
            display_name="不适用动作",
        )
        action = understanding.action_candidates[0]
        core.application_understanding.decide_action(
            project_id,
            action.candidate_id,
            revision=understanding.revision,
            decision=CandidateDecision.REJECTED,
        )

        preview = core.business_boundaries.preview_from_discovery(project_id)
        assert role.candidate_id not in {item.candidate_id for item in preview.candidates}
        assert action.candidate_id not in {item.candidate_id for item in preview.candidates}
    finally:
        core.close()
