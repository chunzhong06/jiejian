# =============================================================================
# 已发布 Run 结果读取
#
# 定位
#   数据库完成态与 immutable publication 工件之间的只读一致性边界
#
# 职责
#   核对发布清单和 hash｜拒绝 staging 或不完整结果｜生成脱敏结果视图
#
# 调用链
#   CLI / API → PublishedResultReader → Storage / published artifacts
# =============================================================================

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.lifecycle import RunLifecycle
from ..errors import ErrorCode, JiejianError
from ..redaction import redact
from ..storage import EvidenceIndexRecord, JobRecord, RunRecord, StorageUnitOfWork
from ..execution.published_artifacts import (
    ValidatedPublication,
    evidence_records_for_publication,
    final_run_dir,
    validate_published_run,
)
from ..execution.request_store import ExecutionRequestStore


@dataclass(frozen=True, slots=True)
class PublishedRunView:
    run: RunRecord
    job: JobRecord
    publication: ValidatedPublication
    evidence: tuple[EvidenceIndexRecord, ...]


class PublishedResultReader:
    """供报告、Finding 与证据读取共同复用的发布态验证服务。"""

    def __init__(self, var_dir: Path, uow_factory: Callable[..., StorageUnitOfWork]) -> None:
        self._var_dir = var_dir.resolve()
        self._uow_factory = uow_factory

    def read(self, run_id: str) -> PublishedRunView:
        with self._uow_factory() as work:
            run = work.runs.get(run_id)
            job = work.jobs.get_by_run(run_id)
            indexed = work.evidence.list_for_run(run_id)
        if run is None or job is None:
            raise JiejianError(ErrorCode.ARTIFACT_NOT_PUBLISHED, "运行未形成可读取的发布结果")
        if run.lifecycle not in {RunLifecycle.COMPLETED, RunLifecycle.SAFETY_STOPPED}:
            raise JiejianError(ErrorCode.ARTIFACT_NOT_PUBLISHED, "运行尚未完成发布")
        publication = validate_published_run(final_run_dir(self._var_dir, run.project_id, run.run_id))
        if (
            publication.manifest.run_id != run.run_id
            or publication.manifest.project_id != run.project_id
            or publication.manifest.job_id != job.job_id
            or publication.result.run_id != run.run_id
            or publication.result.job_id != job.job_id
            or publication.result.run_lifecycle is not run.lifecycle
            or publication.result.verdict is not run.verdict
        ):
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "发布结果与数据库运行记录不一致")
        expected = evidence_records_for_publication(
            publication.final_dir,
            publication.result,
            created_at_us=max(publication.manifest.published_at_us, publication.result.finished_at_us),
        )
        if _evidence_identity(indexed) != _evidence_identity(expected):
            raise JiejianError(ErrorCode.ARTIFACT_HASH_MISMATCH, "证据索引与发布内容不一致")
        return PublishedRunView(run=run, job=job, publication=publication, evidence=expected)

    def document(self, view: PublishedRunView, artifact_path: str) -> dict[str, Any]:
        artifact = next((item for item in view.publication.manifest.files if item.path == artifact_path), None)
        if artifact is None:
            raise JiejianError(ErrorCode.ARTIFACT_NOT_PUBLISHED, "发布工件不存在")
        path = (view.publication.final_dir / artifact.path).resolve()
        if not path.is_relative_to(view.publication.final_dir.resolve()):
            raise JiejianError(ErrorCode.ARTIFACT_HASH_MISMATCH, "发布工件路径越界")
        try:
            raw = path.read_bytes()
            if len(raw) != artifact.byte_count:
                raise ValueError("byte count")
            if hashlib.sha256(raw).hexdigest() != artifact.sha256:
                raise ValueError("file hash")
            document = json.loads(raw, object_pairs_hook=_unique_object)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise JiejianError(ErrorCode.ARTIFACT_HASH_MISMATCH, "发布工件完整性校验失败") from None
        if not isinstance(document, dict):
            raise JiejianError(ErrorCode.ARTIFACT_HASH_MISMATCH, "发布工件 JSON 结构无效")
        return redact(document)

    def report(self, view: PublishedRunView) -> dict[str, Any]:
        return self.document(view, "artifacts/report/report.json")

    def findings(self, view: PublishedRunView) -> list[dict[str, Any]]:
        """只从已验证 Evidence 派生可跟踪问题，SAFE 不构成 Finding。"""

        findings: list[dict[str, Any]] = []
        for record in view.evidence:
            item = self.evidence_document(view, record.evidence_id)
            verdict = item.get("verdict")
            if verdict == "SAFE":
                continue
            findings.append(
                {
                    "schema_version": "1",
                    "finding_id": item.get("evidence_id"),
                    "verdict": verdict,
                    "severity": "high" if verdict == "VULNERABLE" else "unknown",
                    "evidence_refs": [item.get("evidence_id")],
                }
            )
        return findings

    def overview(self, run_id: str, *, published: PublishedRunView | None = None) -> dict[str, Any]:
        """从不可变执行快照和可信发布结果生成 GUI 只读运行概览。"""

        with self._uow_factory() as work:
            run = work.runs.get(run_id)
            job = work.jobs.get_by_run(run_id)
        if run is None or job is None:
            raise JiejianError(ErrorCode.ARTIFACT_NOT_PUBLISHED, "运行缺少持久任务关联")
        request = ExecutionRequestStore(self._var_dir).load(job.job_id, expected_hash=job.request_hash)
        snapshot = request.project_snapshot
        required_observers = sorted(
            {observer for rule in snapshot.contract.rules for observer in rule.required_observers}
        )
        observer_health = {
            "schema_version": "1",
            "http": {"configured": True, "required": "http" in required_observers},
            "owner_api": {
                "configured": snapshot.owner_observer_enabled,
                "required": "owner_api" in required_observers,
            },
            "required_observers": required_observers,
        }
        case_progress: dict[str, Any] = {
            "schema_version": "1",
            "status": "UNAVAILABLE",
            "completed": None,
            "total": None,
        }
        finding_count: int | None = None
        reason_codes: list[str] = []
        safety_context: dict[str, Any] | None = None
        if published is not None:
            reason_codes = list(published.publication.result.reason_codes)
            findings = self.findings(published)
            finding_count = len(findings)
            try:
                plan = self.document(published, "artifacts/mutation-plan.json")
            except JiejianError as exc:
                if exc.code != ErrorCode.ARTIFACT_NOT_PUBLISHED.value:
                    raise
            else:
                cases = plan.get("cases")
                if not isinstance(cases, list):
                    raise JiejianError(ErrorCode.ARTIFACT_HASH_MISMATCH, "已发布变异计划结构无效")
                case_progress = {
                    "schema_version": "1",
                    "status": "PUBLISHED",
                    "completed": len(published.evidence),
                    "total": len(cases),
                }
            if run.lifecycle is RunLifecycle.SAFETY_STOPPED:
                safety_context = {
                    "schema_version": "1",
                    "reason_codes": reason_codes,
                    "target_scope": snapshot.target.model_dump(mode="json"),
                    "budget": request.budget.model_dump(mode="json"),
                }
        return {
            "schema_version": "1",
            "target_scope": snapshot.target.model_dump(mode="json"),
            "budget": request.budget.model_dump(mode="json"),
            "observer_health": observer_health,
            "case_progress": case_progress,
            "finding_count": finding_count,
            "reason_codes": reason_codes,
            "safety_context": safety_context,
        }

    def evidence_document(self, view: PublishedRunView, evidence_id: str) -> dict[str, Any]:
        record = next((item for item in view.evidence if item.evidence_id == evidence_id), None)
        if record is None:
            raise JiejianError(ErrorCode.ARTIFACT_NOT_PUBLISHED, "证据不存在")
        return self.document(view, record.artifact_path)

    def evidence_detail(self, view: PublishedRunView, evidence_id: str) -> dict[str, Any]:
        """以已发布 plan 与不可变请求快照补充证据差分展示数据。"""

        evidence = self.evidence_document(view, evidence_id)
        plan = self.document(view, "artifacts/mutation-plan.json")
        cases = plan.get("cases")
        if not isinstance(cases, list):
            raise JiejianError(ErrorCode.ARTIFACT_HASH_MISMATCH, "变异计划结构无效")
        case = next((item for item in cases if isinstance(item, dict) and item.get("case_id") == evidence.get("case_id")), None)
        if case is None:
            raise JiejianError(ErrorCode.ARTIFACT_HASH_MISMATCH, "证据未在已发布变异计划中声明")
        request = ExecutionRequestStore(self._var_dir).load(view.job.job_id, expected_hash=view.job.request_hash)
        steps = request.project_snapshot.flow.steps
        step = next((item for item in steps if item.id == case.get("step_id")), None)
        if step is None:
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "变异计划与执行请求快照不一致")
        try:
            baseline_path = step.path.format(resource_id=step.resource_id)
        except (IndexError, KeyError, ValueError):
            raise JiejianError(ErrorCode.ARTIFACT_FENCE, "执行请求快照中的基线路径无效") from None
        baseline = {
            "identity_id": step.identity_id,
            "method": step.method,
            "path": baseline_path,
            "resource_id": step.resource_id,
            "json_body": step.json_body,
        }
        return {
            **evidence,
            "difference": {
                "schema_version": "1",
                "baseline_identity_id": step.identity_id,
                "mutation_identity_id": case.get("identity_id"),
                "baseline_request": baseline,
                "mutation_request": evidence.get("request", {}),
                "side_effect_observations": evidence.get("observations", []),
            },
        }


def _evidence_identity(records: tuple[EvidenceIndexRecord, ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(sorted((item.evidence_id, item.run_id, item.case_id, item.artifact_path, item.sha256, item.byte_count) for item in records))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
