# =============================================================================
# 确定性结果业务投影
#
# 定位
#   已验证 Run、Finding 与 Evidence 之上的唯一人类结果表达。
#
# 职责
#   汇总本次范围与三态结论｜解释权限问题的表面结果和真实影响｜提供 GUI/CLI 共用只读 View
#
# 边界
#   只翻译已发布事实，不重新执行 Verification，不修改 Finding、Evidence 或 Report。
#
# 调用链
#   API / CLI / Report → ResultPresentationBuilder → PublishedResultReader / FindingQueries
# =============================================================================

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import RunLifecycle, RunVerdict
from product.backend.core.verification.facts import ObservedEffect, TemporalClosure
from product.protocols.observer import ObserverOutcomeStatus, ObserverType


class _PresentationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class PresentedCaseVerdict(StrEnum):
    SAFE = "SAFE"
    VULNERABLE = "VULNERABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class ResultEvidenceSource(_PresentationModel):
    """把单个已发布观察来源投影为只读、可解释状态。"""

    observer_type: ObserverType
    label: str = Field(min_length=1, max_length=80)
    role: Literal["KEY", "SUPPORTING"]
    status: Literal["FOUND", "NOT_FOUND", "UNAVAILABLE"]
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=8192)


class ResultPresentationIssue(_PresentationModel):
    finding_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    subject_group: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=160)
    resource: str = Field(min_length=1, max_length=160)
    relation: str = Field(min_length=1, max_length=160)
    expectation: str = Field(min_length=1, max_length=240)
    surface_result: str = Field(min_length=1, max_length=240)
    actual_result: str = Field(min_length=1, max_length=240)
    conclusion: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=480)
    planned_identity_id: str = Field(min_length=1, max_length=64)
    planned_identity_label: str | None = Field(default=None, min_length=1, max_length=128)
    actual_identity_status: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    actual_identity_label: None = None
    severity: Literal["unknown", "low", "medium", "high", "critical"]
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=8192)
    evidence_sources: tuple[ResultEvidenceSource, ...] = Field(
        default=(),
        max_length=256,
    )
    verdict: PresentedCaseVerdict
    occurrence_status: str | None = Field(default=None, max_length=32)


class ResultPresentation(_PresentationModel):
    run_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=64)
    project_name: str = Field(min_length=1, max_length=128)
    run_lifecycle: RunLifecycle
    verdict: RunVerdict | None
    headline: str = Field(min_length=1, max_length=160)
    scope_statement: str = Field(min_length=1, max_length=320)
    checked_count: int = Field(ge=0)
    safe_count: int = Field(ge=0)
    problem_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    uncovered_count: int = Field(ge=0)
    execution_problem: str | None = Field(default=None, max_length=320)
    issues: tuple[ResultPresentationIssue, ...] = ()
    limitations: tuple[str, ...] = Field(default=(), max_length=128)


class ResultPresentationBuilder:
    """只接受完整性已验证的 publication，并组合现有只读 Finding 查询。"""

    def __init__(self, reader, findings) -> None:
        self._reader = reader
        self._findings = findings

    def build(self, run_id: str) -> ResultPresentation:
        """生成同一 Run 的唯一业务投影；读取失败由既有稳定错误表达。"""

        view = self._reader.read(run_id)
        snapshot = self._reader.request_snapshot(view)
        finding_views = self._findings.findings_for_run(run_id)
        return build_result_presentation(view, snapshot, finding_views)


def build_result_presentation(
    view: Any,
    snapshot: Any,
    finding_views: list[dict[str, Any]],
) -> ResultPresentation:
    """纯翻译可信结果事实；不会根据文本、状态码或 Occurrence 重算安全结论。"""

    result = view.publication.result
    evidence_items = tuple(result.evidence)
    evidence_by_id = {item.evidence_id: item for item in evidence_items}
    issues = tuple(
        sorted(
            (
                _issue(item, evidence_by_id, snapshot)
                for item in finding_views
            ),
            key=lambda item: item.finding_id,
        )
    )
    case_verdicts = tuple(_value(item.verdict) for item in evidence_items)
    safe_count = case_verdicts.count(PresentedCaseVerdict.SAFE.value)
    problem_count = case_verdicts.count(PresentedCaseVerdict.VULNERABLE.value)
    inconclusive_count = case_verdicts.count(PresentedCaseVerdict.INCONCLUSIVE.value)
    uncovered_count = int(result.coverage_gap_count)
    lifecycle = view.run.lifecycle
    verdict = result.verdict
    limitations: list[str] = []
    if uncovered_count:
        limitations.append(
            f"仍有 {uncovered_count} 项权限要求未覆盖；本次结论只适用于实际执行范围。"
        )
    if inconclusive_count:
        limitations.append(
            f"有 {inconclusive_count} 项因真实状态观察不完整或不可靠而证据不足。"
        )
    if lifecycle is RunLifecycle.SAFETY_STOPPED:
        limitations.append("检查为保护目标现场而安全停止；未完成范围不形成安全结论。")
    execution_problem = _execution_problem(lifecycle)
    return ResultPresentation(
        run_id=view.run.run_id,
        project_id=view.run.project_id,
        project_name=snapshot.project_name,
        run_lifecycle=lifecycle,
        verdict=verdict,
        headline=_headline(verdict, lifecycle),
        scope_statement=_scope_statement(verdict, lifecycle),
        checked_count=len(evidence_items),
        safe_count=safe_count,
        problem_count=problem_count,
        inconclusive_count=inconclusive_count,
        uncovered_count=uncovered_count,
        execution_problem=execution_problem,
        issues=issues,
        limitations=tuple(limitations),
    )


_ROLE_LABELS = {
    "admin": "管理员",
    "member": "成员",
    "user": "普通用户",
    "guest": "访客",
    "owner": "所有者",
    "peer": "同级用户",
}
_ACTION_LABELS = {
    "create": "创建",
    "read": "读取",
    "view": "查看",
    "list": "列出",
    "modify": "修改",
    "update": "修改",
    "write": "写入",
    "delete": "删除",
    "approve": "审批",
}
_RESOURCE_LABELS = {"document": "文档"}
_RELATION_LABELS = {
    "OWNS": "拥有",
    "SAME_TENANT": "同一租户",
    "BELONGS_TO": "属于",
    "MEMBER_OF": "隶属",
}


def _issue(
    item: dict[str, Any],
    evidence_by_id: dict[str, Any],
    snapshot: Any,
) -> ResultPresentationIssue:
    finding = item.get("finding") or {}
    identity = finding.get("identity") or {}
    occurrence = item.get("occurrence") or {}
    finding_id = str(finding.get("finding_id") or identity.get("finding_id") or "")
    evidence_refs = tuple(str(value) for value in occurrence.get("evidence_refs") or ())
    verdict = PresentedCaseVerdict(str(occurrence.get("verdict")))
    evidence = _representative_evidence(evidence_refs, evidence_by_id, verdict)
    planned_identity_id, planned_identity_label = _planned_identity(snapshot, evidence)
    expectation = _expectation(evidence)
    subject_group = _subject_group(identity, expectation)
    action = _action(identity)
    resource = _resource(identity)
    relation = _relation(identity)
    return ResultPresentationIssue(
        finding_id=finding_id,
        title=_title(subject_group, action, resource, verdict),
        subject_group=subject_group,
        action=action,
        resource=resource,
        relation=relation,
        expectation=expectation,
        surface_result=_surface_result(evidence),
        actual_result=_actual_result(evidence),
        conclusion=_case_conclusion(verdict),
        explanation=_explanation(evidence, verdict),
        planned_identity_id=planned_identity_id,
        planned_identity_label=planned_identity_label,
        severity=_severity(occurrence.get("severity")),
        evidence_refs=evidence_refs,
        evidence_sources=_evidence_sources(snapshot, evidence),
        verdict=verdict,
        occurrence_status=(
            str(occurrence["status"])
            if occurrence.get("status") is not None
            else None
        ),
    )


_SOURCE_PRESENTATION = {
    ObserverType.OWNER_API: (0, "目标业务状态"),
    ObserverType.READ_ONLY_SQLITE: (1, "只读数据库"),
    ObserverType.STRUCTURED_AUDIT_LOG: (2, "结构化审计记录"),
    ObserverType.ASYNC_TASK_STATUS: (3, "后台任务"),
    ObserverType.AZURE_QUEUE_PEEK: (4, "消息通道"),
    ObserverType.AZURE_BLOB_OBJECT: (5, "最终对象/文件"),
}


def _evidence_sources(
    snapshot: Any,
    evidence: Any | None,
) -> tuple[ResultEvidenceSource, ...]:
    """只按冻结 EffectBinding 取角色，并按已发布事实翻译来源状态。"""

    if evidence is None:
        return ()
    case = getattr(evidence, "case_snapshot", None)
    action_id = str(getattr(case, "action_id", "") or "")
    action = next(
        (
            item
            for item in getattr(getattr(snapshot, "contract", None), "actions", ())
            if str(getattr(item, "action_id", "")) == action_id
        ),
        None,
    )
    if action is None:
        raise JiejianError(
            ErrorCode.ARTIFACT_FENCE,
            "结果观察来源与冻结 Action 不一致",
        )
    effect_bindings = {
        str(getattr(item, "effect_id", "")): item
        for item in getattr(snapshot, "effect_bindings", ())
    }
    roles: dict[str, Literal["KEY", "SUPPORTING"]] = {}
    for effect_id in getattr(action, "effect_ids", ()):
        effect_binding = effect_bindings.get(str(effect_id))
        if effect_binding is None:
            raise JiejianError(
                ErrorCode.ARTIFACT_FENCE,
                "结果观察来源缺少冻结 EffectBinding",
            )
        for requirement_id in getattr(effect_binding, "required_channels", ()):
            _assign_source_role(roles, str(requirement_id), "KEY")
        for requirement_id in getattr(effect_binding, "corroborating_channels", ()):
            _assign_source_role(roles, str(requirement_id), "SUPPORTING")

    snapshot_bindings = {
        str(getattr(item, "requirement_id", "")): item
        for item in getattr(snapshot, "observer_bindings", ())
    }
    evidence_bindings = {
        str(getattr(item, "requirement_id", "")): item
        for item in getattr(evidence, "requirement_bindings", ())
    }
    evidence_id = str(getattr(evidence, "evidence_id", "") or "")
    sources: list[ResultEvidenceSource] = []
    for requirement_id, role in roles.items():
        binding = snapshot_bindings.get(requirement_id)
        observer_type = getattr(binding, "observer_type", None)
        if binding is None or observer_type not in _SOURCE_PRESENTATION:
            raise JiejianError(
                ErrorCode.ARTIFACT_FENCE,
                "结果观察来源缺少冻结 ObserverBinding",
            )
        _, label = _SOURCE_PRESENTATION[observer_type]
        published_binding = evidence_bindings.get(requirement_id)
        binding_published = bool(
            published_binding is not None
            and getattr(published_binding, "observer_id", None)
            == getattr(binding, "observer_id", None)
            and getattr(published_binding, "observer_type", None) is observer_type
        )
        sources.append(
            ResultEvidenceSource(
                observer_type=observer_type,
                label=label,
                role=role,
                status=_evidence_source_status(
                    evidence,
                    requirement_id=requirement_id,
                    observer_id=str(getattr(binding, "observer_id", "") or ""),
                    required=role == "KEY",
                    binding_published=binding_published,
                ),
                evidence_refs=(evidence_id,) if binding_published and evidence_id else (),
            )
        )
    return tuple(
        sorted(
            sources,
            key=lambda item: _SOURCE_PRESENTATION[item.observer_type][0],
        )
    )


def _assign_source_role(
    roles: dict[str, Literal["KEY", "SUPPORTING"]],
    requirement_id: str,
    role: Literal["KEY", "SUPPORTING"],
) -> None:
    current = roles.get(requirement_id)
    if current is not None and current != role:
        raise JiejianError(
            ErrorCode.ARTIFACT_FENCE,
            "同一观察来源在冻结结果中具有冲突角色",
        )
    roles.setdefault(requirement_id, role)


def _evidence_source_status(
    evidence: Any,
    *,
    requirement_id: str,
    observer_id: str,
    required: bool,
    binding_published: bool,
) -> Literal["FOUND", "NOT_FOUND", "UNAVAILABLE"]:
    if not binding_published:
        return "UNAVAILABLE"
    outcome = next(
        (
            item
            for item in getattr(evidence, "outcomes", ())
            if str(getattr(item, "observer_id", "")) == observer_id
        ),
        None,
    )
    if (
        outcome is None
        or _value(getattr(outcome, "status", None))
        != ObserverOutcomeStatus.AVAILABLE.value
        or bool(getattr(outcome, "required", False)) is not required
    ):
        return "UNAVAILABLE"
    resource_ids = {
        str(value)
        for value in getattr(getattr(evidence, "case_snapshot", None), "resource_ids", ())
    }
    facts = tuple(
        item
        for item in getattr(evidence, "observation_facts", ())
        if str(getattr(item, "requirement_id", "")) == requirement_id
    )
    if (
        not resource_ids
        or {str(getattr(item, "resource_id", "")) for item in facts}
        != resource_ids
    ):
        return "UNAVAILABLE"
    trustworthy = tuple(
        item
        for item in facts
        if bool(getattr(item, "complete", False))
        and bool(getattr(item, "reliable", False))
        and bool(getattr(item, "correlated", False))
    )
    if len(trustworthy) != len(facts):
        return "UNAVAILABLE"
    if any(
        _value(getattr(item, "effect", None)) == ObservedEffect.CONFIRMED.value
        for item in trustworthy
    ):
        return "FOUND"
    if trustworthy and all(
        _value(getattr(item, "effect", None)) == ObservedEffect.ABSENT.value
        and _value(getattr(item, "temporal_closure", None))
        == TemporalClosure.CLOSED.value
        for item in trustworthy
    ):
        return "NOT_FOUND"
    return "UNAVAILABLE"


def _planned_identity(snapshot: Any, evidence: Any | None) -> tuple[str, str | None]:
    """只从冻结请求和代表性 Evidence 还原计划身份，不推断服务器实际身份。"""

    subject_id = str(
        getattr(getattr(evidence, "case_snapshot", None), "subject_id", "") or ""
    )
    binding = next(
        (
            item
            for item in getattr(snapshot, "subject_bindings", ())
            if str(getattr(item, "subject_id", "")) == subject_id
        ),
        None,
    )
    identity_id = str(getattr(binding, "identity_id", "") or "")
    identity = next(
        (
            item
            for item in getattr(snapshot, "identities", ())
            if str(getattr(item, "identity_id", "")) == identity_id
        ),
        None,
    )
    if not subject_id or binding is None or identity is None:
        raise JiejianError(
            ErrorCode.ARTIFACT_FENCE,
            "结果身份绑定与冻结执行请求不一致",
        )
    label = getattr(identity, "label", None)
    return identity_id, str(label) if label is not None else None


def _representative_evidence(
    evidence_refs: tuple[str, ...],
    evidence_by_id: dict[str, Any],
    verdict: PresentedCaseVerdict,
) -> Any | None:
    selected = tuple(
        evidence_by_id[value]
        for value in evidence_refs
        if value in evidence_by_id
    )
    return next(
        (item for item in selected if _value(item.verdict) == verdict.value),
        selected[0] if selected else None,
    )


def _expectation(evidence: Any | None) -> str:
    values = {
        _value(item)
        for item in getattr(getattr(evidence, "case_snapshot", None), "expectations", ())
    }
    if "DENY" in values:
        return "不应允许这次操作，资源也不应发生变化"
    if "ALLOW" in values:
        return "应允许这次操作，并完成预期的资源变化"
    return "按当前权限规则执行"


def _surface_result(evidence: Any | None) -> str:
    outcome = _value(getattr(getattr(evidence, "execution_fact", None), "outcome", None))
    return {
        "DENIED": "页面或接口显示已拒绝",
        "ACCEPTED": "页面或接口显示已接受",
        "FAILED": "操作执行失败",
        "UNKNOWN": "表面结果无法确定",
    }.get(outcome, "表面结果未提供")


def _actual_result(evidence: Any | None) -> str:
    effect_states = {
        _value(item.state)
        for item in getattr(evidence, "security_effect_facts", ())
    }
    if not effect_states:
        effect_states = {
            _value(item.effect)
            for item in getattr(evidence, "observation_facts", ())
        }
    if "CONFIRMED" in effect_states:
        return "真实资源已经发生变化"
    if effect_states and effect_states == {"ABSENT"}:
        return "真实资源没有发生变化"
    return "真实资源状态尚不能可靠确认"


def _explanation(
    evidence: Any | None,
    verdict: PresentedCaseVerdict,
) -> str:
    outcome = _value(getattr(getattr(evidence, "execution_fact", None), "outcome", None))
    changed = _actual_result(evidence) == "真实资源已经发生变化"
    if verdict is PresentedCaseVerdict.VULNERABLE and outcome == "DENIED" and changed:
        return (
            "页面或接口虽然显示已拒绝，但外部可信观察确认真实资源已经变化；"
            "权限限制没有真正阻止修改，表面拒绝没有阻止真实副作用。"
        )
    if verdict is PresentedCaseVerdict.VULNERABLE and changed:
        return "这次操作产生了权限规则不允许的真实资源变化，因此构成权限问题。"
    if verdict is PresentedCaseVerdict.INCONCLUSIVE:
        return "必需观察不完整或不可靠，当前证据不足以确认资源是否按权限规则变化。"
    return "表面执行结果与真实资源观察共同支持当前结论。"


def _subject_group(identity: dict[str, Any], expectation: str) -> str:
    role = _prefixed(identity.get("subject_class"), "role:")
    label = _ROLE_LABELS.get(role or "")
    if label:
        return f"{label}账号"
    return "不应有权限的账号" if expectation.startswith("不应允许") else "应有权限的账号"


def _action(identity: dict[str, Any]) -> str:
    return _ACTION_LABELS.get(str(identity.get("action") or ""), "受保护业务动作")


def _resource(identity: dict[str, Any]) -> str:
    resource_type = _prefixed(identity.get("resource_class"), "type:")
    return _RESOURCE_LABELS.get(resource_type or "", "受保护资源")


def _relation(identity: dict[str, Any]) -> str:
    token = next(
        (
            value
            for value in _tokens(identity.get("resource_relation"))
            if value.startswith("relation:")
        ),
        "",
    )
    relation = token.rsplit(":", 1)[-1] if token else ""
    return _RELATION_LABELS.get(relation, "受权限规则约束")


def _prefixed(value: Any, prefix: str) -> str | None:
    token = next((item for item in _tokens(value) if item.startswith(prefix)), None)
    return None if token is None else token[len(prefix):]


def _tokens(value: Any) -> tuple[str, ...]:
    if isinstance(value, (tuple, list)):
        return tuple(str(item) for item in value)
    if isinstance(value, str) and value:
        return (value,)
    return ()


def _title(
    subject_group: str,
    action: str,
    resource: str,
    verdict: PresentedCaseVerdict,
) -> str:
    if verdict is PresentedCaseVerdict.VULNERABLE:
        return f"{subject_group}不应对{resource}执行{action}"
    if verdict is PresentedCaseVerdict.INCONCLUSIVE:
        return f"{action}{resource}的真实结果暂时无法确认"
    return f"{action}{resource}已符合权限预期"


def _case_conclusion(verdict: PresentedCaseVerdict) -> str:
    return {
        PresentedCaseVerdict.SAFE: "符合预期",
        PresentedCaseVerdict.VULNERABLE: "发现权限问题",
        PresentedCaseVerdict.INCONCLUSIVE: "证据不足",
    }[verdict]


def _headline(verdict: Any, lifecycle: RunLifecycle) -> str:
    if lifecycle is RunLifecycle.SAFETY_STOPPED:
        return "检查已安全停止"
    return {
        RunVerdict.PASS: "当前检查范围未发现确认问题",
        RunVerdict.BLOCK: "发现权限问题",
        RunVerdict.INCONCLUSIVE: "证据不足",
    }.get(verdict, "结果不可用")


def _scope_statement(verdict: Any, lifecycle: RunLifecycle) -> str:
    if lifecycle is RunLifecycle.SAFETY_STOPPED:
        return "检查没有完成全部计划；已形成的事实保留，但未执行范围不代表安全。"
    if verdict is RunVerdict.PASS:
        return "当前实际检查范围内未发现已确认权限问题；这不代表应用绝对安全。"
    if verdict is RunVerdict.INCONCLUSIVE:
        return "操作已经执行，但真实资源最终状态无法可靠确认；这不代表安全，也不代表已经确认漏洞。"
    if verdict is RunVerdict.BLOCK:
        return "可信执行与观察事实确认存在不符合权限预期的真实影响。"
    return "当前运行没有形成可用安全结论。"


def _execution_problem(lifecycle: RunLifecycle) -> str | None:
    if lifecycle is RunLifecycle.FAILED:
        return "检查执行失败，未形成可用安全结论。"
    if lifecycle is RunLifecycle.CANCELLED:
        return "检查已取消，未形成可用安全结论。"
    return None


def _severity(value: Any) -> Literal["unknown", "low", "medium", "high", "critical"]:
    normalized = str(value or "unknown").lower()
    if normalized in {"low", "medium", "high", "critical"}:
        return cast(Literal["low", "medium", "high", "critical"], normalized)
    return "unknown"


def _value(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))


__all__ = [
    "PresentedCaseVerdict",
    "ResultEvidenceSource",
    "ResultPresentation",
    "ResultPresentationBuilder",
    "ResultPresentationIssue",
    "build_result_presentation",
]
