# 共享生命周期枚举与领域模型公共基线。

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ProjectStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    ARCHIVED = "ARCHIVED"


class ContractStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class RunLifecycle(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
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
