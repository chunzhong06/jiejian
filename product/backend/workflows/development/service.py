# 拥有开发任务、变化交付与回执事务；稳定读取入口委托唯一 reader，不拆分一次命令的提交。
from __future__ import annotations
import time
from uuid import uuid4
from product.backend.core.development import DevelopmentAcceptance, DevelopmentContext, DevelopmentDelivery, DevelopmentReceipt, DevelopmentTask
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.changes.service import permission_refs
from product.backend.workflows.development.operations import operation_fingerprint, require_active_task_version
from product.backend.workflows.development.reading import DevelopmentReader


class DevelopmentService:
    def __init__(self, *, uow_factory, understanding, boundaries, changes, clock_us=None, results=None, repairs=None, reading=None):
        self._uow, self._understanding, self._boundaries, self._changes = uow_factory, understanding, boundaries, changes
        self._clock = clock_us or (lambda: time.time_ns() // 1000)
        self._reader = reading or DevelopmentReader(uow_factory, results=results, repairs=repairs)

    def bind_runtime_reader(self, reader):
        """组合根连接运行读取者；读取仍由同一个 DevelopmentReader 负责。"""
        self._reader.bind_runtime_reader(reader)

    def validate_connections(self):
        self._reader.validate_connections()

    def history(self, project_id, *, before_task_id=None, limit=20):
        return self._reader.history(project_id, before_task_id=before_task_id, limit=limit)

    def delivery_page(self, project_id, task_id, *, before_ordinal=None, limit=20):
        return self._reader.delivery_page(project_id, task_id, before_ordinal=before_ordinal, limit=limit)

    def delivery_details(self, project_id, change_id):
        return self._reader.delivery_details(project_id, change_id)

    def attach_check_run(self, work, run, change_id):
        """和 Run/Job 同事务建立精确索引；不按时间或相同源码猜测交付归属。"""
        if change_id is None:
            return
        delivery = work.development.delivery_for_change(run.project_id, change_id)
        if delivery is None:
            return
        snapshot = work.source_changes.snapshot(delivery.current_snapshot_id)
        if snapshot is None or snapshot.source_fingerprint != run.source_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "检查源码与交付记录不一致")
        work.development.add_check_run(delivery.delivery_id, run.run_id, run.created_at_us)

    def delivery_verification(self, project_id, delivery_id):
        return self._reader.delivery_verification(project_id, delivery_id)

    @staticmethod
    def _replay(work, project_id, kind, operation_id, fingerprint):
        receipt = work.development.receipt(project_id, kind, operation_id)
        if receipt is not None and receipt.request_fingerprint != fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "同一操作标识已用于不同内容，请核对原回执")
        return receipt

    def receipt(self, project_id, kind, operation_id):
        return self._reader.receipt(project_id, kind, operation_id)

    def task(self, project_id, task_id):
        return self._reader.task(project_id, task_id)

    def list(self, project_id, *, limit=50):
        return self._reader.list(project_id, limit=limit)

    def context(self, project_id, context_id):
        return self._reader.context(project_id, context_id)

    def active(self, project_id):
        return self._reader.active(project_id)

    def view(self, project_id, task_id):
        return self._reader.view(project_id, task_id)

    def _context_for(self, work, project_id, task_id, revision, title, goal):
        understanding = work.application_understanding.get(project_id)
        if understanding is None or not understanding.source_analysis_authorized or not understanding.source_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "请先确认应用并完成源码分析")
        boundary = self._boundaries.view(project_id, work=work)
        refs = permission_refs(boundary)
        snapshot = work.source_changes.snapshot_for_fingerprint(project_id, understanding.source_fingerprint)
        if not refs or snapshot is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "请先确认权限要求和完整源码起点")
        return DevelopmentContext(context_id="ctx_" + uuid4().hex, task_id=task_id, project_id=project_id,
            revision=revision, title=title, goal=goal, start_snapshot_id=snapshot.snapshot_id,
            source_fingerprint=snapshot.source_fingerprint, policy_epoch=boundary.policy_epoch,
            permission_refs=refs, created_at_us=self._clock())

    def _current_context(self, work, task, context_id):
        context = work.development.context(task.project_id, context_id)
        if context is None or task.context_id != context_id or context.task_id != task.task_id or context.revision != task.revision:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "开工上下文已失效，请读取本次任务的新上下文")
        boundary = self._boundaries.view(task.project_id, work=work)
        if boundary.policy_epoch != context.policy_epoch or permission_refs(boundary) != context.permission_refs:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "权限要求已变化，请先更新任务上下文")
        return context

    def _finish(self, work, task, kind, operation_id, fingerprint, *, delivery=None):
        receipt = DevelopmentReceipt(project_id=task.project_id, operation_id=operation_id, kind=kind,
            request_fingerprint=fingerprint, task_id=task.task_id, task_version=task.version, context_id=task.context_id,
            delivery_id=None if delivery is None else delivery.delivery_id,
            change_id=None if delivery is None else delivery.change_id, created_at_us=self._clock())
        work.development.add_receipt(receipt)
        work.commit()
        # 不在写后读取 Workspace；同步失败不能掩盖已保存回执。
        return receipt

    def create(self, project_id, *, operation_id, title, goal, expected_version=0):
        payload = dict(title=title, goal=goal, expected_version=expected_version)
        fingerprint = operation_fingerprint(project_id, "CREATE", operation_id, payload)
        with self._uow() as work:
            work.acquire_write_lock()
            replay = self._replay(work, project_id, "CREATE", operation_id, fingerprint)
            if replay is not None:
                return replay
            if type(expected_version) is not int or expected_version != 0:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "创建任务的预期版本必须为零")
            active = work.development.active(project_id)
            if active is not None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前应用已有未结束任务", details={"task_id": active.task_id})
            context = self._context_for(work, project_id, "dvt_" + uuid4().hex, 1, title, goal)
            # 当前静态扫描有界且不执行应用；只有与已保存起点一致才允许开工。
            if self._understanding.inspect_source_fingerprint(project_id) != context.source_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "源码起点已变化，请重新分析后建立任务")
            task = DevelopmentTask(task_id=context.task_id, project_id=project_id, version=1, revision=1,
                context_id=context.context_id, created_at_us=context.created_at_us, updated_at_us=context.created_at_us)
            work.development.add_task(task)
            work.development.add_context(context)
            return self._finish(work, task, "CREATE", operation_id, fingerprint)

    def revise(self, project_id, task_id, *, operation_id, expected_version, title, goal):
        fingerprint = operation_fingerprint(project_id, "REVISE", operation_id,
            dict(task_id=task_id, expected_version=expected_version, title=title, goal=goal))
        with self._uow() as work:
            work.acquire_write_lock()
            replay = self._replay(work, project_id, "REVISE", operation_id, fingerprint)
            if replay is not None:
                return replay
            task = require_active_task_version(work, project_id, task_id, expected_version)
            context = self._context_for(work, project_id, task_id, task.revision + 1, title, goal)
            if self._understanding.inspect_source_fingerprint(project_id) != context.source_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "源码起点已变化，请先重新分析")
            updated = task.model_copy(update={"version": task.version + 1, "revision": context.revision,
                "context_id": context.context_id, "updated_at_us": self._clock()})
            work.development.add_context(context)
            work.development.replace_task(updated, expected_version=task.version)
            return self._finish(work, updated, "REVISE", operation_id, fingerprint)

    def accept(self, project_id, task_id, *, operation_id, expected_version, context_id, client_name):
        fingerprint = operation_fingerprint(project_id, "ACCEPT", operation_id,
            dict(task_id=task_id, expected_version=expected_version, context_id=context_id, client_name=client_name))
        with self._uow() as work:
            work.acquire_write_lock()
            replay = self._replay(work, project_id, "ACCEPT", operation_id, fingerprint)
            if replay is not None:
                return replay
            task = require_active_task_version(work, project_id, task_id, expected_version)
            context = self._current_context(work, task, context_id)
            if self._understanding.inspect_source_fingerprint(project_id) != context.source_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "开工起点已变化，不能接收旧上下文")
            if work.development.acceptance(project_id, context_id) is not None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "该上下文已有接收回执，请读取原记录")
            work.development.add_acceptance(DevelopmentAcceptance(context_id=context_id, task_id=task_id,
                project_id=project_id, client_name=client_name, accepted_at_us=self._clock()))
            updated = task.model_copy(update={"version": task.version + 1, "updated_at_us": self._clock()})
            work.development.replace_task(updated, expected_version=task.version)
            return self._finish(work, updated, "ACCEPT", operation_id, fingerprint)

    def deliver(self, project_id, task_id, *, operation_id, expected_version, context_id,
                reason, claimed_paths=(), repair_reference=None, submitted_by):
        payload = dict(task_id=task_id, expected_version=expected_version, context_id=context_id,
            reason=reason, claimed_paths=list(claimed_paths), submitted_by=submitted_by,
            repair_reference=None if repair_reference is None else repair_reference.model_dump(mode="json"))
        fingerprint = operation_fingerprint(project_id, "DELIVER", operation_id, payload)
        # 重放先返回稳定结果，不能因稍后的工作区变化重新扫描或写入第二批。
        with self._uow() as work:
            replay = self._replay(work, project_id, "DELIVER", operation_id, fingerprint)
            if replay is not None:
                return replay
            task = require_active_task_version(work, project_id, task_id, expected_version)
            self._current_context(work, task, context_id)
            # GUI 和明确选择的本机预设不伪造 Agent 接收；MCP 来源始终由 transport 固定前缀。
            if submitted_by not in {"LOCAL_GUI", "预设演示 · 本机用户"} and work.development.acceptance(project_id, context_id) is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "客户端尚未接收本次开工上下文")
        prepared = self._changes.prepare_change(project_id, reason=reason, claimed_paths=claimed_paths,
            repair_reference=repair_reference, submitted_by=submitted_by)
        with self._uow() as work:
            work.acquire_write_lock()
            replay = self._replay(work, project_id, "DELIVER", operation_id, fingerprint)
            if replay is not None:
                return replay
            task = require_active_task_version(work, project_id, task_id, expected_version)
            context = self._current_context(work, task, context_id)
            previous = work.development.deliveries(project_id, task_id, limit=1)
            prior = previous[0] if previous else None
            initial = work.development.first_context(project_id, task_id)
            if initial is None:
                raise JiejianError(ErrorCode.STORAGE_FAILURE, "任务初始上下文缺失")
            baseline = prior.current_snapshot_id if prior is not None else initial.start_snapshot_id
            manifest, change, _ = self._changes.write_prepared_change(work, prepared, baseline_snapshot_id=baseline)
            # 累计比较始终引用任务第一份上下文，而非重修订后的源码起点。
            cumulative_start = initial.start_snapshot_id
            delivery = DevelopmentDelivery(delivery_id="dly_" + uuid4().hex, context_id=context_id,
                task_id=task_id, project_id=project_id, ordinal=1 if prior is None else prior.ordinal + 1,
                change_id=manifest.change_id, previous_delivery_id=None if prior is None else prior.delivery_id,
                start_snapshot_id=cumulative_start, current_snapshot_id=change.current_snapshot_id, created_at_us=self._clock())
            work.development.add_delivery(delivery)
            updated = task.model_copy(update={"version": task.version + 1, "updated_at_us": self._clock()})
            work.development.replace_task(updated, expected_version=task.version)
            return self._finish(work, updated, "DELIVER", operation_id, fingerprint, delivery=delivery)

    def _registration_state(self, work, project_id):
        understanding = work.application_understanding.get(project_id)
        boundary = self._boundaries.view(project_id, work=work)
        refs = permission_refs(boundary)
        if understanding is None or not understanding.source_analysis_authorized or not understanding.source_fingerprint or not refs:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "请先完成源码分析并确认权限要求")
        if work.source_changes.snapshot_for_fingerprint(project_id, understanding.source_fingerprint) is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "缺少可比较的源码起点")
        task = work.development.active(project_id)
        payload = dict(mode="REGISTRATION_STATE", task=None if task is None else task.model_dump(mode="json"),
            understanding_revision=understanding.revision, source_fingerprint=understanding.source_fingerprint,
            policy_epoch=boundary.policy_epoch, permissions=[ref.model_dump(mode="json") for ref in refs])
        return dict(project_id=project_id, fingerprint=operation_fingerprint(project_id, "DELIVER", "0" * 32, payload),
            policy_epoch=boundary.policy_epoch, permission_count=len(refs)), task, boundary

    def registration_preview(self, project_id):
        """只读当前登记条件；不创建任务、不扫描源码、不确认 Agent 接收。"""
        with self._uow() as work:
            return self._registration_state(work, project_id)[0]

    def register_change(self, project_id, *, operation_id, expected_registration_fingerprint,
                        reason="本地源码修改", claimed_paths=(), submitted_by="LOCAL_GUI", repair_reference=None):
        """凭稳定操作键登记一次修改；最小关联与变化一起提交，失败不留下半个任务。"""
        payload = dict(mode="LIGHTWEIGHT_REGISTRATION", expected_registration_fingerprint=expected_registration_fingerprint,
            reason=reason, claimed_paths=list(claimed_paths), submitted_by=submitted_by,
            repair_reference=None if repair_reference is None else repair_reference.model_dump(mode="json"))
        fingerprint = operation_fingerprint(project_id, "DELIVER", operation_id, payload)
        with self._uow() as work:
            replay = self._replay(work, project_id, "DELIVER", operation_id, fingerprint)
            if replay is not None:
                return replay
            if self._registration_state(work, project_id)[0]["fingerprint"] != expected_registration_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "登记范围已变化，请重新核对")
        prepared = self._changes.prepare_change(project_id, reason=reason, claimed_paths=claimed_paths,
            repair_reference=repair_reference, submitted_by=submitted_by)
        with self._uow() as work:
            work.acquire_write_lock()
            replay = self._replay(work, project_id, "DELIVER", operation_id, fingerprint)
            if replay is not None:
                return replay
            preview, task, boundary = self._registration_state(work, project_id)
            if preview["fingerprint"] != expected_registration_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "登记期间权限或源码上下文已变化，请重新核对")
            if task is None:
                context = self._context_for(work, project_id, "dvt_" + uuid4().hex, 1, "应用修改记录", "沿用已确认权限，记录修改与对应检查")
                task = DevelopmentTask(task_id=context.task_id, project_id=project_id, version=1, revision=1,
                    context_id=context.context_id, created_at_us=context.created_at_us, updated_at_us=context.created_at_us)
                work.development.add_task(task)
                work.development.add_context(context)
            else:
                context = work.development.context(project_id, task.context_id)
                if context is None:
                    raise JiejianError(ErrorCode.STORAGE_FAILURE, "修改关联上下文缺失")
                # 已批准规则变化后追加新上下文；旧客户端持有的版本会失效，历史快照不改写。
                if context.policy_epoch != boundary.policy_epoch or context.permission_refs != permission_refs(boundary):
                    context = self._context_for(work, project_id, task.task_id, task.revision + 1, context.title, context.goal)
                    work.development.add_context(context)
            previous = work.development.deliveries(project_id, task.task_id, limit=1)
            prior = previous[0] if previous else None
            initial = work.development.first_context(project_id, task.task_id)
            if initial is None:
                raise JiejianError(ErrorCode.STORAGE_FAILURE, "修改起始上下文缺失")
            baseline = initial.start_snapshot_id if prior is None else prior.current_snapshot_id
            manifest, change, _ = self._changes.write_prepared_change(work, prepared, baseline_snapshot_id=baseline)
            delivery = DevelopmentDelivery(delivery_id="dly_" + uuid4().hex, context_id=context.context_id,
                task_id=task.task_id, project_id=project_id, ordinal=1 if prior is None else prior.ordinal + 1,
                change_id=manifest.change_id, previous_delivery_id=None if prior is None else prior.delivery_id,
                start_snapshot_id=initial.start_snapshot_id, current_snapshot_id=change.current_snapshot_id, created_at_us=self._clock())
            work.development.add_delivery(delivery)
            updated = task.model_copy(update={"version": task.version + 1, "revision": context.revision,
                "context_id": context.context_id, "updated_at_us": self._clock()})
            work.development.replace_task(updated, expected_version=task.version)
            # 登记表示提交者授权记录这次修改，不虚构独立 ACCEPT 接收回执。
            return self._finish(work, updated, "DELIVER", operation_id, fingerprint, delivery=delivery)

    def finish(self, project_id, task_id, *, operation_id, expected_version, cancel=False):
        kind = "CANCEL" if cancel else "CLOSE"
        fingerprint = operation_fingerprint(project_id, kind, operation_id, dict(task_id=task_id, expected_version=expected_version))
        with self._uow() as work:
            work.acquire_write_lock()
            replay = self._replay(work, project_id, kind, operation_id, fingerprint)
            if replay is not None:
                return replay
            task = require_active_task_version(work, project_id, task_id, expected_version)
            updated = task.model_copy(update={"version": task.version + 1,
                "status": "CANCELLED" if cancel else "CLOSED", "updated_at_us": self._clock()})
            work.development.replace_task(updated, expected_version=task.version)
            return self._finish(work, updated, kind, operation_id, fingerprint)
