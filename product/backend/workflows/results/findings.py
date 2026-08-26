# =============================================================================
# 稳定 Finding 应用服务
#
# 定位
#   将 PublishedResultReader 已核验的 Evidence 投影为 Finding/Occurrence
#
# 职责
#   提取稳定身份｜跨 Run 幂等物化｜只读查询 Finding 结果
#
# 边界
#   不修改 Evidence 或 Verdict，不重新执行 Verification，也不把缺失事实推断为已修复。
#
# 调用链
#   Finalizer → FindingMaterializer → UoW；API / Results → FindingQueries → UoW
# =============================================================================

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import CaseVerdict
from product.protocols import RunnerResult
from product.backend.infra.storage import BaseReportFinalizationState, FindingFinalizationState, RunFinalizationRecord, StorageUnitOfWork
from product.backend.infra.storage.results.findings import FindingOccurrenceRecord, FindingRecord
from product.backend.core.verification.findings import Finding, FindingIdentity, FindingInput, FindingOccurrence, OccurrenceStatus, occurrence_id_for

from product.backend.workflows.results.published import PublishedResultReader, PublishedRunView


_SEVERITY_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class FindingMaterializer:
    """只接受已验证 PublishedRunView，并在最终化事务中写入 Finding/Occurrence。"""

    def __init__(self, uow_factory, published_reader: PublishedResultReader, *, utc_now_us=None) -> None:
        self._uow_factory = uow_factory
        self._published_reader = published_reader
        self._utc_now_us = utc_now_us or (lambda: time.time_ns() // 1_000)

    def materialize(self, view: PublishedRunView) -> str:
        """幂等写入单个 publication，并返回按 Finding/Occurrence 排序的快照摘要。"""

        if not isinstance(view, PublishedRunView):
            raise TypeError("finding materializer requires a published run view")
        inputs = finding_inputs(self._published_reader, view)
        timestamp = view.run.finished_at_us or view.run.updated_at_us
        # --- 阶段：按稳定问题身份聚合本次 Evidence ---
        grouped: dict[str, list[FindingInput]] = defaultdict(list)
        for item in inputs:
            grouped[item.identity.finding_id()].append(item)

        # --- 阶段：在事务内追加 Occurrence 并更新 Finding 当前摘要 ---
        with self._uow_factory() as work:
            finalization = work.finalizations.get(view.run.run_id)
            if finalization is None:
                raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
            if finalization.findings_state is FindingFinalizationState.COMPLETE:
                return finalization.findings_snapshot_sha256 or ""
            if finalization.findings_state not in {FindingFinalizationState.PENDING, FindingFinalizationState.RUNNING}:
                raise JiejianError(ErrorCode.RESULT_FINALIZATION_BLOCKED, "Finding 最终化当前不可写入")
            for finding_id, items in sorted(grouped.items()):
                identity = items[0].identity
                existing = work.findings.get(finding_id)
                unsafe = any(item.verdict is not CaseVerdict.SAFE for item in items)
                if existing is None and unsafe:
                    finding = Finding(
                        finding_id=finding_id,
                        project_id=identity.project_id,
                        identity=identity,
                        first_seen_at_us=timestamp,
                        last_seen_at_us=timestamp,
                    )
                    work.findings.add(FindingRecord(
                        finding_id=finding.finding_id,
                        project_id=finding.project_id,
                        identity_json=json.dumps(
                            identity.model_dump(mode="json"),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        created_at_us=finding.first_seen_at_us,
                        updated_at_us=finding.last_seen_at_us,
                    ))
                    existing = work.findings.get(finding_id)
                if existing is None or work.findings.get_occurrence(finding_id, view.run.run_id) is not None:
                    continue
                previous = work.findings.latest_occurrence(finding_id)
                verdict = _aggregate_verdict(items)
                status = _occurrence_status(
                    previous,
                    verdict,
                    allow_disappeared=(
                        view.run.lifecycle.value != "SAFETY_STOPPED"
                        and view.publication.result.coverage_gap_count == 0
                        and all(item.verdict is not CaseVerdict.INCONCLUSIVE for item in items)
                    ),
                )
                occurrence = FindingOccurrence(
                    occurrence_id=occurrence_id_for(finding_id, view.run.run_id),
                    finding_id=finding_id,
                    project_id=identity.project_id,
                    run_id=view.run.run_id,
                    status=status,
                    verdict=verdict,
                    severity=_aggregate_severity(items),
                    evidence_refs=tuple(item.evidence_id for item in items),
                    object_context=_merge_context(items, "object_context"),
                    coverage_context=_merge_context(items, "coverage_context"),
                    created_at_us=timestamp,
                )
                work.findings.add_occurrence(FindingOccurrenceRecord(
                    occurrence_id=occurrence.occurrence_id,
                    finding_id=occurrence.finding_id,
                    project_id=occurrence.project_id,
                    run_id=occurrence.run_id,
                    status=occurrence.status.value,
                    verdict=occurrence.verdict.value,
                    severity=occurrence.severity,
                    evidence_refs_json=json.dumps(occurrence.evidence_refs, ensure_ascii=False, separators=(",", ":")),
                    object_context_json=json.dumps(occurrence.object_context, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    coverage_context_json=json.dumps(occurrence.coverage_context, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    created_at_us=occurrence.created_at_us,
                ))
                work.findings.touch(finding_id, max(timestamp, existing.updated_at_us))
            occurrences = tuple(
                sorted(
                    work.findings.list_occurrences_for_run(view.run.run_id),
                    key=lambda value: (value.finding_id, value.occurrence_id),
                )
            )
            snapshot_payload = [
                _view_record(work.findings.get(item.finding_id), item)
                for item in occurrences
            ]
            snapshot_sha256 = _finding_snapshot_sha256(snapshot_payload)
            completed_at_us = max(
                self._utc_now_us(),
                finalization.created_at_us,
                timestamp,
            )
            next_state = BaseReportFinalizationState.PENDING if finalization.base_report_state is BaseReportFinalizationState.BLOCKED else finalization.base_report_state
            work.finalizations.save(
                _evolve_finalization(
                    finalization,
                    findings_state=FindingFinalizationState.COMPLETE,
                    findings_error_code=None,
                    findings_snapshot_sha256=snapshot_sha256,
                    findings_completed_at_us=completed_at_us,
                    blocked_by_run_id=None,
                    base_report_state=next_state,
                    updated_at_us=completed_at_us,
                )
            )
            work.commit()
            return snapshot_sha256


class FindingQueries:
    """只读 Finding/Occurrence 查询；未完成的最终化不会返回部分事实。"""

    def __init__(self, uow_factory) -> None:
        self._uow_factory = uow_factory

    def findings_for_run(self, run_id: str) -> list[dict[str, Any]]:
        """只读取 COMPLETE finalization 产生的 Finding/Occurrence。"""

        self._require_complete(run_id)
        with self._uow_factory() as work:
            occurrences = tuple(
                sorted(
                    work.findings.list_occurrences_for_run(run_id),
                    key=lambda value: (value.finding_id, value.occurrence_id),
                )
            )
            records = {item.finding_id: work.findings.get(item.finding_id) for item in occurrences}
        return [
            _view_record(records[item.finding_id], item)
            for item in occurrences
            if records[item.finding_id] is not None
        ]

    def _require_complete(self, run_id: str) -> RunFinalizationRecord:
        with self._uow_factory() as work:
            finalization = work.finalizations.get(run_id)
        if finalization is None:
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_FOUND, "结果最终化记录不存在")
        if finalization.findings_state is FindingFinalizationState.COMPLETE:
            return finalization
        if finalization.findings_state is FindingFinalizationState.BLOCKED:
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_BLOCKED, "Finding 最终化被前序 Run 阻断")
        if finalization.findings_state is FindingFinalizationState.FAILED:
            raise JiejianError(ErrorCode.RESULT_FINALIZATION_FAILED, "Finding 最终化失败")
        raise JiejianError(ErrorCode.RESULT_FINALIZATION_NOT_READY, "Finding 尚未完成最终化")


def finding_inputs(reader: PublishedResultReader, view: PublishedRunView) -> tuple[FindingInput, ...]:
    """只从唯一当前 RunnerResult 提取稳定 Finding 身份。"""

    if not isinstance(view.publication.result, RunnerResult):
        raise TypeError("unsupported published result")
    return _permission_inputs(reader, view)


def _permission_inputs(reader: PublishedResultReader, view: PublishedRunView) -> tuple[FindingInput, ...]:
    result = view.publication.result
    assert isinstance(result, RunnerResult)
    snapshot = reader.request_snapshot(view)
    contract = snapshot.contract
    subjects = {item.subject_id: item for item in contract.subjects}
    actions = {item.action_id: item for item in contract.actions}
    resources = {item.resource_id: item for item in contract.resources}
    relations = {item.relation_id: item for item in contract.relations}
    rules = {item.rule_id: item for item in contract.rules}
    planned_case_ids = {item.case_id for item in snapshot.plan.cases}
    outputs: list[FindingInput] = []
    for evidence in result.evidence:
        case = evidence.case_snapshot
        if case.case_id not in planned_case_ids:
            continue
        subject = subjects[case.subject_id]
        action = actions[case.action_id]
        case_resources = tuple(resources[item] for item in case.resource_ids)
        identity = FindingIdentity(
            project_id=view.run.project_id,
            permission_intent=tuple(
                [*(f"rule:{item}" for item in case.source_rule_ids), *(f"expectation:{item.value}" for item in case.expectations)]
            ),
            subject_class=(
                *(f"role:{item}" for item in subject.roles),
                f"tenant:{subject.tenant_id or 'none'}",
                f"department:{subject.department_id or 'none'}",
                f"admin-level:{subject.admin_level}",
            ),
            action=case.action_id,
            resource_class=tuple(
                sorted(
                    {
                        f"type:{item.resource_type}"
                        for item in case_resources
                    }
                    | {f"tenant:{item.tenant_id or 'none'}" for item in case_resources}
                    | {f"department:{item.department_id or 'none'}" for item in case_resources}
                    | {f"workflow:{item.workflow_state}" for item in case_resources}
                    | {
                        f"owner-role:{subjects[item.owner_subject_id].roles[0]}"
                        for item in case_resources
                        if item.owner_subject_id is not None
                    }
                )
            ),
            resource_relation=tuple(
                sorted(
                    {
                        f"relation:{relation_id}:{relations[relation_id].relation.value}"
                        for path in case.relation_paths
                        for relation_id in path
                    }
                    | {
                        f"path-{index}-" + "-".join(path)
                        for index, path in enumerate(case.relation_paths)
                    }
                    | {f"batch:{case.batch_mode.value if case.batch_mode else 'single'}", f"atomic:{case.atomic}"}
                )
            ),
            problem_category="permission-security",
        )
        outputs.append(
            FindingInput(
                project_id=view.run.project_id,
                run_id=evidence.run_id,
                evidence_id=evidence.evidence_id,
                case_id=case.case_id,
                identity=identity,
                verdict=evidence.verdict,
                severity=_permission_severity(case.source_rule_ids, rules),
                object_context={
                    "case_id": case.case_id,
                    "resource_ids": case.resource_ids,
                    "fingerprint": case.fingerprint,
                    "dimensions": tuple(item.value for item in case.dimensions),
                    "retention_reason": case.retention_reason.value,
                },
                coverage_context={
                    "source_rule_ids": case.source_rule_ids,
                    "relation_paths": case.relation_paths,
                    "workflow_states": case.context.workflow_states,
                    "tenant_ids": case.context.tenant_ids,
                    "department_ids": case.context.department_ids,
                },
            )
        )
    return tuple(outputs)


def _permission_severity(rule_ids: Iterable[str], rules: Mapping[str, Any]) -> str:
    return max((rules[item].severity for item in rule_ids), key=lambda value: _SEVERITY_ORDER[value])


def _aggregate_verdict(items: Iterable[FindingInput]) -> CaseVerdict:
    verdicts = {item.verdict for item in items}
    if CaseVerdict.VULNERABLE in verdicts:
        return CaseVerdict.VULNERABLE
    if CaseVerdict.INCONCLUSIVE in verdicts:
        return CaseVerdict.INCONCLUSIVE
    return CaseVerdict.SAFE


def _aggregate_severity(items: Iterable[FindingInput]) -> str:
    return max((item.severity for item in items), key=lambda value: _SEVERITY_ORDER[value])


def _occurrence_status(previous, verdict: CaseVerdict, *, allow_disappeared: bool = True) -> OccurrenceStatus:
    if verdict is CaseVerdict.SAFE:
        return OccurrenceStatus.DISAPPEARED if allow_disappeared and previous is not None and previous.verdict != "SAFE" else OccurrenceStatus.PRESENT
    if previous is None or previous.verdict == "SAFE":
        return OccurrenceStatus.APPEARED if previous is None else OccurrenceStatus.REAPPEARED
    if previous.verdict != verdict.value:
        return OccurrenceStatus.CHANGED
    return OccurrenceStatus.PRESENT


def _merge_context(items: Iterable[FindingInput], field_name: str) -> dict[str, Any]:
    values = [getattr(item, field_name) for item in items]
    keys = sorted({key for value in values for key in value})
    merged: dict[str, Any] = {}
    for key in keys:
        entries = [value[key] for value in values if key in value]
        merged[key] = entries[0] if len(entries) == 1 else entries
    return merged


def _view_record(finding_record_value, occurrence_record_value) -> dict[str, Any]:
    identity = FindingIdentity.model_validate_json(finding_record_value.identity_json)
    finding = Finding(
        finding_id=finding_record_value.finding_id,
        project_id=finding_record_value.project_id,
        identity=identity,
        first_seen_at_us=finding_record_value.created_at_us,
        last_seen_at_us=finding_record_value.updated_at_us,
    )
    occurrence = FindingOccurrence(
        occurrence_id=occurrence_record_value.occurrence_id,
        finding_id=occurrence_record_value.finding_id,
        project_id=occurrence_record_value.project_id,
        run_id=occurrence_record_value.run_id,
        status=OccurrenceStatus(occurrence_record_value.status),
        verdict=CaseVerdict(occurrence_record_value.verdict),
        severity=occurrence_record_value.severity,
        evidence_refs=tuple(json.loads(occurrence_record_value.evidence_refs_json)),
        object_context=json.loads(occurrence_record_value.object_context_json),
        coverage_context=json.loads(occurrence_record_value.coverage_context_json),
        created_at_us=occurrence_record_value.created_at_us,
    )
    return {
        "finding": finding.model_dump(mode="json"),
        "occurrence": occurrence.model_dump(mode="json"),
    }


def _finding_snapshot_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _evolve_finalization(record: RunFinalizationRecord, **updates: Any) -> RunFinalizationRecord:
    return RunFinalizationRecord.model_validate({**record.model_dump(mode="python"), **updates})
