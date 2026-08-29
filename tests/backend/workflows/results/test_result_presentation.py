# 验证唯一结果业务投影只翻译已发布三态事实，不重算安全结论。

from __future__ import annotations

from types import SimpleNamespace

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import CaseVerdict, RunLifecycle, RunVerdict
from product.backend.core.verification.facts import (
    ExecutionOutcome,
    ObservedEffect,
    TemporalClosure,
)
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.results.presentation import build_result_presentation
from product.protocols import ObservationCompleteness, ObserverOutcomeStatus, ObserverType


RUN_ID = "run_" + "1" * 32
PROJECT_ID = "presentation-project"
FINDING_ID = "finding_" + "2" * 32
EVIDENCE_ID = "evidence_" + "3" * 32
ACTION_ID = "modify-document"
EFFECT_ID = "effect-document"
RESOURCE_ID = "owner-document"
REQUIREMENT_ID = "resource_state"
OBSERVER_ID = "owner-observer"
CASE_ID = "case-presentation"


def _view(
    verdict: RunVerdict | None,
    case_verdict: CaseVerdict,
    *,
    lifecycle: RunLifecycle = RunLifecycle.COMPLETED,
    outcome: ExecutionOutcome = ExecutionOutcome.ACCEPTED,
    effect: ObservedEffect = ObservedEffect.ABSENT,
    coverage_gap_count: int = 0,
):
    evidence = SimpleNamespace(
        evidence_id=EVIDENCE_ID,
        verdict=case_verdict,
        case_snapshot=SimpleNamespace(
            case_id=CASE_ID,
            subject_id="member-subject",
            action_id=ACTION_ID,
            resource_ids=(RESOURCE_ID,),
            expectations=(PermissionExpectation.DENY,),
        ),
        execution_fact=SimpleNamespace(outcome=outcome),
        security_effect_facts=(SimpleNamespace(state=effect),),
        requirement_bindings=(
            SimpleNamespace(
                requirement_id=REQUIREMENT_ID,
                observer_id=OBSERVER_ID,
                observer_type=ObserverType.OWNER_API,
            ),
        ),
        observation_facts=(
            SimpleNamespace(
                requirement_id=REQUIREMENT_ID,
                resource_id=RESOURCE_ID,
                effect=effect,
                complete=effect is not ObservedEffect.UNKNOWN,
                reliable=effect is not ObservedEffect.UNKNOWN,
                correlated=effect is not ObservedEffect.UNKNOWN,
                temporal_closure=(
                    TemporalClosure.CLOSED
                    if effect is not ObservedEffect.UNKNOWN
                    else TemporalClosure.OPEN
                ),
            ),
        ),
        outcomes=(
            SimpleNamespace(
                observer_id=OBSERVER_ID,
                required=True,
                status=(
                    ObserverOutcomeStatus.AVAILABLE
                    if effect is not ObservedEffect.UNKNOWN
                    else ObserverOutcomeStatus.INCONCLUSIVE
                ),
            ),
        ),
        observations=(),
    )
    result = SimpleNamespace(
        verdict=verdict,
        evidence=(evidence,),
        coverage_gap_count=coverage_gap_count,
    )
    return SimpleNamespace(
        run=SimpleNamespace(
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            lifecycle=lifecycle,
        ),
        publication=SimpleNamespace(result=result),
    )


def _snapshot(*, include_binding: bool = True):
    return SimpleNamespace(
        project_name="文档系统",
        contract=SimpleNamespace(
            actions=(SimpleNamespace(action_id=ACTION_ID, effect_ids=(EFFECT_ID,)),),
        ),
        effect_bindings=(
            SimpleNamespace(
                effect_id=EFFECT_ID,
                required_channels=(REQUIREMENT_ID,),
                corroborating_channels=(),
            ),
        ),
        observer_bindings=(
            SimpleNamespace(
                requirement_id=REQUIREMENT_ID,
                observer_id=OBSERVER_ID,
                observer_type=ObserverType.OWNER_API,
            ),
        ),
        identities=(
            SimpleNamespace(identity_id="member-account", label="成员测试账号"),
        ),
        subject_bindings=(
            SimpleNamespace(
                subject_id="member-subject",
                identity_id="member-account",
            ),
        )
        if include_binding
        else (),
    )


def _finding(verdict: CaseVerdict, *, status: str = "APPEARED") -> list[dict]:
    return [
        {
            "finding": {
                "finding_id": FINDING_ID,
                "identity": {
                    "subject_class": ["role:member"],
                    "action": "modify",
                    "resource_class": ["type:document"],
                    "resource_relation": ["relation:owns-document:OWNS"],
                },
            },
            "occurrence": {
                "status": status,
                "verdict": verdict.value,
                "severity": "critical",
                "evidence_refs": [EVIDENCE_ID],
            },
        }
    ]


def _six_source_facts(*, unavailable: bool = False):
    source_types = tuple(ObserverType)
    requirements = tuple(f"source_{index}" for index in range(len(source_types)))
    observer_ids = tuple(f"observer-{index}" for index in range(len(source_types)))
    effects = (
        ObservedEffect.CONFIRMED,
        ObservedEffect.ABSENT,
        ObservedEffect.UNKNOWN,
        ObservedEffect.CONFIRMED,
        ObservedEffect.ABSENT,
        ObservedEffect.UNKNOWN,
    )
    if unavailable:
        effects = tuple(ObservedEffect.UNKNOWN for _ in source_types)
    bindings = tuple(
        SimpleNamespace(
            requirement_id=requirement_id,
            observer_id=observer_id,
            observer_type=observer_type,
        )
        for requirement_id, observer_id, observer_type in zip(
            requirements,
            observer_ids,
            source_types,
            strict=True,
        )
    )
    facts = tuple(
        SimpleNamespace(
            requirement_id=requirement_id,
            resource_id=RESOURCE_ID,
            effect=effect,
            complete=effect is not ObservedEffect.UNKNOWN,
            reliable=effect is not ObservedEffect.UNKNOWN,
            correlated=effect is not ObservedEffect.UNKNOWN,
            temporal_closure=(
                TemporalClosure.CLOSED
                if effect is not ObservedEffect.UNKNOWN
                else TemporalClosure.OPEN
            ),
        )
        for requirement_id, effect in zip(requirements, effects, strict=True)
    )
    outcomes = tuple(
        SimpleNamespace(
            observer_id=observer_id,
            required=index in {0, 5},
            status=(
                ObserverOutcomeStatus.AVAILABLE
                if effect is not ObservedEffect.UNKNOWN
                else ObserverOutcomeStatus.INCONCLUSIVE
            ),
        )
        for index, (observer_id, effect) in enumerate(
            zip(observer_ids, effects, strict=True)
        )
    )
    snapshot = _snapshot()
    snapshot.observer_bindings = bindings
    snapshot.effect_bindings = (
        SimpleNamespace(
            effect_id=EFFECT_ID,
            required_channels=(requirements[0], requirements[5]),
            corroborating_channels=requirements[1:5],
        ),
    )
    return requirements, bindings, facts, outcomes, snapshot


def test_block_presentation_preserves_403_with_real_change_as_permission_problem() -> None:
    result = build_result_presentation(
        _view(
            RunVerdict.BLOCK,
            CaseVerdict.VULNERABLE,
            outcome=ExecutionOutcome.DENIED,
            effect=ObservedEffect.CONFIRMED,
            coverage_gap_count=2,
        ),
        _snapshot(),
        _finding(CaseVerdict.VULNERABLE),
    )

    assert result.headline == "发现权限问题"
    assert result.checked_count == 1
    assert result.problem_count == 1
    assert result.uncovered_count == 2
    assert result.execution_problem is None
    assert result.issues[0].title == "成员账号不应对文档执行修改"
    assert result.issues[0].surface_result == "页面或接口显示已拒绝"
    assert result.issues[0].actual_result == "真实资源已经发生变化"
    assert "表面拒绝没有阻止真实副作用" in result.issues[0].explanation
    assert result.issues[0].planned_identity_id == "member-account"
    assert result.issues[0].planned_identity_label == "成员测试账号"
    assert result.issues[0].actual_identity_status == "UNAVAILABLE"
    assert result.issues[0].actual_identity_label is None


@pytest.mark.parametrize(
    ("run_verdict", "case_verdict", "headline", "conclusion"),
    (
        (RunVerdict.PASS, CaseVerdict.SAFE, "当前检查范围未发现确认问题", "符合预期"),
        (RunVerdict.INCONCLUSIVE, CaseVerdict.INCONCLUSIVE, "证据不足", "证据不足"),
    ),
)
def test_pass_and_inconclusive_use_the_same_deterministic_business_view(
    run_verdict: RunVerdict,
    case_verdict: CaseVerdict,
    headline: str,
    conclusion: str,
) -> None:
    effect = ObservedEffect.ABSENT if case_verdict is CaseVerdict.SAFE else ObservedEffect.UNKNOWN
    result = build_result_presentation(
        _view(run_verdict, case_verdict, effect=effect),
        _snapshot(),
        _finding(case_verdict, status="PRESENT"),
    )

    assert result.headline == headline
    assert result.issues[0].conclusion == conclusion
    assert result.execution_problem is None
    if run_verdict is RunVerdict.PASS:
        assert "不代表应用绝对安全" in result.scope_statement
    else:
        assert "不代表安全，也不代表已经确认漏洞" in result.scope_statement


def test_only_failed_or_cancelled_lifecycle_creates_execution_problem() -> None:
    failed = build_result_presentation(
        _view(
            None,
            CaseVerdict.INCONCLUSIVE,
            lifecycle=RunLifecycle.FAILED,
            effect=ObservedEffect.UNKNOWN,
        ),
        _snapshot(),
        _finding(CaseVerdict.INCONCLUSIVE),
    )
    block = build_result_presentation(
        _view(
            RunVerdict.BLOCK,
            CaseVerdict.VULNERABLE,
            effect=ObservedEffect.CONFIRMED,
        ),
        _snapshot(),
        _finding(CaseVerdict.VULNERABLE),
    )

    assert failed.execution_problem == "检查执行失败，未形成可用安全结论。"
    assert block.execution_problem is None


def test_missing_planned_identity_binding_fails_closed() -> None:
    with pytest.raises(JiejianError) as captured:
        build_result_presentation(
            _view(RunVerdict.BLOCK, CaseVerdict.VULNERABLE),
            _snapshot(include_binding=False),
            _finding(CaseVerdict.VULNERABLE),
        )

    assert captured.value.code == ErrorCode.ARTIFACT_FENCE.value


def test_six_sources_use_frozen_roles_stable_order_and_published_fact_status() -> None:
    view = _view(
        RunVerdict.BLOCK,
        CaseVerdict.VULNERABLE,
        outcome=ExecutionOutcome.DENIED,
        effect=ObservedEffect.CONFIRMED,
    )
    _, bindings, facts, outcomes, snapshot = _six_source_facts()
    evidence = view.publication.result.evidence[0]
    evidence.requirement_bindings = bindings
    evidence.observation_facts = facts
    evidence.outcomes = outcomes

    result = build_result_presentation(
        view,
        snapshot,
        _finding(CaseVerdict.VULNERABLE),
    )

    sources = result.issues[0].evidence_sources
    assert [item.observer_type for item in sources] == list(ObserverType)
    assert [item.label for item in sources] == [
        "目标业务状态",
        "只读数据库",
        "结构化审计记录",
        "后台任务",
        "消息通道",
        "最终对象/文件",
    ]
    assert [item.role for item in sources] == [
        "KEY",
        "SUPPORTING",
        "SUPPORTING",
        "SUPPORTING",
        "SUPPORTING",
        "KEY",
    ]
    assert [item.status for item in sources] == [
        "FOUND",
        "NOT_FOUND",
        "UNAVAILABLE",
        "FOUND",
        "NOT_FOUND",
        "UNAVAILABLE",
    ]
    assert all(item.evidence_refs == (EVIDENCE_ID,) for item in sources)
    assert result.verdict is RunVerdict.BLOCK
    assert result.issues[0].verdict.value == CaseVerdict.VULNERABLE.value
    assert result.issues[0].actual_identity_status == "UNAVAILABLE"


def test_source_availability_translation_never_recomputes_verdict() -> None:
    view = _view(
        RunVerdict.BLOCK,
        CaseVerdict.VULNERABLE,
        effect=ObservedEffect.CONFIRMED,
    )
    _, bindings, facts, outcomes, snapshot = _six_source_facts(unavailable=True)
    evidence = view.publication.result.evidence[0]
    evidence.requirement_bindings = bindings
    evidence.observation_facts = facts
    evidence.outcomes = outcomes

    result = build_result_presentation(
        view,
        snapshot,
        _finding(CaseVerdict.VULNERABLE),
    )

    assert {item.status for item in result.issues[0].evidence_sources} == {
        "UNAVAILABLE"
    }
    assert result.verdict is RunVerdict.BLOCK
    assert result.issues[0].verdict.value == CaseVerdict.VULNERABLE.value


def test_published_audit_trace_exposes_actual_actor_without_changing_verdict() -> None:
    semantic_keys = (
        "request_received",
        "server_identity_resolved",
        "export_request_created",
        "authorization_decided",
        "export_message_sent",
        "export_job_started",
        "archive_generated",
        "export_job_completed",
    )
    records = [
        {
            "event_id": f"trace-{index}",
            "parent_event_id": f"trace-{index - 1}" if index > 1 else None,
            "case_tag": CASE_ID,
            "task_id": "task-export",
            "event_type": semantic_key,
            "semantic_key": semantic_key,
            "sequence": index,
            "resource_id": RESOURCE_ID,
            "kind": "authorization" if semantic_key == "authorization_decided" else "event",
            "subject_id": "bob",
            "actor_id": "export-worker" if index >= 6 else "bob",
            "authority_scope": "project:export",
            "authorization_decision": "DENY" if semantic_key == "authorization_decided" else None,
            "source_component": "export-worker" if index >= 6 else "collaboration-server",
            "source_location": "worker:export" if index >= 6 else "api:/projects/export",
            "recorded_at_us": 1_000 + index,
        }
        for index, semantic_key in enumerate(semantic_keys, start=1)
    ]
    view = _view(
        RunVerdict.BLOCK,
        CaseVerdict.VULNERABLE,
        effect=ObservedEffect.CONFIRMED,
    )
    view.publication.result.evidence[0].observations = (
        SimpleNamespace(
            observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
            completeness=ObservationCompleteness.COMPLETE,
            state=SimpleNamespace(canonical_data={"records": records}),
        ),
    )
    original_verdict = view.publication.result.verdict

    result = build_result_presentation(
        view,
        _snapshot(),
        _finding(CaseVerdict.VULNERABLE),
    )

    trace = result.execution_traces[0]
    assert trace.complete is True
    assert trace.events[0].subject_id == trace.events[0].actor_id == "bob"
    assert trace.events[-1].subject_id == "bob"
    assert trace.events[-1].actor_id == "export-worker"
    assert result.verdict is original_verdict is RunVerdict.BLOCK
    assert view.publication.result.verdict is RunVerdict.BLOCK
