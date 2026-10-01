# 显式加载受控示例的一批交付：先保存操作，再执行有界生命周期，未知回执只核对而不重启。
from threading import Lock

from product.backend.core.development import RuntimeActivationReceipt
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.development import operation_fingerprint, require_active_task_version


class RuntimeActivationService:
    def __init__(self, *, uow_factory, loader, reader, clock):
        self._uow = uow_factory
        self._loader, self._reader, self._clock = loader, reader, clock
        self._inflight = set()
        self._guard = Lock()

    def receipt(self, project_id, operation_id):
        with self._uow() as work:
            receipt = work.development.runtime_receipt(project_id, operation_id)
        with self._guard:
            inflight = (project_id, operation_id) in self._inflight
        if receipt is not None and receipt.status == "PENDING" and not inflight:
            return receipt.model_copy(update={"status": "UNKNOWN"})
        return receipt

    def activate(self, project_id, delivery_id, *, operation_id, expected_version):
        fingerprint = operation_fingerprint(project_id, "LOAD_RUNTIME", operation_id,
            dict(delivery_id=delivery_id, expected_version=expected_version))
        with self._uow() as work:
            work.acquire_write_lock()
            previous = work.development.runtime_receipt(project_id, operation_id)
            if previous is not None:
                if previous.request_fingerprint != fingerprint:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "操作标识已用于不同的运行加载请求")
                with self._guard:
                    inflight = (project_id, operation_id) in self._inflight
                if previous.status == "PENDING" and not inflight:
                    try:
                        reference = self._reader(project_id)
                    except (JiejianError, OSError, ValueError):
                        reference = None
                    if reference is not None and reference.source_fingerprint == previous.source_fingerprint:
                        recovered = RuntimeActivationReceipt.model_validate({**previous.model_dump(), "status": "SUCCEEDED", "runtime_reference": reference})
                        work.development.finish_runtime_receipt(previous, recovered)
                        work.commit()
                        return recovered
                return self.receipt(project_id, operation_id)
            delivery = work.development.delivery(project_id, delivery_id)
            if delivery is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "本应用中未找到这批交付")
            task = require_active_task_version(work, project_id, delivery.task_id, expected_version)
            if work.development.deliveries(project_id, task.task_id, limit=1)[0] != delivery or task.context_id != delivery.context_id:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "只有当前任务的最新交付可以加载运行")
            snapshot = work.source_changes.snapshot(delivery.current_snapshot_id)
            if snapshot is None or snapshot.project_id != project_id:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "交付源码快照缺失")
            receipt = RuntimeActivationReceipt(project_id=project_id, operation_id=operation_id, request_fingerprint=fingerprint,
                task_id=task.task_id, delivery_id=delivery_id, source_fingerprint=snapshot.source_fingerprint,
                status="PENDING", created_at_us=self._clock())
            work.development.add_receipt(receipt)
            key = (project_id, operation_id)
            # 提交前登记本进程执行权，避免刚持久化的 PENDING 被并发恢复当作失联。
            with self._guard:
                self._inflight.add(key)
            try:
                work.commit()
            except Exception:
                with self._guard:
                    self._inflight.discard(key)
                raise
        try:
            reference = self._loader(project_id, receipt.source_fingerprint)
            completed = RuntimeActivationReceipt.model_validate({**receipt.model_dump(), "status": "SUCCEEDED", "runtime_reference": reference})
            with self._uow() as work:
                work.acquire_write_lock()
                work.development.finish_runtime_receipt(receipt, completed)
                work.commit()
            return completed
        except Exception as exc:
            # 先核对真实运行；若进程已成功启动而回执持久化失败，只保留 UNKNOWN，不能重启试探。
            try:
                reference = self._reader(project_id)
                matched = reference is not None and reference.source_fingerprint == receipt.source_fingerprint
            except (JiejianError, OSError, ValueError):
                matched = False
            if not matched:
                failed = receipt.model_copy(update={"status": "FAILED", "error_code": exc.code if isinstance(exc, JiejianError) else "RUNTIME_LOAD_FAILED"})
                try:
                    with self._uow() as work:
                        work.acquire_write_lock()
                        work.development.finish_runtime_receipt(receipt, failed)
                        work.commit()
                except Exception:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "运行加载与回执尚未确认，请核对原操作和运行状态") from None
                return failed
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "运行可能已经加载，请核对原操作回执，勿重复重启") from None
        finally:
            with self._guard:
                self._inflight.discard(key)
