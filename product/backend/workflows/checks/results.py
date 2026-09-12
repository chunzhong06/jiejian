# 当前结果只读边界：先交叉核验发布收据、不可变文件与数据库索引，再暴露既有结论。
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState, RunLifecycle, RunVerdict
from product.backend.infra.artifacts.check_packages import (
    CheckPackage, check_final_directory, validate_check_package,
    read_check_bytes, reject_check_links,
)
from product.backend.infra.runtime.paths import RuntimePaths
from product.protocols.check_result import canonical_check_document, parse_check_document, CheckRunnerProgress
from product.protocols.execution_v3 import WireModel


class CheckRunView(WireModel):
    run_id: str
    project_id: str
    lifecycle: RunLifecycle
    verdict: RunVerdict | None
    plan_fingerprint: str
    policy_epoch: int = Field(ge=0)
    created_at_us: int = Field(ge=0)
    finished_at_us: int | None


class CheckJobView(WireModel):
    job_id: str
    state: JobState
    attempt: int = Field(ge=0)
    cancel_requested: bool


class CheckProgressView(WireModel):
    phase: Literal["PREPARING", "EXECUTING", "FINALIZING"]
    completed_cases: int = Field(ge=0)
    planned_cases: int = Field(ge=0)


class CheckRunStatus(WireModel):
    run: CheckRunView
    job: CheckJobView | None
    progress: CheckProgressView | None
    result_integrity: Literal["VALID", "INVALID", "NOT_PUBLISHED"]


class CheckResultReader:
    """没有凭据、执行器和写仓储入口；每次读取重新核验已发布字节，不缓存可变文件结论。"""

    def __init__(self, *, var_dir, uow_factory):
        self._var_dir, self._uow_factory = var_dir, uow_factory

    def list_for_project(self, project_id: str) -> tuple[CheckRunStatus, ...]:
        with self._uow_factory() as work:
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            return tuple(self._status(work, run) for run in work.runs.list_for_project(project_id))

    def status(self, run_id: str, *, project_id: str | None = None) -> CheckRunStatus:
        with self._uow_factory() as work:
            return self._status(work, self._run(work, run_id, project_id))

    def package(self, run_id: str, *, project_id: str | None = None) -> CheckPackage:
        with self._uow_factory() as work:
            run = self._run(work, run_id, project_id)
            return self._package(work, run, work.jobs.get_by_run(run_id))

    def evidence_index(self, run_id: str):
        with self._uow_factory() as work:
            run = self._run(work, run_id, None)
            self._package(work, run, work.jobs.get_by_run(run_id))
            return work.evidence.list_for_run(run_id)

    def evidence(self, run_id: str, evidence_id: str):
        package = self.package(run_id)
        found = next((item for item in package.evidence if item.evidence_id == evidence_id), None)
        if found is None:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "记录不存在")
        return found

    @staticmethod
    def _run(work, run_id, project_id):
        run = work.runs.get(run_id)
        if run is None or (project_id is not None and run.project_id != project_id):
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "记录不存在")
        return run

    def _status(self, work, run):
        job = work.jobs.get_by_run(run.run_id)
        integrity, package = "NOT_PUBLISHED", None
        if work.check_publications.get(run.run_id) is not None or run.verdict is not None:
            try:
                package = self._package(work, run, job)
                integrity = "VALID"
            except JiejianError as exc:
                if not exc.code.startswith("ARTIFACT_"):
                    raise
                integrity = "INVALID"
        # 生命周期是数据库事实；安全结论只在整个发布集合有效时暴露，不修改持久状态。
        return CheckRunStatus(run=CheckRunView(run_id=run.run_id, project_id=run.project_id,
            lifecycle=run.lifecycle, verdict=package.result.verdict if package is not None else None,
            plan_fingerprint=run.plan_fingerprint, policy_epoch=run.policy_epoch,
            created_at_us=run.created_at_us, finished_at_us=run.finished_at_us),
            job=None if job is None else CheckJobView(job_id=job.job_id, state=job.state,
                attempt=job.attempt, cancel_requested=job.cancel_requested_at_us is not None),
            progress=self._progress(run, job) if package is None else CheckProgressView(phase="FINALIZING",
                completed_cases=len(package.result.case_results),
                planned_cases=sum(len(action.cases) for action in package.request.actions)),
            result_integrity=integrity)

    def _progress(self, run, job):
        if job is None or job.operation_type != "CHECK" or job.state is not JobState.RUNNING:
            return None
        root = RuntimePaths(self._var_dir).jobs
        path = root / job.job_id / "attempts" / f"{job.attempt}-{job.fencing_token}" / "progress.json"
        try:
            reject_check_links(root, path)
            progress = parse_check_document(read_check_bytes(path), CheckRunnerProgress)
            if (progress.run_id, progress.job_id, progress.attempt, progress.fencing_token, progress.request_hash) != (
                run.run_id, job.job_id, job.attempt, job.fencing_token, run.request_hash):
                return None
            return CheckProgressView(phase=progress.phase, completed_cases=progress.completed_cases, planned_cases=progress.planned_cases)
        except (ValueError, OSError, JiejianError):
            return None

    def _package(self, work, run, job):
        receipt = work.check_publications.get(run.run_id)
        if receipt is None:
            raise JiejianError(ErrorCode.ARTIFACT_NOT_PUBLISHED, "结果尚未发布")
        package = validate_check_package(check_final_directory(self._var_dir, run.project_id, run.run_id), published=True)
        manifest, result, request = package.manifest, package.result, package.request
        digest = hashlib.sha256(canonical_check_document(manifest)).hexdigest()
        valid = job is not None and manifest is not None and (
            receipt.run_id, receipt.job_id, receipt.attempt, receipt.fencing_token,
            receipt.request_hash, receipt.result_hash, receipt.manifest_hash, receipt.published_at_us
        ) == (run.run_id, result.job_id, result.attempt, result.fencing_token,
            result.request_hash, manifest.result_hash, digest, manifest.published_at_us)
        valid = valid and (job.operation_type, job.state, job.run_id, job.project_id,
            job.request_hash, job.attempt, job.fencing_token, job.cancel_requested_at_us) == (
            "CHECK", JobState.SUCCEEDED, run.run_id, request.project_id, result.request_hash,
            result.attempt, result.fencing_token, None)
        valid = valid and (run.project_id, run.request_hash, run.plan_fingerprint, run.source_fingerprint,
            run.policy_epoch, run.engine_version, run.lifecycle, run.verdict) == (
            request.project_id, result.request_hash, request.plan_fingerprint, request.source_fingerprint,
            request.policy_epoch, request.engine_version, result.lifecycle, result.verdict)
        files = {item.path: item for item in package.files}
        actual = {(item.evidence_id, item.run_id, item.case_id, item.artifact_path,
            item.sha256, item.byte_count, item.created_at_us) for item in work.evidence.list_for_run(run.run_id)}
        expected = {(item.evidence_id, run.run_id, item.case.case_id, f"evidence/{item.evidence_id}.json",
            item.evidence_id[3:], files[f"evidence/{item.evidence_id}.json"].byte_count,
            manifest.published_at_us) for item in package.evidence}
        if not valid or actual != expected:
            raise JiejianError(ErrorCode.ARTIFACT_MANIFEST, "发布结果完整性校验失败")
        return package
