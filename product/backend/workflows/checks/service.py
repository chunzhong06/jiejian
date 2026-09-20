# 当前检查的现场预览与权威提交；不运行目标，冻结资产先写，Run/Job 在同一事务内接受。
from __future__ import annotations

import hashlib
import json
import logging
import time
from uuid import uuid4
from threading import RLock

from pydantic import Field

from product.backend.core.check_plan import ActionCheckPlan, CheckPlanGap
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.artifacts.check_validation import check_publication_budget_reason, validate_check_inputs
from product.backend.infra.runtime.jobs.check_requests import CheckRequestStore
from product.backend.infra.runtime.jobs.models import SubmitJob
from product.protocols.check_runtime import check_runtime_fingerprint
from product.protocols.execution_v3 import Hash, LogicalId, WireModel, canonical_execution_request_v3_bytes, content_hash


class CheckPreview(WireModel):
    project_id: LogicalId
    can_execute: bool
    gaps: tuple[CheckPlanGap, ...]
    plan_fingerprint: Hash
    action_count: int = Field(ge=0)
    case_count: int = Field(ge=0)
    actions: tuple[ActionCheckPlan, ...]


class CheckService:
    """预览只读；提交重验全部当前事实与 expected plan，幂等性绑定完整请求字节。"""

    def __init__(self, *, uow_factory, var_dir, preparation, business_boundaries, runtime_builder,
                 registry, queue, engine_version, source_inspector, clock_us=None):
        self._uow_factory, self._preparation = uow_factory, preparation
        self._boundaries, self._builder, self._registry = business_boundaries, runtime_builder, registry
        self._queue, self._store = queue, CheckRequestStore(var_dir)
        self._engine_version = engine_version
        self._clock = clock_us or (lambda: time.time_ns() // 1000)
        self._submission_lock = RLock()
        self._source_inspector = source_inspector
        self._changes = self._repairs = None
        self.code_observations = None

    def set_revalidation_services(self, *, changes, repairs):
        self._changes,self._repairs = changes,repairs

    def pending_request(self, run_id):
        """只读已提交但未发布的冻结请求，供项目修复状态识别正在复验的精确原题。"""
        with self._uow_factory() as work:
            run = work.runs.get(run_id)
            job = work.jobs.get_by_run(run_id)
            if run is None or job is None:
                return None
            return self._store.load(job.job_id,expected_hash=run.request_hash)

    def cancel(self, project_id, run_id):
        from product.backend.infra.runtime.jobs.models import RequestCancellation
        with self._uow_factory() as work:
            run = work.runs.get(run_id)
            job = work.jobs.get_by_run(run_id)
            if run is None or run.project_id != project_id or job is None or job.operation_type != "CHECK":
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND,"本项目检查不存在")
        return self._queue.request_cancellation(RequestCancellation(job_id=job.job_id,now_us=self._clock()))

    def preview(self, project_id: str, *, change_id=None) -> CheckPreview:
        preview, _request, _bundle = self._freeze(project_id,change_id=change_id)
        return preview

    def submit(self, project_id: str, *, expected_plan_fingerprint: str, idempotency_key: str, change_id=None):
        with self._submission_lock:
            return self._submit(project_id, expected_plan_fingerprint=expected_plan_fingerprint, idempotency_key=idempotency_key,change_id=change_id)

    def _submit(self, project_id: str, *, expected_plan_fingerprint: str, idempotency_key: str, change_id=None):
        preview, request, bundle = self._freeze(project_id,change_id=change_id)
        if not preview.can_execute or request is None or preview.plan_fingerprint != expected_plan_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化",
                details={"reason": "CHECK_PLAN_CHANGED", "plan_fingerprint": preview.plan_fingerprint})
        if self._source_inspector(project_id) != request.source_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,"源码已变化，需要重新登记和准备")
        raw = canonical_execution_request_v3_bytes(request)
        request_hash = hashlib.sha256(raw).hexdigest()
        job_id, run_id = "job_" + uuid4().hex, "run_" + uuid4().hex
        now = self._clock()
        submission = SubmitJob(project_id=project_id, operation_type="CHECK", idempotency_key=idempotency_key,
            request_hash=request_hash, plan_fingerprint=request.plan_fingerprint,
            source_fingerprint=request.source_fingerprint, policy_epoch=request.policy_epoch,
            engine_version=request.engine_version, max_attempts=1, available_at_us=now, now_us=now,
            job_id=job_id, run_id=run_id)
        def checkpoint(work):
            current, current_request, current_bundle = self._freeze(project_id, work=work,change_id=change_id)
            if not current.can_execute or current_request is None or canonical_execution_request_v3_bytes(current_request) != raw:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
            validate_check_inputs(current_request, current_bundle)
            # 普通检查同样核现场；写入前再次扫描，不能用无 change_id 绕过源码漂移。
            if self._source_inspector(project_id) != current_request.source_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,"提交期间源码已变化")
        created = False
        try:
            self._store.write_bundle(job_id, bundle)
            self._store.write(job_id, request)
            metadata = {} if self.code_observations is None else {"on_created": self.code_observations.attach_run}
            result = self._queue.submit(submission, precondition=checkpoint, **metadata)
            created = result.created
            return result
        finally:
            if not created:
                # 只有读回确认本次随机 Job ID 没有持久引用后，才清理这两个原 hash 文件。
                try:
                    with self._uow_factory() as work:
                        orphan = work.jobs.get(job_id) is None
                    if orphan:
                        self._store.remove_if_matches(job_id, request_hash)
                        self._store.remove_if_matches(job_id, request_hash, config_hash=request.config_fingerprint)
                except (JiejianError, OSError):
                    logging.getLogger(__name__).warning("CHECK_ORPHAN_CLEANUP_FAILED", extra={"job_id": job_id})

    def _freeze(self, project_id, *, work=None, change_id=None):
        if work is None:
            with self._uow_factory() as current:
                return self._freeze(project_id, work=current,change_id=change_id)
        if work.projects.get(project_id) is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
        bundle, runtime_reason = None, None
        try:
            bundle = self._builder.build(project_id, work=work)
            config_hash = check_runtime_fingerprint(bundle)
        except (JiejianError, ValueError, OSError) as exc:
            runtime_reason = exc.to_dict()["details"].get("reason", "CHECK_RUNTIME_UNAVAILABLE") if isinstance(exc, JiejianError) else "CHECK_RUNTIME_INVALID"
            registration = self._registry.snapshot(project_id)
            config_hash = content_hash("UnavailableCheckRuntime", dict(project_id=project_id,
                registry_fingerprint=None if registration is None else registration.fingerprint, reason=runtime_reason))
        plan = self._preparation.current_plan(project_id, engine_version=self._engine_version, config_fingerprint=config_hash)
        gaps = list(plan.gaps)
        if runtime_reason is not None:
            gaps.extend(CheckPlanGap(action_id=action.action_id, action_revision=action.action_revision,
                reason=runtime_reason) for action in plan.actions)
        count = sum(len(action.cases) for action in plan.actions)
        budget_reason = check_publication_budget_reason(plan.actions, bundle) if bundle is not None else None
        if budget_reason is not None:
            gaps.extend(CheckPlanGap(action_id=action.action_id, action_revision=action.action_revision,
                reason=budget_reason) for action in plan.actions)
        can_execute = bundle is not None and not gaps and bool(plan.actions) and count > 0
        request = None
        if can_execute:
            request = self._preparation.build_execution_request_v3(project_id, engine_version=self._engine_version,
                config_fingerprint=config_hash, budget_fingerprint=bundle.budget.fingerprint())
            validate_check_inputs(request, bundle)
            if request.plan_fingerprint != plan.plan_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
        if change_id is not None:
            from product.backend.core.check_repair import repair_context
            if self._changes is None or self._repairs is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,"变化复验服务未就绪")
            inspection = self._changes.inspect_revalidation(project_id,change_id)
            if inspection.status != "READY" or not inspection.can_execute:
                can_execute = False
                gaps.extend(CheckPlanGap(action_id=action.action_id,action_revision=action.action_revision,
                    reason="CHANGE_"+inspection.status) for action in plan.actions)
                request = None
            elif request is not None:
                manifest,_,_ = self._changes.get(project_id,change_id)
                context = self._changes.context(project_id,change_id)
                values = request.model_dump(mode="json")
                values["change_context"] = context.model_dump(mode="json")
                if manifest.repair_reference is not None:
                    contract = self._repairs.resolve(project_id,manifest.repair_reference)
                    if contract.original_policy_epoch != request.policy_epoch:
                        raise JiejianError(ErrorCode.STATE_PRECONDITION,"原权限已变化，修复要求已失效")
                    values["repair_context"] = repair_context(contract).model_dump(mode="json")
                request = type(request).model_validate_json(json.dumps(values))
        return CheckPreview(project_id=project_id, can_execute=can_execute, gaps=tuple(gaps),
            plan_fingerprint=plan.plan_fingerprint, action_count=len(plan.actions), case_count=count,
            actions=plan.actions), request, bundle
