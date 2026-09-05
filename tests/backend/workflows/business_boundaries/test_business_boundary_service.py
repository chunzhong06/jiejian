# 验证 Business Boundary Proposal 的原子批准、policy epoch、来源失效与 Actor TestIdentity。

from __future__ import annotations

from pathlib import Path

import pytest

from product.backend.composition import ApplicationCore
from product.backend.core.application_understanding import (
    ActionCandidate,
    ActionRiskHint,
    CandidateConfidence,
    CandidateDecision,
    CandidateEvidence,
    RoleCandidate,
)
from product.backend.core.boundary_proposal import (
    BoundaryProposalBundle,
    BoundarySourceSnapshot,
    ProposalCandidateKind,
    ProposalWriteMode,
    ProposedActionItem,
    ProposedActorItem,
    ProposedEffectItem,
    ProposedPermissionItem,
)
from product.backend.core.business_boundary import (
    ActorImplementationBinding,
    BusinessActionOperationKind,
    BusinessRevisionState,
    ImplementationBindingStatus,
    boundary_sha256,
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
from product.backend.workflows.business_boundaries import (
    BoundaryMaintenanceCommand,
    BoundaryProposalCommand,
)
from product.backend.workflows.business_boundaries.fingerprints import (
    legacy_candidate_source_snapshot,
)


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
    action=None,
    permissions=None,
):
    return core.business_boundaries.create_proposal(
        project_id,
        BoundaryProposalCommand(
            proposed_actors=_actors() if actors is None else actors,
            proposed_actions=(_action() if action is None else action,),
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


def _maintenance_command(draft, *, actors=None, actions=None, permissions=None):
    return BoundaryMaintenanceCommand(
        expected_boundary_state_fingerprint=draft.boundary_state_fingerprint,
        actors=draft.actors if actors is None else actors,
        actions=draft.actions if actions is None else actions,
        permissions=draft.permissions if permissions is None else permissions,
        provenance="本机用户维护业务边界",
    )


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
        assert "validation_contract_complete" not in type(boundary.permission_statuses[0]).model_fields
        assert boundary.permission_statuses[0].reason_codes == ()

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


def test_v2_proposal_without_candidates_ignores_unrelated_revision_change(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        proposal = _create_proposal(core, project_id)
        understanding = core.application_understanding.get(project_id)
        core.application_understanding.add_manual_role(
            project_id,
            revision=understanding.revision,
            display_name="后新增角色",
        )
        boundary = core.business_boundaries.approve(
            project_id,
            proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint,
            reason="无引用候选不受无关变化影响",
        )
        assert len(boundary.actors) == 2
    finally:
        core.close()


def _detected_candidates() -> tuple[RoleCandidate, ActionCandidate]:
    evidence = CandidateEvidence(
        relative_path="app/export.py",
        line_start=10,
        line_end=18,
        symbol="export_project",
        detector="python-structure",
        content_sha256="a" * 64,
    )
    return (
        RoleCandidate(
            candidate_id="role_" + "a" * 32,
            canonical_key="project_owner",
            display_name="项目负责人",
            confidence=CandidateConfidence.HIGH,
            evidence=(evidence,),
        ),
        ActionCandidate(
            candidate_id="action_" + "b" * 32,
            canonical_key="export_project",
            display_name="导出项目",
            confidence=CandidateConfidence.HIGH,
            risk_hint=ActionRiskHint.WRITE,
            evidence=(evidence,),
        ),
    )


def _replace_understanding(core: ApplicationCore, project_id: str, **updates):
    with core.uow_factory() as work:
        current = work.application_understanding.get(project_id)
        assert current is not None
        changed = current.model_copy(update=updates)
        work.application_understanding.replace(changed)
        work.commit()
    return changed


def test_v2_candidate_scoped_approval_and_live_inspection(tmp_path: Path) -> None:
    core, project_id = _core(tmp_path)
    try:
        role, action_candidate = _detected_candidates()
        understanding = core.application_understanding.get(project_id)
        understanding = _replace_understanding(
            core,
            project_id,
            source_analysis_authorized=True,
            source_analysis_authorized_at_us=2,
            source_fingerprint="b" * 64,
            analysis_completed_at_us=3,
            role_candidates=(role,),
            action_candidates=(action_candidate,),
            revision=understanding.revision + 1,
            updated_at_us=max(understanding.updated_at_us, 3),
        )
        actors = _actors()
        actors = (
            actors[0].model_copy(update={"source_candidate_ids": (role.candidate_id,)}),
            actors[1],
        )
        action = _action().model_copy(
            update={"source_candidate_ids": (action_candidate.candidate_id,)}
        )
        proposal = _create_proposal(core, project_id, actors=actors, action=action)
        assert proposal.source_snapshot.basis_version == 2

        # 全局源码事实变化但引用 Candidate 未变，v2 Proposal 仍可批准。
        understanding = _replace_understanding(
            core,
            project_id,
            source_fingerprint="c" * 64,
            revision=understanding.revision + 1,
            updated_at_us=understanding.updated_at_us + 1,
        )
        boundary = core.business_boundaries.approve(
            project_id,
            proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint,
            reason="确认精确实现来源",
        )
        owner = next(item for item in boundary.actors if item.display_name == "项目负责人")
        actor_inspection = next(
            item for item in boundary.actor_bindings if item.actor_id == owner.actor_id
        )
        assert actor_inspection.status is ImplementationBindingStatus.CURRENT
        assert boundary.action_bindings[0].status is ImplementationBindingStatus.CURRENT
        with core.uow_factory() as work:
            binding = work.business_boundaries.action_binding(
                boundary.actions[0].action_id, boundary.actions[0].revision
            )
        assert binding is not None
        assert binding.basis_version == 2
        assert binding.source_proposal_id == proposal.proposal_id
        assert binding.confirmed_at_us == binding.updated_at_us
        assert actor_inspection.source_proposal_id == proposal.proposal_id
        assert actor_inspection.confirmed_at_us == binding.confirmed_at_us
        assert "status" not in type(binding).model_fields

        # 批准后的全局 source 继续变化不影响 v2；明确 REJECTED 才实时 stale。
        understanding = _replace_understanding(
            core,
            project_id,
            source_fingerprint="d" * 64,
            revision=understanding.revision + 1,
            updated_at_us=understanding.updated_at_us + 1,
        )
        assert core.business_boundaries.view(project_id).action_bindings[0].status is ImplementationBindingStatus.CURRENT
        core.application_understanding.decide_action(
            project_id,
            action_candidate.candidate_id,
            revision=understanding.revision,
            decision=CandidateDecision.REJECTED,
        )
        stale = core.business_boundaries.view(project_id).action_bindings[0]
        assert stale.status is ImplementationBindingStatus.STALE
        assert stale.reason_codes == ("CANDIDATE_REJECTED",)
    finally:
        core.close()


def test_v1_source_snapshot_keeps_global_strict_validation(tmp_path: Path) -> None:
    core, project_id = _core(tmp_path)
    try:
        role, _ = _detected_candidates()
        understanding = core.application_understanding.get(project_id).model_copy(
            update={
                "source_analysis_authorized": True,
                "source_analysis_authorized_at_us": 2,
                "source_fingerprint": "e" * 64,
                "analysis_completed_at_us": 3,
                "role_candidates": (role,),
                "revision": 1,
                "updated_at_us": 3,
            }
        )
        legacy = BoundarySourceSnapshot(
            application_understanding_revision=understanding.revision,
            source_fingerprint=understanding.source_fingerprint,
            candidates=(
                legacy_candidate_source_snapshot(ProposalCandidateKind.ROLE, role),
            ),
        )
        assert legacy.basis_version == 1
        core.business_boundaries._validate_source_snapshot(legacy, understanding)

        changed = understanding.model_copy(
            update={"source_fingerprint": "f" * 64, "revision": 2}
        )
        with pytest.raises(JiejianError) as error:
            core.business_boundaries._validate_source_snapshot(legacy, changed)
        assert error.value.code == ErrorCode.BOUNDARY_PROPOSAL_SOURCE_STALE.value
    finally:
        core.close()


def test_persisted_v1_proposal_without_basis_version_keeps_legacy_fingerprint(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        current = _create_proposal(core, project_id)
        legacy_source = BoundarySourceSnapshot(
            application_understanding_revision=(
                current.source_snapshot.application_understanding_revision
            ),
            source_fingerprint=current.source_snapshot.source_fingerprint,
            candidates=current.source_snapshot.candidates,
        )
        proposal_id = "bpr_" + "e" * 32
        fingerprint_payload = {
            "proposal_id": proposal_id,
            "project_id": project_id,
            "source_snapshot": legacy_source.model_dump(mode="json"),
            "proposed_actors": [
                item.model_dump(mode="json") for item in current.proposed_actors
            ],
            "proposed_actions": [
                item.model_dump(mode="json") for item in current.proposed_actions
            ],
            "proposed_permissions": [
                item.model_dump(mode="json") for item in current.proposed_permissions
            ],
            "unresolved_questions": list(current.unresolved_questions),
            "provenance": current.provenance,
            "created_at_us": current.created_at_us,
        }
        fingerprint_payload["source_snapshot"].pop("basis_version")
        legacy = BoundaryProposalBundle(
            proposal_id=proposal_id,
            project_id=project_id,
            source_snapshot=legacy_source,
            proposed_actors=current.proposed_actors,
            proposed_actions=current.proposed_actions,
            proposed_permissions=current.proposed_permissions,
            unresolved_questions=current.unresolved_questions,
            provenance=current.provenance,
            proposal_fingerprint=boundary_sha256(fingerprint_payload),
            created_at_us=current.created_at_us,
        )
        with core.uow_factory() as work:
            work.business_boundaries.add_proposal(legacy)
            work.commit()

        restored = core.business_boundaries.proposal(project_id, proposal_id).proposal
        assert restored.source_snapshot.basis_version == 1
        assert restored.proposal_fingerprint == legacy.proposal_fingerprint
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
        status = core.workspace.get(project_id)
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


def test_maintenance_draft_is_stable_and_guards_complete_current_state(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        initial = _create_proposal(core, project_id)
        core.business_boundaries.approve(
            project_id,
            initial.proposal_id,
            expected_fingerprint=initial.proposal_fingerprint,
            reason="确认首次业务边界",
        )
        first = core.business_boundaries.maintenance_draft(project_id)
        second = core.business_boundaries.maintenance_draft(project_id)
        assert first == second
        assert len(first.actors) == 2
        assert len(first.actions) == 1
        assert len(first.permissions) == 2
        assert all(item.actor_id is not None for item in first.actors)
        assert all(item.action_id is not None for item in first.actions)
        assert all(item.intent_id is not None for item in first.permissions)

        with pytest.raises(JiejianError) as incomplete:
            core.business_boundaries.create_maintenance_proposal(
                project_id,
                _maintenance_command(first, actors=first.actors[1:]),
            )
        assert incomplete.value.code == ErrorCode.BOUNDARY_MAINTENANCE_INCOMPLETE.value

        with pytest.raises(JiejianError) as stale:
            core.business_boundaries.create_maintenance_proposal(
                project_id,
                _maintenance_command(first).model_copy(
                    update={"expected_boundary_state_fingerprint": "f" * 64}
                ),
            )
        assert stale.value.code == ErrorCode.BOUNDARY_REVISION_CONFLICT.value

        duplicate_actor = first.actors[0].model_copy(
            update={"item_id": "pactr_9999999999999999"}
        )
        with pytest.raises(JiejianError) as duplicate:
            core.business_boundaries.create_maintenance_proposal(
                project_id,
                _maintenance_command(
                    first,
                    actors=(*first.actors, duplicate_actor),
                ),
            )
        assert duplicate.value.code == ErrorCode.BOUNDARY_MAINTENANCE_INCOMPLETE.value

        changed_actor = first.actors[0].model_copy(
            update={"description": first.actors[0].description + "，并复核交付"}
        )
        created = core.business_boundaries.create_maintenance_proposal(
            project_id,
            _maintenance_command(
                first,
                actors=(changed_actor, *first.actors[1:]),
            ),
        )
        actor_item = next(
            item
            for item in created.proposal.proposed_actors
            if item.item_id == changed_actor.item_id
        )
        assert actor_item.write_mode is ProposalWriteMode.APPEND_REVISION
        assert created.change_summary is not None
        assert changed_actor.display_name in created.change_summary.business_revision_updates

        with pytest.raises(JiejianError) as pending:
            core.business_boundaries.create_maintenance_proposal(
                project_id,
                _maintenance_command(first),
            )
        assert pending.value.code == ErrorCode.BOUNDARY_PROPOSAL_PENDING.value
        assert pending.value.to_dict()["details"]["proposal_id"] == created.proposal.proposal_id
        assert (
            core.business_boundaries.maintenance_draft(
                project_id
            ).boundary_state_fingerprint
            == first.boundary_state_fingerprint
        )

        with pytest.raises(JiejianError) as initial_again:
            core.business_boundaries.create_initial_proposal(
                project_id,
                BoundaryProposalCommand(provenance="错误的第二次首次建立"),
            )
        assert initial_again.value.code == ErrorCode.BOUNDARY_MAINTENANCE_REQUIRED.value
    finally:
        core.close()


def test_action_revision_carries_permissions_and_advances_epoch_once(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        initial = _create_proposal(
            core,
            project_id,
            permissions=(
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
                _permission(
                    "pperm_3333333333333333",
                    "pactr_2222222222222222",
                    PermissionExpectation.DENY,
                ),
            ),
        )
        before = core.business_boundaries.approve(
            project_id,
            initial.proposal_id,
            expected_fingerprint=initial.proposal_fingerprint,
            reason="确认首次业务边界",
        )
        old_effect_id = before.actions[0].effect_catalog[0].effect_id
        draft = core.business_boundaries.maintenance_draft(project_id)
        action = draft.actions[0].model_copy(
            update={"description": draft.actions[0].description + "，包含维护清单"}
        )
        created = core.business_boundaries.create_maintenance_proposal(
            project_id,
            _maintenance_command(draft, actions=(action,)),
        )

        assert created.proposal.proposed_actions[0].write_mode is ProposalWriteMode.APPEND_REVISION
        assert created.proposal.proposed_actions[0].effect_catalog[0].effect_id == old_effect_id
        assert {
            item.write_mode for item in created.proposal.proposed_permissions
        } == {ProposalWriteMode.APPEND_REVISION}
        assert created.change_summary is not None
        assert len(created.change_summary.permission_carry_forwards) == 3
        assert "CARRY_FORWARD_PERMISSION" in created.change_summary.change_codes

        after = core.business_boundaries.approve(
            project_id,
            created.proposal.proposal_id,
            expected_fingerprint=created.proposal.proposal_fingerprint,
            reason="确认动作 revision 与权限沿用",
        )
        assert after.policy_epoch == before.policy_epoch + 1
        assert after.actions[0].revision == 2
        assert after.actions[0].effect_catalog[0].effect_id == old_effect_id
        assert {item.revision for item in after.permission_intents} == {2}
        with core.uow_factory() as work:
            assert len(work.business_boundaries.list_action_revisions(project_id)) == 2
            assert {item.revision for item in work.permission_intents.list_latest(project_id)} == {2}
    finally:
        core.close()


def test_pure_rebind_replaces_binding_without_business_or_policy_revision(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        initial = _create_proposal(core, project_id)
        before = core.business_boundaries.approve(
            project_id,
            initial.proposal_id,
            expected_fingerprint=initial.proposal_fingerprint,
            reason="确认首次业务边界",
        )
        boundary_only_fingerprint = (
            core.business_boundaries.maintenance_draft(
                project_id
            ).boundary_state_fingerprint
        )
        role, action_candidate = _detected_candidates()
        understanding = core.application_understanding.get(project_id)
        _replace_understanding(
            core,
            project_id,
            source_analysis_authorized=True,
            source_analysis_authorized_at_us=2,
            source_fingerprint="e" * 64,
            analysis_completed_at_us=3,
            role_candidates=(role,),
            action_candidates=(action_candidate,),
            revision=understanding.revision + 1,
            updated_at_us=max(understanding.updated_at_us, 3),
        )
        draft = core.business_boundaries.maintenance_draft(project_id)
        assert draft.boundary_state_fingerprint == boundary_only_fingerprint
        actor = next(item for item in draft.actors if item.display_name == "项目负责人")
        rebound = actor.model_copy(update={"source_candidate_ids": (role.candidate_id,)})
        actors = tuple(rebound if item.item_id == actor.item_id else item for item in draft.actors)
        created = core.business_boundaries.create_maintenance_proposal(
            project_id,
            _maintenance_command(draft, actors=actors),
        )

        assert {item.write_mode for item in created.proposal.proposed_actors} == {
            ProposalWriteMode.REFERENCE
        }
        assert {item.write_mode for item in created.proposal.proposed_permissions} == {
            ProposalWriteMode.REFERENCE
        }
        assert created.change_summary is not None
        assert created.change_summary.implementation_rebinds == (actor.display_name,)

        latest_understanding = core.application_understanding.get(project_id)
        core.application_understanding.decide_role(
            project_id,
            role.candidate_id,
            revision=latest_understanding.revision,
            decision=CandidateDecision.CONFIRMED,
        )

        after = core.business_boundaries.approve(
            project_id,
            created.proposal.proposal_id,
            expected_fingerprint=created.proposal.proposal_fingerprint,
            reason="确认当前实现来源",
        )
        assert after.policy_epoch == before.policy_epoch
        assert [(item.actor_id, item.revision) for item in after.actors] == [
            (item.actor_id, item.revision) for item in before.actors
        ]
        assert [(item.intent_id, item.revision) for item in after.permission_intents] == [
            (item.intent_id, item.revision) for item in before.permission_intents
        ]
        with core.uow_factory() as work:
            binding = work.business_boundaries.actor_binding(
                rebound.actor_id,
                rebound.expected_current_revision,
            )
        assert binding is not None
        assert binding.basis_version == 2
        assert binding.role_candidate_ids == (role.candidate_id,)
        assert binding.source_proposal_id == created.proposal.proposal_id
    finally:
        core.close()


def test_maintenance_proposal_rejects_changed_selected_candidate_evidence(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        initial = _create_proposal(core, project_id)
        before = core.business_boundaries.approve(
            project_id,
            initial.proposal_id,
            expected_fingerprint=initial.proposal_fingerprint,
            reason="确认首次业务边界",
        )
        role, action_candidate = _detected_candidates()
        understanding = core.application_understanding.get(project_id)
        understanding = _replace_understanding(
            core,
            project_id,
            source_analysis_authorized=True,
            source_analysis_authorized_at_us=2,
            source_fingerprint="e" * 64,
            analysis_completed_at_us=3,
            role_candidates=(role,),
            action_candidates=(action_candidate,),
            revision=understanding.revision + 1,
            updated_at_us=max(understanding.updated_at_us, 3),
        )
        draft = core.business_boundaries.maintenance_draft(project_id)
        actor = next(item for item in draft.actors if item.display_name == "项目负责人")
        actors = tuple(
            item.model_copy(update={"source_candidate_ids": (role.candidate_id,)})
            if item.item_id == actor.item_id
            else item
            for item in draft.actors
        )
        created = core.business_boundaries.create_maintenance_proposal(
            project_id,
            _maintenance_command(draft, actors=actors),
        )

        changed_evidence = role.evidence[0].model_copy(
            update={"content_sha256": "f" * 64}
        )
        _replace_understanding(
            core,
            project_id,
            role_candidates=(
                role.model_copy(update={"evidence": (changed_evidence,)}),
            ),
            revision=understanding.revision + 1,
            updated_at_us=understanding.updated_at_us + 1,
        )

        with pytest.raises(JiejianError) as stale:
            core.business_boundaries.approve(
                project_id,
                created.proposal.proposal_id,
                expected_fingerprint=created.proposal.proposal_fingerprint,
                reason="证据已变更时不得批准",
            )
        assert stale.value.code == ErrorCode.BOUNDARY_PROPOSAL_SOURCE_STALE.value
        after = core.business_boundaries.view(project_id)
        assert after.policy_epoch == before.policy_epoch
        assert [(item.actor_id, item.revision) for item in after.actors] == [
            (item.actor_id, item.revision) for item in before.actors
        ]
        assert [(item.intent_id, item.revision) for item in after.permission_intents] == [
            (item.intent_id, item.revision) for item in before.permission_intents
        ]
    finally:
        core.close()


def test_effect_change_gets_new_identity_and_missing_mapping_is_rejected(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        initial = _create_proposal(core, project_id)
        before = core.business_boundaries.approve(
            project_id,
            initial.proposal_id,
            expected_fingerprint=initial.proposal_fingerprint,
            reason="确认首次业务边界",
        )
        old_effect_id = before.actions[0].effect_catalog[0].effect_id
        draft = core.business_boundaries.maintenance_draft(project_id)
        effect = draft.actions[0].effects[0]
        changed_effect = effect.model_copy(
            update={"business_label": effect.business_label + "（复核）"}
        )
        changed_action = draft.actions[0].model_copy(update={"effects": (changed_effect,)})
        created = core.business_boundaries.create_maintenance_proposal(
            project_id,
            _maintenance_command(draft, actions=(changed_action,)),
        )
        assert created.proposal.proposed_actions[0].effect_catalog[0].effect_id is None
        assert created.change_summary is not None
        assert created.change_summary.permission_carry_forwards == ()
        assert len(created.change_summary.permission_updates) == 2
        after = core.business_boundaries.approve(
            project_id,
            created.proposal.proposal_id,
            expected_fingerprint=created.proposal.proposal_fingerprint,
            reason="确认新的业务结果定义",
        )
        assert after.actions[0].effect_catalog[0].effect_id != old_effect_id
        assert {
            item.protected_effect_ids for item in after.permission_intents
        } == {(after.actions[0].effect_catalog[0].effect_id,)}
    finally:
        core.close()

    mapping_root = tmp_path / "mapping"
    mapping_root.mkdir()
    core, project_id = _core(mapping_root)
    try:
        initial = _create_proposal(core, project_id)
        core.business_boundaries.approve(
            project_id,
            initial.proposal_id,
            expected_fingerprint=initial.proposal_fingerprint,
            reason="确认首次业务边界",
        )
        draft = core.business_boundaries.maintenance_draft(project_id)
        replacement = draft.actions[0].effects[0].model_copy(
            update={
                "item_id": "peff_9999999999999999",
                "effect_id": None,
                "business_label": "替代业务结果",
            }
        )
        action = draft.actions[0].model_copy(update={"effects": (replacement,)})
        with pytest.raises(JiejianError) as mapping:
            core.business_boundaries.create_maintenance_proposal(
                project_id,
                _maintenance_command(draft, actions=(action,)),
            )
        assert mapping.value.code == ErrorCode.BOUNDARY_EFFECT_MAPPING_REQUIRED.value
        details = mapping.value.to_dict()["details"]
        assert details["intent_id"] is not None
        assert details["missing_effect_item_ids"] == [
            draft.permissions[0].protected_effect_item_ids[0]
        ] or details["missing_effect_item_ids"] == (
            draft.permissions[0].protected_effect_item_ids[0],
        )
    finally:
        core.close()


def test_retirement_requires_explicit_permission_closure(tmp_path: Path) -> None:
    core, project_id = _core(tmp_path)
    try:
        initial = _create_proposal(core, project_id)
        before = core.business_boundaries.approve(
            project_id,
            initial.proposal_id,
            expected_fingerprint=initial.proposal_fingerprint,
            reason="确认首次业务边界",
        )
        draft = core.business_boundaries.maintenance_draft(project_id)
        retired_actor = draft.actors[0].model_copy(
            update={"effective_state": BusinessRevisionState.RETIRED}
        )
        with pytest.raises(JiejianError) as actor_unclosed:
            core.business_boundaries.create_maintenance_proposal(
                project_id,
                _maintenance_command(
                    draft,
                    actors=(retired_actor, *draft.actors[1:]),
                ),
            )
        assert actor_unclosed.value.code == ErrorCode.BOUNDARY_MAINTENANCE_INCOMPLETE.value
        retired_action = draft.actions[0].model_copy(
            update={"effective_state": BusinessRevisionState.RETIRED}
        )
        with pytest.raises(JiejianError) as unclosed:
            core.business_boundaries.create_maintenance_proposal(
                project_id,
                _maintenance_command(draft, actions=(retired_action,)),
            )
        assert unclosed.value.code == ErrorCode.BOUNDARY_MAINTENANCE_INCOMPLETE.value

        retired_permissions = tuple(
            item.model_copy(
                update={"effective_state": PermissionIntentEffectiveState.RETIRED}
            )
            for item in draft.permissions
        )
        created = core.business_boundaries.create_maintenance_proposal(
            project_id,
            _maintenance_command(
                draft,
                actions=(retired_action,),
                permissions=retired_permissions,
            ),
        )
        assert created.change_summary is not None
        assert created.change_summary.retirements == (retired_action.display_name,)
        assert len(created.change_summary.permission_retirements) == 2
        after = core.business_boundaries.approve(
            project_id,
            created.proposal.proposal_id,
            expected_fingerprint=created.proposal.proposal_fingerprint,
            reason="确认退休动作并闭合权限",
        )
        assert after.actions == ()
        assert after.permission_intents == ()
        assert after.policy_epoch == before.policy_epoch + 1
        with core.uow_factory() as work:
            latest = work.permission_intents.list_latest(project_id)
            history = work.business_boundaries.list_action_revisions(project_id)
        assert {item.effective_state for item in latest} == {
            PermissionIntentEffectiveState.RETIRED
        }
        assert [item.effective_state for item in history] == [
            BusinessRevisionState.ACTIVE,
            BusinessRevisionState.RETIRED,
        ]
    finally:
        core.close()


def test_explicit_review_upgrades_legacy_binding_to_v2_without_revision_changes(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        initial = _create_proposal(core, project_id)
        before = core.business_boundaries.approve(
            project_id,
            initial.proposal_id,
            expected_fingerprint=initial.proposal_fingerprint,
            reason="确认首次业务边界",
        )
        actor = before.actors[0]
        with core.uow_factory() as work:
            current = work.business_boundaries.actor_binding(
                actor.actor_id,
                actor.revision,
            )
            assert current is not None
            legacy_payload = {
                "actor_id": actor.actor_id,
                "actor_revision": actor.revision,
                "understanding_revision": current.understanding_revision,
                "source_fingerprint": current.source_fingerprint,
                "role_candidate_ids": list(current.role_candidate_ids),
            }
            work.business_boundaries.replace_actor_binding(
                ActorImplementationBinding(
                    actor_id=actor.actor_id,
                    actor_revision=actor.revision,
                    understanding_revision=current.understanding_revision,
                    source_fingerprint=current.source_fingerprint,
                    basis_version=1,
                    role_candidate_ids=current.role_candidate_ids,
                    binding_fingerprint=boundary_sha256(legacy_payload),
                    updated_at_us=current.updated_at_us,
                )
            )
            work.commit()

        draft = core.business_boundaries.maintenance_draft(project_id)
        created = core.business_boundaries.create_maintenance_proposal(
            project_id,
            _maintenance_command(draft),
        )
        assert created.change_summary is not None
        assert actor.display_name in created.change_summary.implementation_rebinds
        after = core.business_boundaries.approve(
            project_id,
            created.proposal.proposal_id,
            expected_fingerprint=created.proposal.proposal_fingerprint,
            reason="重新确认旧实现来源",
        )
        assert after.policy_epoch == before.policy_epoch
        assert [(item.actor_id, item.revision) for item in after.actors] == [
            (item.actor_id, item.revision) for item in before.actors
        ]
        with core.uow_factory() as work:
            upgraded = work.business_boundaries.actor_binding(
                actor.actor_id,
                actor.revision,
            )
        assert upgraded is not None
        assert upgraded.basis_version == 2
        assert upgraded.source_proposal_id == created.proposal.proposal_id
    finally:
        core.close()


def test_unreferenced_actor_revision_keeps_epoch_and_new_permission_advances_once(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        initial = _create_proposal(
            core,
            project_id,
            permissions=(
                _permission(
                    "pperm_1111111111111111",
                    "pactr_1111111111111111",
                    PermissionExpectation.ALLOW,
                ),
            ),
        )
        before = core.business_boundaries.approve(
            project_id,
            initial.proposal_id,
            expected_fingerprint=initial.proposal_fingerprint,
            reason="确认首次业务边界",
        )
        draft = core.business_boundaries.maintenance_draft(project_id)
        member = next(item for item in draft.actors if item.display_name == "普通协作成员")
        changed_member = member.model_copy(
            update={"description": member.description + "，负责复核"}
        )
        actors = tuple(
            changed_member if item.item_id == member.item_id else item
            for item in draft.actors
        )
        actor_proposal = core.business_boundaries.create_maintenance_proposal(
            project_id,
            _maintenance_command(draft, actors=actors),
        )
        assert {
            item.write_mode for item in actor_proposal.proposal.proposed_permissions
        } == {ProposalWriteMode.REFERENCE}
        actor_updated = core.business_boundaries.approve(
            project_id,
            actor_proposal.proposal.proposal_id,
            expected_fingerprint=actor_proposal.proposal.proposal_fingerprint,
            reason="确认未被权限引用的主体说明",
        )
        assert actor_updated.policy_epoch == before.policy_epoch
        assert next(
            item for item in actor_updated.actors if item.actor_id == member.actor_id
        ).revision == 2

        current = core.business_boundaries.maintenance_draft(project_id)
        current_member = next(
            item for item in current.actors if item.actor_id == member.actor_id
        )
        template = current.permissions[0]
        new_permission = template.model_copy(
            update={
                "item_id": "pperm_9999999999999999",
                "intent_id": None,
                "expected_current_revision": None,
                "subject_actor_item_id": current_member.item_id,
                "relation": PermissionIntentRelation.OTHER_ROLE,
                "expectation": PermissionExpectation.DENY,
            }
        )
        permission_proposal = core.business_boundaries.create_maintenance_proposal(
            project_id,
            _maintenance_command(
                current,
                permissions=(*current.permissions, new_permission),
            ),
        )
        assert next(
            item
            for item in permission_proposal.proposal.proposed_permissions
            if item.item_id == new_permission.item_id
        ).write_mode is ProposalWriteMode.CREATE
        assert permission_proposal.change_summary is not None
        assert len(permission_proposal.change_summary.permission_updates) == 1
        after = core.business_boundaries.approve(
            project_id,
            permission_proposal.proposal.proposal_id,
            expected_fingerprint=permission_proposal.proposal.proposal_fingerprint,
            reason="确认新增权限",
        )
        assert after.policy_epoch == before.policy_epoch + 1
        assert len(after.permission_intents) == 2
    finally:
        core.close()
