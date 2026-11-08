# 当前检查的现场预览与权威提交；不运行目标，冻结资产先写，Run/Job 在同一事务内接受。
from __future__ import annotations

import hashlib
import json
import logging
import time
from uuid import uuid4
from threading import RLock
from collections.abc import Callable
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from product.backend.infrastructure.storage import StorageUnitOfWork, RunRecord
    from product.backend.application.changes.observations import CodeObservationService
    from product.backend.application.changes.service import CurrentSourceChangeService
    from product.backend.application.checks.repairs.repair import CurrentRepairService

from pydantic import Field

from product.backend.domain.checks.plan import ActionCheckPlan, CheckPlanGap
from product.backend.domain.checks.repair import CurrentRepairReference
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.boundaries.candidate_reviews import BoundaryReviewGap
from product.backend.application.business_boundaries.candidates.reviews import project_review_gaps
from product.backend.application.business_boundaries.candidates.coverage import frozen_requirement_scope
from product.backend.infrastructure.artifacts.checks.check_validation import check_publication_budget_reason, validate_check_inputs
from product.backend.infrastructure.runtime.jobs.check_requests import CheckRequestStore
from product.backend.infrastructure.runtime.jobs.models import SubmitJob
from product.backend.infrastructure.runtime.jobs.models import JobSubmissionResult
from product.protocols.checks.scenarios import FrozenBusinessScenario,ScenarioReference
from product.protocols.checks.check_runtime import check_runtime_fingerprint
from product.protocols.checks.execution_request import Hash, LogicalId, WireModel, FrozenRequirementScope, FrozenCheckSelection, PermissionReference, canonical_execution_request_bytes, content_hash


class ExternalRecheckCommand(WireModel):
    reference: CurrentRepairReference
    deployment_statement: str = Field(min_length=1,max_length=256)


class CheckPreview(WireModel):
    project_id: LogicalId
    can_execute: bool
    gaps: tuple[CheckPlanGap, ...]
    plan_fingerprint: Hash
    action_count: int = Field(ge=0)
    case_count: int = Field(ge=0)
    actions: tuple[ActionCheckPlan, ...]
    boundary_review_gaps: tuple[BoundaryReviewGap, ...] = ()
    requirement_scope: tuple[FrozenRequirementScope, ...] = ()
    selection: FrozenCheckSelection | None = None
    omitted_review_gaps: tuple[BoundaryReviewGap, ...] = ()
    scenario: FrozenBusinessScenario | None = Field(default=None,exclude_if=lambda value:value is None)


def _preview_fingerprint(plan, scope, selection):
    fingerprint = content_hash('ScopedCheckPreview', {'plan': plan,
        'scope': tuple(item.model_dump(mode='json') for item in scope)}) if scope else plan
    return content_hash('SelectedCheckPreview', {'preview': fingerprint,
        'selection': selection.model_dump(mode='json')}) if selection is not None else fingerprint


class CheckService:
    """预览只读；提交重验全部当前事实与 expected plan，幂等性绑定完整请求字节。"""

    def __init__(self, *, uow_factory, var_dir, preparation, business_boundaries, runtime_builder,
                 registry, queue, engine_version, source_inspector, clock_us=None, code_observations: CodeObservationService | None = None, proof_authority=None):
        self._uow_factory, self._preparation = uow_factory, preparation
        self._boundaries, self._builder, self._registry = business_boundaries, runtime_builder, registry
        self._queue, self._store = queue, CheckRequestStore(var_dir)
        self._engine_version = engine_version
        self._clock = clock_us or (lambda: time.time_ns() // 1000)
        self._submission_lock = RLock()
        self._source_inspector = source_inspector
        self._changes = self._repairs = None
        self._code_observations = code_observations
        self._delivery_run_attacher = None
        self._proof_authority=proof_authority or (lambda _project,sources:not sources)
        self._authority_input=None

    def job_authorized(self,job):
        """多步骤执行持续核对源码及准确证明授权；只缓存不可变输入，不缓存授权结论。"""
        if job.run_id is None:return True
        try:
            key=(job.job_id,job.request_hash)
            if self._authority_input is None or self._authority_input[0]!=key:
                request=self._store.load(job.job_id,expected_hash=job.request_hash)
                bundle=self._store.load_bundle(job.job_id,expected_hash=request.config_fingerprint)
                self._authority_input=(key,request,bundle)
            _,request,bundle=self._authority_input
            if request.scenario is None:return True
            return (self._source_inspector(job.project_id)==request.source_fingerprint
                and self._proof_authority(job.project_id,bundle.proof_sources))
        except (OSError,ValueError,JiejianError):
            return False

    def set_revalidation_services(self, *, changes: CurrentSourceChangeService, repairs: CurrentRepairService):
        """连接变化与原题读取；同一对象可重申，不能在装配后替换成另一套服务。"""
        if (self._changes is not None and self._changes is not changes) or (self._repairs is not None and self._repairs is not repairs):
            raise ValueError("检查复验服务已经连接")
        self._changes,self._repairs = changes,repairs

    def bind_delivery_recorder(self, recorder: Callable[[StorageUnitOfWork, RunRecord, str | None], None]):
        """记录器使用 JobQueue 提供的原 UoW；连接时不调用它。"""
        if self._delivery_run_attacher is not None and self._delivery_run_attacher != recorder:
            raise ValueError("交付检查记录器已经连接")
        self._delivery_run_attacher = recorder

    def validate_connections(self):
        if any(value is None for value in (self._changes, self._repairs, self._delivery_run_attacher, self._code_observations)):
            raise ValueError("生产检查的变化、修复或记录能力尚未连接")

    def pending_request(self, run_id):
        """只读已提交但未发布的冻结请求，供项目修复状态识别正在复验的精确原题。"""
        with self._uow_factory() as work:
            run = work.runs.get(run_id)
            job = work.jobs.get_by_run(run_id)
            if run is None or job is None:
                return None
            return self._store.load(job.job_id,expected_hash=run.request_hash)

    def cancel(self, project_id, run_id):
        from product.backend.infrastructure.runtime.jobs.models import RequestCancellation
        with self._uow_factory() as work:
            run = work.runs.get(run_id)
            job = work.jobs.get_by_run(run_id)
            if run is None or run.project_id != project_id or job is None or job.operation_type != "CHECK":
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND,"本项目检查不存在")
        return self._queue.request_cancellation(RequestCancellation(job_id=job.job_id,now_us=self._clock()))

    def bind_routines(self, routines):
        self._routines = routines

    def routine_receipt(self, project_id, reference, fingerprint, operation):
        """只回读并核对原方案请求；找不到时不创建或执行检查。"""
        return self._accepted_submission(project_id, expected_plan_fingerprint=fingerprint, idempotency_key=operation,
            change_id=None, selected_permissions=None, external_recheck=None, scenario_reference=None, routine_reference=reference)

    def preview(self, project_id: str, *, change_id=None, selected_permissions=None, external_recheck=None, scenario_reference=None, routine_reference=None) -> CheckPreview:
        # 预览只反映本次读取的现场；提交会重新冻结，页面不能直接复用旧请求作为执行授权。
        preview, _request, _bundle = self._freeze(project_id,change_id=change_id, selected_permissions=selected_permissions, external_recheck=external_recheck, scenario_reference=scenario_reference, routine_reference=routine_reference)
        return preview

    def submit(self, project_id: str, *, expected_plan_fingerprint: str, idempotency_key: str, change_id=None, selected_permissions=None, external_recheck=None, scenario_reference=None, routine_reference=None):
        # 本地锁只避免同实例交错；跨进程的请求唯一性和事务前置条件仍由 JobQueue 核对。
        with self._submission_lock:
            arguments = dict(expected_plan_fingerprint=expected_plan_fingerprint, idempotency_key=idempotency_key,
                change_id=change_id, selected_permissions=selected_permissions,
                external_recheck=external_recheck, scenario_reference=scenario_reference, routine_reference=routine_reference)
            previous = self._accepted_submission(project_id, **arguments)
            if previous is not None:
                return previous
            try:
                return self._submit(project_id, **arguments)
            except JiejianError:
                # 另一进程可能在本次现场核验期间接受了同一请求；只回读，不重放目标。
                previous = self._accepted_submission(project_id, **arguments)
                if previous is not None:
                    return previous
                raise

    def _accepted_submission(self, project_id, *, expected_plan_fingerprint, idempotency_key,
                             change_id, selected_permissions, external_recheck, scenario_reference, routine_reference):
        with self._uow_factory() as work:
            job = work.jobs.get_by_idempotency(project_id, 'CHECK', idempotency_key)
            if job is None:
                return None
            request = self._store.load(job.job_id, expected_hash=job.request_hash)
            fingerprint = _preview_fingerprint(request.plan_fingerprint, request.requirement_scope, request.selection)
            original_change = request.change_context.change_id if request.change_context else None
            matches = original_change == change_id
            if routine_reference is not None:
                matches = matches and request.routine is not None and all(
                    getattr(request.routine, name) == getattr(routine_reference, name)
                    for name in ('routine_id', 'revision', 'binding_id'))
            else:
                matches = matches and request.routine is None
            if external_recheck is not None:
                # 合同 reader 核对原 Run/Case/hash；不读取当前材料或执行环境。
                contract = self._repairs.resolve(project_id, external_recheck.reference)
                matches = matches and request.external_recheck is not None and request.repair_context is not None
                if matches:
                    matches = (request.repair_context.repair_reference == contract.repair_fingerprint
                        and request.external_recheck.deployment_statement == external_recheck.deployment_statement)
            else:
                matches = matches and request.external_recheck is None
            if request.external_recheck is not None:
                fingerprint = content_hash('ExternalRecheckPreview', dict(preview=fingerprint,
                    repair=request.repair_context.repair_reference,
                    context=request.external_recheck.model_dump(mode='json')))
            if request.routine is not None:
                fingerprint = content_hash('RoutinePreview', dict(preview=fingerprint, routine=request.routine.model_dump(mode='json')))
            if routine_reference is not None:
                matches = matches and change_id is None and external_recheck is None and selected_permissions is None and scenario_reference is None
            elif change_id is not None or external_recheck is not None:
                matches = matches and selected_permissions is None and scenario_reference is None
            elif scenario_reference is not None:
                document = request.scenario.document if request.scenario else None
                matches = matches and selected_permissions is None and document is not None
                if document is not None:
                    matches = matches and (document.id, document.revision) == (scenario_reference.scenario_id, scenario_reference.revision)
            else:
                matches = matches and request.scenario is None
                supplied = None if selected_permissions is None else tuple(sorted({
                    (item.intent_id, item.revision, item.intent_hash) for item in selected_permissions}))
                original = None if request.selection is None else tuple(
                    (item.intent_id, item.revision, item.intent_hash) for item in request.selection.selected)
                matches = matches and supplied == original
            if not matches or fingerprint != expected_plan_fingerprint:
                raise JiejianError(ErrorCode.JOB_IDEMPOTENCY_CONFLICT, '同一检查请求标识不能用于不同内容')
            run = work.runs.get(job.run_id)
            if run is None or run.project_id != project_id:
                raise JiejianError(ErrorCode.STORAGE_STATE, '原检查回执关联不完整')
            return JobSubmissionResult(created=False, job=job, run=run)

    def _submit(self, project_id: str, *, expected_plan_fingerprint: str, idempotency_key: str, change_id=None, selected_permissions=None, external_recheck=None, scenario_reference=None, routine_reference=None):
        preview, request, bundle = self._freeze(project_id,change_id=change_id, selected_permissions=selected_permissions, external_recheck=external_recheck, scenario_reference=scenario_reference, routine_reference=routine_reference)
        if not preview.can_execute or request is None or preview.plan_fingerprint != expected_plan_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化",
                details={"reason": "CHECK_PLAN_CHANGED", "plan_fingerprint": preview.plan_fingerprint})
        if self._source_inspector(project_id) != request.source_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,"源码已变化，需要重新登记和准备")
        raw = canonical_execution_request_bytes(request)
        request_hash = hashlib.sha256(raw).hexdigest()
        job_id, run_id = "job_" + uuid4().hex, "run_" + uuid4().hex
        now = self._clock()
        submission = SubmitJob(project_id=project_id, operation_type="CHECK", idempotency_key=idempotency_key,
            request_hash=request_hash, plan_fingerprint=request.plan_fingerprint,
            source_fingerprint=request.source_fingerprint, policy_epoch=request.policy_epoch,
            engine_version=request.engine_version, max_attempts=1, available_at_us=now, now_us=now,
            job_id=job_id, run_id=run_id)
        def checkpoint(work):
            # 文件准备期间材料仍可能变化；在创建 Run/Job 的同一工作单元内重建计划并比较完整输入。
            current, current_request, _ = self._freeze(project_id, work=work,change_id=change_id, selected_permissions=selected_permissions, external_recheck=external_recheck, scenario_reference=scenario_reference, routine_reference=routine_reference)
            if not current.can_execute or current.plan_fingerprint != preview.plan_fingerprint or current_request is None or canonical_execution_request_bytes(current_request) != raw:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
            # 普通检查同样核现场；写入前再次扫描，不能用无 change_id 绕过源码漂移。
            if self._source_inspector(project_id) != current_request.source_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,"提交期间源码已变化")
        created = False
        try:
            self._store.write_bundle(job_id, bundle)
            self._store.write(job_id, request)
            def attach_created(work, run):
                if self._code_observations is not None:
                    self._code_observations.attach_run(work, run)
                if self._delivery_run_attacher is not None:
                    self._delivery_run_attacher(work, run, change_id)
            result = self._queue.submit(submission, precondition=checkpoint, on_created=attach_created)
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
                    logging.getLogger("jiejian.application.checks.service").warning("CHECK_ORPHAN_CLEANUP_FAILED", extra={"job_id": job_id})

    def _freeze(self, project_id, *, work=None, change_id=None, selected_permissions=None, external_recheck=None, scenario_reference=None, routine_reference=None):
        # 同次读取共享注册快照，防止计划与运行配置取到两代事实；作用域结束后不缓存授权。
        if work is None:
            with self._uow_factory() as current:
                return self._freeze(project_id, work=current,change_id=change_id, selected_permissions=selected_permissions, external_recheck=external_recheck, scenario_reference=scenario_reference, routine_reference=routine_reference)
        with self._registry.read_scope(project_id):
            return self._freeze_current(project_id, work=work, change_id=change_id, selected_permissions=selected_permissions, external_recheck=external_recheck, scenario_reference=scenario_reference, routine_reference=routine_reference)

    def _freeze_current(self, project_id, *, work, change_id=None, selected_permissions=None, external_recheck=None, scenario_reference=None, routine_reference=None):
        routine_document = routine_binding = None
        if routine_reference is not None:
            if any(value is not None for value in (change_id, selected_permissions, external_recheck, scenario_reference)):
                raise JiejianError(ErrorCode.INPUT_INVALID, '方案有自己的准确范围，不能混入其他检查或复验范围')
            routine_document, routine_binding = self._routines.resolve(project_id, routine_reference, work)
            selected_permissions = routine_document.scope.permissions or None
            scenario_reference = routine_document.scope.scenario
        if (change_id is not None or external_recheck is not None) and selected_permissions is not None:
            raise JiejianError(ErrorCode.INPUT_INVALID, "原题复验须保留原问题与正常对照，不能缩小范围。")
        if work.projects.get(project_id) is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
        scenario_document=None
        if scenario_reference is not None:
            if change_id is not None or external_recheck is not None or selected_permissions is not None:
                raise JiejianError(ErrorCode.INPUT_INVALID,'场景有自己的准确规则范围，不能混入其他范围或复验合同')
            scenario_document=work.business_scenarios.get(project_id,scenario_reference.scenario_id,scenario_reference.revision)
            if scenario_document is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'场景修订不存在')
            if not work.business_scenarios.is_reviewed(project_id,scenario_reference.scenario_id,scenario_reference.revision):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先在本机审阅并保存这份场景，再执行其中的实验')
        elif self._repairs is not None and (change_id is not None or external_recheck is not None):
            references=(external_recheck.reference,) if external_recheck is not None else self._changes.repair_references(project_id,change_id)
            frozen=[self._repairs.source_request(project_id,reference) for reference in references]
            scenarios={item.scenario.fingerprint:item.scenario for item in frozen if item.scenario is not None}
            selections={content_hash('OriginalSelection',None if item.selection is None else item.selection.model_dump(mode='json')):
                item.selection for item in frozen}
            if len(selections)>1:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'这些原问题的检查范围不同，请分别保留原题复验')
            original_selection=next(iter(selections.values()),None)
            if original_selection is not None:
                selected_permissions=original_selection.selected
            if len(scenarios)>1:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'这些原问题来自不同业务场景，请分别保留原题复验')
            if scenarios:
                scenario_document=next(iter(scenarios.values())).document
        if scenario_document is not None:
            selected_permissions=tuple(PermissionReference(**value) for value in {
                (item.permission.intent_id,item.permission.revision,item.permission.intent_hash):item.permission.model_dump()
                for experiment in scenario_document.experiments for invocation in experiment.invocations for item in invocation.items}.values())
        bundle, runtime_reason = None, None
        try:
            bundle = self._builder.build(project_id, work=work, **({} if selected_permissions is None else {"selected_permissions": selected_permissions}))
            if routine_document is not None:
                bundle = self._routines.constrain(routine_document, routine_binding, bundle)
            config_hash = check_runtime_fingerprint(bundle)
        except (JiejianError, ValueError, OSError) as exc:
            runtime_reason = exc.to_dict()["details"].get("reason", "CHECK_RUNTIME_UNAVAILABLE") if isinstance(exc, JiejianError) else "CHECK_RUNTIME_INVALID"
            registration = self._registry.snapshot(project_id)
            config_hash = content_hash("UnavailableCheckRuntime", dict(project_id=project_id,
                registry_fingerprint=None if registration is None else registration.fingerprint, reason=runtime_reason))
        plan = self._preparation.current_plan(project_id, engine_version=self._engine_version, config_fingerprint=config_hash, selected_permissions=selected_permissions)
        if scenario_document is not None:
            from product.backend.domain.checks.scenarios import compile_business_scenario
            plan=compile_business_scenario(plan,scenario_document,bundle)
        gaps = list(plan.gaps)
        if bundle is not None and plan.scenario is not None:
            from product.backend.domain.checks.scenarios import scenario_http_budget
            cost=scenario_http_budget(plan,bundle)
            if cost is not None and sum(cost)>bundle.budget.max_requests:
                gaps.extend(CheckPlanGap(action_id=action.action_id,action_revision=action.action_revision,
                    reason='SCENARIO_REQUEST_BUDGET_INSUFFICIENT') for action in plan.actions)
        if runtime_reason is not None:
            gaps.extend(CheckPlanGap(action_id=action.action_id, action_revision=action.action_revision,
                reason=runtime_reason) for action in plan.actions)
        count = sum(len(action.cases) for action in plan.actions)
        if routine_document is not None and count > routine_document.limits.max_cases:
            gaps.extend(CheckPlanGap(action_id=action.action_id, action_revision=action.action_revision,
                reason='ROUTINE_CASE_BUDGET_INSUFFICIENT') for action in plan.actions)
        budget_reason = check_publication_budget_reason(plan.actions, bundle) if bundle is not None else None
        if budget_reason is not None:
            gaps.extend(CheckPlanGap(action_id=action.action_id, action_revision=action.action_revision,
                reason=budget_reason) for action in plan.actions)
        boundary_gaps = project_review_gaps(work, project_id, plan=plan, bundle=bundle)
        requirement_scope = frozen_requirement_scope(work, project_id)
        case_rules = {(case.permission.intent_id, case.permission.revision, case.permission.intent_hash) for action in plan.actions for case in action.cases}
        for scope in requirement_scope:
            if any(item.disposition == 'IN_SCOPE' and (not item.permissions or not {(v.intent_id, v.revision, v.intent_hash) for v in item.permissions} <= case_rules) for item in scope.requirements):
                boundary_gaps += (BoundaryReviewGap(candidate_id=scope.candidate_id, revision=scope.revision,
                    issue_id='bri_'+content_hash('ScopePlanGap', scope.model_dump(mode='json')),
                    message='这份已确认要求尚未完整进入当前检查计划；请补齐材料，规则修订变化时重新关联。', status='PLAN_NOT_COVERED',
                    review_url=f'#/permissions?project_id={project_id}&candidate={scope.candidate_id}&revision={scope.revision}',
                    next_url=f'#/tests?materials=1&project_id={project_id}', next_label='核对检查材料'),)
        selection, omitted_reviews = None, ()
        if selected_permissions is not None:
            from product.backend.domain.checks.selection import permission_key, references
            from product.backend.domain.preparation.requirements import compile_action_assurance
            boundary = self._boundaries.view(project_id, work=work)
            current = tuple(item for item in boundary.permission_intents if item.effective_state.value == 'ACTIVE')
            selected_keys = {permission_key(item) for item in selected_permissions}
            controls = set()
            for action in boundary.actions:
                contract = compile_action_assurance(action, current, work.action_preparation.allow_controls(project_id))
                controls.update(permission_key(item.resolved_allow_permission) for item in contract.allow_controls
                    if permission_key(item.deny_permission) in selected_keys and item.resolved_allow_permission is not None)
            included = selected_keys | controls
            uncovered = tuple(sorted(f'{scope.candidate_id}@{scope.revision}/{item.requirement_id}'
                for scope in requirement_scope for item in scope.requirements if item.disposition == 'IN_SCOPE'
                and (not item.permissions or not {permission_key(ref) for ref in item.permissions} <= included or item.time_scope == 'HISTORY')))
            omitted_reviews, boundary_gaps = tuple(item for item in boundary_gaps if item.status != 'PLAN_NOT_COVERED'), ()
            selection = FrozenCheckSelection(selected=references(selected_keys), added_controls=references(controls-selected_keys),
                omitted=references({permission_key(item) for item in current}-included), uncovered_requirements=uncovered,
                pending_review_ids=tuple(sorted({item.issue_id for item in omitted_reviews})))
        # 预览指纹还覆盖人工确认的要求范围，避免执行计划相同却漏掉新确认的业务要求。
        preview_fingerprint = _preview_fingerprint(plan.plan_fingerprint, requirement_scope, selection)
        # 未纳入正式权限的真实要求没有action_id，不伪造Case；完整检查在冻结前阻塞。
        can_execute = bundle is not None and not gaps and not boundary_gaps and bool(plan.actions) and count > 0
        request = None
        if can_execute:
            request = self._preparation.build_execution_request(project_id, engine_version=self._engine_version,
                config_fingerprint=config_hash, budget_fingerprint=bundle.budget.fingerprint(), selected_permissions=selected_permissions)
            if plan.scenario is not None:
                values=request.model_dump(mode='json')
                values.update(actions=[action.model_dump(mode='json',exclude={'gaps'}) for action in plan.actions],
                    scenario=plan.scenario.model_dump(mode='json'),plan_fingerprint=plan.plan_fingerprint)
                request=type(request).model_validate_json(json.dumps(values))
            from product.protocols.checks.execution_request import ExecutionRequest
            request = ExecutionRequest(**request.model_dump(exclude={"requirement_scope"}),
                requirement_scope=requirement_scope, selection=selection)
            if request.environment != bundle.environment:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '执行环境已变化，请重新预览')
            if request.plan_fingerprint != plan.plan_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "准备来源已变化")
        if change_id is not None:
            from product.backend.domain.checks.repair import repair_context
            if self._changes is None or self._repairs is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,"变化复验服务未就绪")
            # 复用当前材料预览，变化检查仅重核源码、权限和映射。
            inspection = self._changes.inspect_revalidation(project_id,change_id,
                preparation_preview=CheckPreview(project_id=project_id,can_execute=can_execute,
                    boundary_review_gaps=boundary_gaps,
                    gaps=tuple(gaps),plan_fingerprint=plan.plan_fingerprint,
                    action_count=len(plan.actions),case_count=count,actions=plan.actions))
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
        if external_recheck is not None:
            from product.protocols.checks.execution_request import ExternalRecheckContext
            from product.backend.domain.checks.repair import repair_context
            if change_id is not None:
                raise JiejianError(ErrorCode.INPUT_INVALID,'外部原题复验不能混入源码变更或缩小原检查范围')
            contract, source_environment = self._repairs.external_source(project_id,external_recheck.reference)
            if contract.original_policy_epoch != plan.policy_epoch:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'原权限已变化，请重新确认问题要求')
            context=ExternalRecheckContext(source_environment_fingerprint=source_environment.fingerprint,
                deployment_statement=external_recheck.deployment_statement)
            preview_fingerprint=content_hash('ExternalRecheckPreview',dict(preview=preview_fingerprint,
                repair=contract.repair_fingerprint,context=context.model_dump(mode='json')))
            if request is not None:
                if (request.source_fingerprint is not None or request.environment is None
                    or request.environment.environment_id!=source_environment.environment_id
                    or request.environment.target!=source_environment.target or bundle.runtime.kind!='EXTERNAL_WEB'):
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,'外部原题复验要求同一环境与目标范围，且没有源码版本核验')
                request=request.model_copy(update=dict(repair_context=repair_context(contract),external_recheck=context))
        if routine_document is not None:
            context = self._routines.frozen_reference(routine_document, routine_binding)
            preview_fingerprint = content_hash('RoutinePreview', dict(preview=preview_fingerprint, routine=context.model_dump(mode='json')))
            if request is not None:
                request = request.model_copy(update=dict(routine=context))
        if request is not None:
            validate_check_inputs(request, bundle)
        return CheckPreview(project_id=project_id, can_execute=can_execute, gaps=tuple(gaps),
            boundary_review_gaps=boundary_gaps,
            requirement_scope=requirement_scope, selection=selection, omitted_review_gaps=omitted_reviews,
            plan_fingerprint=preview_fingerprint, action_count=len(plan.actions), case_count=count,
            actions=plan.actions,scenario=plan.scenario), request, bundle
