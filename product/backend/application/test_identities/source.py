# 核对当前角色与确认地址，计算提交和采用登录结果共用的来源指纹。
from product.backend.domain.boundaries.entities import BusinessRevisionState, boundary_sha256
from product.backend.domain.errors import ErrorCode, JiejianError


def preparation_source(identity, understanding, boundary):
    # 角色仍有效与来源未变化是两个条件：来源摘要不能替代 ACTIVE 修订校验。
    actor = next(
        (
            item
            for item in boundary.actors
            if item.actor_id == identity.actor_id
            and item.project_id == identity.project_id
            and item.revision == identity.actor_revision
            and item.effective_state is BusinessRevisionState.ACTIVE
        ),
        None,
    )
    if actor is None:
        raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY, "账号角色需要重新核对")
    if (
        understanding.confirmed_endpoint is None
        or not understanding.endpoint_reachable
        or understanding.endpoint_confirmed_at_us is None
        or understanding.endpoint_source_fingerprint is None
    ):
        raise JiejianError(ErrorCode.APPLICATION_ENDPOINT_INVALID, "请先核对应用运行地址")
    # 摘要绑定账号身份、角色修订、确认地址、源码来源和账号更新时间；不包含登录秘密值。
    # 认证重置的代次另由持久任务核对，不能只靠时间戳判断旧结果是否仍可采用。
    facts = {
        key: getattr(identity, key)
        for key in (
            "project_id",
            "identity_id",
            "actor_id",
            "actor_revision",
            "created_at_us",
            "updated_at_us",
        )
    }
    facts.update(
        {
            key: getattr(understanding, key)
            for key in ("confirmed_endpoint", "endpoint_source_fingerprint", "source_fingerprint")
        }
    )
    return understanding.confirmed_endpoint, boundary_sha256(facts)
