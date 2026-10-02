# 普通交付加载沿用已确认入口与端口；交付回执、加载输入和Job同事务提交，查询不重放。
from product.backend.core.development import NodeRuntimeActivationReceipt
from product.backend.core.errors import ErrorCode,JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.infra.runtime.process.node_owned import read_node_manifest
from product.backend.workflows.development import operation_fingerprint,require_active_task_version


class NodeRuntimeActivation:
    def __init__(self,uow_factory,runtime,clock):
        self._uow,self.runtime,self.clock=uow_factory,runtime,clock

    def activate(self,project_id,delivery_id,*,operation_id,expected_version):
        fingerprint=operation_fingerprint(project_id,'LOAD_RUNTIME',operation_id,
            dict(delivery_id=delivery_id,expected_version=expected_version))
        with self._uow() as work:
            work.acquire_write_lock()
            previous=work.development.runtime_receipt(project_id,operation_id)
            if previous is not None:
                if previous.request_fingerprint!=fingerprint or not isinstance(previous,NodeRuntimeActivationReceipt):
                    raise JiejianError(ErrorCode.STATE_PRECONDITION,'原操作已对应另一份运行请求')
                return self._resolve(work,previous)
            delivery=work.development.delivery(project_id,delivery_id)
            if delivery is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'本应用中未找到这批交付')
            task=require_active_task_version(work,project_id,delivery.task_id,expected_version)
            if work.development.deliveries(project_id,task.task_id,limit=1)[0]!=delivery or task.context_id!=delivery.context_id:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'只有当前任务的最新交付可以加载运行')
            snapshot=work.source_changes.snapshot(delivery.current_snapshot_id)
            previous_load=work.runtime_loads.latest(project_id)
            if snapshot is None or snapshot.project_id!=project_id or previous_load is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'请先在应用与环境中确认启动方式')
            _,manifest=read_node_manifest(self.runtime.var_dir,previous_load)
            understanding=work.application_understanding.get(project_id)
            preview=self.runtime.preview(project_id,entry=manifest.entry,port=manifest.port,revision=understanding.revision)
            if preview.source_fingerprint!=snapshot.source_fingerprint:
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'本地源码与这批交付不一致，请先登记当前修改')
            self.runtime.start(project_id,entry=preview.entry,port=preview.port,revision=preview.revision,
                preview_fingerprint=preview.preview_fingerprint,operation_id=operation_id,consent_execute=True,work=work)
            request=work.runtime_loads.operation(project_id,operation_id)
            receipt=NodeRuntimeActivationReceipt(project_id=project_id,operation_id=operation_id,
                request_fingerprint=fingerprint,task_id=task.task_id,delivery_id=delivery_id,
                source_fingerprint=snapshot.source_fingerprint,status='PENDING',runtime_load_id=request.load_id,created_at_us=self.clock())
            work.development.add_receipt(receipt)
            work.commit()
            return receipt

    def receipt(self,project_id,operation_id):
        with self._uow() as work:
            work.acquire_write_lock()
            value=work.development.runtime_receipt(project_id,operation_id)
            if not isinstance(value,NodeRuntimeActivationReceipt):
                raise JiejianError(ErrorCode.STATE_PRECONDITION,'原操作不属于普通运行加载')
            return self._resolve(work,value)

    def _resolve(self,work,value):
        if value.status!='PENDING':
            return value
        request=work.runtime_loads.get(value.runtime_load_id)
        if (request is None or request.project_id!=value.project_id or request.operation_id!=value.operation_id
                or request.source_fingerprint!=value.source_fingerprint):
            raise JiejianError(ErrorCode.STORAGE_STATE,'交付加载与持久Job关联不一致')
        operation=self.runtime.jobs._view(work,request)
        job,load_receipt=operation['job'],operation['receipt']
        update=None
        if job.state is JobState.SUCCEEDED:
            update={'status':'SUCCEEDED','runtime_reference':load_receipt.reference}
        elif job.state in {JobState.FAILED,JobState.CANCELLED}:
            update={'status':'FAILED','error_code':'RUNTIME_LOAD_CANCELLED' if job.state is JobState.CANCELLED else 'RUNTIME_LOAD_FAILED'}
        if update is not None:
            completed=NodeRuntimeActivationReceipt.model_validate(value.model_dump()|update)
            work.development.finish_runtime_receipt(value,completed);work.commit()
            return completed
        if request.control_session_id!=self.runtime.supervisor.control_session_id:
            return value.model_copy(update={'status':'UNKNOWN'})
        return value
