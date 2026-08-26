# 验证唯一结果业务投影只翻译已发布三态事实，不重算安全结论。

from __future__ import annotations

from types import SimpleNamespace

import pytest

from product.backend.core.lifecycle import CaseVerdict, RunLifecycle, RunVerdict
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.results.presentation import build_result_presentation


RUN_ID = "run_" + "1" * 32
PROJECT_ID = "presentation-project"
FINDING_ID = "finding_" + "2" * 32
EVIDENCE_ID = "evidence_" + "3" * 32


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
        case_snapshot=SimpleNamespace(expectations=(PermissionExpectation.DENY,)),
        execution_fact=SimpleNamespace(outcome=outcome),
        security_effect_facts=(SimpleNamespace(state=effect),),
        observation_facts=(),
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


def test_block_presentation_preserves_403_with_real_change_as_permission_problem() -> None:
    result = build_result_presentation(
        _view(
            RunVerdict.BLOCK,
            CaseVerdict.VULNERABLE,
            outcome=ExecutionOutcome.DENIED,
            effect=ObservedEffect.CONFIRMED,
            coverage_gap_count=2,
        ),
        SimpleNamespace(project_name="文档系统"),
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
        SimpleNamespace(project_name="文档系统"),
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
        SimpleNamespace(project_name="文档系统"),
        _finding(CaseVerdict.INCONCLUSIVE),
    )
    block = build_result_presentation(
        _view(
            RunVerdict.BLOCK,
            CaseVerdict.VULNERABLE,
            effect=ObservedEffect.CONFIRMED,
        ),
        SimpleNamespace(project_name="文档系统"),
        _finding(CaseVerdict.VULNERABLE),
    )

    assert failed.execution_problem == "检查执行失败，未形成可用安全结论。"
    assert block.execution_problem is None
