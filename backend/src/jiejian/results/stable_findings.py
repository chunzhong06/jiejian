# =============================================================================
# 稳定 Finding 应用服务
#
# 定位
#   将 PublishedResultReader 已核验的 V1/V2 Evidence 投影为 Finding/Occurrence
#
# 职责
#   版本分派身份提取｜跨 Run 幂等物化｜只读查询稳定 Finding 结果
#
# 调用链
#   API v2 / Results → PublishedResultReader → FindingApplicationService → UoW
# =============================================================================

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from ..domain.lifecycle import CaseVerdict
from ..protocols import RunnerResultV2, RunnerResultV1
from ..storage import StorageUnitOfWork
from ..storage.repositories.findings import FindingOccurrenceRecord, FindingRecord
from ..verification.findings import (
    Finding,
    FindingIdentity,
    FindingInput,
    FindingOccurrence,
    OccurrenceStatus,
    occurrence_id_for,
)

if TYPE_CHECKING:
    from .published import PublishedResultReader, PublishedRunView


_SEVERITY_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class FindingApplicationService:
    """只接受已发布读取器交付的 View，不能绕过 publication 自行读取结果。"""

    def __init__(self, uow_factory, published_reader: PublishedResultReader) -> None:
        self._uow_factory = uow_factory
        self._published_reader = published_reader

    def findings_for_run(self, run_id: str) -> list[dict[str, Any]]:
        view = self._published_reader.read(run_id)
        inputs = finding_inputs(self._published_reader, view)
        timestamp = view.run.finished_at_us or view.run.updated_at_us
        grouped: dict[str, list[FindingInput]] = defaultdict(list)
        for item in inputs:
            grouped[item.identity.finding_id()].append(item)

        with self._uow_factory() as work:
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
                if existing is None or work.findings.get_occurrence(finding_id, run_id) is not None:
                    continue
                previous = work.findings.latest_occurrence(finding_id)
                verdict = _aggregate_verdict(items)
                status = _occurrence_status(previous, verdict)
                occurrence = FindingOccurrence(
                    occurrence_id=occurrence_id_for(finding_id, run_id),
                    finding_id=finding_id,
                    project_id=identity.project_id,
                    run_id=run_id,
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
            work.commit()

        with self._uow_factory() as work:
            occurrences = work.findings.list_occurrences_for_run(run_id)
            records = {item.finding_id: work.findings.get(item.finding_id) for item in occurrences}
        return [
            _view_record(records[item.finding_id], item)
            for item in occurrences
            if records[item.finding_id] is not None
        ]

    def stored_findings_for_run(self, run_id: str) -> list[dict[str, Any]]:
        """只读取已持久化 Finding/Occurrence，不因报告读取产生新的事实。"""

        with self._uow_factory() as work:
            occurrences = work.findings.list_occurrences_for_run(run_id)
            records = {item.finding_id: work.findings.get(item.finding_id) for item in occurrences}
        return [
            _view_record(records[item.finding_id], item)
            for item in occurrences
            if records[item.finding_id] is not None
        ]


def finding_inputs(reader: PublishedResultReader, view: PublishedRunView) -> tuple[FindingInput, ...]:
    """按 publication 结果类型分派；V1/V2 正文均先经过 PublishedResultReader。"""

    if isinstance(view.publication.result, RunnerResultV2):
        return _v2_inputs(reader, view)
    if isinstance(view.publication.result, RunnerResultV1):
        return _v1_inputs(reader, view)
    raise TypeError("unsupported published result version")


def _v2_inputs(reader: PublishedResultReader, view: PublishedRunView) -> tuple[FindingInput, ...]:
    result = view.publication.result
    assert isinstance(result, RunnerResultV2)
    snapshot = reader.request_snapshot(view)
    contract = snapshot.contract
    subjects = {item.subject_id: item for item in contract.subjects}
    actions = {item.action_id: item for item in contract.actions}
    resources = {item.resource_id: item for item in contract.resources}
    relations = {item.relation_id: item for item in contract.relations}
    rules = {item.rule_id: item for item in contract.rules}
    outputs: list[FindingInput] = []
    for evidence in result.evidence:
        case = evidence.case_snapshot
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
                severity=_v2_severity(case.source_rule_ids, rules),
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


def _v1_inputs(reader: PublishedResultReader, view: PublishedRunView) -> tuple[FindingInput, ...]:
    if not view.evidence:
        return ()
    snapshot = reader.request_snapshot(view)
    plan = reader.document(view, "artifacts/mutation-plan.json")
    cases = {item["case_id"]: item for item in plan.get("cases", ()) if isinstance(item, dict)}
    identities = {item.id: item for item in snapshot.identities}
    resources = {item.id: item for item in snapshot.resources}
    steps = {item.id: item for item in snapshot.flow.steps}
    rules = {item.id: item for item in snapshot.contract.rules}
    outputs: list[FindingInput] = []
    for record in view.evidence:
        document = reader.evidence_document(view, record.evidence_id)
        case = cases.get(record.case_id)
        if case is None:
            raise ValueError("published V1 Evidence is missing from the published plan")
        rule = rules[case["rule_id"]]
        step = steps[case["step_id"]]
        identity_source = identities[case["identity_id"]]
        resource = resources[case["resource_id"]]
        owner = identities[resource.owner_identity_id]
        identity = FindingIdentity(
            project_id=view.run.project_id,
            permission_intent=(f"rule:{rule.id}", f"kind:{rule.kind.value}"),
            subject_class=(f"role:{identity_source.role}",),
            action=step.method.lower(),
            resource_class=("type:legacy-resource", f"owner-role:{owner.role}"),
            resource_relation=(f"kind:{rule.kind.value}", f"mutation:{case['mutation']}"),
            problem_category=f"legacy-{rule.kind.value}",
        )
        outputs.append(
            FindingInput(
                project_id=view.run.project_id,
                run_id=view.run.run_id,
                evidence_id=record.evidence_id,
                case_id=record.case_id,
                identity=identity,
                verdict=CaseVerdict(document["verdict"]),
                severity=rule.severity,
                object_context={
                    "case_id": record.case_id,
                    "resource_id": case["resource_id"],
                    "identity_id": case["identity_id"],
                    "fingerprint": case["fingerprint"],
                    "mutation": case["mutation"],
                },
                coverage_context={
                    "rule_id": rule.id,
                    "step_id": step.id,
                    "method": step.method,
                    "path_template": step.path,
                },
            )
        )
    return tuple(outputs)


def _v2_severity(rule_ids: Iterable[str], rules: Mapping[str, Any]) -> str:
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


def _occurrence_status(previous, verdict: CaseVerdict) -> OccurrenceStatus:
    if verdict is CaseVerdict.SAFE:
        return OccurrenceStatus.DISAPPEARED if previous is not None and previous.verdict != "SAFE" else OccurrenceStatus.PRESENT
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
        "schema_version": "2",
        "finding": finding.model_dump(mode="json"),
        "occurrence": occurrence.model_dump(mode="json"),
    }
