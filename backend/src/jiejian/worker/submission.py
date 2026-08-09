"""CLI/API 提交内容快照、项目元数据与持久 Job 的应用边界。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib.metadata import version
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..domain.identifiers import JOB_ID_PATTERN, RUN_ID_PATTERN
from ..domain.lifecycle import ProjectStatus
from ..errors import ErrorCode, JiejianError
from ..storage import ProjectRecord, StorageUnitOfWork
from .models import JobSubmissionResultV1, SubmitJobV1
from .queue import JobQueueService
from .request_store import ExecutionRequestStore, PersistedExecutionRequestV1


class SubmitExecutionV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"
    request: PersistedExecutionRequestV1
    idempotency_key: str = Field(min_length=1, max_length=128)
    max_attempts: int = Field(default=3, ge=1, le=1_000)
    available_at_us: int = Field(ge=0)
    now_us: int = Field(ge=0)
    run_id: str | None = Field(default=None, pattern=RUN_ID_PATTERN)
    job_id: str | None = Field(default=None, pattern=JOB_ID_PATTERN)


class ExecutionSubmissionService:
    """协调文件快照与既有 JobQueueService，不执行或领取任务。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        request_store: ExecutionRequestStore,
    ) -> None:
        self._uow_factory = uow_factory
        self._request_store = request_store
        self._queue = JobQueueService(uow_factory)

    def submit(
        self,
        command: SubmitExecutionV1,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobSubmissionResultV1:
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
            result = self._queue.submit(
                SubmitJobV1(
                    project_id=snapshot.project_id,
                    operation_type="ACTIVE_RUN",
                    idempotency_key=command.idempotency_key,
                    request_hash=request_hash,
                    contract_id=snapshot.contract.id,
                    contract_version=snapshot.contract.version,
                    engine_version=version("jiejian"),
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
        command: SubmitExecutionV1,
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
