# 验证历史比较只有在同一权限要求取得充分 SAFE 证据时才显示已修复。

from __future__ import annotations

from types import SimpleNamespace

from product.backend.core.lifecycle import RunLifecycle, RunVerdict
from product.backend.core.permission_intent import (
    HumanApproval,
    HumanApprovalChannel,
    PermissionIntentEffectiveState,
    PermissionIntentRelation,
    PermissionIntentRevision,
    PermissionIntentSemantic,
    permission_intent_sha256,
)
from product.backend.core.repair import (
    RepairContractReference,
    RepairVerification,
    RepairVerificationStatus,
)
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.results.history import (
    HistoryChangeStatus,
    HistoryComparisonBuilder,
)
from product.backend.workflows.results.presentation import (
    PresentedCaseVerdict,
    ResultClaimBoundary,
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
INTENT_ID = "pin_" + "7" * 32
INTENT_SEMANTIC = PermissionIntentSemantic(
    effective_state=PermissionIntentEffectiveState.ACTIVE,
    subject_display_name="成员账号",
    action_display_name="修改文档",
    resource_owner_display_name="本人",
    relation=PermissionIntentRelation.OWNS,
    expectation=PermissionExpectation.DENY,
)
INTENT_HASH = permission_intent_sha256(INTENT_SEMANTIC.canonical_payload())


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
        claim_boundary=ResultClaimBoundary(
            surface_response_status=ExecutionOutcome.DENIED,
            business_effect_status=(
                ObservedEffect.ABSENT
                if verdict is PresentedCaseVerdict.SAFE
                else ObservedEffect.CONFIRMED
            ),
            actual_identity_status="UNAVAILABLE",
            supported_statement="测试主张。",
            unsupported_statements=("测试限制。",),
        ),
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
        relevant_intents=(
            ResultRelevantIntent(
                intent_id=INTENT_ID,
                revision=2,
                intent_hash=INTENT_HASH,
                display_label="P-001",
            ),
        ),
        change_verification=(
            ResultChangeVerification(
                change_id="chg_" + "6" * 32,
                required_intents=(
                    ResultRelevantIntent(
                        intent_id=INTENT_ID,
                        revision=2,
                        intent_hash=INTENT_HASH,
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


class _PermissionIntents:
    def __init__(self, revisions: tuple[PermissionIntentRevision, ...]) -> None:
        self._revisions = revisions

    def list_revisions(self, project_id: str) -> tuple[PermissionIntentRevision, ...]:
        assert project_id == PROJECT_ID
        return self._revisions


class _Work:
    def __init__(
        self,
        runs: tuple[object, ...],
        revisions: tuple[PermissionIntentRevision, ...] = (),
    ) -> None:
        self.runs = _Runs(runs)
        self.permission_intents = _PermissionIntents(revisions)

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


def _intent_revision() -> PermissionIntentRevision:
    return PermissionIntentRevision(
        **INTENT_SEMANTIC.model_dump(mode="python"),
        intent_id=INTENT_ID,
        project_id=PROJECT_ID,
        revision=2,
        intent_hash=INTENT_HASH,
        policy_epoch=3,
        approval=HumanApproval(
            channel=HumanApprovalChannel.LOCAL_GUI,
            approved_by="本机用户",
            approved_at_us=3,
            reason="确认业务权限要求",
        ),
        created_at_us=3,
    )


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
        lambda: _Work(runs, (_intent_revision(),)),
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
    assert result.intents[0].display_label == "P-001"
    assert result.intents[0].revisions[0].business_statement == (
        "成员账号不可以对本人的资源执行“修改文档”（资源属于该账号自己）。"
    )
    assert [item.association_status for item in result.intents[0].runs] == [
        "EXACT",
        "EXACT",
        "EXACT",
    ]
    assert result.intents[0].runs[-1].change_revalidation is True
    assert result.intents[0].runs[-1].repair_status == "VERIFIED"


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


def test_multi_intent_run_keeps_policy_membership_without_attributing_verdict() -> None:
    other_intent = "pin_" + "9" * 32
    run = SimpleNamespace(
        run_id=RUN_BLOCK,
        lifecycle=RunLifecycle.COMPLETED,
        finished_at_us=10,
        updated_at_us=10,
    )
    presentation = _presentation(
        RUN_BLOCK,
        _issue(PresentedCaseVerdict.VULNERABLE, "APPEARED"),
    ).model_copy(
        update={
            "relevant_intents": (
                ResultRelevantIntent(
                    intent_id=INTENT_ID,
                    revision=2,
                    intent_hash=INTENT_HASH,
                    display_label="P-001",
                ),
                ResultRelevantIntent(
                    intent_id=other_intent,
                    revision=1,
                    intent_hash="a" * 64,
                    display_label="P-002",
                ),
            )
        }
    )
    builder = HistoryComparisonBuilder(
        lambda: _Work((run,), (_intent_revision(),)),
        _Presentation({RUN_BLOCK: presentation}),
    )

    result = builder.build(PROJECT_ID)

    associated = result.intents[0].runs[0]
    assert associated.association_status == "POLICY_ONLY"
    assert associated.verdict is None
    assert associated.diagnosis_summary is None
    assert "无法可靠归到单条要求" in associated.association_note
