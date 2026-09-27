# 所属业务域的共享测试构造器；不导入测试用例。
from __future__ import annotations
from pathlib import Path
from product.backend.composition import ApplicationCore
from product.backend.core.boundaries.proposals import ProposalWriteMode, ProposedActionItem, ProposedActorItem, ProposedEffectItem, ProposedPermissionItem
from product.backend.core.boundaries.entities import BusinessActionOperationKind, BusinessRevisionState
from product.backend.core.boundaries.permissions import PermissionIntentEffectiveState, PermissionIntentRelation
from product.backend.core.verification.permissions import (
    PermissionExpectation,
    SecurityEffectKind,
)
from product.backend.workflows.business_boundaries import (
    BoundaryMaintenanceCommand,
    BoundaryProposalCommand,
)

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
