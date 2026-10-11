# 把人的情境选择关联到精确候选与批准；所有调用都沿外层UoW，不自行提交。
from __future__ import annotations

from product.backend.core.boundaries.entities import boundary_sha256
from product.backend.core.boundaries.permissions import permission_relation_consistent
from product.backend.core.boundaries.rule_candidates import RuleCandidateRevision
from product.backend.core.boundaries.candidate_scenarios import CandidateApprovalEntities, CandidateActorReference, CandidateActionReference, CandidateEffectReference
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.boundaries.candidate_reviews import boundary_review_items
from product.backend.core.boundaries.candidate_scope import scope_issues
from product.backend.workflows.business_boundaries.candidates.coverage import coverage_items


CANDIDATE_REVISION_GUIDANCE = [
    "优先按next_tasks处理：USER由人核对，AGENT修订规则，CAPABILITY说明能力边界。不要把材料问题一律转为情境。",
    "先保存requirement_sources，再由人确认本轮范围；补充权限引用已确认要求，源码接口只作为线索。可用merge=true分批补充同一候选，未提交项不会删除。",
    "已关联具体权限、入口和时间范围的准备缺口可进入规则审阅；检查前仍核验实际计划与材料。PLANNED不是已覆盖或PASS。任意历史范围仍阻塞。",
    "不单独建模、基础接口归属及Agent额外推断可由用户在候选详情的“业务边界核对”直接确认；无需编造权限选项或原文摘录。",
    "原问题和unsupported_constraints原文持续保留。人工分类及保留的实际要求从boundary_reviews读取；准备前提、证据及覆盖缺口仍阻塞，不能用分类代替检查。",
    "修订前调用jiejian_rule_context，再用jiejian_rule_candidate_show不指定revision读取最新候选；保存携带最新expected_basis_id和expected_revision。",
    "逐条处理旧content.unresolved_questions：尚未处理的原样保留；转入scenarios时，question须逐字保留旧问题（包括标点），不能只保留大意或一次清空全部问题。",
    "先由Agent保存带情境的新修订，再由用户打开返回的review_url，在“含义核对”选择、纠正或暂存待定；保存情境前不要求用户在空白界面作决定。",
    "情境options只表达真实业务歧义，每组选项替换同一组现有权限项；replacements.item_id复用content.permissions中的item_id，不创建新的替换标识。",
    "original_excerpt须摘自original_text，occurrence为该摘录的出现序号。每处情境有2至4个真实选项；scenario_id在候选内唯一，option_id在情境内唯一。",
    "业务要求已明确时，不编造相反选项或把取证能力缺口改成业务选择。保留原始要求与未解决问题，向用户说明缺口；情境选择本身不会建立历史证据。",
    "unsupported_constraints与unresolved_questions分别处理；不能将真实不支持的要求移入情境后冒充已支持。用户未约定的允许不自动变成禁止，Agent额外增加的限制应说明并交由人纠正。",
    "原始允许、禁止及受保护结果必须保留。曾开放后撤回仍违规的要求不能降为只检查最终状态；内部文件与公开文件分别建模，不擅自增加隔离要求。",
    "响应未知时只用jiejian_rule_operation查询原SAVE操作键；明确拒绝时按报错定位修正并回读最新候选，不能通过新建候选、归档或删减要求绕过核对。",
]


def _edit_error(current, reason, message, issues, recovery):
    # 错误只带持久记录的索引与受控标识，原问题可能含秘密，不回显到异常正文。
    return JiejianError(ErrorCode.STATE_PRECONDITION, message, details={
        "reason": reason, "candidate_id": current.candidate_id, "revision": current.revision,
        "issues": issues, "recovery": recovery,
        "review_url": f"#/permissions?project_id={current.project_id}&candidate={current.candidate_id}&revision={current.revision}",
    })


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
    missing = []
    for index, question in enumerate(current.content.unresolved_questions):
        if question in incoming.unresolved_questions:
            continue
        resolved = any(scene.question == question and state_by_id[scene.scenario_id]["status"] in {"SELECT", "DISMISS"}
            for scene in old_scenes.values())
        if question not in new_questions and not resolved:
            missing.append({"code": "QUESTION_REVIEW_REQUIRED", "question_number": index + 1, "path": f"candidate.content.unresolved_questions[{index}]",
                "target_path": "candidate.content.scenarios[].question", "match": "EXACT_TEXT"})
    if missing:
        positions = "、".join(str(item["question_number"]) for item in missing)
        raise _edit_error(current, "CANDIDATE_QUESTION_REVIEW_REQUIRED",
            f"修订未保存：旧候选第 {positions} 条待核对问题被移除，但尚无对应情境或人的决定。",
            missing, "读取本错误revision对应的旧候选，按issues.path定位；保留未处理问题，或以逐字相同的question保存情境。保存成功后，用户再到候选详情的“含义核对”处理；原修订保持不变。")
    for index, (scenario_id, old) in enumerate(old_scenes.items()):
        new = incoming_scenes.get(scenario_id)
        if new is None and state_by_id[scenario_id]["status"] not in {"SELECT", "DISMISS"}:
            raise _edit_error(current, "CANDIDATE_SCENARIO_REVIEW_REQUIRED", "修订未保存：已有未决情境不能静默删除。",
                [{"code": "SCENARIO_REVIEW_REQUIRED", "path": f"candidate.content.scenarios[{index}]", "scenario_id": scenario_id}],
                "保留这处情境；请用户在候选详情的“含义核对”作选择或纠正。不适用时由用户填写原因并明确结束该问题，Agent不能代替人的决定。")
        if new is not None and new.scenario_fingerprint == old.scenario_fingerprint and state_by_id[scenario_id]["status"] == "SELECT":
            actual = {item.item_id: item for item in incoming.permissions}
            for option in old.options:
                if option.option_id == state_by_id[scenario_id]["decision"].option_id:
                    if any(item.item_id not in conflicts and actual.get(item.item_id) != replacements.get(item.item_id) for item in option.replacements):
                        raise _edit_error(current, "CANDIDATE_SELECTED_REQUIREMENT_CHANGED", "修订未保存：权限变化与已保存的人的选择不一致。",
                            [{"code": "SELECTED_REQUIREMENT_CHANGED", "path": f"candidate.content.scenarios[{index}]", "scenario_id": scenario_id}],
                            "保留已选择的权限要求；确需修改时，更新对应情境及选项后保存，再由用户重新核对，不能沿用旧选择。")


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
    planned = {item['issue_id'] for item in coverage_items(value) if item['status'] == 'PLANNED'}
    if scope_issues(value) or any(item["blocking"] and item['issue_id'] not in planned for item in boundary_review_items(value)):
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "业务边界仍有未决问题或未覆盖要求，不能批准这份提案")
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
