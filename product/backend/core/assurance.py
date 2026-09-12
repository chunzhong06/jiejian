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
from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN
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
    intent_id: str = Field(pattern=r"^pin_[0-9a-f]{32}$")
    revision: int = Field(ge=1)
    intent_hash: str = Field(pattern=SHA256_PATTERN)


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
    protected_effect_ids: tuple[str, ...]
    candidate_allow_permissions: tuple[PermissionIdentity, ...]
    resolved_allow_permission: PermissionIdentity | None
    selection_fingerprint: str = Field(pattern=SHA256_PATTERN)


# 只记录有限候选中的人工技术选择；不拥有审批权或 policy epoch。
class ActionAllowControlBinding(BoundaryModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    deny_intent_id: str = Field(pattern=r"^pin_[0-9a-f]{32}$")
    deny_intent_revision: int = Field(ge=1)
    deny_intent_hash: str = Field(pattern=SHA256_PATTERN)
    selected_allow_intent_id: str = Field(pattern=r"^pin_[0-9a-f]{32}$")
    selected_allow_intent_revision: int = Field(ge=1)
    selected_allow_intent_hash: str = Field(pattern=SHA256_PATTERN)
    selection_fingerprint: str = Field(pattern=SHA256_PATTERN)
    confirmed_at_us: int = Field(ge=0)


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

    def plan(
        self, permissions: tuple[PermissionIntentRevision, ...],
        controls: tuple[AllowControlRequirement, ...] = (),
    ) -> IdentityRequirementPlan:
        ordered = tuple(sorted(permissions, key=lambda item: (item.intent_id, item.revision)))
        if any(not _relation_valid(item) for item in ordered):
            raise ValueError("PERMISSION_RELATION_REVIEW_REQUIRED")
        if len({item.intent_id for item in ordered}) != len(ordered):
            raise ValueError("current permission identities must be unique")
        # 先以并查集合并 OWNS 和已解析 Twin 的 owner，再构造同角色 distinct 图。
        components: dict[tuple[str, int], list[tuple[tuple[str, str], ...]]] = defaultdict(list)
        edges: list[tuple[tuple[str, str], tuple[str, str]]] = []
        parents = {(item.intent_id, role): (item.intent_id, role)
                   for item in ordered for role in ("subject", "owner")}
        actors = {(item.intent_id, role): actor for item in ordered for role, actor in (
            ("subject", (item.subject_actor_id, item.subject_actor_revision)),
            ("owner", (item.resource_owner_actor_id, item.resource_owner_actor_revision)),
        )}

        def root(position):
            while parents[position] != position:
                position = parents[position]
            return position

        def merge(left, right):
            if left not in parents or right not in parents or actors[left] != actors[right]:
                raise ValueError("CHECK_TWIN_INVARIANT_REQUIRED")
            a, b = sorted((root(left), root(right)))
            parents[b] = a

        for item in ordered:
            subject = (item.intent_id, "subject")
            owner = (item.intent_id, "owner")
            subject_actor = (item.subject_actor_id, item.subject_actor_revision)
            owner_actor = (item.resource_owner_actor_id, item.resource_owner_actor_revision)
            if item.relation is PermissionIntentRelation.OWNS:
                merge(subject, owner)
            else:
                edges.append((subject, owner))
        for control in controls:
            if control.resolved_allow_permission is not None:
                merge((control.deny_permission.intent_id, "owner"),
                      (control.resolved_allow_permission.intent_id, "owner"))
        grouped = defaultdict(list)
        for position in sorted(parents):
            grouped[root(position)].append(position)
        for representative, positions in sorted(grouped.items()):
            components[actors[representative]].append(tuple(positions))
        if any(root(left) == root(right) for left, right in edges):
            raise ValueError("IDENTITY_DISTINCT_REQUIRED")

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
    allow_control_bindings: tuple[ActionAllowControlBinding, ...] = (),
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
    allows = tuple(item for item in current if item.expectation is PermissionExpectation.ALLOW and _relation_valid(item))
    controls = tuple(_compile_allow_control(action, deny, allows, allow_control_bindings)
                     for deny in current if deny.expectation is PermissionExpectation.DENY)
    if not allows or any(not item.candidate_allow_permissions for item in controls):
        reasons.append("ALLOW_CONTROL_REQUIRED")
    if any(item.candidate_allow_permissions and item.resolved_allow_permission is None for item in controls):
        reasons.append("ALLOW_CONTROL_SELECTION_REQUIRED")
    try:
        plan = IdentityRequirementPlanner().plan(current if valid else (), controls if valid else ())
    except ValueError as error:
        if str(error) not in {"CHECK_TWIN_INVARIANT_REQUIRED", "IDENTITY_DISTINCT_REQUIRED"}:
            raise
        reasons.append(str(error))
        plan = IdentityRequirementPlanner().plan(())
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


def _compile_allow_control(action, deny, allows, bindings):
    candidates = tuple(allow for allow in allows if _relation_valid(deny)
        and (allow.resource_owner_actor_id, allow.resource_owner_actor_revision)
        == (deny.resource_owner_actor_id, deny.resource_owner_actor_revision)
        and set(allow.protected_effect_ids) >= set(deny.protected_effect_ids))
    # ID 只控制展示顺序，不能用来解决同级候选歧义。
    def rank(allow):
        return int((allow.subject_actor_id, allow.subject_actor_revision)
                   != (deny.subject_actor_id, deny.subject_actor_revision))
    best_rank = min((rank(item) for item in candidates), default=None)
    identities = tuple(_permission_identity(item) for item in candidates if rank(item) == best_rank)
    deny_identity = _permission_identity(deny)
    effects = tuple(sorted(set(deny.protected_effect_ids)))
    fingerprint = boundary_sha256({
        "kind": "ActionAllowControlSelection", "deny_permission": deny_identity.model_dump(mode="json"),
        "protected_effect_ids": effects,
        "candidate_allow_permissions": [item.model_dump(mode="json") for item in identities],
    })
    resolved = identities[0] if len(identities) == 1 else None
    if len(identities) > 1:
        selected = {(
            item.selected_allow_intent_id, item.selected_allow_intent_revision, item.selected_allow_intent_hash
        ) for item in bindings if item.project_id == action.project_id
            and (item.deny_intent_id, item.deny_intent_revision, item.deny_intent_hash)
            == (deny.intent_id, deny.revision, deny.intent_hash)
            and item.selection_fingerprint == fingerprint}
        matches = tuple(item for item in identities
                        if (item.intent_id, item.revision, item.intent_hash) in selected)
        if len(matches) == 1:
            resolved = matches[0]
    return AllowControlRequirement(
        deny_permission=deny_identity, protected_effect_ids=effects,
        candidate_allow_permissions=identities, resolved_allow_permission=resolved,
        selection_fingerprint=fingerprint,
    )


__all__ = [
    "ActionAssuranceContract", "ActionAllowControlBinding", "AllowControlRequirement", "ActionResourceRequirement", "AllocationMode",
    "AssuranceStatus", "EffectEvidenceRequirement", "IdentityRequirementPlan",
    "IdentityRequirementPlanner", "IdentityRequirementSlot", "PermissionIdentity",
    "PermissionIdentitySlots", "compile_action_assurance",
]
