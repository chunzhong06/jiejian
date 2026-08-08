"""支撑阶段 0 状态不变量的最小领域模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ProjectStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    ARCHIVED = "ARCHIVED"


class RecordingState(StrEnum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    RECORDING = "RECORDING"
    PROCESSING = "PROCESSING"
    REVIEWABLE = "REVIEWABLE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ContractStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class RunLifecycle(StrEnum):
    QUEUED = "QUEUED"
    PREFLIGHT = "PREFLIGHT"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    REPORTING = "REPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SAFETY_STOPPED = "SAFETY_STOPPED"


class RunVerdict(StrEnum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    INCONCLUSIVE = "INCONCLUSIVE"


class CaseLifecycle(StrEnum):
    PLANNED = "PLANNED"
    SNAPSHOTTED = "SNAPSHOTTED"
    EXECUTED = "EXECUTED"
    OBSERVED = "OBSERVED"
    CLEANED = "CLEANED"
    DONE = "DONE"
    ERROR = "ERROR"


class CaseVerdict(StrEnum):
    SAFE = "SAFE"
    VULNERABLE = "VULNERABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class JobState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"


class StateTransitionEvent(DomainModel):
    entity_id: UUID
    machine: str
    source: str
    target: str
    operator: str = Field(min_length=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EntityModel(DomainModel):
    id: UUID = Field(default_factory=uuid4)
    events: tuple[StateTransitionEvent, ...] = ()


class Project(EntityModel):
    name: str = Field(min_length=1)
    status: ProjectStatus = ProjectStatus.DRAFT


class Recording(EntityModel):
    project_id: UUID
    state: RecordingState = RecordingState.CREATED


class Contract(EntityModel):
    version: int = Field(default=1, ge=1)
    rules: tuple[str, ...] = ()
    status: ContractStatus = ContractStatus.DRAFT
    supersedes_id: UUID | None = None


class Run(EntityModel):
    contract_version: int = Field(ge=1)
    engine_version: str = Field(min_length=1)
    lifecycle: RunLifecycle = RunLifecycle.QUEUED
    verdict: RunVerdict | None = None


class TestCase(EntityModel):
    run_id: UUID
    lifecycle: CaseLifecycle = CaseLifecycle.PLANNED
    verdict: CaseVerdict | None = None


class Job(EntityModel):
    job_type: str = Field(min_length=1)
    state: JobState = JobState.PENDING
    attempts: int = Field(default=0, ge=0)
