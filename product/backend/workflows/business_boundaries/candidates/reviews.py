# 人工核对进入项目后持续保存未决范围；归档和另建候选不能掩盖检查缺口。
from product.backend.core.boundaries.candidate_reviews import BoundaryReviewGap, boundary_review_items
from product.backend.core.boundaries.entities import boundary_sha256
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.business_boundaries.candidates.decisions import scenario_state
from product.backend.core.boundaries.candidate_scope import scope_issues, only_auxiliary_scope
from product.backend.workflows.business_boundaries.candidates.coverage import coverage_ready, coverage_items


def project_review_gaps(work, project_id, *, plan=None, bundle=None):
    result = []
    for reference in work.rule_candidates.head_references(project_id):
        candidate_id, revision = reference["candidate_id"], reference["revision"]
        value = work.rule_candidates.get(project_id, candidate_id, revision)
        # 旧版已有人工情境决定也表示此候选进入了人工核对，升级不丢失其剩余范围。
        if not getattr(value, "boundary_reviews", ()) and not getattr(value, 'scope_decisions', ()) and not work.rule_candidates.decisions(project_id, candidate_id, revision):
            continue
        proposal_id = work.rule_candidates.proposal_id(candidate_id, revision)
        decision = None if proposal_id is None else work.business_boundaries.decision_for_proposal(proposal_id)
        approved = decision is not None and decision.decision.value == 'APPROVED'
        candidate_gap_start = len(result)
        for issue in scope_issues(value):
            result.append(BoundaryReviewGap(candidate_id=candidate_id, revision=revision,
                issue_id='bri_'+boundary_sha256([candidate_id, issue]), message=issue['message'], status='NEEDS_DECISION',
                review_url=f'#/permissions?project_id={project_id}&candidate={candidate_id}&revision={revision}'))
        for item in boundary_review_items(value):
            if item["blocking"] and not coverage_ready(work, value, item['issue_id'], plan, bundle):
                linked = next((row for row in coverage_items(value) if row['issue_id'] == item['issue_id'] and row['status'] == 'PLANNED'), None)
                result.append(BoundaryReviewGap(candidate_id=candidate_id, revision=revision,
                    issue_id=item["issue_id"], message=item["text"], status=item["status"],
                    next_url=f'#/tests?materials=1&project_id={project_id}' if approved and linked else None,
                    next_label='准备检查材料' if approved and linked else None,
                    review_url=f"#/permissions?project_id={project_id}&candidate={candidate_id}&revision={revision}"))
        states, _, conflicts = scenario_state(work, value)
        scenes = {item.scenario_id: item for item in getattr(value.content, "scenarios", ())}
        for state in states:
            if state["status"] not in {"SELECT", "DISMISS"} or conflicts:
                scene = scenes[state["scenario_id"]]
                result.append(BoundaryReviewGap(candidate_id=candidate_id, revision=revision,
                    issue_id="bri_" + boundary_sha256([candidate_id, scene.scenario_id]),
                    message=scene.question, status="NEEDS_DECISION",
                    review_url=f"#/permissions?project_id={project_id}&candidate={candidate_id}&revision={revision}"))
        # 尚有待澄清内容时只报当前缺口；全部明确后再提示批准，避免把下一步重复计为问题。
        if getattr(value, 'scope_decisions', ()) and not approved and not only_auxiliary_scope(value) and len(result) == candidate_gap_start:
            result.append(BoundaryReviewGap(candidate_id=candidate_id, revision=revision,
                issue_id='bri_'+boundary_sha256([candidate_id, 'AWAITING_APPROVAL']), message='已确认的本轮范围还没有对应的批准记录，请完成规则审阅。', status='NEEDS_APPROVAL',
                review_url=f'#/permissions?project_id={project_id}&candidate={candidate_id}&revision={revision}'))
    return tuple(result)


def protect_review_sources(current, incoming):
    """保留原始限制及已进入人工核对的问题；修改解释要形成新决定，不能清空数组。"""
    reviewed_questions = {item.text for item in getattr(current, "boundary_reviews", ()) if item.source == "unresolved_questions"}
    if any(item.question in reviewed_questions for item in incoming.scenarios):
        raise JiejianError(ErrorCode.STATE_PRECONDITION, "这条问题已有业务边界核对，请保留原问题并更新人工决定，不能改换入口隐藏缺口")
    for source in ("unsupported_constraints", "unresolved_questions"):
        old = list(getattr(current.content, source))
        if source == "unresolved_questions":
            reviewed = {item.text for item in getattr(current, "boundary_reviews", ()) if item.source == source}
            old = [text for text in old if text in reviewed]
        new = list(getattr(incoming, source))
        for text in old:
            if text not in new:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,
                    "原问题或限制不能静默移除。请保留原文，在候选详情的业务边界核对中说明实际要求。",
                    details={"reason": "BOUNDARY_REVIEW_REQUIRED", "path": f"candidate.content.{source}"})
            new.remove(text)
