# 构造权限编译和准备服务共同使用的正式业务事实，不依赖数据库或真实秘密。

from product.backend.core.approval import HumanApproval, HumanApprovalChannel
from product.backend.core.business_boundary import (
    BusinessActionOperationKind, BusinessActionRevision, BusinessActorRevision,
    BusinessEffectDefinition, BusinessRevisionState, boundary_sha256,
)
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState, PermissionIntentRelation, PermissionIntentRevision,
    PermissionIntentSemantic, permission_intent_sha256,
)
from product.backend.core.permission_semantics import BusinessEffectKind, PermissionExpectation


PROJECT = "assurance-test"
ACTOR = "bar_" + "1" * 32
OTHER_ACTOR = "bar_" + "2" * 32
EFFECT = "bef_" + "1" * 32
SECOND_EFFECT = "bef_" + "2" * 32


def approval():
    return HumanApproval(channel=HumanApprovalChannel.LOCAL_GUI, approved_by="本机界鉴用户",
                         approved_at_us=10, reason="确认测试业务权限")


def actor(actor_id=ACTOR, revision=1):
    payload = dict(actor_id=actor_id, project_id=PROJECT, display_name="普通成员" if actor_id == ACTOR else "负责人",
                   description="参与业务协作", effective_state=BusinessRevisionState.ACTIVE)
    return BusinessActorRevision(**payload, revision=revision, approval=approval(), created_at_us=10,
                                 semantic_fingerprint=boundary_sha256(payload))


def action(*, state_changing=True, revision=1):
    effects = tuple(BusinessEffectDefinition(
        effect_id=effect_id, business_label=label, effect_kind=BusinessEffectKind.STATE_MUTATION,
        resource_concept="文档", description=label,
    ) for effect_id, label in ((EFFECT, "文档更新"), (SECOND_EFFECT, "审阅更新")))
    payload = dict(action_id="bac_" + "1" * 32, project_id=PROJECT,
                   display_name="更新文档", description="修改协作文档", primary_resource_concept="文档",
                   operation_kind=BusinessActionOperationKind.CHANGE,
                   state_changing=state_changing, effect_catalog=effects,
                   effective_state=BusinessRevisionState.ACTIVE)
    fingerprint_payload = payload | {"effect_catalog": [item.model_dump(mode="json") for item in effects]}
    return BusinessActionRevision(**payload, revision=revision, approval=approval(), created_at_us=10,
                                  semantic_fingerprint=boundary_sha256(fingerprint_payload))


def permission(number=1, *, subject=ACTOR, owner=ACTOR, relation=PermissionIntentRelation.OWNS,
               expectation=PermissionExpectation.ALLOW, effects=(EFFECT,), revision=1, **updates):
    semantic = PermissionIntentSemantic(**(dict(
        effective_state=PermissionIntentEffectiveState.ACTIVE,
        subject_actor_id=subject, subject_actor_revision=1,
        business_action_id="bac_" + "1" * 32, action_revision=1,
        resource_owner_actor_id=owner, resource_owner_actor_revision=1,
        relation=relation, expectation=expectation, protected_effect_ids=effects,
    ) | updates))
    return PermissionIntentRevision(
        **semantic.model_dump(), intent_id=f"pin_{number:032x}", project_id=PROJECT, revision=revision,
        intent_hash=permission_intent_sha256(semantic.canonical_payload()), policy_epoch=1,
        approval=approval(), created_at_us=10,
    )
