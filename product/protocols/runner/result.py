# Runner 生命周期、清理、错误与受限结果模型。

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from product.backend.core.identifiers import JOB_ID_PATTERN, RUN_ID_PATTERN, SHA256_PATTERN
from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.protocols.execution import ProtocolModel
from .input import (
    CleanupIssueCode,
    CleanupStatus,
    RunnerFailurePhase,
    RunnerResultType,
    STAGED_ARTIFACT_MAX_BYTES,
    STAGED_ARTIFACT_TOTAL_MAX_BYTES,
    _FORBIDDEN_PATH_CHARS,
    _HEX,
    _LEASE_OWNER,
    _REASON_CODE,
    _SAFE_SECRET_KEY_NAMES,
    _SECRET_KEY,
    _WINDOWS_DRIVE,
    _WINDOWS_RESERVED_NAMES,
    _validate_reason_codes,
)
from .evidence import Evidence

def _reject_secret_material(value: Any) -> None:
    pending: list[tuple[tuple[str | int, ...], Any]] = [((), value)]
    while pending:
        path, item = pending.pop()
        if isinstance(item, str):
            if item.startswith("env:"):
                continue
            if re.search(
                r"\bBearer\s+\S+|\b(?:authorization|cookie|password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+",
                item,
                re.I,
            ):
                raise ValueError(" protocol contains inline secret material")
        elif isinstance(item, Mapping):
            for key, child in item.items():
                key_text = str(key)
                child_path = (*path, key_text)
                if (
                    key_text not in _SAFE_SECRET_KEY_NAMES
                    and not key_text.endswith("_ref")
                    and not _is_snapshot_cookie_descriptor_path(child_path)
                    and _SECRET_KEY.search(key_text)
                ):
                    raise ValueError(" protocol contains an inline secret field")
                pending.append((child_path, child))
        elif isinstance(item, Sequence) and not isinstance(item, (bytes, bytearray, str)):
            pending.extend(((*path, index), child) for index, child in enumerate(item))


def _is_snapshot_cookie_descriptor_path(path: tuple[str | int, ...]) -> bool:
    """只识别 Runner 冻结快照中的类型化 Cookie 身份描述。"""

    return (
        len(path) == 5
        and path[0:2] == ("project_snapshot", "identities")
        and isinstance(path[2], int)
        and path[3:] == ("binding", "cookies")
    )

class CleanupIssue(ProtocolModel):
    """一个清理问题及其可选稳定底层原因。"""

    code: CleanupIssueCode
    cause_code: str | None = Field(default=None, pattern=_REASON_CODE)


class CleanupResult(ProtocolModel):
    """独立于主错误的现场恢复与资源关闭结果。"""

    status: CleanupStatus
    finished_at_us: int | None = Field(default=None, ge=0)
    issues: tuple[CleanupIssue, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def validate_cleanup(self) -> CleanupResult:
        if self.status is CleanupStatus.NOT_REQUIRED:
            if self.finished_at_us is not None or self.issues:
                raise ValueError("not-required cleanup cannot contain completion facts")
        elif self.finished_at_us is None:
            raise ValueError("performed cleanup requires a completion time")
        if self.status is CleanupStatus.FAILED:
            if not self.issues:
                raise ValueError("failed cleanup requires structured issues")
        elif self.issues:
            raise ValueError("successful cleanup cannot contain issues")
        if len({item.code for item in self.issues}) != len(self.issues):
            raise ValueError("cleanup issue codes must be unique")
        object.__setattr__(
            self,
            "issues",
            tuple(sorted(self.issues, key=lambda item: item.code.value)),
        )
        return self


class RunnerError(ProtocolModel):
    """一次 Runner 失败的主错误、阶段和稳定原因。"""

    code: str = Field(pattern=_REASON_CODE)
    phase: RunnerFailurePhase
    cause_code: str | None = Field(default=None, pattern=_REASON_CODE)
    retryable: bool


class StagedArtifact(ProtocolModel):
    path: str = Field(min_length=1, max_length=512)
    byte_count: int = Field(ge=0, le=STAGED_ARTIFACT_MAX_BYTES)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        segments = value.split("/")
        if (
            value.startswith("/")
            or _WINDOWS_DRIVE.match(value)
            or "\\" in value
            or any(character in _FORBIDDEN_PATH_CHARS for character in value)
            or any(segment in {"", ".", ".."} for segment in segments)
            or any(ord(character) < 32 for character in value)
            or any(len(segment) > 255 for segment in segments)
            or any(segment.endswith((".", " ")) for segment in segments)
            or any(segment.split(".", 1)[0].rstrip(" .").casefold() in _WINDOWS_RESERVED_NAMES for segment in segments)
        ):
            raise ValueError("artifact path must be normalized and relative")
        return value


class RunnerResult(ProtocolModel):
    schema_version: Literal["1"] = "1"
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    attempt: int = Field(ge=1)
    lease_owner: str = Field(pattern=_LEASE_OWNER)
    fencing_token: int = Field(ge=1)
    finished_at_us: int = Field(ge=0)
    result_type: RunnerResultType
    run_lifecycle: RunLifecycle
    job_state: JobState
    verdict: RunVerdict | None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=128)
    cleanup: CleanupResult
    error: RunnerError | None
    plan_fingerprint: str = Field(pattern=_HEX)
    coverage_record_count: int = Field(ge=0, le=16384)
    coverage_gap_count: int = Field(ge=0, le=16384)
    evidence: tuple[Evidence, ...] = Field(default=(), max_length=8192)
    artifacts: tuple[StagedArtifact, ...] = Field(default=(), max_length=8192)

    @model_validator(mode="after")
    def validate_result(self) -> RunnerResult:
        reasons = _validate_reason_codes(self.reason_codes, "result reason_codes")
        allowed_cleanup = {CleanupStatus.NOT_REQUIRED, CleanupStatus.SUCCEEDED}
        if self.result_type is RunnerResultType.SUCCESS:
            valid = (
                self.run_lifecycle is RunLifecycle.COMPLETED
                and self.job_state is JobState.SUCCEEDED
                and self.error is None
                and self.cleanup.status in allowed_cleanup
            )
            if valid and self.coverage_gap_count > 0:
                valid = self.verdict is RunVerdict.INCONCLUSIVE
            elif valid:
                valid = bool(self.evidence)
                aggregate = (
                    RunVerdict.BLOCK
                    if any(item.verdict is CaseVerdict.VULNERABLE for item in self.evidence)
                    else RunVerdict.INCONCLUSIVE
                    if any(item.verdict is CaseVerdict.INCONCLUSIVE for item in self.evidence)
                    else RunVerdict.PASS
                )
                valid = self.verdict is aggregate
        elif self.result_type is RunnerResultType.SAFETY_STOPPED:
            valid = self.run_lifecycle is RunLifecycle.SAFETY_STOPPED and self.job_state is JobState.SUCCEEDED and self.verdict is None and self.error is None and bool(reasons) and self.cleanup.status in allowed_cleanup
        elif self.result_type is RunnerResultType.CANCELLED:
            valid = self.run_lifecycle is RunLifecycle.CANCELLED and self.job_state is JobState.CANCELLED and self.verdict is None and self.error is None and self.cleanup.status is CleanupStatus.SUCCEEDED
        elif self.result_type is RunnerResultType.RETRYABLE_ERROR:
            valid = self.run_lifecycle is RunLifecycle.RUNNING and self.job_state is JobState.RETRY_WAIT and self.verdict is None and self.error is not None and self.error.retryable and self.cleanup.status in allowed_cleanup
        else:
            valid = self.run_lifecycle is RunLifecycle.FAILED and self.job_state is JobState.FAILED and self.verdict is None and self.error is not None and not self.error.retryable and self.cleanup.status in {CleanupStatus.NOT_REQUIRED, CleanupStatus.SUCCEEDED, CleanupStatus.FAILED}
        if self.cleanup.status is CleanupStatus.FAILED:
            valid = (
                valid
                and self.result_type is RunnerResultType.FATAL_ERROR
                and self.error is not None
            )
        if not valid:
            raise ValueError("runner  result violates the lifecycle and verdict matrix")
        if any(item.run_id != self.run_id for item in self.evidence):
            raise ValueError("evidence run_id must match the runner result")
        if any(item.window.finished_at_us > self.finished_at_us for item in (observation for evidence in self.evidence for observation in evidence.observations)):
            raise ValueError("runner finish time precedes an evidence observation window")
        if self.cleanup.finished_at_us is not None and self.cleanup.finished_at_us > self.finished_at_us:
            raise ValueError("runner finish time precedes cleanup completion")
        execution_keys = {
            (
                item.case_snapshot.case_id,
                item.twin_snapshot.twin_id if item.twin_snapshot is not None else None,
                item.twin_role,
            )
            for item in self.evidence
        }
        if len(execution_keys) != len(self.evidence):
            raise ValueError("runner result evidence executions must be unique")
        if len({item.path.casefold() for item in self.artifacts}) != len(self.artifacts):
            raise ValueError("artifact paths must be case-insensitively unique")
        if sum(item.byte_count for item in self.artifacts) > STAGED_ARTIFACT_TOTAL_MAX_BYTES:
            raise ValueError("artifact total exceeds the limit")
        object.__setattr__(self, "reason_codes", reasons)
        _reject_secret_material(self.model_dump(mode="python"))
        return self


__all__ = [name for name in globals() if not name.startswith("__")]
