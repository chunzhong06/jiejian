# 从已发布事实形成 Claim Boundary、Evidence Explanation 与有限业务措辞。

from __future__ import annotations

from typing import Any, Literal

from product.backend.core.lifecycle import RunLifecycle, RunVerdict
from product.backend.core.repair import RepairVerificationStatus
from product.backend.core.verification.breakpoints import BreakpointPrecision
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect
from product.backend.core.verification.trace import ExecutionTrace, TraceEventKind
from product.protocols.execution_request import PermissionPolicySnapshot
from product.protocols.observer import ObserverType

from .models import (
    PresentedCaseVerdict,
    ResultClaimBoundary,
    ResultDiagnosis,
    ResultEvidenceExplanation,
    ResultEvidenceSource,
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

_SOURCE_PRESENTATION = {
    ObserverType.OWNER_API: (0, "目标业务状态"),
    ObserverType.READ_ONLY_SQLITE: (1, "只读数据库"),
    ObserverType.STRUCTURED_AUDIT_LOG: (2, "结构化审计记录"),
    ObserverType.ASYNC_TASK_STATUS: (3, "后台任务"),
    ObserverType.AZURE_QUEUE_PEEK: (4, "消息通道"),
    ObserverType.AZURE_BLOB_OBJECT: (5, "最终对象/文件"),
}

_SOURCE_STEPS = {
    ObserverType.OWNER_API: "确认目标业务状态",
    ObserverType.READ_ONLY_SQLITE: "核对持久化状态",
    ObserverType.STRUCTURED_AUDIT_LOG: "核对结构化过程记录",
    ObserverType.ASYNC_TASK_STATUS: "核对后台任务状态",
    ObserverType.AZURE_QUEUE_PEEK: "核对消息通道",
    ObserverType.AZURE_BLOB_OBJECT: "确认最终对象或文件",
}

_SOURCE_LIMITS = {
    ObserverType.OWNER_API: "不能单独证明实际执行身份或最早权限断裂位置。",
    ObserverType.READ_ONLY_SQLITE: "不能单独证明请求主体、完整异步过程或外部最终对象。",
    ObserverType.STRUCTURED_AUDIT_LOG: "不能单独证明日志之外的最终业务对象已经形成。",
    ObserverType.ASYNC_TASK_STATUS: "不能单独证明后台任务已经产生最终业务后果。",
    ObserverType.AZURE_QUEUE_PEEK: "不能单独证明 Worker 已执行或最终对象已经生成。",
    ObserverType.AZURE_BLOB_OBJECT: "不能单独证明执行主体或权限断裂发生在哪个环节。",
}

_SOURCE_FOUND_FACTS = {
    ObserverType.OWNER_API: "目标业务状态来源观察到相关状态：{business_effect_label}。",
    ObserverType.READ_ONLY_SQLITE: "只读数据库观察到本轮相关持久化记录。",
    ObserverType.STRUCTURED_AUDIT_LOG: (
        "结构化审计来源观察到本轮相关过程记录。"
    ),
    ObserverType.ASYNC_TASK_STATUS: "后台任务来源观察到本轮相关任务状态。",
    ObserverType.AZURE_QUEUE_PEEK: "消息通道来源观察到与本轮关联的队列消息。",
    ObserverType.AZURE_BLOB_OBJECT: (
        "最终对象或文件来源观察到相关对象：{business_effect_label}。"
    ),
}

_SOURCE_SUPPORTED_CLAIMS = {
    ObserverType.OWNER_API: "这项观察可以直接支持本轮目标业务状态的判断。",
    ObserverType.READ_ONLY_SQLITE: "这项观察支持本轮相关持久化状态已经形成。",
    ObserverType.STRUCTURED_AUDIT_LOG: "这项观察支持本轮相关过程节点确实发生。",
    ObserverType.ASYNC_TASK_STATUS: "这项观察支持本轮后台任务已经进入对应状态。",
    ObserverType.AZURE_QUEUE_PEEK: "这项观察支持本轮消息已经进入后台通道。",
    ObserverType.AZURE_BLOB_OBJECT: "这项观察可以直接支持本轮最终文件或对象是否存在的判断。",
}

def _business_effect_label(
    snapshot: Any,
    policy: PermissionPolicySnapshot,
    evidence: Any | None,
) -> str:
    """只在冻结 Contract 与权限快照唯一匹配时使用人的业务后果标签。"""

    case = getattr(evidence, "case_snapshot", None)
    action_id = str(getattr(case, "action_id", "") or "")
    contract = getattr(snapshot, "contract", None)
    action = next(
        (
            item
            for item in getattr(contract, "actions", ())
            if str(getattr(item, "action_id", "")) == action_id
        ),
        None,
    )
    effect_ids = set(getattr(action, "effect_ids", ()))
    effect_keys = {
        (
            _value(getattr(effect, "kind", None)),
            str(getattr(effect, "resource_type", "") or ""),
        )
        for effect in getattr(contract, "effects", ())
        if getattr(effect, "effect_id", None) in effect_ids
    }
    labels = {
        protected.business_label
        for entry in policy.entries
        for protected in entry.protected_effects
        if (protected.kind.value, protected.resource_type) in effect_keys
    }
    if len(labels) == 1:
        return next(iter(labels))
    return _actual_result(evidence)

def _claim_boundary(
    evidence: Any | None,
    *,
    business_effect_label: str,
    planned_identity_label: str,
    actual_identity_status: Literal["CONFIRMED", "UNAVAILABLE"],
    actual_identity_label: str | None,
    diagnosis: ResultDiagnosis | None,
) -> ResultClaimBoundary:
    outcome = _execution_outcome(evidence)
    effect = _business_effect_status(evidence)
    if effect is ObservedEffect.CONFIRMED:
        if actual_identity_status == "CONFIRMED" and actual_identity_label:
            supported = f"服务器已确认实际主体为{actual_identity_label}；{business_effect_label}。"
        else:
            supported = f"计划使用{planned_identity_label}凭据的实验中，{business_effect_label}。"
    elif effect is ObservedEffect.ABSENT:
        supported = "本轮关键来源已完整闭合，受保护业务后果被可靠确认为未发生。"
    else:
        supported = (
            f"{_surface_result(evidence)}；受保护业务后果当前仍无法可靠确认。"
        )

    unsupported: list[str] = []
    if effect is ObservedEffect.UNKNOWN:
        unsupported.append("不能宣称受保护业务后果没有发生，也不能据此宣称当前实现安全。")
    if outcome is ExecutionOutcome.DENIED and effect is not ObservedEffect.ABSENT:
        unsupported.append("不能把表面拒绝直接解释为后台副作用或最终业务后果未发生。")
    if actual_identity_status == "UNAVAILABLE":
        unsupported.append("不能宣称服务器已经独立确认实际执行主体。")
    if diagnosis is None:
        unsupported.append("不能宣称已经定位到具体权限断裂环节。")
    elif diagnosis.precision is BreakpointPrecision.VIOLATION_ONLY:
        unsupported.append("只能确认违规后果，不能宣称具体断裂位置。")
    elif diagnosis.precision is BreakpointPrecision.RANGE:
        unsupported.append("只能宣称断裂区间，不能宣称唯一精确断点。")
    unsupported.append("当前没有已发布的修复复验结论，不能宣称修复已经通过。")
    return ResultClaimBoundary(
        surface_response_status=outcome,
        business_effect_status=effect,
        actual_identity_status=actual_identity_status,
        breakpoint_precision=diagnosis.precision if diagnosis is not None else None,
        repair_status=None,
        supported_statement=supported,
        unsupported_statements=tuple(unsupported),
    )

def _claim_boundary_with_repair(
    boundary: ResultClaimBoundary,
    repair_status: RepairVerificationStatus | None,
) -> ResultClaimBoundary:
    statements = tuple(
        item
        for item in boundary.unsupported_statements
        if "修复" not in item
    )
    if repair_status is RepairVerificationStatus.NOT_VERIFIED:
        statements += ("正式复验尚未通过，不能宣称修复已经成立。",)
    elif repair_status is RepairVerificationStatus.INCONCLUSIVE:
        statements += ("修复复验证据不足，不能宣称修复已经成立。",)
    elif repair_status is None:
        statements += ("当前没有已发布的修复复验结论，不能宣称修复已经通过。",)
    return boundary.model_copy(
        update={
            "repair_status": repair_status,
            "unsupported_statements": statements,
        }
    )

def _evidence_explanations(
    evidence: Any | None,
    *,
    snapshot: Any,
    sources: tuple[ResultEvidenceSource, ...],
    trace: ExecutionTrace | None,
    diagnosis: ResultDiagnosis | None,
    business_effect_label: str,
) -> tuple[ResultEvidenceExplanation, ...]:
    if evidence is None:
        return ()
    evidence_id = str(getattr(evidence, "evidence_id", "") or "")
    outcome = _execution_outcome(evidence)
    surface_event = trace.events[0] if trace is not None and trace.events else None
    execution_fact = getattr(evidence, "execution_fact", None)
    output_hash = str(getattr(execution_fact, "output_hash", "") or "")
    explanations = [
        ResultEvidenceExplanation(
            label=_surface_result(evidence),
            source="执行表面响应",
            step="目标响应",
            proves={
                ExecutionOutcome.ACCEPTED: "目标在本轮返回了接受响应。",
                ExecutionOutcome.DENIED: "目标在本轮返回了拒绝响应。",
                ExecutionOutcome.FAILED: "本轮目标操作执行失败。",
                ExecutionOutcome.UNKNOWN: "本轮没有形成可确认的目标响应。",
            }[outcome],
            does_not_prove="不能单独证明后台副作用或最终业务后果是否发生。",
            relevance="来自当前 Run 的已发布 Evidence，并关联到本次检查项。",
            evidence_refs=(evidence_id,) if evidence_id else (),
            component=(surface_event.source_component if surface_event is not None else None),
            location=(
                f"{surface_event.source_component} · {surface_event.source_location}"
                if surface_event is not None
                else "本轮目标执行结果记录"
            ),
            provenance_type="EXECUTION_FACT",
            source_sha256=(output_hash if len(output_hash) == 64 else None),
            observed_at_us=(surface_event.recorded_at_us if surface_event is not None else None),
        )
    ]
    for source in sources:
        state_detail = {
            "FOUND": _SOURCE_FOUND_FACTS[source.observer_type].format(
                business_effect_label=business_effect_label
            ),
            "NOT_FOUND": "该已发布来源在完整、可靠、相关且闭合的范围内未观察到相关业务变化。",
            "UNAVAILABLE": "该来源未形成足以支持业务结论的完整可靠事实。",
        }[source.status]
        observer = _observer_context(
            snapshot,
            evidence,
            source.observer_type,
            observer_id=source.observer_id,
        )
        supported_claim = {
            "FOUND": _SOURCE_SUPPORTED_CLAIMS[source.observer_type],
            "NOT_FOUND": "在该来源完整、可靠、相关且闭合的范围内，可以支持“未观察到相关变化”。",
            "UNAVAILABLE": "只能确认该观察位置本轮不可用，不能据此推断业务后果不存在。",
        }[source.status]
        explanations.append(
            ResultEvidenceExplanation(
                label=state_detail,
                source=source.label,
                step=f"在“{source.label}”中{_SOURCE_STEPS[source.observer_type]}",
                proves=supported_claim,
                does_not_prove=_SOURCE_LIMITS[source.observer_type],
                relevance="该观察由本次检查发布，并通过同一证据引用关联到当前账号与业务动作。",
                evidence_refs=source.evidence_refs,
                location=observer["location"],
                observer_id=observer["observer_id"],
                observation_phase=observer["observation_phase"],
                provenance_type=observer["provenance_type"],
                adapter_version=observer["adapter_version"],
                source_sha256=observer["source_sha256"],
                observed_at_us=observer["observed_at_us"],
            )
        )
    identity_event = _identity_trace_event(trace)
    if identity_event is not None:
        explanations.append(
            ResultEvidenceExplanation(
                label="目标应用识别出的实际账号",
                source="实际执行身份",
                step="确认目标服务器实际主体",
                proves=f"本轮已发布 Trace 确认实际主体为 {identity_event.subject_id}。",
                does_not_prove="不能单独证明最终业务后果已经发生或权限检查位置。",
                relevance="来自当前 Run 同一检查项的已发布 ExecutionTrace。",
                evidence_refs=identity_event.evidence_refs,
                component=identity_event.source_component,
                location=f"{identity_event.source_component} · {identity_event.source_location}",
                provenance_type="EXECUTION_TRACE",
                observed_at_us=identity_event.recorded_at_us,
            )
        )
    if diagnosis is not None:
        breakpoint_event = _diagnosis_trace_event(trace, diagnosis)
        explanations.append(
            ResultEvidenceExplanation(
                label="权限断裂",
                source="权限断裂定位",
                step="定位权限断裂",
                proves=diagnosis.summary,
                does_not_prove={
                    BreakpointPrecision.EXACT: "不能脱离当前已发布 Trace 扩大到其他路径或其他运行。",
                    BreakpointPrecision.RANGE: "不能证明区间内唯一的精确断裂节点。",
                    BreakpointPrecision.VIOLATION_ONLY: "不能证明具体断裂类型或位置。",
                }[diagnosis.precision],
                relevance="由当前 Run 同一检查项的已发布 ResultDiagnosis 形成。",
                evidence_refs=diagnosis.evidence_refs,
                component=(breakpoint_event.source_component if breakpoint_event is not None else None),
                location=(
                    f"{breakpoint_event.source_component} · {breakpoint_event.source_location}"
                    if breakpoint_event is not None
                    else "本轮已发布执行路径"
                ),
                provenance_type="BREAKPOINT_LOCATOR",
                observed_at_us=(breakpoint_event.recorded_at_us if breakpoint_event is not None else None),
            )
        )
    return tuple(explanations)


def _observer_context(
    snapshot: Any,
    evidence: Any,
    observer_type: ObserverType,
    *,
    observer_id: str | None,
) -> dict[str, Any]:
    """按冻结 Binding 精确匹配 Observer，并公开无秘密的位置与采集来源。"""

    specs = tuple(
        item
        for item in getattr(snapshot, "observers", ())
        if getattr(item, "observer_type", None) is observer_type
        and (
            observer_id is None
            or str(getattr(item, "observer_id", "") or "") == observer_id
        )
    )
    if len(specs) != 1:
        return _empty_observer_context()
    spec = specs[0]
    resolved_observer_id = str(getattr(spec, "observer_id", "") or "")
    observations = tuple(
        item
        for item in getattr(evidence, "observations", ())
        if str(getattr(item, "observer_id", "") or "") == resolved_observer_id
    )
    observation = max(observations, key=_observation_sort_key, default=None)
    provenance = getattr(observation, "provenance", None)
    phase = _value(getattr(observation, "phase", None)) if observation is not None else None
    observed_at_us = getattr(getattr(observation, "window", None), "finished_at_us", None)
    source_sha256 = str(getattr(provenance, "source_sha256", "") or "")
    return {
        "location": _observer_location(spec, observation),
        "observer_id": resolved_observer_id or None,
        "observation_phase": phase or None,
        "provenance_type": _value(getattr(provenance, "provenance_type", None)) or None,
        "adapter_version": str(getattr(provenance, "adapter_version", "") or "") or None,
        "source_sha256": source_sha256 if len(source_sha256) == 64 else None,
        "observed_at_us": observed_at_us,
    }


def _empty_observer_context() -> dict[str, Any]:
    return {
        "location": None,
        "observer_id": None,
        "observation_phase": None,
        "provenance_type": None,
        "adapter_version": None,
        "source_sha256": None,
        "observed_at_us": None,
    }


def _observation_sort_key(observation: Any) -> tuple[int, int]:
    priority = {"BASELINE": 0, "BEFORE": 1, "AFTER": 2, "EVENTUAL": 3}
    phase = _value(getattr(observation, "phase", None))
    finished_at_us = int(getattr(getattr(observation, "window", None), "finished_at_us", 0) or 0)
    return priority.get(phase, -1), finished_at_us


def _observer_location(spec: Any, observation: Any | None) -> str | None:
    """把冻结 Locator 投影为可核验位置，同时排除所有凭据引用。"""

    target = getattr(spec, "target", None)
    locator = getattr(target, "locator", None)
    if locator is None:
        return None
    locator_type = str(getattr(locator, "locator_type", "") or "")
    correlation = getattr(observation, "correlation", None)
    resource_id = str(getattr(correlation, "resource_id", "") or "")
    request_marker = str(getattr(correlation, "request_marker", "") or "")
    if locator_type == "OWNER_API":
        path = str(getattr(locator, "relative_path_template", "") or "")
        return f"目标应用接口 {path.replace('{resource_id}', resource_id or '{resource_id}')}"
    if locator_type == "READ_ONLY_SQLITE":
        table = str(getattr(locator, "table_or_view", "") or "")
        query = str(getattr(locator, "query_template_id", "") or "")
        return f"SQLite 表或视图 {table} · 查询模板 {query}"
    if locator_type == "STRUCTURED_AUDIT_LOG":
        pattern = str(getattr(locator, "relative_file_pattern", "") or "")
        return f"结构化审计文件 {pattern}"
    if locator_type == "ASYNC_TASK_STATUS":
        base_url = str(getattr(locator, "base_url", "") or "").rstrip("/")
        path = str(getattr(locator, "relative_path_template", "") or "")
        return f"任务状态接口 {base_url}{path.replace('{request_marker}', request_marker or '{request_marker}')}"
    if locator_type == "AZURE_QUEUE_PEEK":
        service_url = str(getattr(locator, "service_url", "") or "").rstrip("/")
        queue_name = str(getattr(locator, "queue_name", "") or "")
        return f"只读队列 {service_url}/{queue_name}"
    if locator_type == "AZURE_BLOB_OBJECT":
        service_url = str(getattr(locator, "service_url", "") or "").rstrip("/")
        container = str(getattr(locator, "container_name", "") or "")
        prefix = str(getattr(locator, "prefix_template", "") or "").replace(
            "{request_marker}",
            request_marker or "{request_marker}",
        )
        return f"对象存储 {service_url}/{container}/{prefix}"
    target_id = str(getattr(target, "target_id", "") or "")
    return f"观察目标 {target_id}" if target_id else None

def _execution_outcome(evidence: Any | None) -> ExecutionOutcome:
    value = _value(getattr(getattr(evidence, "execution_fact", None), "outcome", None))
    try:
        return ExecutionOutcome(value)
    except ValueError:
        return ExecutionOutcome.UNKNOWN

def _business_effect_status(evidence: Any | None) -> ObservedEffect:
    states = {
        ObservedEffect(_value(item.state))
        for item in getattr(evidence, "security_effect_facts", ())
    }
    if ObservedEffect.CONFIRMED in states:
        return ObservedEffect.CONFIRMED
    if states and states == {ObservedEffect.ABSENT}:
        return ObservedEffect.ABSENT
    return ObservedEffect.UNKNOWN

def _identity_trace_event(trace: ExecutionTrace | None):
    if trace is None or not trace.complete:
        return None
    events = tuple(
        item
        for item in trace.events
        if item.kind is TraceEventKind.IDENTITY
        and item.subject_id is not None
        and item.evidence_refs
        and item.correlation_kind.value != "TEMPORAL"
    )
    subjects = {item.subject_id for item in events}
    return events[0] if events and len(subjects) == 1 else None

def _diagnosis_trace_event(
    trace: ExecutionTrace | None,
    diagnosis: ResultDiagnosis,
):
    if trace is None or diagnosis.precision is BreakpointPrecision.VIOLATION_ONLY:
        return None
    witness = diagnosis.minimal_witness[4]
    if witness.event_id is None:
        return None
    return next((item for item in trace.events if item.event_id == witness.event_id), None)

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

def _value(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))
