# 验证动作级 Workspace 唯一主任务优先级、实时实现检查与无 Binding 允许状态。

from pathlib import Path
from types import SimpleNamespace

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
    ProposalWriteMode,
    ProposedActionItem,
    ProposedActorItem,
    ProposedEffectItem,
    ProposedPermissionItem,
)
from product.backend.core.business_boundary import (
    BusinessActionOperationKind,
    BusinessRevisionState,
    ImplementationBindingStatus,
)
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState,
    PermissionIntentRelation,
)
from product.backend.core.verification.permissions import (
    PermissionExpectation,
    SecurityEffectKind,
)
from product.backend.workflows.business_boundaries import BoundaryProposalCommand
from product.backend.workflows.business_boundaries.inspection import (
    inspect_action_binding,
    inspect_actor_binding,
)


pytestmark = [pytest.mark.database, pytest.mark.essential]


def _core(tmp_path: Path) -> tuple[ApplicationCore, str]:
    source = tmp_path / "source"
    source.mkdir()
    core = ApplicationCore(tmp_path / "var")
    connected = core.application_understanding.connect(
        str(source),
        project_name="动作工作区测试",
    )
    return core, connected.project.project_id


def _replace_understanding(core: ApplicationCore, project_id: str, **updates):
    with core.uow_factory() as work:
        current = work.application_understanding.get(project_id)
        assert current is not None
        changed = current.model_copy(update=updates)
        work.application_understanding.replace(changed)
        work.commit()
    return changed


def _ready_understanding(
    core: ApplicationCore,
    project_id: str,
    *,
    role_candidates=(),
    action_candidates=(),
):
    current = core.application_understanding.get(project_id)
    return _replace_understanding(
        core,
        project_id,
        confirmed_endpoint="http://127.0.0.1:8080",
        endpoint_source_fingerprint="a" * 64,
        endpoint_confirmed_at_us=1,
        endpoint_last_checked_at_us=1,
        endpoint_reachable=True,
        source_analysis_authorized=True,
        source_analysis_authorized_at_us=2,
        source_fingerprint="b" * 64,
        analysis_completed_at_us=3,
        role_candidates=role_candidates,
        action_candidates=action_candidates,
        revision=current.revision + 1,
        updated_at_us=max(current.updated_at_us, 3),
    )


def _proposal(
    core: ApplicationCore,
    project_id: str,
    *,
    actor_source_ids=(),
    action_source_ids=(),
    expectation=PermissionExpectation.ALLOW,
    relation=PermissionIntentRelation.OWNS,
):
    actor_id = "pactr_1111111111111111"
    action_id = "pactn_1111111111111111"
    effect_id = "peff_1111111111111111"
    return core.business_boundaries.create_proposal(
        project_id,
        BoundaryProposalCommand(
            proposed_actors=(
                ProposedActorItem(
                    item_id=actor_id,
                    write_mode=ProposalWriteMode.CREATE,
                    display_name="项目负责人",
                    description="负责项目交付",
                    effective_state=BusinessRevisionState.ACTIVE,
                    source_candidate_ids=actor_source_ids,
                ),
            ),
            proposed_actions=(
                ProposedActionItem(
                    item_id=action_id,
                    write_mode=ProposalWriteMode.CREATE,
                    display_name="导出完整项目交付包",
                    description="形成完整项目交付包",
                    primary_resource_concept="项目交付空间",
                    operation_kind=BusinessActionOperationKind.EXPORT,
                    state_changing=True,
                    effect_catalog=(
                        ProposedEffectItem(
                            item_id=effect_id,
                            business_label="完整项目交付包真实形成",
                            effect_kind=SecurityEffectKind.OBJECT_CREATION,
                            resource_concept="项目交付包",
                            description="交付包已经形成",
                        ),
                    ),
                    effective_state=BusinessRevisionState.ACTIVE,
                    source_candidate_ids=action_source_ids,
                ),
            ),
            proposed_permissions=(
                ProposedPermissionItem(
                    item_id="pperm_1111111111111111",
                    write_mode=ProposalWriteMode.CREATE,
                    effective_state=PermissionIntentEffectiveState.ACTIVE,
                    subject_actor_item_id=actor_id,
                    business_action_item_id=action_id,
                    resource_owner_actor_item_id=actor_id,
                    relation=relation,
                    expectation=expectation,
                    protected_effect_item_ids=(effect_id,),
                ),
            ),
            provenance="本机用户提交动作工作区测试边界",
        ),
    ).proposal


def _candidate_evidence() -> CandidateEvidence:
    return CandidateEvidence(
        relative_path="app/export.py",
        line_start=10,
        line_end=18,
        symbol="export_project",
        detector="python-structure",
        content_sha256="d" * 64,
    )


def _role_candidate() -> RoleCandidate:
    return RoleCandidate(
        candidate_id="role_" + "e" * 32,
        canonical_key="project_owner",
        display_name="项目负责人",
        confidence=CandidateConfidence.HIGH,
        evidence=(_candidate_evidence(),),
    )


def _action_candidate() -> ActionCandidate:
    return ActionCandidate(
        candidate_id="action_" + "c" * 32,
        canonical_key="export_project",
        display_name="导出项目",
        confidence=CandidateConfidence.HIGH,
        risk_hint=ActionRiskHint.WRITE,
        evidence=(_candidate_evidence(),),
    )


def test_workspace_primary_task_follows_single_fixed_priority(tmp_path: Path) -> None:
    core, project_id = _core(tmp_path)
    try:
        first = core.workspace.get(project_id)
        assert first.primary_task is not None
        assert first.primary_task.task_kind == "CONFIRM_APPLICATION_ENDPOINT"
        assert core.workspace.get(project_id).primary_task == first.primary_task

        current = core.application_understanding.get(project_id)
        current = _replace_understanding(
            core,
            project_id,
            confirmed_endpoint="http://127.0.0.1:8080",
            endpoint_source_fingerprint="a" * 64,
            endpoint_confirmed_at_us=1,
            endpoint_last_checked_at_us=1,
            endpoint_reachable=True,
            revision=current.revision + 1,
            updated_at_us=max(current.updated_at_us, 1),
        )
        assert core.workspace.get(project_id).primary_task.task_kind == (
            "AUTHORIZE_SOURCE_ANALYSIS"
        )

        current = _replace_understanding(
            core,
            project_id,
            source_analysis_authorized=True,
            source_analysis_authorized_at_us=2,
            revision=current.revision + 1,
            updated_at_us=max(current.updated_at_us, 2),
        )
        assert core.workspace.get(project_id).primary_task.task_kind == (
            "RUN_SOURCE_ANALYSIS"
        )

        _replace_understanding(
            core,
            project_id,
            source_fingerprint="b" * 64,
            analysis_completed_at_us=3,
            revision=current.revision + 1,
            updated_at_us=max(current.updated_at_us, 3),
        )
        assert core.workspace.get(project_id).primary_task.task_kind == (
            "ESTABLISH_BUSINESS_BOUNDARY"
        )

        proposal = _proposal(core, project_id)
        assert core.workspace.get(project_id).primary_task.task_kind == (
            "REVIEW_BOUNDARY_PROPOSAL"
        )
        core.business_boundaries.approve(
            project_id,
            proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint,
            reason="确认动作工作区测试边界",
        )
        workspace = core.workspace.get(project_id)
        assert workspace.primary_task is not None
        assert workspace.primary_task.task_kind == "REVIEW_ACTOR_IMPLEMENTATION"
        assert workspace.actors[0].implementation.binding_exists is True
        assert workspace.actors[0].implementation.status is ImplementationBindingStatus.MISSING
        assert workspace.actions[0].actor_implementation_issue_count == 1
        assert workspace.areas[1].status == "NEEDS_ATTENTION"
    finally:
        core.close()


def test_existing_stale_action_binding_becomes_rebind_task(tmp_path: Path) -> None:
    core, project_id = _core(tmp_path)
    try:
        role = _role_candidate()
        candidate = _action_candidate()
        _ready_understanding(
            core,
            project_id,
            role_candidates=(role,),
            action_candidates=(candidate,),
        )
        proposal = _proposal(
            core,
            project_id,
            actor_source_ids=(role.candidate_id,),
            action_source_ids=(candidate.candidate_id,),
        )
        core.business_boundaries.approve(
            project_id,
            proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint,
            reason="确认动作及当前代码实现",
        )
        current = core.workspace.get(project_id)
        assert current.primary_task is None
        assert current.actions[0].implementation.status is ImplementationBindingStatus.CURRENT

        understanding = core.application_understanding.get(project_id)
        core.application_understanding.decide_action(
            project_id,
            candidate.candidate_id,
            revision=understanding.revision,
            decision=CandidateDecision.REJECTED,
        )
        stale = core.workspace.get(project_id)
        assert stale.primary_task is not None
        assert stale.primary_task.task_kind == "REVIEW_ACTION_IMPLEMENTATION"
        assert stale.primary_task.business_action_id == stale.actions[0].action_id
        assert stale.actions[0].implementation.status is ImplementationBindingStatus.STALE
        assert stale.areas[1].status == "NEEDS_ATTENTION"
    finally:
        core.close()


def test_never_bound_manual_business_items_do_not_force_rebind_task(
    tmp_path: Path,
) -> None:
    core, project_id = _core(tmp_path)
    try:
        understanding = _ready_understanding(core, project_id)
        proposal = _proposal(core, project_id)
        core.business_boundaries.approve(
            project_id,
            proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint,
            reason="确认手工业务边界",
        )
        boundary = core.business_boundaries.view(project_id)
        without_rows = boundary.model_copy(
            update={
                "actor_bindings": tuple(
                    inspect_actor_binding(
                        item.actor_id,
                        item.revision,
                        None,
                        understanding,
                    )
                    for item in boundary.actors
                ),
                "action_bindings": tuple(
                    inspect_action_binding(
                        item.action_id,
                        item.revision,
                        None,
                        understanding,
                    )
                    for item in boundary.actions
                ),
            }
        )
        core.workspace._business_boundaries = SimpleNamespace(
            view=lambda _project_id: without_rows,
            proposals=lambda _project_id, pending_only: SimpleNamespace(proposals=()),
        )

        workspace = core.workspace.get(project_id)

        assert workspace.primary_task is None
        assert workspace.actors[0].implementation.binding_exists is False
        assert workspace.actions[0].implementation.binding_exists is False
        assert workspace.actions[0].actor_implementation_issue_count == 0
    finally:
        core.close()


def test_permission_revision_review_precedes_stale_binding(tmp_path: Path) -> None:
    core, project_id = _core(tmp_path)
    try:
        candidate = _action_candidate()
        understanding = _ready_understanding(
            core,
            project_id,
            action_candidates=(candidate,),
        )
        proposal = _proposal(
            core,
            project_id,
            action_source_ids=(candidate.candidate_id,),
        )
        core.business_boundaries.approve(
            project_id,
            proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint,
            reason="确认动作及当前代码实现",
        )
        core.application_understanding.decide_action(
            project_id,
            candidate.candidate_id,
            revision=understanding.revision,
            decision=CandidateDecision.REJECTED,
        )
        boundary = core.business_boundaries.view(project_id)
        review_status = boundary.permission_statuses[0].model_copy(
            update={
                "permission_semantics_confirmed": False,
                "reason_codes": ("PERMISSION_REVISION_REVIEW_REQUIRED",),
            }
        )
        task = core.workspace._primary_task(
            core.application_understanding.get(project_id),
            boundary.model_copy(update={"permission_statuses": (review_status,)}),
            (),
        )
        assert task is not None
        assert task.task_kind == "REVIEW_PERMISSION_REVISION"
    finally:
        core.close()


def test_deny_only_prioritizes_allow_control_and_preparation_reads_real_identity(tmp_path: Path) -> None:
    from product.backend.workflows.preparation import PreparationService

    core, project_id = _core(tmp_path)
    try:
        _ready_understanding(core, project_id)
        proposal = _proposal(core, project_id, expectation=PermissionExpectation.DENY)
        boundary = core.business_boundaries.approve(
            project_id, proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint, reason="确认拒绝权限",
        )
        workspace = core.workspace.get(project_id)
        assert workspace.primary_task.task_kind == "COMPLETE_ALLOW_CONTROL"
        assert workspace.primary_task.route == "/permissions"
        assert workspace.areas[1].status == "NEEDS_ATTENTION"
        service = PreparationService(core.business_boundaries, core.test_identities)
        first = service.get(project_id).actions[0]
        actor = boundary.actors[0]
        identity = core.test_identities.create(project_id, actor_id=actor.actor_id,
                                               actor_revision=actor.revision, label="负责人账号")
        second = service.get(project_id).actions[0]
        assert first.identity_requirements.slots[0].test_identity_id is None
        assert second.identity_requirements.slots[0].test_identity_id == identity.identity_id
        assert second.assurance_contract_fingerprint == first.assurance_contract_fingerprint
        assert second.preparation_complete is False
        assert core.business_boundaries.view(project_id) == boundary
    finally:
        core.close()


def test_new_initial_and_maintenance_relation_writes_are_rejected_without_side_effects(tmp_path: Path) -> None:
    from product.backend.core.errors import JiejianError
    from product.backend.workflows.business_boundaries import BoundaryMaintenanceCommand

    core, project_id = _core(tmp_path)
    try:
        _ready_understanding(core, project_id)
        with pytest.raises(JiejianError, match="权限资源关系"):
            _proposal(core, project_id, relation=PermissionIntentRelation.OTHER_ROLE)
        assert core.business_boundaries.proposals(project_id).proposals == ()
        proposal = _proposal(core, project_id)
        before = core.business_boundaries.approve(
            project_id, proposal.proposal_id,
            expected_fingerprint=proposal.proposal_fingerprint, reason="确认合法权限",
        )
        draft = core.business_boundaries.maintenance_draft(project_id)
        command = BoundaryMaintenanceCommand(
            expected_boundary_state_fingerprint=draft.boundary_state_fingerprint,
            actors=draft.actors, actions=draft.actions,
            permissions=tuple(item.model_copy(update={"relation": PermissionIntentRelation.OTHER_ROLE})
                              for item in draft.permissions),
            provenance="校验同一业务主体不能声明不同角色关系",
        )
        with pytest.raises(JiejianError, match="权限资源关系"):
            core.business_boundaries.create_maintenance_proposal(project_id, command)
        assert core.business_boundaries.view(project_id) == before
        assert core.business_boundaries.proposals(project_id, pending_only=True).proposals == ()
    finally:
        core.close()
