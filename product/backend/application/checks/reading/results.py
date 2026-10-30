# 当前结果只读边界：先交叉核验发布收据、不可变文件与数据库索引，再暴露既有结论。
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.lifecycle import JobState, RunLifecycle, RunVerdict
from product.backend.domain.identifiers import RUN_ID_PATTERN
from product.backend.infrastructure.artifacts.checks.check_packages import CheckPackage, check_final_directory, validate_check_package, read_check_bytes, reject_check_links
from product.backend.infrastructure.artifacts.checks.check_validation import validate_check_inputs
from product.backend.infrastructure.runtime.jobs.check_requests import CheckRequestStore
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.protocols.checks.check_result import canonical_check_document, parse_check_document, CheckRunnerProgress
from product.protocols.checks.execution_request import WireModel


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
    error_code: str | None = None
    failure_phase: str | None = None
    cause_code: str | None = None


class CheckProgressCaseView(WireModel):
    case_id: str
    action_label: str
    expectation: Literal["ALLOW", "DENY"]
    planned_subject_label: str
    planned_resource_owner_label: str
    resource_id: str
    effect_labels: tuple[str, ...]


class CheckProgressView(WireModel):
    phase: Literal["PREPARING", "EXECUTING", "FINALIZING"]
    completed_cases: int = Field(ge=0)
    planned_cases: int = Field(ge=0)
    current_case: CheckProgressCaseView | None = None


class CheckRunStatus(WireModel):
    run: CheckRunView
    job: CheckJobView | None
    progress: CheckProgressView | None
    result_integrity: Literal["VALID", "INVALID", "NOT_PUBLISHED"]


class CheckHistoryCursor(WireModel):
    created_at_us: int = Field(ge=0)
    run_id: str = Field(pattern=RUN_ID_PATTERN)


class CheckHistoryItem(WireModel):
    status: CheckRunStatus
    action_labels: tuple[str, ...] = ()
    change_id: str | None = None
    source_run_id: str | None = None
    matching_cases:tuple[str,...]=()
    matching_verdicts:tuple[str,...]=()


class CheckHistoryPage(WireModel):
    project_id: str
    items: tuple[CheckHistoryItem, ...]
    next_cursor: CheckHistoryCursor | None = None


class CheckResultReader:
    """没有凭据、执行器和写仓储入口；每次读取重新核验已发布字节，不缓存可变文件结论。"""

    def __init__(self, *, var_dir, uow_factory):
        self._var_dir, self._uow_factory = var_dir, uow_factory

    def list_for_project(self, project_id: str) -> tuple[CheckRunStatus, ...]:
        return tuple(status for status, _ in self.project_readings(project_id))

    def project_readings(self, project_id):
        """历史聚合只在当前请求传递核验后的包，避免修复与总览再次读取同一文件。"""
        with self._uow_factory() as work:
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            return tuple(self._status_and_package(work, run) for run in work.runs.list_for_project(project_id))

    def active_for_project(self, project_id: str) -> CheckRunStatus | None:
        """按持久生命周期定位一条本项目活动 Run，不为活动项验证全部历史。"""
        with self._uow_factory() as work:
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            candidates = work.runs.page_for_project(project_id, limit=1,
                lifecycles=(RunLifecycle.QUEUED, RunLifecycle.RUNNING))
            return None if not candidates else self._status(work, candidates[0])

    def history(self, project_id: str, *, limit: int = 25, before_created_at_us: int | None = None,
                before_run_id: str | None = None, query: str | None = None,
                verdict: RunVerdict | None = None, lifecycle: RunLifecycle | None = None,rule_reference:tuple[str,int,str]|None=None) -> CheckHistoryPage:
        """一次最多校验 250 条；过滤后仍以最后扫描键续读，不声称跨请求快照或总量。"""
        if not 1 <= limit <= 50 or (before_created_at_us is None) != (before_run_id is None):
            raise JiejianError(ErrorCode.INPUT_INVALID, "历史分页参数无效")
        needle = (query or "").strip().casefold()
        with self._uow_factory() as work:
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            if rule_reference is None:
                candidates = work.runs.page_for_project(project_id, limit=250,
                    before_created_at_us=before_created_at_us, before_run_id=before_run_id)
            else:
                ids=work.rule_history.runs(project_id,rule_reference,limit=250,before_time=before_created_at_us,before_run=before_run_id)
                candidates=tuple(run for run_id in ids if (run:=work.runs.get(run_id)) is not None and run.project_id==project_id)
            items, last = [], None
            for run in candidates:
                last = run
                status, package = self._status_and_package(work, run)
                labels, change_id, source_run_id = (), None, None
                matched=()
                if package is not None:
                    # request 冻结实际动作集合与顺序；可读标签只从同一已校验 bundle 按 action_id 关联。
                    configured = {action.action_id: action for action in package.bundle.actions}
                    labels = tuple(dict.fromkeys(configured[action.action_id].display_name for action in package.request.actions))
                    change_id = None if package.request.change_context is None else package.request.change_context.change_id
                    source_run_id = None if package.request.repair_context is None else package.request.repair_context.source_run_id
                    if rule_reference is not None:
                        selected_cases={case.case_id for action in package.request.actions for case in action.cases
                            if (case.permission.intent_id,case.permission.revision,case.permission.intent_hash)==rule_reference}
                        matched=tuple(item for item in package.result.case_results if item.case_id in selected_cases)
                        if not matched:continue
                        labels=tuple(dict.fromkeys(configured[item.action_id].display_name for item in matched))
                if verdict is not None and status.run.verdict != verdict:
                    continue
                if lifecycle is not None and status.run.lifecycle != lifecycle:
                    continue
                if needle and not any(needle in value.casefold() for value in (run.run_id, *labels)):
                    continue
                items.append(CheckHistoryItem(status=status, action_labels=labels,
                    change_id=change_id, source_run_id=source_run_id,matching_cases=tuple(item.case_id for item in matched),matching_verdicts=tuple(item.verdict.value for item in matched)))
                if len(items) == limit:
                    break
            cursor = None
            more=last is not None and (work.runs.has_after_for_project(project_id,last.created_at_us,last.run_id) if rule_reference is None else
                bool(work.rule_history.runs(project_id,rule_reference,limit=1,before_time=last.created_at_us,before_run=last.run_id)))
            if more:
                cursor = CheckHistoryCursor(created_at_us=last.created_at_us, run_id=last.run_id)
            return CheckHistoryPage(project_id=project_id, items=tuple(items), next_cursor=cursor)

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

    def evidence_records(self,run_id,evidence_id,case_id,*,project_id=None,record_id=None):
        from product.backend.application.checks.reading.records import record_index,record_view
        package=self.package(run_id,project_id=project_id)
        return record_index(package,evidence_id,case_id) if record_id is None else record_view(package,evidence_id,case_id,record_id)

    def evidence_bundle(self, project_id, run_id, case_id, evidence_ids):
        """同次展开所需文档和索引共享一次完整核验；其它请求仍重新校验字节。"""
        from product.backend.application.checks.reading.records import record_index
        ids = tuple(dict.fromkeys(evidence_ids))
        if not ids or len(evidence_ids) > 32:
            raise JiejianError(ErrorCode.INPUT_INVALID, '每次请选择1至32份发布证据')
        package = self.package(run_id, project_id=project_id)
        values = []
        for evidence_id in ids:
            index = record_index(package, evidence_id, case_id)
            document = next(item for item in package.evidence if item.evidence_id == evidence_id)
            values.append(dict(document=document.model_dump(mode='json'), index=index.model_dump(mode='json')))
        return dict(project_id=project_id, run_id=run_id, case_id=case_id, items=values)

    @staticmethod
    def _run(work, run_id, project_id):
        run = work.runs.get(run_id)
        if run is None or (project_id is not None and run.project_id != project_id):
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "记录不存在")
        return run

    def _status(self, work, run):
        return self._status_and_package(work, run)[0]

    def _status_and_package(self, work, run):
        job = work.jobs.get_by_run(run.run_id)
        failure = next((event.metadata for event in reversed(work.job_events.list_for_job(job.job_id)) if event.event_type == 'JOB_FAILED'), {}) if job is not None and job.state is JobState.FAILED else {}
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
                attempt=job.attempt, cancel_requested=job.cancel_requested_at_us is not None,
                error_code=failure.get('error_code'), failure_phase=failure.get('phase'), cause_code=failure.get('cause_code')),
            progress=self._progress(run, job) if package is None else CheckProgressView(phase="FINALIZING",
                completed_cases=len(package.result.case_results),
                planned_cases=sum(len(action.cases) for action in package.request.actions)),
            result_integrity=integrity), package

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
            return CheckProgressView(phase=progress.phase, completed_cases=progress.completed_cases,
                planned_cases=progress.planned_cases, current_case=self._progress_case(run, job, progress))
        except (ValueError, OSError, JiejianError):
            return None

    def _progress_case(self, run, job, progress) -> CheckProgressCaseView | None:
        """补充最近进度所指的计划考题，不证明实际请求、身份或效果已经形成。"""
        if progress.phase != "EXECUTING" or not 0 <= progress.completed_cases < progress.planned_cases:
            return None
        try:
            store = CheckRequestStore(self._var_dir)
            request = store.load(job.job_id, expected_hash=run.request_hash)
            bundle = store.load_bundle(job.job_id, expected_hash=request.config_fingerprint)
            validate_check_inputs(request, bundle)
            if (request.project_id, request.source_fingerprint, request.plan_fingerprint,
                request.policy_epoch, request.engine_version) != (run.project_id, run.source_fingerprint,
                run.plan_fingerprint, run.policy_epoch, run.engine_version) or (
                job.run_id, job.project_id, job.request_hash) != (run.run_id, run.project_id, run.request_hash):
                return None
            cases = [(action, case) for action in request.actions for case in action.cases]
            # 必须跟随 infra/execution/check_executor.py::execute 的串行顺序，不能按请求数组位置猜当前题。
            cases.sort(key=lambda pair: (pair[1].permission.expectation == "DENY", pair[0].action_id, pair[1].case_id))
            if progress.planned_cases != len(cases):
                return None
            action, case = cases[progress.completed_cases]
            configured = next((item for item in bundle.actions if item.action_id == action.action_id), None)
            identities = {item.identity_id: item for item in bundle.identities}
            subject = identities.get(case.subject_test_identity_id)
            owner = identities.get(case.resource_owner_test_identity_id)
            if configured is None or subject is None or owner is None:
                return None
            proofs = {item.binding_fingerprint: item for item in configured.proofs}
            if any(item.binding_fingerprint not in proofs for item in case.proof_requirements):
                return None
            labels = tuple(dict.fromkeys(proofs[item.binding_fingerprint].business_label for item in case.proof_requirements))
            return CheckProgressCaseView(case_id=case.case_id, action_label=configured.display_name,
                expectation=case.permission.expectation, planned_subject_label=subject.label,
                planned_resource_owner_label=owner.label, resource_id='由本次创建后独立识别' if getattr(configured,'created_resource',None) is not None else case.resource_id, effect_labels=labels)
        except (ValueError, OSError, JiejianError):
            # 冻结资产不可读或关联失效只降级本说明；原有效阶段/计数继续保留，编程错误不宽泛吞掉。
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
