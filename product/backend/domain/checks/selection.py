"""按准确规则修订缩小检查输入；保留原账号槽位和禁止场景的正常对照。"""
from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.preparation.requirements import AssuranceStatus, compile_action_assurance
from product.protocols.checks.execution_request import PermissionReference


def permission_key(value):
    return value.intent_id, value.revision, value.intent_hash


def resolve_selected_permissions(current, selected):
    keys = {permission_key(item) for item in selected}
    if not keys or len(keys) != len(selected) or not keys <= {permission_key(item) for item in current if item.effective_state.value == "ACTIVE"}:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "所选权限规则已变化，请重新选择。",
                           details={"reason": "CHECK_SELECTION_STALE"})
    return keys


def select_assurance(action, current, assurance, selected):
    direct = tuple(item for item in current if permission_key(item) in selected)
    if not direct:
        return None
    controls = tuple(item for item in assurance.allow_controls
                     if permission_key(item.deny_permission) in selected)
    keys = {permission_key(item) for item in direct}
    keys.update(permission_key(item.resolved_allow_permission) for item in controls
                if item.resolved_allow_permission is not None)
    permissions = tuple(item for item in current if permission_key(item) in keys)
    contract = compile_action_assurance(action, permissions)
    reasons = set(contract.reason_codes) - {"ALLOW_CONTROL_SELECTION_REQUIRED", "ALLOW_CONTROL_REQUIRED"}
    if any(not item.candidate_allow_permissions for item in controls):
        reasons.add("ALLOW_CONTROL_REQUIRED")
    if any(item.candidate_allow_permissions and item.resolved_allow_permission is None for item in controls):
        reasons.add("ALLOW_CONTROL_SELECTION_REQUIRED")
    # 重新分配身份会改变槽位摘要，令原账号绑定失效；仅投影完整合同中的既有槽位。
    positions = tuple(item for item in assurance.identity_requirements.permissions
                      if permission_key(item.permission) in keys)
    slot_ids = {slot for item in positions for slot in (item.subject_slot_id, item.resource_owner_slot_id)}
    old_plan = assurance.identity_requirements
    identity_plan = old_plan.model_copy(update={"permissions": positions, "slots": tuple(
        item.model_copy(update={
            "required_by_intent_ids": tuple(value for value in item.required_by_intent_ids if any(key[0] == value for key in keys)),
            "distinct_slot_ids": tuple(value for value in item.distinct_slot_ids if value in slot_ids),
        }) for item in old_plan.slots if item.slot_id in slot_ids)})
    contract = contract.model_copy(update={"allow_controls": controls, "identity_requirements": identity_plan,
        "resources": tuple(item.model_copy(update={"required_by_intent_ids": tuple(
            value for value in item.required_by_intent_ids if any(key[0] == value for key in keys))})
            for item in assurance.resources if item.owner_slot_id in {row.resource_owner_slot_id for row in positions}),
        "status": AssuranceStatus.BLOCKED if reasons else AssuranceStatus.READY, "reason_codes": tuple(sorted(reasons))})
    contract = contract.model_copy(update={"fingerprint": boundary_sha256(contract.model_dump(mode="json", exclude={"fingerprint"}))})
    return permissions, contract


def select_action_input(prepared, selected):
    projected = select_assurance(prepared.action, prepared.permissions, prepared.assurance, selected)
    if projected is None:
        return None
    permissions, contract = projected
    # 原汇总含未选择场景的缺口；具体绑定已由准备所有者核对，编译器会逐 Case 检查所需事实。
    return prepared.model_copy(update={"permissions": permissions, "assurance": contract, "reason_codes": ()})


def references(keys):
    return tuple(PermissionReference(intent_id=key[0], revision=key[1], intent_hash=key[2]) for key in sorted(keys))
