# =============================================================================
# 已发布 Run 结果读取
#
# 定位
#   数据库完成态与 immutable publication 工件之间的只读一致性边界
#
# 职责
#   核对发布清单和 hash｜拒绝 staging 或不完整结果｜生成脱敏结果视图
#
# 边界
#   不读取未发布 staging，不重新执行 Verification，也不修补缺失或不一致的历史事实。
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

from product.backend.core.lifecycle import JobState, RunLifecycle
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.redaction import redact
from product.backend.infra.storage import EvidenceIndexRecord, JobRecord, RunRecord, StorageUnitOfWork
from product.protocols import CleanupIssueCode, RunnerFailurePhase, RunnerResult
from product.backend.infra.artifacts.run_packages import ValidatedPublication, evidence_records_for_publication, final_run_dir, validate_published_run
from product.backend.infra.runtime.jobs.requests import ExecutionRequestStore
from product.protocols.execution_request import ExecutionRequestDocument
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.workflows.assistant import ErrorDiagnosisContext, diagnose_error


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
        """读取完成态 Run，并验证数据库 publication 引用、manifest 与内容 hash 一致。"""

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
        """读取 manifest 已声明的 JSON 工件；拒绝路径逃逸、未声明文件与非对象正文。"""

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

    def execution_request(self, view: PublishedRunView) -> ExecutionRequestDocument:
        """读取与已发布 Job hash 绑定的完整不可变执行请求。"""

        return ExecutionRequestStore(self._var_dir).load_historical(
            view.job.job_id,
            expected_hash=view.job.request_hash,
        )

    def request_snapshot(self, view: PublishedRunView):
        """保留项目执行快照只读接口，调用方不能借此回读 live Ledger。"""

        return self.execution_request(view).project_snapshot

    def overview(self, run_id: str, *, published: PublishedRunView | None = None) -> dict[str, Any]:
        """从当前执行快照和可信发布结果生成 GUI 只读运行概览。"""

        with self._uow_factory() as work:
            run = work.runs.get(run_id)
            job = work.jobs.get_by_run(run_id)
            events = work.job_events.list_for_job(job.job_id) if job is not None else ()
        if run is None or job is None:
            raise JiejianError(ErrorCode.ARTIFACT_NOT_PUBLISHED, "运行缺少持久任务关联")
        request = ExecutionRequestStore(self._var_dir).load_historical(
            job.job_id,
            expected_hash=job.request_hash,
        )
        snapshot = request.project_snapshot
        required_observations = sorted({requirement for case in snapshot.plan.cases for requirement in case.required_observations})
        binding_map = {binding.requirement_id: binding for binding in snapshot.observer_bindings if binding.kind.value == "OBSERVER_SPEC"}
        spec_map = {spec.observer_id: spec for spec in snapshot.observers}
        observer_health: dict[str, Any] = {"required_observations": required_observations}
        for requirement in required_observations:
            binding = binding_map.get(requirement)
            spec = spec_map.get(binding.observer_id) if binding is not None else None
            observer_health[requirement] = {
                "configured": spec is not None,
                "required": bool(spec and spec.required),
                "observer_id": binding.observer_id if binding is not None else None,
                "observer_type": binding.observer_type.value if binding is not None else None,
                "phases": [phase.value for phase in binding.phases] if binding is not None else [],
            }
        reason_codes = list(published.publication.result.reason_codes) if published is not None else []
        completed_case_count = (
            len({item.case_id for item in published.evidence})
            if published is not None
            else None
        )
        execution_errors = self._execution_errors(job, events)
        return {
            "execution_schema_version": "1",
            "result_schema_version": published.publication.result.schema_version if published is not None else None,
            "target_scope": snapshot.target.scope.model_dump(mode="json"),
            "budget": request.budget.model_dump(mode="json"),
            "observer_health": observer_health,
            "case_progress": {
                "status": (
                    "PUBLISHED"
                    if published is not None
                    else "FAILED"
                    if job.state is JobState.FAILED
                    else "UNAVAILABLE"
                ),
                "completed": completed_case_count,
                "total": len(snapshot.plan.cases),
            },
            # Finding 只能由最终化事务写入，并由上层 FindingQueries 补充数量；
            # publication reader 不在 GET 路径临时投影或写入 Finding。
            "finding_count": None,
            "reason_codes": reason_codes,
            "execution_errors": execution_errors,
            "coverage_record_count": len(snapshot.plan.coverage),
            "coverage_gap_count": len(snapshot.plan.gaps),
            "safety_context": None,
        }

    def _execution_errors(self, job: JobRecord, events: tuple[Any, ...]) -> list[dict[str, Any]]:
        """把失败事件投影为普通用户可复制的诊断，不暴露秘密或内部堆栈。"""

        if job.state is not JobState.FAILED:
            return []
        latest = next((event for event in reversed(events) if event.target_state is JobState.FAILED), None)
        metadata = latest.metadata if latest else {}
        reason_code = str(metadata.get("reason_code") or "WORKER_FATAL")
        error_code = str(metadata.get("error_code") or reason_code)
        phase_code = metadata.get("phase")
        phase_code = str(phase_code) if phase_code else None
        stage = {
            "TARGET_VALIDATION": "目标校验",
            "PREPARE_RECOVERY": "执行前恢复",
            "IDENTITY_PREPARATION": "身份准备",
            "SETUP": "测试准备",
            "BASELINE": "基线观察",
            "BEFORE": "执行前观察",
            "TARGET": "目标操作",
            "AFTER": "执行后观察",
            "EVENTUAL": "最终状态观察",
            "VERIFY": "事实验证",
            "POST_CASE_RECOVERY": "现场恢复",
            "RUNTIME_CLOSE": "运行资源关闭",
        }.get(phase_code, "后台执行")
        cause_code = metadata.get("cause_code")
        cause_code = str(cause_code) if cause_code else None
        cleanup_value = metadata.get("cleanup_issue_codes")
        cleanup_issues = (
            [item for item in cleanup_value.split(",") if item]
            if isinstance(cleanup_value, str)
            else []
        )
        runner_phase = (
            RunnerFailurePhase(phase_code)
            if phase_code in {item.value for item in RunnerFailurePhase}
            else None
        )
        cleanup_codes = tuple(
            CleanupIssueCode(item)
            for item in cleanup_issues
            if item in {code.value for code in CleanupIssueCode}
        )
        diagnosis = diagnose_error(
            ErrorDiagnosisContext(
                error_code=error_code,
                runner_phase=runner_phase,
                cause_code=cause_code,
                cleanup_issue_codes=cleanup_codes,
            )
        )
        cause = f"检查在{stage}阶段未完整结束，错误代码为 {error_code}。"
        if cause_code is not None:
            cause += f" 底层原因为 {cause_code}。"
        if cleanup_issues:
            cause += " 同时记录到现场恢复或资源关闭问题。"
        recovery = "查看对应任务日志，确认目标服务和测试环境后重新发起检查。"
        log_path = str(RuntimePaths(self._var_dir).worker_logs / f"{job.job_id}.log")
        copy_text = (
            f"界鉴任务失败\n阶段：{stage}\n原因：{cause}\n任务：{job.job_id}\n"
            f"错误代码：{error_code}\n"
            f"底层原因：{cause_code or '无'}\n"
            f"清理问题：{','.join(cleanup_issues) or '无'}\n"
            f"日志：{log_path}\n建议：{recovery}"
        )
        return [{
            "stage": stage,
            "message": cause,
            "code": error_code,
            "phase": phase_code,
            "cause_code": cause_code,
            "cleanup_issues": cleanup_issues,
            "job_id": job.job_id,
            "log_path": log_path,
            "recovery": recovery,
            "copy_text": copy_text,
            "diagnosis": diagnosis.model_dump(mode="json"),
        }]
    def evidence_document(self, view: PublishedRunView, evidence_id: str) -> dict[str, Any]:
        record = next((item for item in view.evidence if item.evidence_id == evidence_id), None)
        if record is None:
            raise JiejianError(ErrorCode.ARTIFACT_NOT_PUBLISHED, "证据不存在")
        return self.document(view, record.artifact_path)

    def evidence_detail(self, view: PublishedRunView, evidence_id: str) -> dict[str, Any]:
        return self.evidence_document(view, evidence_id)


def _evidence_identity(records: tuple[EvidenceIndexRecord, ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(sorted((item.evidence_id, item.run_id, item.case_id, item.artifact_path, item.sha256, item.byte_count) for item in records))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
