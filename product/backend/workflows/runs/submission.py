# =============================================================================
# Execution 提交应用服务
#
# 定位
#   已构造 ExecutionRequest 进入持久请求文件和 Job 队列的边界
#
# 职责
#   校验项目元数据｜原子保存请求快照｜创建或复用幂等 Job
#
# 边界
#   不领取或执行任务，不直接访问目标，也不把入口参数重新解释为安全结论。
#
# 调用链
#   CLI / API → RunSubmission → ExecutionRequestStore / JobQueue
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from product.backend import __version__
from product.backend.core.identifiers import JOB_ID_PATTERN, RUN_ID_PATTERN
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import ProjectRecord, StorageUnitOfWork
from product.backend.infra.runtime.jobs.models import JobSubmissionResult, SubmitJob
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.jobs.requests import ExecutionRequestStore, PersistedExecutionRequest


class SubmitExecution(BaseModel):
    """只扩展内部提交命令；不创建新的 API/CLI 入口。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    request: PersistedExecutionRequest
    idempotency_key: str = Field(min_length=1, max_length=128)
    max_attempts: int = Field(default=3, ge=1, le=1_000)
    available_at_us: int = Field(ge=0)
    now_us: int = Field(ge=0)
    run_id: str | None = Field(default=None, pattern=RUN_ID_PATTERN)
    job_id: str | None = Field(default=None, pattern=JOB_ID_PATTERN)


class RunSubmission:
    """协调文件快照与既有 JobQueue，不执行或领取任务。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        request_store: ExecutionRequestStore,
        *,
        queue: JobQueue | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._request_store = request_store
        self._queue = queue or JobQueue(uow_factory)

    def submit(
        self,
        command: SubmitExecution,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobSubmissionResult:
        run_id = command.run_id or f"run_{uuid4().hex}"
        job_id = command.job_id or f"job_{uuid4().hex}"
        request_hash, snapshot_created = self._request_store.write(
            job_id,
            command.request,
            known_secrets=known_secrets,
        )
        try:
            self._ensure_project(command, known_secrets)
            snapshot = command.request.project_snapshot
            contract_id = snapshot.contract.contract_id
            contract_version = snapshot.contract.version
            result = self._queue.submit(
                SubmitJob(
                    project_id=snapshot.project_id,
                    operation_type="ACTIVE_RUN",
                    idempotency_key=command.idempotency_key,
                    request_hash=request_hash,
                    contract_id=contract_id,
                    contract_version=contract_version,
                    engine_version=__version__,
                    max_attempts=command.max_attempts,
                    available_at_us=command.available_at_us,
                    now_us=command.now_us,
                    run_id=run_id,
                    job_id=job_id,
                ),
                known_secrets=known_secrets,
            )
            if result.job.job_id != job_id:
                self._request_store.write(
                    result.job.job_id,
                    command.request,
                    known_secrets=known_secrets,
                )
                if snapshot_created:
                    self._request_store.remove_if_matches(job_id, request_hash)
            return result
        except Exception:
            if snapshot_created:
                self._request_store.remove_if_matches(job_id, request_hash)
            raise

    def _ensure_project(
        self,
        command: SubmitExecution,
        known_secrets: Sequence[str],
    ) -> None:
        snapshot = command.request.project_snapshot
        with self._uow_factory(known_secrets=known_secrets) as work:
            project = work.projects.get(snapshot.project_id)
            if project is None:
                work.projects.add(
                    ProjectRecord(
                        project_id=snapshot.project_id,
                        name=snapshot.project_name,
                        status=ProjectStatus.READY,
                        created_at_us=command.now_us,
                        updated_at_us=command.now_us,
                    )
                )
                work.commit()
                return
            if project.status is not ProjectStatus.READY:
                raise JiejianError(
                    ErrorCode.JOB_PERSISTENCE,
                    "项目状态不允许创建任务",
                )
