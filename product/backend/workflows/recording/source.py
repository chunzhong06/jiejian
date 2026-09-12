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


def recording_source_fingerprint(action, identity, understanding, action_binding, actor_binding, *, owner, owner_actor_binding):
    """冻结录制开始时的非秘密来源；重登录不会抹去已确认的技术事实。"""
    return boundary_sha256({
        "action_id": action.action_id, "revision": action.revision,
        "action_semantic_fingerprint": action.semantic_fingerprint,
        "action_implementation_fingerprint": action_binding.binding_fingerprint,
        "subject_actor_implementation_fingerprint": actor_binding.binding_fingerprint,
        "owner_actor_implementation_fingerprint": owner_actor_binding.binding_fingerprint,
        "source_fingerprint": understanding.source_fingerprint,
        "endpoint_fingerprint": recording_endpoint_fingerprint(understanding),
        "subject_test_identity_id": identity.identity_id,
        "resource_owner_test_identity_id": owner.identity_id,
        "subject_identity_fingerprint": identity_source_fingerprint(identity),
        "owner_identity_fingerprint": identity_source_fingerprint(owner),
    })


def require_recording_source(work, request, *, historical_source=None):
    """只读取当前事务中的非秘密事实；登录秘密仍由受控凭据服务负责。"""

    root = work.business_boundaries.action(request.business_action_id)
    action = work.business_boundaries.action_revision(request.business_action_id, request.action_revision)
    identity = work.test_identities.get(request.subject_test_identity_id)
    owner = work.test_identities.get(request.resource_owner_test_identity_id)
    understanding = work.application_understanding.get(request.project_id)
    if (
        root is None or action is None or identity is None or owner is None or understanding is None
        or root.project_id != request.project_id or action.project_id != request.project_id
        or root.current_revision != request.action_revision
        or action.effective_state is not BusinessRevisionState.ACTIVE
        or identity.project_id != request.project_id or identity.prepared_at_us is None
        or owner.project_id != request.project_id or owner.prepared_at_us is None
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
    owner_root = work.business_boundaries.actor(owner.actor_id)
    owner_actor = work.business_boundaries.actor_revision(owner.actor_id, owner.actor_revision)
    owner_binding = work.business_boundaries.actor_binding(owner.actor_id, owner.actor_revision)
    if (owner_root is None or owner_actor is None or owner_root.current_revision != owner.actor_revision
            or owner_actor.effective_state is not BusinessRevisionState.ACTIVE
            or inspect_actor_binding(owner.actor_id, owner.actor_revision, owner_binding, understanding).status is not ImplementationBindingStatus.CURRENT):
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "业务动作或测试角色的实现需要重新确认")
    expected = recording_source_fingerprint(
        action, identity, understanding,
        work.business_boundaries.action_binding(action.action_id, action.revision),
        work.business_boundaries.actor_binding(actor.actor_id, actor.revision),
        owner=owner, owner_actor_binding=owner_binding,
    )
    if historical_source is not None:
        from product.protocols.recording_legacy import LegacyRecordingRunnerRequest
        if (not isinstance(historical_source, LegacyRecordingRunnerRequest)
                or identity.identity_id != owner.identity_id
                or any(getattr(historical_source, name) != getattr(request, name)
                       for name in ("project_id", "recording_id", "business_action_id", "action_revision",
                                    "subject_test_identity_id", "resource_owner_test_identity_id", "preparation_source_fingerprint"))):
            raise JiejianError(ErrorCode.RECORD_PROTOCOL_INVALID, "历史录制来源无效")
        # 仅由已验原始文件 hash 的明确历史 reader 进入，不能用尝试旧 hash 作为 fallback。
        expected = boundary_sha256({
            "action_id": action.action_id, "revision": action.revision,
            "action_semantic_fingerprint": action.semantic_fingerprint,
            "action_implementation_fingerprint": work.business_boundaries.action_binding(action.action_id, action.revision).binding_fingerprint,
            "actor_implementation_fingerprint": work.business_boundaries.actor_binding(actor.actor_id, actor.revision).binding_fingerprint,
            "source_fingerprint": understanding.source_fingerprint,
            "endpoint_fingerprint": recording_endpoint_fingerprint(understanding),
            "identity_fingerprint": identity_source_fingerprint(identity),
        })
    if request.preparation_source_fingerprint != expected:
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制开始后的业务实现或目标来源已变化，请重新演示")
    _require_assignment(work, request, action)
    if request.effect_id is not None and request.effect_id not in {item.effect_id for item in action.effect_catalog}:
        raise JiejianError(ErrorCode.INPUT_INVALID, "业务效果不属于当前动作")
    if request.purpose is RecordingPurpose.RECOVERY and not action.state_changing:
        raise JiejianError(ErrorCode.INPUT_INVALID, "只读业务动作不需要恢复录制")
    if request.parent_recording_id is not None:
        parent = work.recordings.get(request.parent_recording_id)
        if (
            parent is None or parent.state is not RecordingState.COMPLETED
            or parent.purpose is not RecordingPurpose.TARGET
            or parent.resource_owner_test_identity_id != request.resource_owner_test_identity_id
            or (parent.project_id, parent.business_action_id, parent.action_revision, parent.subject_test_identity_id)
            != (request.project_id, request.business_action_id, request.action_revision, request.subject_test_identity_id)
        ):
            raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "补录需要同一动作版本和账号的已完成业务录制")
    return action, identity, understanding


def require_persisted_recording_source(work, recording, var_dir):
    """先按 Job 原始 hash 读取来源格式，再选择唯一明确的来源校验路径。"""
    from product.backend.infra.recording.request_store import RecordingRequestStore
    from product.protocols.recording_legacy import LegacyRecordingRunnerRequest
    job = work.jobs.get_by_recording(recording.recording_id)
    if job is None:
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制来源已失效")
    source = RecordingRequestStore(var_dir).load_history(job.job_id, expected_hash=job.request_hash)
    if any(getattr(source, name) != getattr(recording, name) for name in (
        "project_id", "recording_id", "business_action_id", "action_revision", "subject_test_identity_id",
        "resource_owner_test_identity_id", "preparation_source_fingerprint", "purpose", "parent_recording_id", "effect_id",
    )):
        raise JiejianError(ErrorCode.RECORD_PROTOCOL_INVALID, "录制来源无效")
    return require_recording_source(work, source,
        historical_source=source if isinstance(source, LegacyRecordingRunnerRequest) else None)


def _require_assignment(work, request, action):
    from types import SimpleNamespace
    from product.backend.core.assurance import compile_action_assurance, AssuranceStatus
    from product.backend.workflows.business_boundaries.service import BusinessBoundaryService
    from product.backend.workflows.preparation.service import PreparationService
    from product.backend.workflows.preparation.demonstrations import legal_demonstrations
    from product.backend.workflows.test_identities.service import TestIdentityStatus
    actors = tuple(item for root in work.business_boundaries.list_actors(action.project_id)
                   if (item := work.business_boundaries.actor_revision(root.actor_id, root.current_revision)) is not None
                   and item.effective_state is BusinessRevisionState.ACTIVE)
    permissions, _ = BusinessBoundaryService._current_permission_intents(
        work.permission_intents.list_latest(action.project_id), actors, (action,))
    contract = compile_action_assurance(action, permissions, work.action_preparation.allow_controls(action.project_id))
    identities = tuple(SimpleNamespace(
        identity_id=item.identity_id, actor_id=item.actor_id, actor_revision=item.actor_revision,
        created_at_us=item.created_at_us,
        status=TestIdentityStatus.PREPARED if item.prepared_at_us is not None else TestIdentityStatus.NOT_PREPARED,
    ) for item in work.test_identities.list_for_project(action.project_id))
    prepared = PreparationService._identities(contract, identities,
        {(item.actor_id, item.revision): item.display_name for item in actors})
    choices = legal_demonstrations(contract, permissions, prepared)
    matched = tuple(item for item in choices if item.can_execute
        and (item.subject_test_identity_id, item.resource_owner_test_identity_id)
        == (request.subject_test_identity_id, request.resource_owner_test_identity_id))
    if hasattr(request, "subject_slot_id"):
        matched = tuple(item for item in matched if (item.subject_slot_id, item.resource_owner_slot_id)
                        == (request.subject_slot_id, request.resource_owner_slot_id))
        if request.subject_test_identity_id != request.resource_owner_test_identity_id and request.resource_owner_confirmed is not True:
            matched = ()
    if contract.status is not AssuranceStatus.READY or not matched:
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "准备来源已变化", details={"reason": "ALLOW_RESOURCE_SETUP_REQUIRED"})
