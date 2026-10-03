# 普通运行加载的持久提交与fenced回执发布；API调用这里只排队，不启动目标。
from uuid import uuid4
from contextlib import nullcontext

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState, ProjectStatus
from product.backend.infra.runtime.jobs.events import append_job_event
from product.backend.infra.runtime.jobs.models import JobEventType
from product.backend.infra.storage import JobRecord
from product.protocols.runtime.node_runtime import NodeRuntimeLoadRequest, NodeRuntimeLoadReceipt, node_document_fingerprint


class RuntimeLoadJobs:
    def __init__(self, uow_factory):
        self._uow = uow_factory

    def submit(self, request: NodeRuntimeLoadRequest, *, validate_current=None, work=None):
        """冻结输入和Job一次提交；同键异文拒绝，已提交的未知操作不自动重建。"""
        owns_transaction=work is None
        with self._uow() if owns_transaction else nullcontext(work) as work:
            work.acquire_write_lock()
            previous = work.runtime_loads.operation(request.project_id, request.operation_id)
            if previous is not None:
                if previous != request:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "加载操作已对应另一份冻结输入")
                return self.read_in_work(work, previous)
            project = work.projects.get(request.project_id)
            if project is None or project.status is ProjectStatus.ARCHIVED:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "加载项目不存在或已归档")
            if validate_current is not None:
                validate_current(work)
            if any(job.state in {JobState.PENDING, JobState.RUNNING, JobState.RETRY_WAIT}
                    for job in work.jobs.list_for_project(request.project_id)):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "项目仍有未结束操作，暂不能加载另一份实现")
            work.runtime_loads.add(request)
            job = JobRecord(job_id="job_" + uuid4().hex, project_id=request.project_id,
                runtime_load_id=request.load_id, operation_type="RUNTIME_LOAD", state=JobState.PENDING,
                idempotency_key=request.operation_id, request_hash=node_document_fingerprint(request),
                attempt=0, max_attempts=1, available_at_us=request.created_at_us,
                fencing_token=0, created_at_us=request.created_at_us, updated_at_us=request.created_at_us)
            work.jobs.add(job)
            append_job_event(work, job=job, event_type=JobEventType.JOB_SUBMITTED,
                source_state=None, target_state=JobState.PENDING, occurred_at_us=request.created_at_us,
                metadata={"operation_type": "RUNTIME_LOAD"})
            if owns_transaction:
                work.commit()
            return {"request": request, "job": job, "receipt": None}

    def operation(self, project_id: str, operation_id: str):
        with self._uow() as work:
            request = work.runtime_loads.operation(project_id, operation_id)
            return None if request is None else self.read_in_work(work, request)

    def publish(self, *, job_id: str, attempt: int, lease_owner: str, fencing_token: int,
            receipt: NodeRuntimeLoadReceipt):
        """Worker核对真实进程及端口后调用；取消或失效fence不得发布启动成功。"""
        with self._uow() as work:
            work.acquire_write_lock()
            job = work.jobs.get(job_id)
            if job is None or job.runtime_load_id != receipt.load_id:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "加载回执不属于当前任务")
            if job.state is JobState.SUCCEEDED and work.runtime_loads.receipt(receipt.load_id) == receipt:
                return receipt
            completed = work.job_control.complete_runtime_load(job_id=job_id, load_id=receipt.load_id,
                request_hash=receipt.request_fingerprint, attempt=attempt, lease_owner=lease_owner,
                fencing_token=fencing_token, now_us=receipt.started_at_us)
            if completed is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "加载任务已取消、过期或不再属于当前执行者")
            work.runtime_loads.publish(receipt)
            append_job_event(work, job=completed, event_type=JobEventType.JOB_SUCCEEDED,
                source_state=JobState.RUNNING, target_state=JobState.SUCCEEDED,
                occurred_at_us=receipt.started_at_us, metadata={"attempt": attempt, "fencing_token": fencing_token})
            work.commit()
            return receipt

    @staticmethod
    def read_in_work(work, request):
        """只读核验调用方事务内的请求、Job 和回执；不另开事务或提交。"""
        job = work.jobs.get_by_runtime_load(request.load_id)
        receipt = work.runtime_loads.receipt(request.load_id)
        if (job is None or job.project_id != request.project_id or job.request_hash != node_document_fingerprint(request)
                or (job.state is JobState.SUCCEEDED) != (receipt is not None)):
            raise JiejianError(ErrorCode.STORAGE_STATE, "加载输入、任务或回执关联不一致")
        return {"request": request, "job": job, "receipt": receipt}
