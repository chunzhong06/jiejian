# 读取任务、交付、差异和已发布检查；不扫描源码或创建交付，不从任务状态推断安全结论。
from __future__ import annotations
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.changes.models import build_current_change_set


class DevelopmentReader:
    def __init__(self, uow_factory, *, results=None, repairs=None):
        self._uow = uow_factory
        self._results, self._repairs = results, repairs
        self._runtime_reader = None

    def bind_runtime_reader(self, reader):
        """组合根完成运行提供方后连接；此处不启动或读取运行实例。"""
        if self._runtime_reader is not None and self._runtime_reader != reader:
            raise ValueError("开发记录的运行读取者已经连接")
        self._runtime_reader = reader

    def validate_connections(self):
        if self._runtime_reader is None:
            raise ValueError("生产开发记录尚未连接运行读取者")

    def history(self, project_id, *, before_task_id=None, limit=20):
        """有界读取任务名称和状态；游标只接受同项目既有任务，不猜测缺失历史。"""
        if type(limit) is not int or not 1 <= limit <= 50:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "任务列表数量超出范围")
        with self._uow() as work:
            before = None if before_task_id is None else work.development.task(project_id, before_task_id)
            if before_task_id is not None and before is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "任务游标不属于当前应用")
            tasks = work.development.tasks(project_id, limit + 1, before=before)
            items = []
            for task in tasks[:limit]:
                context = work.development.context(project_id, task.context_id)
                if context is None:
                    raise JiejianError(ErrorCode.STORAGE_FAILURE, "任务上下文缺失")
                items.append(dict(task_id=task.task_id, title=context.title, status=task.status,
                    revision=task.revision, updated_at_us=task.updated_at_us))
        return dict(project_id=project_id, items=items, next_task_id=tasks[limit - 1].task_id if len(tasks) > limit else None)


    def delivery_page(self, project_id, task_id, *, before_ordinal=None, limit=20):
        if type(limit) is not int or not 1 <= limit <= 50 or before_ordinal is not None and (type(before_ordinal) is not int or before_ordinal < 1):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "交付列表范围无效")
        self.task(project_id, task_id)
        with self._uow() as work:
            values = work.development.deliveries(project_id, task_id, limit + 1, before_ordinal=before_ordinal)
            items = []
            for delivery in values[:limit]:
                saved = work.source_changes.current_change(project_id, delivery.change_id)
                if saved is None:
                    raise JiejianError(ErrorCode.STORAGE_FAILURE, "交付变化记录缺失")
                items.append(dict(delivery=delivery.model_dump(mode="json"), reason=saved[0].reason,
                    submitted_by=saved[0].submitted_by))
        return dict(project_id=project_id, task_id=task_id, items=items,
            next_ordinal=values[limit - 1].ordinal if len(values) > limit else None)


    def delivery_details(self, project_id, change_id):
        """上一批差异与累计差异都来自已保存快照；此读取不扫描工作区，不新增交付。"""
        with self._uow() as work:
            delivery = work.development.delivery_for_change(project_id, change_id)
            if delivery is None:
                return None
            saved = work.source_changes.current_change(project_id, change_id)
            initial = work.source_changes.snapshot(delivery.start_snapshot_id)
            current = work.source_changes.snapshot(delivery.current_snapshot_id)
            context = work.development.context(project_id, delivery.context_id)
            if saved is None or initial is None or current is None or context is None:
                raise JiejianError(ErrorCode.STORAGE_FAILURE, "交付上下文或源码快照缺失")
            manifest, relative, _ = saved
            cumulative = build_current_change_set(manifest, initial, current)
        return dict(project_id=project_id, delivery=delivery.model_dump(mode="json"), context=context.model_dump(mode="json"),
            relative_change=relative.model_dump(mode="json"), cumulative_change=cumulative.model_dump(mode="json"),
            verification=self.delivery_verification(project_id, delivery.delivery_id))


    def delivery_verification(self, project_id, delivery_id):
        with self._uow() as work:
            delivery = work.development.delivery(project_id, delivery_id)
            if delivery is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "交付不存在或不属于当前应用")
            run_id = work.development.latest_check_run(project_id, delivery_id)
        value = dict(delivery=delivery.model_dump(mode="json"), run_id=run_id, lifecycle=None,
            verdict=None, runtime_status="UNSUPPORTED", repair_status=None)
        if run_id is None or self._results is None:
            return value
        status = self._results.status(run_id, project_id=project_id)
        value["lifecycle"] = status.run.lifecycle.value
        if status.result_integrity != "VALID":
            return value
        package = self._results.package(run_id, project_id=project_id)
        if package.request.change_context is None or package.request.change_context.change_id != delivery.change_id:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "交付检查关联不完整")
        correspondence = getattr(package.result, "runtime_correspondence", None)
        value["runtime_status"] = "UNSUPPORTED" if correspondence is None else "MATCHED" if correspondence.before == correspondence.after == "MATCHED" else "UNCONFIRMED"
        value["verdict"] = package.result.verdict.value if package.result.verdict is not None else None
        repair = None if self._repairs is None else self._repairs.verification(run_id)
        value["repair_status"] = None if repair is None else repair.status
        return value


    def receipt(self, project_id, kind, operation_id):
        with self._uow() as work:
            return work.development.receipt(project_id, kind, operation_id)


    def task(self, project_id, task_id):
        with self._uow() as work:
            task = work.development.task(project_id, task_id)
        if task is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "任务不存在或不属于当前应用")
        return task


    def list(self, project_id, *, limit=50):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "任务列表数量超出范围")
        with self._uow() as work:
            return work.development.tasks(project_id, limit)


    def context(self, project_id, context_id):
        with self._uow() as work:
            context = work.development.context(project_id, context_id)
        if context is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "开工上下文不存在或不属于当前应用")
        return context


    def active(self, project_id):
        with self._uow() as work:
            return work.development.active(project_id)


    def view(self, project_id, task_id):
        """只读持久任务事实；不扫描源码，不由任务状态推导检查结论。"""
        with self._uow() as work:
            task = work.development.task(project_id, task_id)
            if task is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "任务不存在或不属于当前应用")
            context = work.development.context(project_id, task.context_id)
            if context is None:
                raise JiejianError(ErrorCode.STORAGE_FAILURE, "任务上下文缺失")
            acceptance = work.development.acceptance(project_id, context.context_id)
            deliveries = work.development.deliveries(project_id, task_id, limit=51)
            latest_snapshot = None if not deliveries else work.source_changes.snapshot(deliveries[0].current_snapshot_id)
        runtime_state = "UNSUPPORTED"
        if latest_snapshot is not None and self._runtime_reader is not None:
            try:
                reference = self._runtime_reader(project_id)
                if reference is not None:
                    runtime_state = "MATCHED" if reference.source_fingerprint == latest_snapshot.source_fingerprint else "NOT_LOADED"
            except JiejianError as exc:
                runtime_state = "NOT_LOADED" if exc.to_dict().get("details", {}).get("reason") == "RUNTIME_SOURCE_NOT_LOADED" else "UNCONFIRMED"
            except (OSError, ValueError):
                runtime_state = "UNCONFIRMED"
        return dict(task=task.model_dump(mode="json"), context=context.model_dump(mode="json"),
            runtime_state=runtime_state,
            latest_verification=None if not deliveries else self.delivery_verification(project_id, deliveries[0].delivery_id),
            acceptance=None if acceptance is None else acceptance.model_dump(mode="json"),
            deliveries=[item.model_dump(mode="json") for item in deliveries[:50]], has_more=len(deliveries) > 50)
