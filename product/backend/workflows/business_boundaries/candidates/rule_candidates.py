# 对话规则的受控接入：候选可由Agent保存，转提案与批准仍由GUI沿普通边界处理。
from __future__ import annotations

import json
import time
from uuid import uuid4

from pydantic import ValidationError

from product.backend.core.boundaries.entities import boundary_sha256
from product.backend.core.boundaries.rule_candidates import RuleCandidateRevision, ReviewedRuleCandidateRevision, RuleCandidateSave, RuleCandidateContentInput, freeze_candidate_content
from product.backend.core.boundaries.rule_candidates import ScopedRuleCandidateRevision, GroupedRuleCandidateRevision, scoped_content, revised_candidate
from product.backend.core.boundaries.candidate_scope import scope_items, scope_issues, only_auxiliary_scope
from product.backend.workflows.business_boundaries.candidates.scope import decide_scope, decide_scope_batch, merge_content, protect_scope, issue_tasks
from product.backend.workflows.business_boundaries.candidates.coverage import coverage_items
from product.backend.core.boundaries.candidate_reviews import BoundaryReviewCommand, BoundaryReviewRecord, boundary_review_items
from product.backend.workflows.business_boundaries.candidates.reviews import protect_review_sources, project_review_gaps
from product.backend.core.boundaries.candidate_scenarios import RuleCandidateDecide, RuleCandidateDecision
from product.backend.workflows.business_boundaries.candidates.decisions import (
    CANDIDATE_REVISION_GUIDANCE, check_candidate_edit, decision_digest, pending_scenario_issues, scenario_state, selected_permission_issues,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.business_boundaries.models import (
    BoundaryMaintenanceActionItem, BoundaryMaintenanceActorItem, BoundaryMaintenanceCommand,
    BoundaryMaintenancePermissionItem,
)


class RuleCandidateService:
    def __init__(self, uow_factory, boundaries, *, preparation=None, clock_us=None):
        self._uow_factory, self._boundaries = uow_factory, boundaries
        self._preparation = preparation
        self._clock_us = clock_us or (lambda: time.time_ns() // 1000)

    def context(self, project_id: str, *, offset: int = 0, archived: bool = False, include_preparation: bool = True):
        if type(offset) is not int or offset < 0:
            raise JiejianError(ErrorCode.INPUT_INVALID, "候选列表位置无效")
        with self._uow_factory() as work:
            draft = self._boundaries.maintenance_draft(project_id, work=work, allow_empty=True)
            candidates = work.rule_candidates.list(project_id, offset=offset, limit=51, archived=archived)
            understanding = work.application_understanding.get(project_id)
            source_items = [] if understanding is None else [*understanding.role_candidates, *understanding.action_candidates]
            # 不输出源码摘要/绝对路径；这个不透明基线仅涵盖正式业务修订。
            result = {"project_id": project_id, "basis_id": "rb_" + draft.boundary_state_fingerprint,
                "candidate_input_schema": RuleCandidateSave.model_json_schema(),
                "revision_guidance": CANDIDATE_REVISION_GUIDANCE,
                "actors": draft.actors, "actions": draft.actions, "permissions": draft.permissions,
                "supported_relations": ["OWNS", "SAME_ROLE_OTHER_ACCOUNT", "OTHER_ROLE"],
                "supported_expectations": ["ALLOW", "DENY"],
                "limitations": ["不支持任意时间、金额、唯一性或并发约束", "保存候选不批准权限，不表示能够执行检查"],
                "modeling_guidance": [
                    "可一次保存权限候选与requirement_sources清单，不强制先提交空权限。区分USER原话、SOURCE源码线索、AGENT推断，由用户确认含义和本轮范围后审阅最终提案。发现接口不等于必须新增权限。",
                    "按可独立决定的业务目标组织来源，不按每个角色定义、接口或证据重复拆项。补充源码线索优先写入对应要求的解释；已保存的重复或辅助来源由用户在核对清单关联为补充依据，不静默删除。USER/SOURCE/AGENT只是来源标记，不等于已获用户确认。",
                    "界鉴支持集中勾选明确要求并一次保存；歧义单独核对。补充依据必须由用户关联到已确认业务要求，不为消除阻塞强迫源码线索选择IN_SCOPE。MCP不能代用户确认或提交scope-batch。",
                    "IN_SCOPE决定中的requirement才是已确认的含义；PREPARATION只用于登录/造数据/恢复，OUT_OF_SCOPE不新增本轮权限。必要合法对照关联同一业务要求，不能遗漏。",
                    "requirement_sources.permission_item_ids关联本候选权限；新增来源或修改原话解释需要重新确认。不能把检查窗口扩大成任意历史。",
                    "材料或覆盖问题可在coverage_suggestions中提供已核对的目标接口、权限和证明类型建议，供GUI中的人确认；无需让用户从零填写技术字段，建议不构成人的决定。",
                    "可分批保存同一候选：merge=true按稳定item_id合并，未提交的项保留；最终统一审阅，不因数量上限合并不同检查入口。单候选最多100动作、200权限、1MiB。",
                    "维护已有规则时先读取当前actors/actions/permissions，沿用item_id、稳定ID与expected_current_revision。新增、修改和停用均可提交候选；停用设effective_state=RETIRED，不通过漏传规则删除，其他规则与历史保留，仍需人批准。",
                    "正式业务边界为空时仍可保存首次CREATE候选；候选完成后由人审阅提案并批准，不需要先手工建立同一套边界。",
                    "DATA_DISCLOSURE必须列出真实披露的protected_projection；其他效果类型不填写字段投影。",
                    "授予、开放或撤回资源访问范围属于STATE_MUTATION，相应动作state_changing为true；读取实际凭据才属于CREDENTIAL_ACCESS。",
                    "曾经开放后又撤回的要求不能降为只检查最终状态。当前检查窗口内、主体和资源正确关联且来源完整的独立提交可证明状态变化；任意历史范围不能据此视为支持。",
                    "文件交付、数据披露和访问范围变化应分别列为效果。同一动作可产生多个效果，保持原始允许或禁止要求，不为保存成功删减受保护结果。",
                ],
                "source_summary": None if understanding is None else {
                    "roles": sum(not c.stale and c.decision == "CONFIRMED" for c in understanding.role_candidates),
                    "actions": sum(not c.stale and c.decision == "CONFIRMED" for c in understanding.action_candidates),
                    "pending": sum(c.stale or c.decision in {"PROPOSED", "REVIEW_REQUIRED"} for c in source_items),
                    "analyzed": understanding.analysis_completed_at_us is not None},
                "formal_permission_count": len(draft.permissions),
                "boundary_review_gaps": project_review_gaps(work, project_id),
                "candidates": [self._view(work, c, draft=draft, summary=True) for c in candidates[:50]],
                "next_offset": offset + 50 if len(candidates) > 50 else None}
        # 正式准备仍由原服务现场投影；读取上下文不生成绑定或执行目标。
        result["preparation"] = None if self._preparation is None or not include_preparation else self._preparation.get(project_id)
        return result

    def save(self, project_id: str, command: RuleCandidateSave, *, submitted_via: str):
        if submitted_via not in {"MCP", "LOCAL_GUI"}:
            raise JiejianError(ErrorCode.INPUT_INVALID, "候选提交渠道无效")
        fingerprint = boundary_sha256({"command": command.model_dump(mode="json"), "channel": submitted_via})
        with self._uow_factory() as work:
            work.acquire_write_lock()
            receipt = work.rule_candidates.receipt(project_id, "SAVE", command.operation_id)
            if receipt:
                self._same_request(receipt, fingerprint)
                return self._view(work, self._required(work, project_id, receipt[1], receipt[2]))
            draft = self._boundaries.maintenance_draft(project_id, work=work, allow_empty=True)
            self._current_basis(command.expected_basis_id, draft)
            current = None
            if command.candidate_id:
                current = self._required(work, project_id, command.candidate_id)
                if work.rule_candidates.visibility(command.candidate_id)["archived"]:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选已归档，请由用户恢复后再补充")
                if current.revision != command.expected_revision:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选已有新修订", details={"reason": "CONFLICT"})
            elif len(work.rule_candidates.list(project_id, limit=201)) >= 200:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选数量已达上限", details={"reason": "LIMIT_EXCEEDED"})
            content = scoped_content(merge_content(current, command.content) if command.merge else command.content)
            if current:
                check_candidate_edit(work, current, content)
                protect_review_sources(current, content)
                protect_scope(current, content)
            carried = {name: getattr(current, name, ()) for name in ('boundary_reviews', 'scope_decisions', 'coverage_links')}
            revision_model = GroupedRuleCandidateRevision if current is not None and current.schema_version == '5' else ScopedRuleCandidateRevision
            if revision_model is GroupedRuleCandidateRevision:
                carried['scope_references'] = current.scope_references
            value = revision_model(**carried, project_id=project_id,
                candidate_id=command.candidate_id or f"rcd_{uuid4().hex}",
                revision=(command.expected_revision or 0) + 1, basis_id=command.expected_basis_id,
                content=content, submitted_via=submitted_via, created_at_us=self._clock_us())
            # 每个选项只替换有限权限项；保存前验证所有选项的引用，不执行其中任何业务动作。
            for scenario in content.scenarios:
                for option in scenario.options:
                    replacements = {item.item_id: item for item in option.replacements}
                    changed = content.model_copy(update={"permissions": tuple(replacements.get(item.item_id, item) for item in content.permissions)})
                    self._merge(value.model_copy(update={"content": changed}), draft)
            work.rule_candidates.append(value, expected_revision=command.expected_revision)
            work.rule_candidates.add_receipt(project_id, "SAVE", command.operation_id, fingerprint, value)
            result = self._view(work, value)
            work.commit()
            return result

    def decide(self, project_id: str, candidate_id: str, command: RuleCandidateDecide):
        """仅由LOCAL_GUI调用；人的决定、候选修订及DECIDE回执原子落库。"""
        fingerprint = boundary_sha256({"candidate_id": candidate_id, "command": command.model_dump(mode="json")})
        with self._uow_factory() as work:
            work.acquire_write_lock()
            receipt = work.rule_candidates.receipt(project_id, "DECIDE", command.operation_id)
            if receipt:
                self._same_request(receipt, fingerprint)
                return self._view(work, self._required(work, project_id, receipt[1], receipt[2]))
            draft = self._boundaries.maintenance_draft(project_id, work=work, allow_empty=True)
            self._current_basis(command.expected_basis_id, draft)
            current = self._required(work, project_id, candidate_id)
            if work.rule_candidates.visibility(candidate_id)["archived"]:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "请先恢复候选再核对含义")
            if current.revision != command.expected_revision or current.basis_id != command.expected_basis_id:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选已经变化，请重新核对含义", details={"reason": "CONFLICT"})
            scenario = next((item for item in getattr(current.content, "scenarios", ()) if item.scenario_id == command.scenario_id), None)
            if scenario is None or scenario.scenario_fingerprint != command.scenario_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "这处含义已有变化，请重新读取")
            if command.action == "SELECT" and command.option_id not in {item.option_id for item in scenario.options}:
                raise JiejianError(ErrorCode.INPUT_INVALID, "选项不属于这处含义")
            decision = RuleCandidateDecision(**command.model_dump(), decision_id=f"rcdcn_{uuid4().hex}",
                project_id=project_id, candidate_id=candidate_id, output_revision=current.revision + 1,
                request_fingerprint=fingerprint, created_at_us=self._clock_us())
            _, replacements, _ = scenario_state(work, current, extra=decision)
            questions = tuple(question for question in current.content.unresolved_questions
                if not (command.action in {"SELECT", "DISMISS"} and question == scenario.question))
            content = current.content.model_copy(update={"permissions": tuple(replacements.get(item.item_id, item) for item in current.content.permissions),
                "unresolved_questions": questions})
            value = revised_candidate(current, revision=current.revision + 1,
                content=scoped_content(content), submitted_via="LOCAL_GUI", created_at_us=self._clock_us())
            self._merge(value, draft)
            work.rule_candidates.append(value, expected_revision=current.revision)
            work.rule_candidates.add_decision(decision)
            work.rule_candidates.add_receipt(project_id, "DECIDE", command.operation_id, fingerprint, value)
            result = self._view(work, value)
            work.commit()
            return result

    def review_boundary(self, project_id: str, candidate_id: str, command: BoundaryReviewCommand):
        """仅GUI写入人的范围判断；不改变权限正文，不将能力或证据缺口标为已验证。"""
        fingerprint = boundary_sha256({"kind": "BOUNDARY_REVIEW", "candidate_id": candidate_id, "command": command.model_dump(mode="json")})
        with self._uow_factory() as work:
            work.acquire_write_lock()
            receipt = work.rule_candidates.receipt(project_id, "DECIDE", command.operation_id)
            if receipt:
                self._same_request(receipt, fingerprint)
                return self._view(work, self._required(work, project_id, receipt[1], receipt[2]))
            current = self._required(work, project_id, candidate_id)
            draft = self._boundaries.maintenance_draft(project_id, work=work, allow_empty=True)
            self._current_basis(command.expected_basis_id, draft)
            if current.revision != command.expected_revision or current.basis_id != command.expected_basis_id:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选已变化，请读取最新内容后重新核对", details={"reason": "CONFLICT"})
            if work.rule_candidates.visibility(candidate_id)["archived"]:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "请先恢复候选再核对业务边界")
            issue = next((item for item in boundary_review_items(current) if item["issue_id"] == command.issue_id), None)
            if issue is None or issue["issue_fingerprint"] != command.issue_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "问题及其业务依据已变化，请重新读取")
            if issue["source"] == "unsupported_constraints" and command.outcome in {"NOT_SEPARATE_ACTION", "REPRESENTED_BY_RULES"}:
                raise JiejianError(ErrorCode.INPUT_INVALID, "接口合并或不单独建模不能消除能力与覆盖缺口")
            if not set(command.permission_item_ids) <= {item.item_id for item in current.content.permissions}:
                raise JiejianError(ErrorCode.INPUT_INVALID, "只能引用这份候选中已经存在的权限项")
            record = BoundaryReviewRecord(**command.model_dump(), decision_id="brd_" + uuid4().hex,
                source=issue["source"], text=issue["text"], output_revision=current.revision + 1, created_at_us=self._clock_us())
            records = tuple(item for item in getattr(current, "boundary_reviews", ()) if item.issue_id != command.issue_id) + (record,)
            # v1首次进入此入口只补空情境；不制造权限选项或原话摘录。
            content = current.content if hasattr(current.content, "scenarios") else freeze_candidate_content(
                RuleCandidateContentInput(**current.content.model_dump()))
            value = revised_candidate(current,
                revision=current.revision + 1, content=scoped_content(content),
                boundary_reviews=records, submitted_via="LOCAL_GUI", created_at_us=self._clock_us())
            work.rule_candidates.append(value, expected_revision=current.revision)
            work.rule_candidates.add_receipt(project_id, "DECIDE", command.operation_id, fingerprint, value)
            result = self._view(work, value)
            work.commit()
            return result

    def show(self, project_id: str, candidate_id: str, revision: int | None = None):
        with self._uow_factory() as work:
            return self._view(work, self._required(work, project_id, candidate_id, revision))

    def decide_scope(self, project_id, candidate_id, command):
        return decide_scope(self, project_id, candidate_id, command)

    def decide_scope_batch(self, project_id, candidate_id, command):
        return decide_scope_batch(self, project_id, candidate_id, command)

    def link_coverage(self, project_id, candidate_id, command):
        return decide_scope(self, project_id, candidate_id, command, coverage=True)

    def set_visibility(self, project_id: str, candidate_id: str, *, archived: bool, revision: int, expected_version: int):
        """GUI显式归档或恢复；展示状态与业务修订分离，未决提案不能隐藏。"""
        with self._uow_factory() as work:
            work.acquire_write_lock()
            value = self._required(work, project_id, candidate_id)
            if value.revision != revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选已有新修订，请重新读取")
            if archived and any(not work.business_boundaries.decision_for_proposal(proposal_id)
                for proposal_id in work.rule_candidates.proposal_ids(candidate_id)):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "这条候选还有待决定提案，请先审阅或放弃提案")
            result = work.rule_candidates.set_visibility(candidate_id, archived=archived,
                expected_version=expected_version, now_us=self._clock_us())
            work.commit()
            return result

    def preview(self, project_id: str, command):
        from product.backend.workflows.business_boundaries.candidates.preview import preview_rules
        with self._uow_factory() as work:
            return {"project_id": project_id, **preview_rules(work, project_id, command, self)}

    def operation(self, project_id: str, kind: str, operation_id: str):
        with self._uow_factory() as work:
            receipt = work.rule_candidates.receipt(project_id, kind, operation_id)
            if receipt is None:
                return {"status": "UNKNOWN", "operation_id": operation_id}
            return {"status": "FOUND", "operation_id": operation_id,
                "candidate": self._view(work, self._required(work, project_id, receipt[1], receipt[2]))}

    def propose(self, project_id: str, candidate_id: str, *, revision: int, operation_id: str):
        """仅供GUI路由调用；提案、来源关联、回执共用一个事务，绝不批准。"""
        fingerprint = boundary_sha256({"candidate_id": candidate_id, "revision": revision})
        with self._uow_factory() as work:
            work.acquire_write_lock()
            receipt = work.rule_candidates.receipt(project_id, "PROPOSE", operation_id)
            if receipt:
                self._same_request(receipt, fingerprint)
                return self._view(work, self._required(work, project_id, receipt[1], receipt[2]))
            value = self._required(work, project_id, candidate_id, revision)
            if work.rule_candidates.visibility(candidate_id)["archived"]:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "请先恢复候选再生成提案")
            head = self._required(work, project_id, candidate_id)
            if head.revision != revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "请审阅候选最新修订", details={"reason": "CONFLICT"})
            linked = work.rule_candidates.proposal_id(candidate_id, revision)
            if linked is None:
                view = self._view(work, value)
                if view["assessment"] != "REVIEWABLE":
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "先解决候选中的问题", details={"reason": view["assessment"]})
                draft = self._boundaries.maintenance_draft(project_id, work=work, allow_empty=True)
                proposal = self._boundaries.create_maintenance_proposal(project_id, self._merge(value, draft), work=work, allow_initial=True)
                states, _, _ = scenario_state(work, value)
                work.rule_candidates.link_proposal(candidate_id, revision, proposal.proposal.proposal_id,
                    content_hash=boundary_sha256(value.content.model_dump(mode="json")), decision_digest=decision_digest(states))
            work.rule_candidates.add_receipt(project_id, "PROPOSE", operation_id, fingerprint, value)
            result = self._view(work, value)
            work.commit()
            return result

    def _view(self, work, value, *, draft=None, summary=False):
        draft = draft or self._boundaries.maintenance_draft(value.project_id, work=work, allow_empty=True)
        issues = []
        content = value.content
        states, _, conflicts = scenario_state(work, value)
        issues.extend(pending_scenario_issues(states, conflicts))
        issues.extend(scope_issues(value))
        if value.basis_id != "rb_" + draft.boundary_state_fingerprint:
            issues.append({"code": "CONTEXT_STALE", "message": "正式规则已变化，需要重新核对候选"})
        review_items = boundary_review_items(value)
        coverage = coverage_items(value)
        planned = {item['issue_id'] for item in coverage if item['status'] == 'PLANNED'}
        pending = {(item["source"], item["text"]) for item in review_items if item["blocking"]}
        resolved = {(item["source"], item["text"]) for item in review_items if not item["blocking"] or item['issue_id'] in planned}
        resolved -= {(item['source'], item['text']) for item in review_items if item['blocking'] and item['issue_id'] not in planned}
        for index, text in enumerate(content.unsupported_constraints):
            if ("unsupported_constraints", text) not in resolved:
                issues.append({"code": "RULE_KIND_UNSUPPORTED", "message": text, "path": f"candidate.content.unsupported_constraints[{index}]"})
        for index, text in enumerate(content.unresolved_questions):
            if ("unresolved_questions", text) not in resolved:
                issues.append({"code": "NEEDS_CLARIFICATION", "message": text, "path": f"candidate.content.unresolved_questions[{index}]"})
        permission_ids = {item.item_id for item in content.permissions}
        known_ids = permission_ids | {item.item_id for item in draft.permissions}
        mapped = {item.permission_item_id for item in content.examples}
        if not content.actors and not draft.actors:
            issues.append({"code": "ROLE_REQUIRED", "message": "还没有业务角色，请沿用已确认的源码角色或补充角色含义"})
        if not content.actions and not draft.actions:
            issues.append({"code": "ACTION_REQUIRED", "message": "还没有业务动作，请补充动作及需要保护的结果"})
        if not content.permissions and not draft.permissions:
            issues.append({"code": "PERMISSION_REQUIRED", "message": "还没有权限要求，请说明谁可以或不可以对谁的资源执行这些动作"})
        if not content.permissions or not content.examples or permission_ids - mapped:
            missing = [item.item_id for item in content.permissions if item.item_id not in mapped]
            issues.append({"code": "PERMISSION_EXAMPLE_REQUIRED", "message": "权限例子不完整：每条拟确认权限（包括合法对照）都须在 examples 中有对应例子。请补齐例子，无需为此新增含义选项或删除权限。",
                "path": "candidate.content.examples", "permission_item_ids": missing})
        for example in content.examples:
            if example.permission_item_id not in known_ids:
                issues.append({"code": "EXAMPLE_NOT_COVERED", "message": example.uncovered_reason or "例子引用的权限不存在"})
        unchanged = False
        merged = None
        try:
            merged = self._merge(value, draft)
            issues.extend(selected_permission_issues(merged.permissions))
            unchanged = all({item.item_id: item for item in getattr(merged, name)}
                == {item.item_id: item for item in getattr(draft, name)} for name in ("actors", "actions", "permissions"))
        except (JiejianError, ValidationError):
            issues.append({"code": "AMBIGUOUS_REFERENCE", "message": "业务引用或当前修订不一致，请回到开发客户端中的 Agent 修订"})
        proposal_id = work.rule_candidates.proposal_id(value.candidate_id, value.revision)
        decision = None if proposal_id is None else work.business_boundaries.decision_for_proposal(proposal_id)
        scope_only = only_auxiliary_scope(value)
        if value.schema_version in {'4', '5'} and not content.permissions and (not scope_items(value) or any(item['status'] != 'CONFIRMED' for item in scope_items(value))):
            issues = [issue for issue in issues if issue['code'] not in {'ROLE_REQUIRED', 'ACTION_REQUIRED', 'PERMISSION_REQUIRED', 'PERMISSION_EXAMPLE_REQUIRED', 'REQUIREMENT_RULE_REQUIRED'}]
        if scope_only:
            issues = [issue for issue in issues if issue['code'] not in {'ROLE_REQUIRED', 'ACTION_REQUIRED', 'PERMISSION_REQUIRED', 'PERMISSION_EXAMPLE_REQUIRED'}]
        # 范围/覆盖确认也需要一次精确提案来源，即使权限正文沿用；否则无法冻结新范围。
        assessment = "DECIDED" if decision else "NEEDS_CHANGES" if issues else "ALREADY_CONFIRMED" if scope_only or unchanged and value.schema_version not in {'4', '5'} else "REVIEWABLE"
        visibility = work.rule_candidates.visibility(value.candidate_id)
        if summary:
            # 列表共用一份正式基线，不展开逐条材料库存和完整审阅正文。
            return {"candidate_id": value.candidate_id, "revision": value.revision,
                "original_text": content.original_text, "submitted_via": value.submitted_via,
                "created_at_us": value.created_at_us, "assessment": assessment,
                "counts": {name: len(getattr(content, name)) for name in ("actors", "actions", "permissions", "examples")},
                "issue_count": 0 if decision else len(issues), "proposal_id": proposal_id,
                "decision": None if decision is None else decision.decision, "visibility": visibility}
        # 已作决定的候选是历史输入；不能因自身批准推进基线而提示用户再次修改同一候选。
        return {"candidate": value, "assessment": assessment, "visibility": visibility,
            "scope_only": scope_only,
            "revision_guidance": CANDIDATE_REVISION_GUIDANCE,
            "issues": [] if decision else issues, "proposal_id": proposal_id, "decision": decision,
            "scenario_decisions": states,
            "boundary_reviews": review_items,
            "scope_review": scope_items(value),
            "coverage_review": coverage,
            "next_tasks": [] if decision else issue_tasks(issues, review_items),
            "meaning_context": {"actors": [] if merged is None else [{"item_id": item.item_id, "display_name": item.display_name} for item in merged.actors],
                "actions": [] if merged is None else [{"item_id": item.item_id, "display_name": item.display_name,
                    "effect_catalog": [{"item_id": effect.item_id, "business_label": effect.business_label} for effect in item.effects]} for item in merged.actions]},
            "approval_mappings": [] if proposal_id is None else work.rule_candidates.approval_mappings(proposal_id=proposal_id),
            "reuse": {"status": "HISTORICAL" if decision else "PREDICTION",
                "message": "这是当时的候选记录，当前准备以正式规则为准" if decision else "以下只列现有材料及可能的复用；批准后还要核对账号、实现与证明，当前不访问目标。",
                "actions": [] if decision else self._reuse_prediction(work, value, draft)},
            "review_url": f"#/permissions?project_id={value.project_id}&candidate={value.candidate_id}&revision={value.revision}"}

    def _reuse_prediction(self, work, value, draft):
        """只列精确业务引用的材料库存，不用名称匹配或材料存在推断可执行。"""
        try:
            merged = self._merge(value, draft)
        except (JiejianError, ValidationError):
            return []
        current = {item.item_id: item for item in draft.actions}
        used = {item.business_action_item_id for item in value.content.permissions}
        result = []
        for action in merged.actions:
            if action.item_id not in used:
                continue
            prior = current.get(action.item_id)
            if prior is None:
                result.append({"item_id": action.item_id, "display_name": action.display_name,
                    "status": "NEW_ACTION", "materials": [], "message": "新增动作，批准后准备账号、演示和证明。"})
                continue
            action_id, revision = prior.action_id, prior.expected_current_revision
            repo = work.action_preparation
            materials = []
            if repo.execution(action_id, revision):
                materials.append("EXECUTION")
            if repo.resources(action_id, revision):
                materials.append("RESOURCE")
            if any(effect.effect_id and repo.evidence(action_id, revision, effect.effect_id) for effect in prior.effects):
                materials.append("PROOF")
            if repo.recovery(action_id, revision):
                materials.append("RECOVERY")
            unchanged = action == prior
            result.append({"item_id": action.item_id, "display_name": action.display_name,
                "status": "MAY_REUSE" if unchanged and materials else "NEEDS_REVIEW" if materials else "MISSING",
                "materials": materials, "message": "动作定义未变；已有材料待按新规则核对。" if unchanged and materials
                    else "动作定义变化；保留旧材料，批准后核对受影响部分。" if materials
                    else "尚无该动作的准备材料。"})
        return result

    def _merge(self, value, draft):
        """把有界增量合入完整当前边界；write_mode由原维护规划器重新计算。"""
        self._current_basis(value.basis_id, draft)
        def merged(existing, incoming, model, identity):
            values = {item.item_id: item for item in existing}
            for proposed in incoming:
                data = proposed.model_dump(mode="json", exclude={"write_mode"})
                if "effect_catalog" in data:
                    data["effects"] = data.pop("effect_catalog")
                item = model.model_validate_json(json.dumps(data))
                current = values.get(item.item_id)
                formal_id = getattr(item, identity)
                if current is not None and getattr(current, identity) != formal_id:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "局部引用不能替换另一业务对象")
                if formal_id is not None and (current is None or current.expected_current_revision != item.expected_current_revision):
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前业务引用不匹配")
                values[item.item_id] = item
            return tuple(values.values())
        actors = merged(draft.actors, value.content.actors, BoundaryMaintenanceActorItem, "actor_id")
        actions = merged(draft.actions, value.content.actions, BoundaryMaintenanceActionItem, "action_id")
        permissions = merged(draft.permissions, value.content.permissions, BoundaryMaintenancePermissionItem, "intent_id")
        actor_ids, action_map = {item.item_id for item in actors}, {item.item_id: item for item in actions}
        for permission in permissions:
            action = action_map.get(permission.business_action_item_id)
            if (permission.subject_actor_item_id not in actor_ids or permission.resource_owner_actor_item_id not in actor_ids
                    or action is None or not set(permission.protected_effect_item_ids) <= {e.item_id for e in action.effects}):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "权限引用的主体、动作或效果不完整")
        return BoundaryMaintenanceCommand(expected_boundary_state_fingerprint=draft.boundary_state_fingerprint,
            actors=actors, actions=actions, permissions=permissions,
            provenance=f"对话规则候选 {value.candidate_id} 修订 {value.revision}；待本机用户确认")

    @staticmethod
    def _required(work, project_id, candidate_id, revision=None):
        value = work.rule_candidates.get(project_id, candidate_id, revision)
        if value is None:
            raise JiejianError(ErrorCode.BOUNDARY_PROPOSAL_NOT_FOUND, "规则候选不存在")
        return value

    @staticmethod
    def _same_request(receipt, fingerprint):
        if receipt[0] != fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "操作标识已用于不同内容", details={"reason": "CONFLICT"})

    @staticmethod
    def _current_basis(basis_id, draft):
        if basis_id != "rb_" + draft.boundary_state_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "正式规则已变化，请重新读取上下文", details={"reason": "CONTEXT_STALE"})
