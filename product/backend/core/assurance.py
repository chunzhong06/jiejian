# 从正式业务权限确定性编译身份、资源、效果证明与恢复需求，不读取技术资产或执行 I/O。
# 合同只表达测试需要；不可持久化，不含真实账号、Flow、URL、Observer 或秘密。

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum

from pydantic import Field

from product.backend.core.business_boundary import (
    BoundaryModel,
    BusinessActionRevision,
    boundary_sha256,
)
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState,
    PermissionIntentRelation,
    PermissionIntentRevision,
    permission_relation_consistent,
)
from product.backend.core.permission_semantics import PermissionExpectation


class AllocationMode(StrEnum):
    EXACT = "EXACT"
    CONSERVATIVE = "CONSERVATIVE"


class AssuranceStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class PermissionIdentity(BoundaryModel):
    intent_id: str
    revision: int = Field(ge=1)
    intent_hash: str


class IdentityRequirementSlot(BoundaryModel):
    slot_id: str
    actor_id: str
    actor_revision: int = Field(ge=1)
    ordinal: int = Field(ge=1)
    required_by_intent_ids: tuple[str, ...]
    distinct_slot_ids: tuple[str, ...]


class PermissionIdentitySlots(BoundaryModel):
    permission: PermissionIdentity
    subject_slot_id: str
    resource_owner_slot_id: str


class IdentityRequirementPlan(BoundaryModel):
    allocation_mode: AllocationMode
    slots: tuple[IdentityRequirementSlot, ...]
    permissions: tuple[PermissionIdentitySlots, ...]


class ActionResourceRequirement(BoundaryModel):
    owner_slot_id: str
    required_by_intent_ids: tuple[str, ...]


class EffectEvidenceRequirement(BoundaryModel):
    effect_id: str
    required_by_intent_ids: tuple[str, ...]


class AllowControlRequirement(BoundaryModel):
    deny_permission: PermissionIdentity
    effect_id: str
    allow_permission: PermissionIdentity | None


class ActionAssuranceContract(BoundaryModel):
    action_id: str
    action_revision: int = Field(ge=1)
    action_semantic_fingerprint: str
    permissions: tuple[PermissionIdentity, ...]
    allow_controls: tuple[AllowControlRequirement, ...]
    identity_requirements: IdentityRequirementPlan
    resources: tuple[ActionResourceRequirement, ...]
    effect_evidence: tuple[EffectEvidenceRequirement, ...]
    recovery_required: bool
    status: AssuranceStatus
    reason_codes: tuple[str, ...]
    fingerprint: str


def _permission_identity(intent: PermissionIntentRevision) -> PermissionIdentity:
    return PermissionIdentity(
        intent_id=intent.intent_id, revision=intent.revision, intent_hash=intent.intent_hash
    )


def _relation_valid(intent: PermissionIntentRevision) -> bool:
    return permission_relation_consistent(
        intent.relation,
        (intent.subject_actor_id, intent.subject_actor_revision),
        (intent.resource_owner_actor_id, intent.resource_owner_actor_revision),
    )


def _color_components(neighbors: tuple[frozenset[int], ...]) -> tuple[int, ...]:
    """小图精确最少着色；大图使用同一固定节点序的保守贪心。"""

    size = len(neighbors)
    colors = [-1] * size
    for node in range(size):
        unavailable = {colors[other] for other in neighbors[node] if colors[other] >= 0}
        colors[node] = next(color for color in range(size) if color not in unavailable)
    if size > 12 or not size:
        return tuple(colors)

    upper = max(colors) + 1
    # 依次尝试颜色上界，并固定搜索顺序和颜色首次出现次序，结果不受 hash/set 顺序影响。
    def assign(node: int, used: int, limit: int) -> bool:
        if node == size:
            return True
        unavailable = {colors[other] for other in neighbors[node] if other < node}
        for color in range(min(used + 1, limit)):
            if color in unavailable:
                continue
            colors[node] = color
            if assign(node + 1, max(used, color + 1), limit):
                return True
        colors[node] = -1
        return False

    for limit in range(1, upper + 1):
        colors[:] = [-1] * size
        if assign(0, 0, limit):
            return tuple(colors)
    raise AssertionError("greedy upper bound must be colorable")


class IdentityRequirementPlanner:
    """先合并 OWNS，再按每个 Actor revision 的不同身份约束分组；输入须已通过关系审查。"""

    def plan(self, permissions: tuple[PermissionIntentRevision, ...]) -> IdentityRequirementPlan:
        ordered = tuple(sorted(permissions, key=lambda item: (item.intent_id, item.revision)))
        if any(not _relation_valid(item) for item in ordered):
            raise ValueError("PERMISSION_RELATION_REVIEW_REQUIRED")
        if len({item.intent_id for item in ordered}) != len(ordered):
            raise ValueError("current permission identities must be unique")
        # 一个逻辑位置由权限身份与 subject/owner 角色确定；OWNS 的两端使用同一个组件。
        components: dict[tuple[str, int], list[tuple[tuple[str, str], ...]]] = defaultdict(list)
        edges: list[tuple[tuple[str, str], tuple[str, str]]] = []
        for item in ordered:
            subject = (item.intent_id, "subject")
            owner = (item.intent_id, "owner")
            subject_actor = (item.subject_actor_id, item.subject_actor_revision)
            owner_actor = (item.resource_owner_actor_id, item.resource_owner_actor_revision)
            if item.relation is PermissionIntentRelation.OWNS:
                components[subject_actor].append(tuple(sorted((subject, owner))))
            else:
                components[subject_actor].append((subject,))
                components[owner_actor].append((owner,))
                edges.append((subject, owner))

        slot_specs: list[tuple[str, str, int, int, tuple[str, ...]]] = []
        position_slots: dict[tuple[str, str], str] = {}
        intent_by_id = {item.intent_id: item for item in ordered}
        mode = AllocationMode.EXACT
        for (actor_id, revision), groups in sorted(components.items()):
            groups.sort()
            index = {position: ordinal for ordinal, group in enumerate(groups) for position in group}
            graph: list[set[int]] = [set() for _ in groups]
            for left, right in edges:
                if left in index and right in index:
                    graph[index[left]].add(index[right])
                    graph[index[right]].add(index[left])
            if len(groups) > 12:
                mode = AllocationMode.CONSERVATIVE
            colors = _color_components(tuple(frozenset(values) for values in graph))
            for color in range(max(colors) + 1):
                positions = tuple(sorted(
                    position for node, group in enumerate(groups)
                    if colors[node] == color for position in group
                ))
                required_ids = tuple(sorted({intent_id for intent_id, _ in positions}))
                slot_id = "isl_" + boundary_sha256({
                    "actor_id": actor_id, "actor_revision": revision,
                    "positions": [
                        {"permission": _permission_identity(intent_by_id[intent_id]).model_dump(mode="json"),
                         "position": position}
                        for intent_id, position in positions
                    ],
                })[:32]
                slot_specs.append((slot_id, actor_id, revision, color + 1, required_ids))
                position_slots.update({position: slot_id for position in positions})
        distinct: dict[str, set[str]] = defaultdict(set)
        for left, right in edges:
            left_slot, right_slot = position_slots[left], position_slots[right]
            if left_slot == right_slot:
                raise AssertionError("distinct logical identities were merged")
            distinct[left_slot].add(right_slot)
            distinct[right_slot].add(left_slot)
        return IdentityRequirementPlan(
            allocation_mode=mode,
            slots=tuple(IdentityRequirementSlot(
                slot_id=slot_id, actor_id=actor_id, actor_revision=revision, ordinal=ordinal,
                required_by_intent_ids=required_ids,
                distinct_slot_ids=tuple(sorted(distinct[slot_id])),
            ) for slot_id, actor_id, revision, ordinal, required_ids in slot_specs),
            permissions=tuple(PermissionIdentitySlots(
                permission=_permission_identity(item),
                subject_slot_id=position_slots[(item.intent_id, "subject")],
                resource_owner_slot_id=position_slots[(item.intent_id, "owner")],
            ) for item in ordered),
        )


def compile_action_assurance(
    action: BusinessActionRevision,
    permissions: tuple[PermissionIntentRevision, ...],
) -> ActionAssuranceContract:
    """现场编译 current 权限；无 ALLOW 或历史关系不一致均阻断，不推测替代身份。"""

    current = tuple(sorted((item for item in permissions
        if item.project_id == action.project_id
        and item.business_action_id == action.action_id and item.action_revision == action.revision
        and item.effective_state is PermissionIntentEffectiveState.ACTIVE
    ), key=lambda item: (item.intent_id, item.revision)))
    reasons: list[str] = []
    if not current:
        reasons.append("PERMISSION_SEMANTICS_REQUIRED")
    valid = all(_relation_valid(item) for item in current)
    if not valid:
        reasons.append("PERMISSION_RELATION_REVIEW_REQUIRED")
    effects = {effect.effect_id for effect in action.effect_catalog}
    if any(not set(item.protected_effect_ids) <= effects for item in current):
        reasons.append("PERMISSION_REVISION_REVIEW_REQUIRED")
    plan = IdentityRequirementPlanner().plan(current if valid else ())
    allows = tuple(item for item in current if item.expectation is PermissionExpectation.ALLOW and _relation_valid(item))
    controls = tuple(AllowControlRequirement(
        deny_permission=_permission_identity(deny), effect_id=effect_id,
        allow_permission=next((
            _permission_identity(allow) for allow in allows if effect_id in allow.protected_effect_ids
        ), None),
    ) for deny in current if deny.expectation is PermissionExpectation.DENY
        for effect_id in deny.protected_effect_ids)
    if not allows or any(item.allow_permission is None for item in controls):
        reasons.append("ALLOW_CONTROL_REQUIRED")
    owner_intents: dict[str, set[str]] = defaultdict(set)
    for item in plan.permissions:
        owner_intents[item.resource_owner_slot_id].add(item.permission.intent_id)
    protected = sorted({effect_id for item in current for effect_id in item.protected_effect_ids})
    payload = dict(
        action_id=action.action_id, action_revision=action.revision,
        action_semantic_fingerprint=action.semantic_fingerprint,
        permissions=tuple(_permission_identity(item) for item in current),
        allow_controls=controls, identity_requirements=plan,
        resources=tuple(ActionResourceRequirement(
            owner_slot_id=slot_id, required_by_intent_ids=tuple(sorted(intent_ids)),
        ) for slot_id, intent_ids in sorted(owner_intents.items())),
        effect_evidence=tuple(EffectEvidenceRequirement(
            effect_id=effect_id,
            required_by_intent_ids=tuple(item.intent_id for item in current if effect_id in item.protected_effect_ids),
        ) for effect_id in protected),
        recovery_required=action.state_changing,
        status=AssuranceStatus.BLOCKED if reasons else AssuranceStatus.READY,
        reason_codes=tuple(reasons),
    )
    contract = ActionAssuranceContract(**payload, fingerprint="")
    return contract.model_copy(update={
        "fingerprint": boundary_sha256(contract.model_dump(mode="json", exclude={"fingerprint"}))
    })


__all__ = [
    "ActionAssuranceContract", "ActionResourceRequirement", "AllocationMode",
    "AssuranceStatus", "EffectEvidenceRequirement", "IdentityRequirementPlan",
    "IdentityRequirementPlanner", "IdentityRequirementSlot", "PermissionIdentity",
    "PermissionIdentitySlots", "compile_action_assurance",
]
