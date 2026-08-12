# =============================================================================
# Execution JobHandler 端口
#
# 定位
#   Worker 调度壳与 Verification/Recording 实现之间的依赖反转边界
#
# 职责
#   定义 JobHandler｜定义最小 attempt 操作｜按 Job target 惰性注册 Handler
#
# 调用链
#   ApplicationContext → JobHandlerRegistry → VerificationRunJobHandler / RecordingJobHandler
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol, TypeVar

from ..errors import ErrorCode, JiejianError
from ..storage import JobRecord
from .models import (
    CancellationResultV1,
    ClaimJobV1,
    ClaimedJobV1,
    CompleteCancellationV1,
    FatalFailureV1,
    JobMutationResultV1,
    RetryableFailureV1,
    RenewLeaseV1,
)
from .targets import JobTargetType

ResultT_co = TypeVar("ResultT_co", covariant=True)


class JobHandler(Protocol[ResultT_co]):
    """一个作业处理器的稳定执行端口。"""

    def run_job(self, job_id: str) -> ResultT_co | None:
        ...


class JobAttemptPort(Protocol):
    """Recording 与 Worker Attempt 服务之间的最小端口。"""

    def claim(
        self,
        request: ClaimJobV1,
        *,
        known_secrets: Sequence[str] = (),
    ) -> ClaimedJobV1 | None:
        ...

    def renew_lease(
        self,
        request: RenewLeaseV1,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResultV1:
        ...

    def complete_cancellation(
        self,
        request: CompleteCancellationV1,
        *,
        known_secrets: Sequence[str] = (),
    ) -> CancellationResultV1:
        ...

    def record_retryable_failure(
        self,
        request: RetryableFailureV1,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResultV1:
        ...

    def record_fatal_failure(
        self,
        request: FatalFailureV1,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResultV1:
        ...


class JobHandlerRegistry:
    """按 Job 目标类型惰性创建单任务 Handler。"""

    def __init__(self) -> None:
        self._factories: dict[JobTargetType, Callable[[], JobHandler[Any]]] = {}

    def register(
        self,
        target_type: JobTargetType,
        factory: Callable[[], JobHandler[Any]],
    ) -> None:
        if not isinstance(target_type, JobTargetType):
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务目标类型非法")
        if target_type in self._factories:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务处理器重复注册")
        self._factories[target_type] = factory

    def resolve(self, job: JobRecord) -> JobHandler[Any]:
        target_type = JobTargetType.from_job(job)
        try:
            factory = self._factories[target_type]
        except KeyError:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务处理器未注册") from None
        return factory()
