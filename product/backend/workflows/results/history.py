# =============================================================================
# 权限结果历史比较
#
# 定位
#   多次已验证 Run 之间的稳定问题变化只读投影。
#
# 职责
#   维护稳定问题身份｜保留各 Run 冻结权限版本与修复复验｜区分新发现、已修复、证据不足与本次未覆盖
#
# 边界
#   不新建历史表，不修改 Finding，不以 DISAPPEARED 或缺失记录单独推断已修复。
#
# 调用链
#   Results API / GUI → HistoryComparisonBuilder → ResultPresentationBuilder / Run Repository
# =============================================================================

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import RunLifecycle
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState,
    PermissionIntentRelation,
    PermissionIntentRevision,
)
from product.backend.core.repair import RepairVerification
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.results.presentation import (
    PresentedCaseVerdict,
    ResultPresentation,
    ResultPresentationBuilder,
    ResultChangeVerification,
    ResultPresentationIssue,
    ResultRelevantIntent,
)


class _HistoryModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class HistoryChangeStatus(StrEnum):
    NEW = "NEW"
    FIXED = "FIXED"
    PERSISTENT = "PERSISTENT"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_COVERED = "NOT_COVERED"


class HistoryChange(_HistoryModel):
    finding_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    subject_group: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=160)
    resource: str = Field(min_length=1, max_length=160)
    relation: str = Field(min_length=1, max_length=160)
    status: HistoryChangeStatus
    status_label: str = Field(min_length=1, max_length=32)
    explanation: str = Field(min_length=1, max_length=320)
    severity: str = Field(min_length=1, max_length=16)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=8192)
    current_verdict: PresentedCaseVerdict | None = None
    occurrence_status: str | None = Field(default=None, max_length=32)


class HistoryComparison(_HistoryModel):
    run_id: str = Field(min_length=1, max_length=128)
    previous_run_id: str | None = Field(default=None, max_length=128)
    checked_at_us: int = Field(ge=0)
    policy_epoch: int = Field(ge=0)
    policy_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    relevant_intents: tuple[ResultRelevantIntent, ...] = Field(
        default=(),
        max_length=4096,
    )
    change_verification: ResultChangeVerification | None = None
    repair_verification: RepairVerification | None = None
    changes: tuple[HistoryChange, ...] = ()


class IntentRevisionHistory(_HistoryModel):
    revision: int = Field(ge=1)
    intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_epoch: int = Field(ge=1)
    effective_state: PermissionIntentEffectiveState
    business_statement: str = Field(min_length=1, max_length=640)
    approved_by: str = Field(min_length=1, max_length=128)
    approved_at_us: int = Field(ge=0)


class IntentRunHistory(_HistoryModel):
    run_id: str = Field(min_length=1, max_length=128)
    checked_at_us: int = Field(ge=0)
    revision: int = Field(ge=1)
    intent_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_epoch: int = Field(ge=0)
    association_status: Literal["EXACT", "POLICY_ONLY"]
    association_note: str = Field(min_length=1, max_length=320)
    verdict: str | None = Field(default=None, max_length=32)
    diagnosis_summary: str | None = Field(default=None, min_length=1, max_length=320)
    change_revalidation: bool = False
    repair_status: str | None = Field(default=None, max_length=32)


class ResultIntentHistory(_HistoryModel):
    intent_id: str = Field(pattern=r"^pin_[0-9a-f]{32}$")
    display_label: str = Field(pattern=r"^P-[0-9]{3,4}$")
    revisions: tuple[IntentRevisionHistory, ...] = Field(default=(), max_length=4096)
    runs: tuple[IntentRunHistory, ...] = Field(default=(), max_length=20)


class HistoryView(_HistoryModel):
    project_id: str = Field(min_length=1, max_length=64)
    intents: tuple[ResultIntentHistory, ...] = Field(default=(), max_length=4096)
    comparisons: tuple[HistoryComparison, ...] = Field(default=(), max_length=20)


class HistoryComparisonBuilder:
    """从近期已验证 Run 形成历史变化；无写入、无 Finding 再物化。"""

    def __init__(self, uow_factory, presentation: ResultPresentationBuilder) -> None:
        self._uow_factory = uow_factory
        self._presentation = presentation

    def build(self, project_id: str, *, limit: int = 10) -> HistoryView:
        """按时间返回最近的有界比较；不可验证或未最终化 Run 不参与。"""

        if limit < 1 or limit > 20:
            raise ValueError("history limit must be between 1 and 20")
        with self._uow_factory() as work:
            runs = tuple(work.runs.list_for_project(project_id))
            intent_repository = getattr(work, "permission_intents", None)
            revisions = (
                ()
                if intent_repository is None
                else tuple(intent_repository.list_revisions(project_id))
            )
        verified: list[tuple[object, ResultPresentation]] = []
        for run in runs:
            if run.lifecycle not in {RunLifecycle.COMPLETED, RunLifecycle.SAFETY_STOPPED}:
                continue
            try:
                presentation = self._presentation.build(run.run_id)
            except JiejianError:
                continue
            verified.append((run, presentation))
            if len(verified) == limit:
                break
        verified.reverse()
        return HistoryView(
            project_id=project_id,
            intents=_intent_histories(revisions, tuple(verified)),
            comparisons=_comparisons(tuple(verified)),
        )


_RELATION_TEXT = {
    PermissionIntentRelation.OWNS: "资源属于该账号自己",
    PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT: "资源属于同权限组的其他账号",
    PermissionIntentRelation.OTHER_ROLE: "资源属于其他权限组",
}


def _intent_histories(
    revisions: tuple[PermissionIntentRevision, ...],
    verified: tuple[tuple[object, ResultPresentation], ...],
) -> tuple[ResultIntentHistory, ...]:
    by_intent: dict[str, list[PermissionIntentRevision]] = {}
    labels: dict[str, str] = {}
    for revision in revisions:
        by_intent.setdefault(revision.intent_id, []).append(revision)
    for _, presentation in verified:
        for relevant in presentation.relevant_intents:
            if relevant.display_label is not None:
                labels[relevant.intent_id] = relevant.display_label
    for index, intent_id in enumerate(sorted(by_intent), start=1):
        labels.setdefault(intent_id, f"P-{index:03d}")

    outputs: list[ResultIntentHistory] = []
    for intent_id in sorted(by_intent):
        ordered_revisions = tuple(
            sorted(by_intent[intent_id], key=lambda item: item.revision)
        )
        known_revisions = {
            (item.revision, item.intent_hash) for item in ordered_revisions
        }
        revision_views = tuple(
            IntentRevisionHistory(
                revision=item.revision,
                intent_hash=item.intent_hash,
                policy_epoch=item.policy_epoch,
                effective_state=item.effective_state,
                business_statement=_intent_statement(item),
                approved_by=item.approval.approved_by,
                approved_at_us=item.approval.approved_at_us,
            )
            for item in ordered_revisions
        )
        run_views: list[IntentRunHistory] = []
        for run, presentation in verified:
            relevant = next(
                (item for item in presentation.relevant_intents if item.intent_id == intent_id),
                None,
            )
            if relevant is None:
                continue
            exact = (
                len(presentation.relevant_intents) == 1
                and (relevant.revision, relevant.intent_hash) in known_revisions
            )
            issue = presentation.issues[0] if exact and len(presentation.issues) == 1 else None
            change_related = bool(
                presentation.change_verification
                and any(
                    item.intent_id == intent_id
                    and item.revision == relevant.revision
                    and item.intent_hash == relevant.intent_hash
                    for item in presentation.change_verification.required_intents
                )
            )
            run_views.append(
                IntentRunHistory(
                    run_id=run.run_id,
                    checked_at_us=run.finished_at_us or run.updated_at_us,
                    revision=relevant.revision,
                    intent_hash=relevant.intent_hash,
                    policy_epoch=presentation.policy_epoch,
                    association_status="EXACT" if exact else "POLICY_ONLY",
                    association_note=(
                        "本轮只依据这一条权限要求，可以可靠关联结果与诊断。"
                        if exact
                        else "本轮权限快照包含这条要求，但聚合结果无法可靠归到单条要求。"
                    ),
                    verdict=(
                        None
                        if not exact or presentation.verdict is None
                        else presentation.verdict.value
                    ),
                    diagnosis_summary=(
                        issue.diagnosis.summary
                        if issue is not None and issue.diagnosis is not None
                        else None
                    ),
                    change_revalidation=change_related,
                    repair_status=(
                        presentation.repair_verification.status.value
                        if exact and presentation.repair_verification is not None
                        else None
                    ),
                )
            )
        outputs.append(
            ResultIntentHistory(
                intent_id=intent_id,
                display_label=labels[intent_id],
                revisions=revision_views,
                runs=tuple(run_views),
            )
        )
    return tuple(outputs)


def _intent_statement(revision: PermissionIntentRevision) -> str:
    permission = "可以" if revision.expectation is PermissionExpectation.ALLOW else "不可以"
    statement = (
        f"{revision.subject_display_name}{permission}对"
        f"{revision.resource_owner_display_name}的资源执行“{revision.action_display_name}”"
        f"（{_RELATION_TEXT[revision.relation]}）。"
    )
    if revision.expectation is PermissionExpectation.DENY and revision.protected_effects:
        effects = "、".join(item.business_label for item in revision.protected_effects)
        statement += f"受保护业务后果“{effects}”不得发生。"
    return statement


_STATUS_VIEW = {
    HistoryChangeStatus.NEW: ("新发现", "本次首次确认该权限问题。"),
    HistoryChangeStatus.FIXED: ("已解决", "本次对同一权限要求取得了充分的安全证据。"),
    HistoryChangeStatus.PERSISTENT: ("仍存在", "同一权限问题在本次检查中仍有充分证据。"),
    HistoryChangeStatus.INCONCLUSIVE: ("证据不足", "本次执行了对应检查，但真实结果证据不足。"),
    HistoryChangeStatus.NOT_COVERED: ("本次未覆盖", "本次没有执行并充分证明这一权限要求，不能显示为已修复。"),
}


def _comparisons(
    verified: tuple[tuple[object, ResultPresentation], ...],
) -> tuple[HistoryComparison, ...]:
    active: dict[str, ResultPresentationIssue] = {}
    known: dict[str, ResultPresentationIssue] = {}
    outputs: list[HistoryComparison] = []
    previous_run_id: str | None = None
    for run, presentation in verified:
        current = {item.finding_id: item for item in presentation.issues}
        changes: list[HistoryChange] = []
        for finding_id in sorted(set(current) | set(active)):
            item = current.get(finding_id)
            prior = active.get(finding_id)
            status = _status(item, prior)
            if status is None:
                continue
            source = item or prior or known[finding_id]
            changes.append(_change(source, item, status))
        for finding_id, item in current.items():
            known[finding_id] = item
            if item.verdict is PresentedCaseVerdict.VULNERABLE:
                active[finding_id] = item
            elif item.verdict is PresentedCaseVerdict.SAFE:
                active.pop(finding_id, None)
        outputs.append(
            HistoryComparison(
                run_id=run.run_id,
                previous_run_id=previous_run_id,
                checked_at_us=run.finished_at_us or run.updated_at_us,
                policy_epoch=presentation.policy_epoch,
                policy_fingerprint=presentation.policy_fingerprint,
                relevant_intents=presentation.relevant_intents,
                change_verification=presentation.change_verification,
                repair_verification=presentation.repair_verification,
                changes=tuple(changes),
            )
        )
        previous_run_id = run.run_id
    return tuple(outputs)


def _status(
    current: ResultPresentationIssue | None,
    prior: ResultPresentationIssue | None,
) -> HistoryChangeStatus | None:
    if current is None:
        return HistoryChangeStatus.NOT_COVERED if prior is not None else None
    if current.verdict is PresentedCaseVerdict.VULNERABLE:
        return (
            HistoryChangeStatus.PERSISTENT
            if prior is not None
            else HistoryChangeStatus.NEW
        )
    if current.verdict is PresentedCaseVerdict.INCONCLUSIVE:
        return HistoryChangeStatus.INCONCLUSIVE
    if current.verdict is PresentedCaseVerdict.SAFE and prior is not None:
        return HistoryChangeStatus.FIXED
    return None


def _change(
    source: ResultPresentationIssue,
    current: ResultPresentationIssue | None,
    status: HistoryChangeStatus,
) -> HistoryChange:
    label, explanation = _STATUS_VIEW[status]
    return HistoryChange(
        finding_id=source.finding_id,
        title=source.title,
        subject_group=source.subject_group,
        action=source.action,
        resource=source.resource,
        relation=source.relation,
        status=status,
        status_label=label,
        explanation=explanation,
        severity=source.severity,
        evidence_refs=() if current is None else current.evidence_refs,
        current_verdict=None if current is None else current.verdict,
        occurrence_status=None if current is None else current.occurrence_status,
    )


__all__ = [
    "HistoryChange",
    "HistoryChangeStatus",
    "HistoryComparison",
    "HistoryComparisonBuilder",
    "HistoryView",
    "IntentRevisionHistory",
    "IntentRunHistory",
    "ResultIntentHistory",
]
