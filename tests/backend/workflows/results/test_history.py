# 验证历史比较只有在同一权限要求取得充分 SAFE 证据时才显示已修复。

from __future__ import annotations

from types import SimpleNamespace

from product.backend.core.lifecycle import RunLifecycle, RunVerdict
from product.backend.core.repair import (
    RepairContractReference,
    RepairVerification,
    RepairVerificationStatus,
)
from product.backend.workflows.results.history import (
    HistoryChangeStatus,
    HistoryComparisonBuilder,
)
from product.backend.workflows.results.presentation import (
    PresentedCaseVerdict,
    ResultChangeVerification,
    ResultPresentation,
    ResultPresentationIssue,
    ResultRelevantIntent,
)


PROJECT_ID = "history-project"
RUN_BLOCK = "run_" + "1" * 32
RUN_UNCOVERED = "run_" + "2" * 32
RUN_FIXED = "run_" + "3" * 32
FINDING_ID = "finding_" + "4" * 32


def _issue(verdict: PresentedCaseVerdict, occurrence_status: str) -> ResultPresentationIssue:
    return ResultPresentationIssue(
        finding_id=FINDING_ID,
        title="成员账号不应对文档执行修改",
        subject_group="成员账号",
        action="修改",
        resource="文档",
        relation="拥有",
        expectation="不应允许这次操作，资源也不应发生变化",
        surface_result="页面或接口显示已拒绝",
        actual_result=(
            "真实资源没有发生变化"
            if verdict is PresentedCaseVerdict.SAFE
            else "真实资源已经发生变化"
        ),
        conclusion=("符合预期" if verdict is PresentedCaseVerdict.SAFE else "发现权限问题"),
        explanation="测试投影说明。",
        planned_identity_id="member-account",
        planned_identity_label="成员测试账号",
        severity="high",
        evidence_refs=("evidence_" + verdict.value.lower(),),
        verdict=verdict,
        occurrence_status=occurrence_status,
    )


def _presentation(run_id: str, issue: ResultPresentationIssue | None) -> ResultPresentation:
    verdict = RunVerdict.PASS if issue is None or issue.verdict is PresentedCaseVerdict.SAFE else RunVerdict.BLOCK
    return ResultPresentation(
        run_id=run_id,
        project_id=PROJECT_ID,
        project_name="文档系统",
        run_lifecycle=RunLifecycle.COMPLETED,
        verdict=verdict,
        policy_epoch=int(run_id[-1]),
        policy_fingerprint=run_id[-1] * 64,
        change_verification=(
            ResultChangeVerification(
                change_id="chg_" + "6" * 32,
                required_intents=(
                    ResultRelevantIntent(
                        intent_id="pin_" + "7" * 32,
                        revision=2,
                        intent_hash="8" * 64,
                    ),
                ),
            )
            if run_id == RUN_FIXED
            else None
        ),
        headline="测试标题",
        scope_statement="测试范围说明。",
        checked_count=1,
        safe_count=1 if verdict is RunVerdict.PASS else 0,
        problem_count=1 if verdict is RunVerdict.BLOCK else 0,
        inconclusive_count=0,
        uncovered_count=1 if issue is None else 0,
        execution_problem=None,
        issues=() if issue is None else (issue,),
        limitations=(),
    )


class _Presentation:
    def __init__(self, values: dict[str, ResultPresentation]) -> None:
        self.values = values

    def build(self, run_id: str) -> ResultPresentation:
        return self.values[run_id]


class _Runs:
    def __init__(self, runs: tuple[object, ...]) -> None:
        self._runs = runs

    def list_for_project(self, project_id: str) -> tuple[object, ...]:
        assert project_id == PROJECT_ID
        return self._runs


class _Work:
    def __init__(self, runs: tuple[object, ...]) -> None:
        self.runs = _Runs(runs)

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


def test_uncovered_run_never_looks_fixed_and_later_safe_evidence_can_fix() -> None:
    runs = tuple(
        SimpleNamespace(
            run_id=run_id,
            lifecycle=RunLifecycle.COMPLETED,
            finished_at_us=timestamp,
            updated_at_us=timestamp,
        )
        for run_id, timestamp in (
            (RUN_FIXED, 30),
            (RUN_UNCOVERED, 20),
            (RUN_BLOCK, 10),
        )
    )
    presentations = {
        RUN_BLOCK: _presentation(
            RUN_BLOCK,
            _issue(PresentedCaseVerdict.VULNERABLE, "APPEARED"),
        ),
        RUN_UNCOVERED: _presentation(RUN_UNCOVERED, None),
        RUN_FIXED: _presentation(
            RUN_FIXED,
            _issue(PresentedCaseVerdict.SAFE, "DISAPPEARED"),
        ).model_copy(
            update={
                "repair_verification": RepairVerification(
                    reference=RepairContractReference(
                        source_run_id=RUN_BLOCK,
                        source_finding_id=FINDING_ID,
                        repair_fingerprint="9" * 64,
                    ),
                    verification_run_id=RUN_FIXED,
                    status=RepairVerificationStatus.VERIFIED,
                    message="原违规业务后果已消失，合法功能保持。",
                    reason_codes=("REPAIR_REQUIREMENTS_SATISFIED",),
                )
            }
        ),
    }
    builder = HistoryComparisonBuilder(
        lambda: _Work(runs),
        _Presentation(presentations),
    )

    result = builder.build(PROJECT_ID)

    assert [item.run_id for item in result.comparisons] == [
        RUN_BLOCK,
        RUN_UNCOVERED,
        RUN_FIXED,
    ]
    assert result.comparisons[0].changes[0].status is HistoryChangeStatus.NEW
    assert result.comparisons[1].changes[0].status is HistoryChangeStatus.NOT_COVERED
    assert result.comparisons[1].changes[0].status_label == "本次未覆盖"
    assert result.comparisons[1].changes[0].current_verdict is None
    assert result.comparisons[1].policy_epoch == 2
    assert result.comparisons[1].policy_fingerprint == "2" * 64
    assert result.comparisons[2].changes[0].status is HistoryChangeStatus.FIXED
    assert result.comparisons[2].changes[0].status_label == "已解决"
    assert result.comparisons[2].changes[0].current_verdict is PresentedCaseVerdict.SAFE
    assert result.comparisons[2].change_verification is not None
    assert len(result.comparisons[2].change_verification.required_intents) == 1
    assert result.comparisons[2].repair_verification is not None
    assert result.comparisons[2].repair_verification.status is RepairVerificationStatus.VERIFIED


def test_repeated_vulnerable_evidence_is_still_present() -> None:
    run_again = "run_" + "5" * 32
    runs = (
        SimpleNamespace(run_id=run_again, lifecycle=RunLifecycle.COMPLETED, finished_at_us=20, updated_at_us=20),
        SimpleNamespace(run_id=RUN_BLOCK, lifecycle=RunLifecycle.COMPLETED, finished_at_us=10, updated_at_us=10),
    )
    issue = _issue(PresentedCaseVerdict.VULNERABLE, "PRESENT")
    builder = HistoryComparisonBuilder(
        lambda: _Work(runs),
        _Presentation(
            {
                RUN_BLOCK: _presentation(RUN_BLOCK, issue),
                run_again: _presentation(run_again, issue),
            }
        ),
    )

    result = builder.build(PROJECT_ID)

    assert result.comparisons[-1].changes[0].status is HistoryChangeStatus.PERSISTENT
    assert result.comparisons[-1].changes[0].status_label == "仍存在"
