# 任务执行与进程监督共用的最小 attempt 端口，不装配具体处理器。
from typing import Protocol
from collections.abc import Sequence
from product.backend.infrastructure.storage.unit_of_work import StorageUnitOfWork
from product.backend.infrastructure.runtime.jobs.models import CancellationResult, ClaimJob, ClaimedJob, CompleteCancellation, FatalFailure, JobMutationResult, RetryableFailure, RenewLease, WaitingFatalFailure

class JobAttemptPort(Protocol):
    """Recording 与 Worker Attempt 服务之间的最小端口。"""

    def claim_in_work(self, work: StorageUnitOfWork, request: ClaimJob, *,
                      known_secrets: Sequence[str] = ()) -> ClaimedJob | None:
        """在调用者事务中领取，事务所有权仍属于调用者。"""
        ...

    def claim(
        self,
        request: ClaimJob,
        *,
        known_secrets: Sequence[str] = (),
    ) -> ClaimedJob | None:
        ...

    def renew_lease(
        self,
        request: RenewLease,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResult:
        ...

    def complete_cancellation(
        self,
        request: CompleteCancellation,
        *,
        known_secrets: Sequence[str] = (),
    ) -> CancellationResult:
        ...

    def record_retryable_failure(
        self,
        request: RetryableFailure,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResult:
        ...

    def record_fatal_failure(
        self,
        request: FatalFailure,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResult:
        ...

    def record_waiting_fatal_failure(
        self,
        request: WaitingFatalFailure,
        *,
        known_secrets: Sequence[str] = (),
    ) -> JobMutationResult | None:
        ...
