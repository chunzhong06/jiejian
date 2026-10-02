# 对话规则的受控接入：候选可由Agent保存，转提案与批准仍由GUI沿普通边界处理。
from __future__ import annotations

import json
import time
from uuid import uuid4

from pydantic import ValidationError

from product.backend.core.boundaries.entities import boundary_sha256
from product.backend.core.boundaries.rule_candidates import RuleCandidateRevision, RuleCandidateSave
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

    def context(self, project_id: str, *, offset: int = 0):
        if type(offset) is not int or offset < 0:
            raise JiejianError(ErrorCode.INPUT_INVALID, "候选列表位置无效")
        with self._uow_factory() as work:
            draft = self._boundaries.maintenance_draft(project_id, work=work, allow_empty=True)
            candidates = work.rule_candidates.list(project_id, offset=offset, limit=51)
            # 不输出源码摘要/绝对路径；这个不透明基线仅涵盖正式业务修订。
            result = {"project_id": project_id, "basis_id": "rb_" + draft.boundary_state_fingerprint,
                "candidate_input_schema": RuleCandidateSave.model_json_schema(),
                "actors": draft.actors, "actions": draft.actions, "permissions": draft.permissions,
                "supported_relations": ["OWNS", "SAME_ROLE_OTHER_ACCOUNT", "OTHER_ROLE"],
                "supported_expectations": ["ALLOW", "DENY"],
                "limitations": ["不支持任意时间、金额、唯一性或并发约束", "保存候选不批准权限，不表示能够执行检查"],
                "candidates": [{"candidate_id": c.candidate_id, "revision": c.revision,
                    "original_text": c.content.original_text, "submitted_via": c.submitted_via,
                    "created_at_us": c.created_at_us} for c in candidates[:50]],
                "next_offset": offset + 50 if len(candidates) > 50 else None}
        # 正式准备仍由原服务现场投影；读取上下文不生成绑定或执行目标。
        result["preparation"] = None if self._preparation is None else self._preparation.get(project_id)
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
            if command.candidate_id:
                current = self._required(work, project_id, command.candidate_id)
                if current.revision != command.expected_revision:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选已有新修订", details={"reason": "CONFLICT"})
            elif len(work.rule_candidates.list(project_id, limit=201)) >= 200:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "候选数量已达上限", details={"reason": "LIMIT_EXCEEDED"})
            value = RuleCandidateRevision(project_id=project_id,
                candidate_id=command.candidate_id or f"rcd_{uuid4().hex}",
                revision=(command.expected_revision or 0) + 1, basis_id=command.expected_basis_id,
                content=command.content, submitted_via=submitted_via, created_at_us=self._clock_us())
            work.rule_candidates.append(value, expected_revision=command.expected_revision)
            work.rule_candidates.add_receipt(project_id, "SAVE", command.operation_id, fingerprint, value)
            result = self._view(work, value)
            work.commit()
            return result

    def show(self, project_id: str, candidate_id: str, revision: int | None = None):
        with self._uow_factory() as work:
            return self._view(work, self._required(work, project_id, candidate_id, revision))

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
                work.rule_candidates.link_proposal(candidate_id, revision, proposal.proposal.proposal_id)
            work.rule_candidates.add_receipt(project_id, "PROPOSE", operation_id, fingerprint, value)
            result = self._view(work, value)
            work.commit()
            return result

    def _view(self, work, value):
        draft = self._boundaries.maintenance_draft(value.project_id, work=work, allow_empty=True)
        issues = []
        content = value.content
        if value.basis_id != "rb_" + draft.boundary_state_fingerprint:
            issues.append({"code": "CONTEXT_STALE", "message": "正式规则已变化，需要重新核对候选"})
        for text in content.unsupported_constraints:
            issues.append({"code": "RULE_KIND_UNSUPPORTED", "message": text})
        for text in content.unresolved_questions:
            issues.append({"code": "NEEDS_CLARIFICATION", "message": text})
        permission_ids = {item.item_id for item in content.permissions}
        known_ids = permission_ids | {item.item_id for item in draft.permissions}
        mapped = {item.permission_item_id for item in content.examples}
        if not content.permissions or not content.examples or permission_ids - mapped:
            issues.append({"code": "NEEDS_CLARIFICATION", "message": "每条拟确认权限都需要具体情形说明"})
        for example in content.examples:
            if example.permission_item_id not in known_ids:
                issues.append({"code": "EXAMPLE_NOT_COVERED", "message": example.uncovered_reason or "例子引用的权限不存在"})
        unchanged = False
        try:
            merged = self._merge(value, draft)
            unchanged = all({item.item_id: item for item in getattr(merged, name)}
                == {item.item_id: item for item in getattr(draft, name)} for name in ("actors", "actions", "permissions"))
        except (JiejianError, ValidationError):
            issues.append({"code": "AMBIGUOUS_REFERENCE", "message": "业务引用或当前修订不一致，请回到原Agent修订"})
        proposal_id = work.rule_candidates.proposal_id(value.candidate_id, value.revision)
        decision = None if proposal_id is None else work.business_boundaries.decision_for_proposal(proposal_id)
        # 已作决定的候选是历史输入；不能因自身批准推进基线而提示用户再次修改同一候选。
        return {"candidate": value, "assessment": "DECIDED" if decision else "NEEDS_CHANGES" if issues else "ALREADY_CONFIRMED" if unchanged else "REVIEWABLE",
            "issues": [] if decision else issues, "proposal_id": proposal_id, "decision": decision,
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
