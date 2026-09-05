# 在录制写入事务内复核正式动作、角色、实现映射和补录来源，拒绝陈旧提交。

from product.backend.core.business_boundary import BusinessRevisionState, ImplementationBindingStatus, boundary_sha256
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.recording import RecordingPurpose, RecordingState
from product.backend.workflows.business_boundaries.inspection import inspect_action_binding, inspect_actor_binding


def identity_source_fingerprint(identity):
    return boundary_sha256({
        "identity_id": identity.identity_id, "project_id": identity.project_id,
        "actor_id": identity.actor_id, "actor_revision": identity.actor_revision,
        "created_at_us": identity.created_at_us,
    })


def recording_endpoint_fingerprint(understanding):
    """同时绑定确认的目标地址与发现来源，切换端口也必须重新确认技术事实。"""
    # endpoint_source_fingerprint 描述源码位置，本身不能区分同一应用的不同目标地址。
    return boundary_sha256({
        "confirmed_endpoint": understanding.confirmed_endpoint,
        "endpoint_source_fingerprint": understanding.endpoint_source_fingerprint,
    })


def recording_source_fingerprint(action, identity, understanding, action_binding, actor_binding):
    """冻结录制开始时的非秘密来源；重登录不会抹去已确认的技术事实。"""
    return boundary_sha256({
        "action_id": action.action_id, "revision": action.revision,
        "action_semantic_fingerprint": action.semantic_fingerprint,
        "action_implementation_fingerprint": action_binding.binding_fingerprint,
        "actor_implementation_fingerprint": actor_binding.binding_fingerprint,
        "source_fingerprint": understanding.source_fingerprint,
        "endpoint_fingerprint": recording_endpoint_fingerprint(understanding),
        "identity_fingerprint": identity_source_fingerprint(identity),
    })


def require_recording_source(work, request):
    """只读取当前事务中的非秘密事实；登录秘密仍由受控凭据服务负责。"""

    root = work.business_boundaries.action(request.business_action_id)
    action = work.business_boundaries.action_revision(request.business_action_id, request.action_revision)
    identity = work.test_identities.get(request.test_identity_id)
    understanding = work.application_understanding.get(request.project_id)
    if (
        root is None or action is None or identity is None or understanding is None
        or root.project_id != request.project_id or action.project_id != request.project_id
        or root.current_revision != request.action_revision
        or action.effective_state is not BusinessRevisionState.ACTIVE
        or identity.project_id != request.project_id or identity.prepared_at_us is None
        or understanding.confirmed_endpoint is None
    ):
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制来源已失效，请刷新业务动作和测试账号")
    actor_root = work.business_boundaries.actor(identity.actor_id)
    actor = work.business_boundaries.actor_revision(identity.actor_id, identity.actor_revision)
    if (
        actor_root is None or actor is None or actor.project_id != request.project_id
        or actor_root.current_revision != identity.actor_revision
        or actor.effective_state is not BusinessRevisionState.ACTIVE
        or inspect_action_binding(
            action.action_id, action.revision,
            work.business_boundaries.action_binding(action.action_id, action.revision), understanding,
        ).status is not ImplementationBindingStatus.CURRENT
        or inspect_actor_binding(
            actor.actor_id, actor.revision,
            work.business_boundaries.actor_binding(actor.actor_id, actor.revision), understanding,
        ).status is not ImplementationBindingStatus.CURRENT
    ):
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "业务动作或测试角色的实现需要重新确认")
    expected = recording_source_fingerprint(
        action, identity, understanding,
        work.business_boundaries.action_binding(action.action_id, action.revision),
        work.business_boundaries.actor_binding(actor.actor_id, actor.revision),
    )
    if request.preparation_source_fingerprint != expected:
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制开始后的业务实现或目标来源已变化，请重新演示")
    if request.effect_id is not None and request.effect_id not in {item.effect_id for item in action.effect_catalog}:
        raise JiejianError(ErrorCode.INPUT_INVALID, "业务效果不属于当前动作")
    if request.purpose is RecordingPurpose.RECOVERY and not action.state_changing:
        raise JiejianError(ErrorCode.INPUT_INVALID, "只读业务动作不需要恢复录制")
    if request.parent_recording_id is not None:
        parent = work.recordings.get(request.parent_recording_id)
        if (
            parent is None or parent.state is not RecordingState.COMPLETED
            or parent.purpose is not RecordingPurpose.TARGET
            or (parent.project_id, parent.business_action_id, parent.action_revision, parent.test_identity_id)
            != (request.project_id, request.business_action_id, request.action_revision, request.test_identity_id)
        ):
            raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "补录需要同一动作版本和账号的已完成业务录制")
    return action, identity, understanding
