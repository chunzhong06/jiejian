# 官方业务边界公开合同：只生成普通 Proposal command，不批准或写正式 revision。

from __future__ import annotations

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
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState,
    PermissionIntentRelation,
)
from product.backend.core.permission_semantics import (
    PermissionExpectation,
    BusinessEffectKind,
)
from product.backend.workflows.business_boundaries.models import (
    BoundaryProposalCommand,
    OfficialBoundaryActionSummary,
    OfficialBoundaryActorSummary,
    OfficialBoundaryEffectSummary,
    OfficialBoundaryPermissionSummary,
    OfficialBoundaryRecipe,
)


OFFICIAL_BOUNDARY_PROVENANCE = "界鉴 1.1.0 官方公开业务合同"

_OWNER = "pactr_1100000000000001"
_MEMBER = "pactr_1100000000000002"
_EXPORT = "pactn_1100000000000001"
_VIEW = "pactn_1100000000000002"
_EXPORT_EFFECT = "peff_1100000000000001"
_VIEW_EFFECT = "peff_1100000000000002"


def official_boundary_recipe() -> OfficialBoundaryRecipe:
    """返回可由任意普通项目复用、且必须经 LOCAL_GUI 批准的固定合同。"""

    actors = (
        ProposedActorItem(
            item_id=_OWNER,
            write_mode=ProposalWriteMode.CREATE,
            display_name="项目负责人",
            description="负责项目交付范围与完整交付物管理",
            effective_state=BusinessRevisionState.ACTIVE,
        ),
        ProposedActorItem(
            item_id=_MEMBER,
            write_mode=ProposalWriteMode.CREATE,
            display_name="普通协作成员",
            description="参与项目日常协作并查看获准材料",
            effective_state=BusinessRevisionState.ACTIVE,
        ),
    )
    export_effect = ProposedEffectItem(
        item_id=_EXPORT_EFFECT,
        business_label="完整项目交付包真实形成",
        effect_kind=BusinessEffectKind.OBJECT_CREATION,
        resource_concept="项目交付包",
        expected_state="完整项目交付包已经生成",
        description="形成包含项目正式交付材料的完整文件包",
    )
    view_effect = ProposedEffectItem(
        item_id=_VIEW_EFFECT,
        business_label="日常协作资料的有限内容可见",
        effect_kind=BusinessEffectKind.DATA_DISCLOSURE,
        resource_concept="日常协作资料",
        expected_state="只展示获准的日常协作字段",
        protected_projection=(
            "collaboration_material.summary",
            "collaboration_material.title",
        ),
        description="普通协作成员可以读取日常协作资料的有限投影",
    )
    actions = (
        ProposedActionItem(
            item_id=_EXPORT,
            write_mode=ProposalWriteMode.CREATE,
            display_name="导出完整项目交付包",
            description="生成包含项目正式交付材料的完整项目包",
            primary_resource_concept="项目交付空间",
            operation_kind=BusinessActionOperationKind.EXPORT,
            state_changing=True,
            effect_catalog=(export_effect,),
            effective_state=BusinessRevisionState.ACTIVE,
        ),
        ProposedActionItem(
            item_id=_VIEW,
            write_mode=ProposalWriteMode.CREATE,
            display_name="查看日常协作资料",
            description="读取项目日常协作资料的获准字段",
            primary_resource_concept="日常协作资料",
            operation_kind=BusinessActionOperationKind.READ,
            state_changing=False,
            effect_catalog=(view_effect,),
            effective_state=BusinessRevisionState.ACTIVE,
        ),
    )
    permissions = (
        _permission(
            "pperm_1100000000000001",
            subject=_OWNER,
            action=_EXPORT,
            owner=_OWNER,
            relation=PermissionIntentRelation.OWNS,
            expectation=PermissionExpectation.ALLOW,
            effect=_EXPORT_EFFECT,
        ),
        _permission(
            "pperm_1100000000000002",
            subject=_MEMBER,
            action=_EXPORT,
            owner=_OWNER,
            relation=PermissionIntentRelation.OTHER_ROLE,
            expectation=PermissionExpectation.DENY,
            effect=_EXPORT_EFFECT,
        ),
        _permission(
            "pperm_1100000000000003",
            subject=_MEMBER,
            action=_VIEW,
            owner=_MEMBER,
            relation=PermissionIntentRelation.OWNS,
            expectation=PermissionExpectation.ALLOW,
            effect=_VIEW_EFFECT,
        ),
    )
    command = BoundaryProposalCommand(
        proposed_actors=actors,
        proposed_actions=actions,
        proposed_permissions=permissions,
        provenance=OFFICIAL_BOUNDARY_PROVENANCE,
    )
    return OfficialBoundaryRecipe(
        application_display="创新项目交付空间",
        project_display="校园数字展馆",
        actors=tuple(
            OfficialBoundaryActorSummary(
                display_name=item.display_name,
                description=item.description,
            )
            for item in actors
        ),
        actions=(
            OfficialBoundaryActionSummary(
                display_name=actions[0].display_name,
                effects=(
                    OfficialBoundaryEffectSummary(
                        business_label=export_effect.business_label,
                        effect_kind=export_effect.effect_kind.value,
                        resource_concept=export_effect.resource_concept,
                    ),
                ),
            ),
            OfficialBoundaryActionSummary(
                display_name=actions[1].display_name,
                effects=(
                    OfficialBoundaryEffectSummary(
                        business_label=view_effect.business_label,
                        effect_kind=view_effect.effect_kind.value,
                        resource_concept=view_effect.resource_concept,
                        protected_projection=view_effect.protected_projection,
                    ),
                ),
            ),
        ),
        permissions=(
            OfficialBoundaryPermissionSummary(
                subject="项目负责人",
                action="导出完整项目交付包",
                resource_owner="项目负责人",
                relation=PermissionIntentRelation.OWNS.value,
                expectation=PermissionExpectation.ALLOW.value,
            ),
            OfficialBoundaryPermissionSummary(
                subject="普通协作成员",
                action="导出完整项目交付包",
                resource_owner="项目负责人",
                relation=PermissionIntentRelation.OTHER_ROLE.value,
                expectation=PermissionExpectation.DENY.value,
            ),
            OfficialBoundaryPermissionSummary(
                subject="普通协作成员",
                action="查看日常协作资料",
                resource_owner="普通协作成员",
                relation=PermissionIntentRelation.OWNS.value,
                expectation=PermissionExpectation.ALLOW.value,
            ),
        ),
        proposal_command=command,
    )


def _permission(
    item_id: str,
    *,
    subject: str,
    action: str,
    owner: str,
    relation: PermissionIntentRelation,
    expectation: PermissionExpectation,
    effect: str,
) -> ProposedPermissionItem:
    return ProposedPermissionItem(
        item_id=item_id,
        write_mode=ProposalWriteMode.CREATE,
        effective_state=PermissionIntentEffectiveState.ACTIVE,
        subject_actor_item_id=subject,
        business_action_item_id=action,
        resource_owner_actor_item_id=owner,
        relation=relation,
        expectation=expectation,
        protected_effect_item_ids=(effect,),
    )


__all__ = ["OFFICIAL_BOUNDARY_PROVENANCE", "official_boundary_recipe"]
