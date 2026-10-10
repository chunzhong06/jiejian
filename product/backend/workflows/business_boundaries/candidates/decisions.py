# 把人的情境选择关联到精确候选与批准；所有调用都沿外层UoW，不自行提交。
from __future__ import annotations

from product.backend.core.boundaries.entities import boundary_sha256
from product.backend.core.boundaries.permissions import permission_relation_consistent
from product.backend.core.boundaries.rule_candidates import RuleCandidateRevision
from product.backend.core.boundaries.candidate_scenarios import CandidateApprovalEntities, CandidateActorReference, CandidateActionReference, CandidateEffectReference
from product.backend.core.errors import ErrorCode, JiejianError


def scenario_state(work, value, *, extra=None):
    """按候选内指纹读取最后一次人的决定；较新纠正不能复活更早的选择。"""
    history = work.rule_candidates.decisions(value.project_id, value.candidate_id, value.revision) if getattr(value.content, "scenarios", ()) else ()
    if extra is not None:
        history = (*history, extra)
    latest = {item.scenario_id: item for item in history}
    states, replacements, conflicts = [], {}, set()
    for scenario in getattr(value.content, "scenarios", ()):
        decision = latest.get(scenario.scenario_id)
        if decision is not None and decision.scenario_fingerprint != scenario.scenario_fingerprint:
            decision = None
        option = None if decision is None else next((item for item in scenario.options if item.option_id == decision.option_id), None)
        status = decision.action if decision is not None else "NEEDS_DECISION"
        if status == "SELECT" and option is None:
            status = "NEEDS_DECISION"
        if status == "SELECT":
            for item in option.replacements:
                if item.item_id in replacements and replacements[item.item_id] != item:
                    conflicts.add(item.item_id)
                replacements[item.item_id] = item
        states.append({"scenario_id": scenario.scenario_id, "status": status, "decision": decision})
    # 冲突项不使用最后一次点击的值；正文保留原候选，阻止生成提案并显示冲突。
    for item_id in conflicts:
        replacements.pop(item_id, None)
    return states, replacements, conflicts


def decision_digest(states):
    return boundary_sha256([{"scenario_id": item["scenario_id"], "status": item["status"],
        "decision": None if item["decision"] is None else item["decision"].model_dump(mode="json")}
        for item in sorted(states, key=lambda item: item["scenario_id"])])


def pending_scenario_issues(states, conflicts):
    issues = [{"code": "NEEDS_DECISION", "message": "这处含义仍需你选择或说明。", "scenario_id": item["scenario_id"]}
        for item in states if item["status"] not in {"SELECT", "DISMISS"}]
    if conflicts:
        issues.append({"code": "CHOICES_CONFLICT", "message": "这些选择对同一权限提出了不同要求，请重新整理。"})
    return issues


def selected_permission_issues(permissions):
    active = [item for item in permissions if item.effective_state.value == "ACTIVE"]
    if any(not permission_relation_consistent(item.relation, (item.subject_actor_item_id, 1),
        (item.resource_owner_actor_item_id, 1)) for item in active):
        return [{"code": "AMBIGUOUS_REFERENCE", "message": "所选资源关系与角色不一致，请重新整理。"}]
    allows = [item for item in active if item.expectation.value == "ALLOW"]
    if any(not any(allow.business_action_item_id == deny.business_action_item_id
        and allow.resource_owner_actor_item_id == deny.resource_owner_actor_item_id
        and set(allow.protected_effect_item_ids) >= set(deny.protected_effect_item_ids) for allow in allows)
        for deny in active if deny.expectation.value == "DENY"):
        return [{"code": "ALLOW_CONTROL_REQUIRED", "message": "还需要保留同一资源与结果的正常使用要求，才能核对禁止要求。"}]
    cells = {}
    for item in active:
        for effect in item.protected_effect_item_ids:
            key = (item.subject_actor_item_id, item.resource_owner_actor_item_id, item.relation, item.business_action_item_id, effect)
            if key in cells and cells[key] != item.expectation:
                return [{"code": "CHOICES_CONFLICT", "message": "同一情境同时出现允许和禁止要求，请重新整理。"}]
            cells[key] = item.expectation
    return []


def check_candidate_edit(work, current, incoming):
    states, replacements, conflicts = scenario_state(work, current)
    incoming_scenes = {item.scenario_id: item for item in incoming.scenarios}
    old_scenes = {item.scenario_id: item for item in getattr(current.content, "scenarios", ())}
    state_by_id = {item["scenario_id"]: item for item in states}
    # 旧候选只有问题文字；升级时先转成同名情境，不能清空字段就假称歧义已解决。
    new_questions = {item.question for item in incoming.scenarios}
    for question in set(current.content.unresolved_questions) - set(incoming.unresolved_questions):
        resolved = any(scene.question == question and state_by_id[scene.scenario_id]["status"] in {"SELECT", "DISMISS"}
            for scene in old_scenes.values())
        if question not in new_questions and not resolved:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "已登记的问题仍需人核对，请先转成对应情境")
    for scenario_id, old in old_scenes.items():
        new = incoming_scenes.get(scenario_id)
        if new is None and state_by_id[scenario_id]["status"] not in {"SELECT", "DISMISS"}:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "已有情境不能静默删除，请由用户明确结束不适用的情境")
        if new is not None and new.scenario_fingerprint == old.scenario_fingerprint and state_by_id[scenario_id]["status"] == "SELECT":
            actual = {item.item_id: item for item in incoming.permissions}
            for option in old.options:
                if option.option_id == state_by_id[scenario_id]["decision"].option_id:
                    if any(item.item_id not in conflicts and actual.get(item.item_id) != replacements.get(item.item_id) for item in option.replacements):
                        raise JiejianError(ErrorCode.STATE_PRECONDITION, "已选择的要求发生变化，请更新对应情境并重新核对")


def validate_approval_source(work, proposal, current_basis):
    source = work.rule_candidates.proposal_source(proposal.proposal_id)
    if source is None:
        return None
    candidate_id, revision, content_hash, digest = source
    value = work.rule_candidates.get(proposal.project_id, candidate_id)
    if value is None or value.revision != revision or value.basis_id != current_basis:
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选或正式规则已有变化，请重新审阅最新候选")
    states, replacements, conflicts = scenario_state(work, value)
    if pending_scenario_issues(states, conflicts):
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "含义核对尚未完成，不能批准这份提案")
    if content_hash is not None or isinstance(value, RuleCandidateRevision):
        if content_hash != boundary_sha256(value.content.model_dump(mode="json")) or digest != decision_digest(states):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "提案与人的选择不再对应，请重新审阅")
    # 旧v1来源没有人工选择，不补写来源hash；仍检查候选头与原提案业务项一致。
    proposed = {item.item_id: item for item in proposal.proposed_permissions}
    for item in value.content.permissions:
        if item.item_id not in proposed or item.model_dump(exclude={"write_mode"}) != proposed[item.item_id].model_dump(exclude={"write_mode"}):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "提案中的权限与候选不一致")
    return value, states


def save_approval_mappings(work, source, proposal_id, boundary_decision_id, permission_plans, action_plans):
    if source is None:
        return
    value, states = source
    candidate_ids = {item.item_id for item in value.content.permissions}
    scenes = {item.scenario_id: item for item in getattr(value.content, "scenarios", ())}
    actions = {item.item.item_id: item for item in action_plans}
    for plan in permission_plans:
        if plan.item.item_id not in candidate_ids:
            continue
        decision_ids = [state["decision"].decision_id for state in states if state["status"] == "SELECT"
            and any(item.item_id == plan.item.item_id for item in scenes[state["scenario_id"]].options[0].replacements)]
        formal = work.permission_intents.get_revision(plan.intent_id, plan.revision)
        actors = {plan.item.subject_actor_item_id: CandidateActorReference(item_id=plan.item.subject_actor_item_id,
            actor_id=formal.subject_actor_id, revision=formal.subject_actor_revision),
            plan.item.resource_owner_actor_item_id: CandidateActorReference(item_id=plan.item.resource_owner_actor_item_id,
            actor_id=formal.resource_owner_actor_id, revision=formal.resource_owner_actor_revision)}
        action = actions[plan.item.business_action_item_id]
        # effect ID在批准时已明确生成；不能事后按显示名或两个已排序列表的位置反推。
        entities = CandidateApprovalEntities(actors=tuple(actors.values()),
            action=CandidateActionReference(item_id=plan.item.business_action_item_id,
                action_id=formal.business_action_id, revision=formal.action_revision),
            effects=tuple(CandidateEffectReference(item_id=item_id,effect_id=action.effect_ids[item_id]) for item_id in plan.item.protected_effect_item_ids))
        work.rule_candidates.add_approval_mapping(proposal_id=proposal_id, permission_item_id=plan.item.item_id,
            intent_id=plan.intent_id, intent_revision=plan.revision, intent_hash=formal.intent_hash,
            boundary_decision_id=boundary_decision_id, reused=not plan.write_revision, scenario_decision_ids=decision_ids, entity_references=entities)
