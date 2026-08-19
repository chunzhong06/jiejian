# Job 控制 持久化任务控制面的冻结输入、结果与策略。

from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from product.backend.core.identifiers import JOB_ID_PATTERN, PROJECT_ID_PATTERN, RECORDING_ID_PATTERN, RUN_ID_PATTERN, SHA256_PATTERN
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import JobRecord, RecordingRecord, RunRecord
from product.backend.infra.storage import ensure_storage_payload_safe

MAX_LEASE_DURATION_US = 300_000_000
MAX_RETRY_DELAY_US = 86_400_000_000
MAX_RECOVERY_SCAN_ITEMS = 1_000
_MAX_SQLITE_INTEGER = 9_223_372_036_854_775_807


class JobEventType(StrEnum):
    JOB_SUBMITTED = "JOB_SUBMITTED"
    JOB_CLAIMED = "JOB_CLAIMED"
    JOB_LEASE_RENEWED = "JOB_LEASE_RENEWED"
    JOB_CANCEL_REQUESTED = "JOB_CANCEL_REQUESTED"
    JOB_CANCELLED = "JOB_CANCELLED"
    JOB_RETRY_SCHEDULED = "JOB_RETRY_SCHEDULED"
    JOB_FAILED = "JOB_FAILED"
    JOB_RECOVERY_CONFIRMED = "JOB_RECOVERY_CONFIRMED"
    JOB_SUCCEEDED = "JOB_SUCCEEDED"


class RetryableFailureCode(StrEnum):
    EXEC_REQUEST = "EXEC_REQUEST"
    EXEC_TIMEOUT = "EXEC_TIMEOUT"
    RUNNER_START_FAILED = "RUNNER_START_FAILED"
    WORKER_INTERRUPTED = "WORKER_INTERRUPTED"


class FatalFailureCode(StrEnum):
    PROTOCOL_INVALID = "PROTOCOL_INVALID"
    RUNNER_FATAL = "RUNNER_FATAL"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    WORKER_FATAL = "WORKER_FATAL"


class RecoveryProofType(StrEnum):
    EXECUTION_EXITED = "EXECUTION_EXITED"
    CLEANUP_COMPLETED = "CLEANUP_COMPLETED"


class RecoveryOperator(StrEnum):
    WORKER_SUPERVISOR = "WORKER_SUPERVISOR"
    RECOVERY_CONTROLLER = "RECOVERY_CONTROLLER"


class RecoveryReasonCode(StrEnum):
    PROCESS_EXIT_CONFIRMED = "PROCESS_EXIT_CONFIRMED"
    CLEANUP_CONFIRMED = "CLEANUP_CONFIRMED"


class WorkerControlModel(BaseModel):
    """Job 控制 对外 DTO 的共同严格边界。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"


class RetryPolicy(WorkerControlModel):
    base_delay_us: int = Field(default=1_000_000, ge=1, le=MAX_RETRY_DELAY_US)
    max_delay_us: int = Field(
        default=300_000_000,
        ge=1,
        le=MAX_RETRY_DELAY_US,
    )
    max_jitter_us: int = Field(default=250_000, ge=0, le=MAX_RETRY_DELAY_US)

    @model_validator(mode="after")
    def validate_bounds(self) -> RetryPolicy:
        if self.base_delay_us > self.max_delay_us:
            raise ValueError("retry base delay exceeds maximum")
        if self.max_jitter_us > self.max_delay_us:
            raise ValueError("retry jitter exceeds maximum")
        return self


class SubmitJob(WorkerControlModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    operation_type: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    request_hash: str = Field(pattern=SHA256_PATTERN)
    contract_id: str = Field(min_length=1, max_length=128)
    contract_version: int = Field(ge=1)
    engine_version: str = Field(min_length=1, max_length=64)
    max_attempts: int = Field(default=3, ge=1, le=1_000)
    available_at_us: int = Field(ge=0)
    now_us: int = Field(ge=0)
    run_id: str | None = Field(default=None, pattern=RUN_ID_PATTERN)
    job_id: str | None = Field(default=None, pattern=JOB_ID_PATTERN)


class ClaimJob(WorkerControlModel):
    lease_owner: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    now_us: int = Field(ge=0)
    lease_duration_us: int = Field(ge=1, le=MAX_LEASE_DURATION_US)
    job_id: str | None = Field(default=None, pattern=JOB_ID_PATTERN)


class RenewLease(WorkerControlModel):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    lease_owner: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    fencing_token: int = Field(ge=1)
    now_us: int = Field(ge=0)
    lease_expires_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_new_deadline(self) -> RenewLease:
        if self.lease_expires_at_us <= self.now_us:
            raise ValueError("new lease deadline must be in the future")
        if self.lease_expires_at_us - self.now_us > MAX_LEASE_DURATION_US:
            raise ValueError("new lease duration exceeds its maximum")
        return self


class RequestCancellation(WorkerControlModel):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    now_us: int = Field(ge=0)


class FencedJobMutation(WorkerControlModel):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    lease_owner: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    fencing_token: int = Field(ge=1)
    now_us: int = Field(ge=0)


class CompleteCancellation(FencedJobMutation):
    pass


class RetryableFailure(FencedJobMutation):
    reason_code: RetryableFailureCode


class FatalFailure(FencedJobMutation):
    reason_code: FatalFailureCode


class RecoveryScan(WorkerControlModel):
    now_us: int = Field(ge=0)
    limit: int = Field(default=100, ge=1, le=MAX_RECOVERY_SCAN_ITEMS)


class ConfirmRecovery(FencedJobMutation):
    proof_type: RecoveryProofType
    operator: RecoveryOperator
    reason_code: RecoveryReasonCode

    @model_validator(mode="after")
    def validate_proof_reason(self) -> ConfirmRecovery:
        expected = {
            RecoveryProofType.EXECUTION_EXITED: (
                RecoveryReasonCode.PROCESS_EXIT_CONFIRMED
            ),
            RecoveryProofType.CLEANUP_COMPLETED: RecoveryReasonCode.CLEANUP_CONFIRMED,
        }
        if self.reason_code is not expected[self.proof_type]:
            raise ValueError("recovery proof and reason code are inconsistent")
        return self


class JobSubmissionResult(WorkerControlModel):
    created: bool
    job: JobRecord
    run: RunRecord


class ClaimedJob(WorkerControlModel):
    job: JobRecord
    run: RunRecord | None = None
    recording: RecordingRecord | None = None

    @model_validator(mode="after")
    def validate_target(self) -> ClaimedJob:
        if (self.run is None) == (self.recording is None):
            raise ValueError("claimed job must expose exactly one target")
        return self


class JobMutationResult(WorkerControlModel):
    job: JobRecord
    run: RunRecord | None = None
    recording: RecordingRecord | None = None

    @model_validator(mode="after")
    def validate_target(self) -> JobMutationResult:
        if (self.run is None) == (self.recording is None):
            raise ValueError("job mutation must expose exactly one target")
        return self


class CancellationResult(JobMutationResult):
    first_requested_at_us: int = Field(ge=0)
    completed: bool


class RecoveryCandidate(WorkerControlModel):
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    run_id: str | None = Field(default=None, pattern=RUN_ID_PATTERN)
    recording_id: str | None = Field(default=None, pattern=RECORDING_ID_PATTERN)
    attempt: int = Field(ge=1)
    max_attempts: int = Field(ge=1)
    lease_owner: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    fencing_token: int = Field(ge=1)
    lease_expires_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_target(self) -> RecoveryCandidate:
        if (self.run_id is None) == (self.recording_id is None):
            raise ValueError("recovery candidate must reference exactly one target")
        return self


def validate_control_request(
    request: WorkerControlModel,
    known_secrets: Sequence[str],
) -> None:
    """在服务打开事务前执行统一时间和秘密边界检查。"""

    for key, value in request.model_dump(mode="python").items():
        if key.endswith("_us") and type(value) is int and value > _MAX_SQLITE_INTEGER:
            raise JiejianError(
                ErrorCode.JOB_TIME_INVALID,
                "任务时间超过持久化整数边界",
            )
    try:
        ensure_storage_payload_safe(request.model_dump(mode="json"), known_secrets)
    except JiejianError as exc:
        if exc.code == ErrorCode.STORAGE_SECRET.value:
            raise JiejianError(
                ErrorCode.JOB_SECRET,
                "任务控制数据包含敏感内容",
            ) from None
        raise


def checked_time_add(left: int, right: int) -> int:
    """拒绝超出 SQLite 有符号整数上限的微秒加法。"""

    result = left + right
    if result > _MAX_SQLITE_INTEGER:
        raise JiejianError(
            ErrorCode.JOB_TIME_INVALID,
            "任务时间超过持久化整数边界",
        )
    return result


def compute_retry_available_at(
    *,
    policy: RetryPolicy,
    jitter_source: Callable[[int], int],
    now_us: int,
    attempt: int,
) -> int:
    """按冻结策略计算有上限的指数退避时间。"""

    exponent = max(attempt - 1, 0)
    if exponent >= policy.max_delay_us.bit_length():
        base_delay = policy.max_delay_us
    else:
        base_delay = min(
            policy.base_delay_us * (1 << exponent),
            policy.max_delay_us,
        )
    jitter_limit = min(
        policy.max_jitter_us,
        policy.max_delay_us - base_delay,
    )
    jitter = 0
    if jitter_limit:
        try:
            jitter = jitter_source(jitter_limit + 1)
        except Exception:
            raise JiejianError(
                ErrorCode.JOB_RETRY_POLICY_INVALID,
                "重试抖动源失败",
            ) from None
        if type(jitter) is not int or not 0 <= jitter <= jitter_limit:
            raise JiejianError(
                ErrorCode.JOB_RETRY_POLICY_INVALID,
                "重试抖动值无效",
            )
    return checked_time_add(now_us, base_delay + jitter)
