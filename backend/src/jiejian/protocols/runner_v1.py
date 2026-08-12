# =============================================================================
# Runner V1 进程协议
#
# 定位
#   Worker 与隔离 Verification Runner 之间的稳定版本化 Wire DTO 边界
#
# 职责
#   校验输入快照和预算｜编码可信结果｜限制路径、大小、hash 与 schema_version
#
# 调用链
#   Execution supervisor ↔ Runner V1 JSON files ↔ runner.execution
# =============================================================================

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal, TypeAlias, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from ..domain.identifiers import (
    JOB_ID_PATTERN,
    PROJECT_ID_PATTERN,
    RUN_ID_PATTERN,
    SHA256_PATTERN,
)
from ..domain.lifecycle import ContractStatus, JobState, RunLifecycle, RunVerdict
from ..verification.models import (
    Flow,
    Identity,
    ResourceDefinition,
    RuleKind,
    SecurityContract,
    TargetScope,
)
from ..errors import JiejianError

RUNNER_INPUT_MAX_BYTES = 1_048_576
RUNNER_RESULT_MAX_BYTES = 4_194_304
STAGED_ARTIFACT_MAX_BYTES = 1_073_741_824
STAGED_ARTIFACT_TOTAL_MAX_BYTES = 1_073_741_824

_LEASE_OWNER = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_REASON_CODE = r"^[A-Z][A-Z0-9_]{0,127}$"
_SECRET_KEY = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)",
    re.IGNORECASE,
)
_INLINE_SECRET = re.compile(
    r"(?:\bBearer\s+\S+|\b(?:authorization|cookie|credential|password|passwd|"
    r"secret|token|api[_-]?key)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_WINDOWS_FORBIDDEN_CHARACTERS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)


class ProtocolModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"]


class RunnerResultType(StrEnum):
    SUCCESS = "SUCCESS"
    SAFETY_STOPPED = "SAFETY_STOPPED"
    CANCELLED = "CANCELLED"
    RETRYABLE_ERROR = "RETRYABLE_ERROR"
    FATAL_ERROR = "FATAL_ERROR"


class CleanupStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ExecutionBudgetV1(ProtocolModel):
    max_requests: int = Field(ge=1, le=500)
    request_timeout_us: int = Field(ge=1, le=30_000_000)
    max_duration_us: int = Field(ge=1, le=3_600_000_000)
    max_response_bytes: int = Field(ge=1, le=4_194_304)
    max_parallel_cases: Literal[1]


class ExecutionProjectSnapshotV1(ProtocolModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    project_name: str = Field(min_length=1, max_length=128)
    target: TargetScope
    identities: tuple[Identity, ...] = Field(min_length=2)
    resources: tuple[ResourceDefinition, ...] = Field(min_length=2)
    flow: Flow
    contract: SecurityContract
    owner_observer_enabled: bool
    mutation_seed: int

    @model_validator(mode="after")
    def validate_snapshot_references(self) -> ExecutionProjectSnapshotV1:
        identity_ids = {item.id for item in self.identities}
        resource_ids = {item.id for item in self.resources}
        step_ids = {item.id for item in self.flow.steps}
        rule_ids = {item.id for item in self.contract.rules}
        rule_kinds = {item.kind for item in self.contract.rules}
        if len(identity_ids) != len(self.identities):
            raise ValueError("identity IDs must be unique")
        if len(resource_ids) != len(self.resources):
            raise ValueError("resource IDs must be unique")
        if len(step_ids) != len(self.flow.steps):
            raise ValueError("flow step IDs must be unique")
        if len(rule_ids) != len(self.contract.rules):
            raise ValueError("contract rule IDs must be unique")
        if len(rule_kinds) != len(self.contract.rules):
            raise ValueError("contract rule kinds must be unique")
        if any(item.owner_identity_id not in identity_ids for item in self.resources):
            raise ValueError("resource owner must reference a snapshot identity")
        if any(
            reference not in identity_ids
            for step in self.flow.steps
            for reference in (step.identity_id, step.alternate_identity_id)
        ):
            raise ValueError("flow identity must reference a snapshot identity")
        if any(
            reference not in resource_ids
            for step in self.flow.steps
            for reference in (step.resource_id, step.alternate_resource_id)
        ):
            raise ValueError("flow resource must reference a snapshot resource")
        if self.contract.status is not ContractStatus.ACTIVE:
            raise ValueError("runner snapshot requires an ACTIVE contract")
        required_kinds = {RuleKind.FOREIGN_READ}
        if any(step.method != "GET" for step in self.flow.steps):
            required_kinds.update(
                {RuleKind.UNAUTHORIZED_SIDE_EFFECT, RuleKind.PRIVILEGED_FIELD}
            )
        if not required_kinds.issubset(rule_kinds):
            raise ValueError("contract lacks relationship rules required by the flow")
        _reject_inline_secret_material(self.model_dump(mode="python"))
        return self


class RunnerInputV1(ProtocolModel):
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    attempt: int = Field(ge=1)
    lease_owner: str = Field(pattern=_LEASE_OWNER)
    fencing_token: int = Field(ge=1)
    created_at_us: int = Field(ge=0)
    budget: ExecutionBudgetV1
    project_snapshot: ExecutionProjectSnapshotV1

    @model_validator(mode="after")
    def validate_budget_snapshot(self) -> RunnerInputV1:
        target = self.project_snapshot.target
        if self.budget.max_requests != target.max_requests:
            raise ValueError("budget max_requests must match target snapshot")
        if self.budget.max_response_bytes != target.max_response_bytes:
            raise ValueError("budget max_response_bytes must match target snapshot")
        if self.budget.request_timeout_us != int(target.timeout_seconds * 1_000_000):
            raise ValueError("budget request_timeout_us must match target snapshot")
        if _contains_non_finite(self.model_dump(mode="python")):
            raise ValueError("protocol values must not contain non-finite numbers")
        return self


class CleanupResultV1(ProtocolModel):
    status: CleanupStatus
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            re.fullmatch(_REASON_CODE, value) is None for value in values
        ):
            raise ValueError("cleanup reason codes must be unique stable codes")
        return values

    @model_validator(mode="after")
    def validate_failed_cleanup_reason(self) -> CleanupResultV1:
        if self.status is CleanupStatus.FAILED and not self.reason_codes:
            raise ValueError("failed cleanup requires a reason code")
        if self.status is not CleanupStatus.FAILED and self.reason_codes:
            raise ValueError("successful or unnecessary cleanup has no reason code")
        return self


class RunnerErrorV1(ProtocolModel):
    code: str = Field(pattern=_REASON_CODE)
    retryable: bool


class StagedArtifactV1(ProtocolModel):
    path: str = Field(min_length=1, max_length=512)
    byte_count: int = Field(ge=0, le=STAGED_ARTIFACT_MAX_BYTES)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("path")
    @classmethod
    def validate_relative_posix_path(cls, value: str) -> str:
        segments = value.split("/")
        if (
            value.startswith("/")
            or _WINDOWS_DRIVE.match(value)
            or "\\" in value
            or any(character in _WINDOWS_FORBIDDEN_CHARACTERS for character in value)
            or any(segment in {"", ".", ".."} for segment in segments)
            or any(ord(character) < 32 for character in value)
            or any(len(segment) > 255 for segment in segments)
            or any(segment.endswith((".", " ")) for segment in segments)
            or any(
                segment.split(".", 1)[0].rstrip(" .").casefold()
                in _WINDOWS_RESERVED_NAMES
                for segment in segments
            )
        ):
            raise ValueError("artifact path must be a normalized Windows-safe path")
        return value


class RunnerResultV1(ProtocolModel):
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
    cleanup: CleanupResultV1
    error: RunnerErrorV1 | None
    artifacts: tuple[StagedArtifactV1, ...] = Field(default=(), max_length=4096)

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            re.fullmatch(_REASON_CODE, value) is None for value in values
        ):
            raise ValueError("reason codes must be unique stable codes")
        return values

    @model_validator(mode="after")
    def validate_result_matrix(self) -> RunnerResultV1:
        allowed_cleanup = {CleanupStatus.NOT_REQUIRED, CleanupStatus.SUCCEEDED}
        if self.result_type is RunnerResultType.SUCCESS:
            valid = (
                self.run_lifecycle is RunLifecycle.COMPLETED
                and self.job_state is JobState.SUCCEEDED
                and self.verdict is not None
                and self.error is None
                and self.cleanup.status in allowed_cleanup
            )
        elif self.result_type is RunnerResultType.SAFETY_STOPPED:
            valid = (
                self.run_lifecycle is RunLifecycle.SAFETY_STOPPED
                and self.job_state is JobState.SUCCEEDED
                and self.verdict is None
                and self.error is None
                and bool(self.reason_codes)
                and self.cleanup.status in allowed_cleanup
            )
        elif self.result_type is RunnerResultType.CANCELLED:
            valid = (
                self.run_lifecycle is RunLifecycle.CANCELLED
                and self.job_state is JobState.CANCELLED
                and self.verdict is None
                and self.error is None
                and self.cleanup.status is CleanupStatus.SUCCEEDED
            )
        elif self.result_type is RunnerResultType.RETRYABLE_ERROR:
            valid = (
                self.run_lifecycle
                in {
                    RunLifecycle.PREFLIGHT,
                    RunLifecycle.PLANNING,
                    RunLifecycle.EXECUTING,
                    RunLifecycle.VERIFYING,
                    RunLifecycle.REPORTING,
                }
                and self.job_state is JobState.RETRY_WAIT
                and self.verdict is None
                and self.error is not None
                and self.error.retryable
                and self.cleanup.status in allowed_cleanup
            )
        else:
            valid = (
                self.run_lifecycle is RunLifecycle.FAILED
                and self.job_state is JobState.FAILED
                and self.verdict is None
                and self.error is not None
                and not self.error.retryable
            )
        if not valid:
            raise ValueError("runner result violates the lifecycle and verdict matrix")
        if len({item.path.casefold() for item in self.artifacts}) != len(
            self.artifacts
        ):
            raise ValueError("staged artifact paths must be case-insensitively unique")
        if (
            sum(item.byte_count for item in self.artifacts)
            > STAGED_ARTIFACT_TOTAL_MAX_BYTES
        ):
            raise ValueError("staged artifact total byte count exceeds the limit")
        return self


ProtocolDocument: TypeAlias = RunnerInputV1 | RunnerResultV1
ProtocolT = TypeVar("ProtocolT", RunnerInputV1, RunnerResultV1)


def canonical_json_bytes(
    document: ProtocolDocument,
    *,
    known_secrets: Sequence[str] = (),
) -> bytes:
    """返回协议文档的唯一 UTF-8 JSON 字节表示。"""

    if not isinstance(document, (RunnerInputV1, RunnerResultV1)):
        raise TypeError("canonical JSON only accepts a Runner protocol document")
    model_data = document.model_dump(mode="json")
    _reject_known_secret_material(model_data, known_secrets)
    try:
        encoded = json.dumps(
            model_data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise JiejianError(
            "PROTOCOL_INVALID",
            "协议文档无法规范序列化",
            details={"reason": type(exc).__name__},
        ) from None
    maximum = (
        RUNNER_INPUT_MAX_BYTES
        if isinstance(document, RunnerInputV1)
        else RUNNER_RESULT_MAX_BYTES
    )
    if len(encoded) > maximum:
        raise JiejianError("PROTOCOL_TOO_LARGE", "协议文档超过大小限制")
    return encoded


def canonical_json_sha256(
    document: ProtocolDocument,
    *,
    known_secrets: Sequence[str] = (),
) -> str:
    """对协议的规范 JSON 字节计算小写 SHA-256。"""

    return hashlib.sha256(
        canonical_json_bytes(document, known_secrets=known_secrets)
    ).hexdigest()


def parse_runner_input(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> RunnerInputV1:
    return _parse_protocol_json(
        raw,
        RunnerInputV1,
        RUNNER_INPUT_MAX_BYTES,
        "Runner 输入",
        known_secrets,
    )


def parse_runner_result(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> RunnerResultV1:
    return _parse_protocol_json(
        raw,
        RunnerResultV1,
        RUNNER_RESULT_MAX_BYTES,
        "Runner 结果",
        known_secrets,
    )


def _parse_protocol_json(
    raw: bytes,
    model: type[ProtocolT],
    maximum: int,
    label: str,
    known_secrets: Sequence[str],
) -> ProtocolT:
    if not isinstance(raw, bytes):
        raise TypeError("protocol parser requires bytes")
    if len(raw) > maximum:
        raise JiejianError("PROTOCOL_TOO_LARGE", f"{label}超过大小限制")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError("PROTOCOL_INVALID", f"{label}不得包含 UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_non_finite_constant,
        )
        _reject_known_secret_material(parsed, known_secrets)
        return model.model_validate_json(raw, strict=True)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateKey, _NonFinite):
        raise JiejianError("PROTOCOL_INVALID", f"{label}不是严格 JSON") from None
    except ValidationError as exc:
        issue_types = tuple(issue["type"] for issue in exc.errors()[:64])
        raise JiejianError(
            "PROTOCOL_INVALID",
            f"{label}校验失败",
            details={
                "issue_count": exc.error_count(),
                "issue_types": issue_types,
            },
        ) from None


class _DuplicateKey(ValueError):
    pass


class _NonFinite(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey
        result[key] = value
    return result


def _reject_non_finite_constant(_: str) -> None:
    raise _NonFinite


def _contains_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(
            _contains_non_finite(key) or _contains_non_finite(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_non_finite(item) for item in value)
    return False


def _reject_known_secret_material(
    value: Any,
    known_secrets: Sequence[str],
) -> None:
    if any(not isinstance(secret, str) for secret in known_secrets):
        raise TypeError("known_secrets must contain only strings")
    secrets = tuple(secret for secret in known_secrets if secret)
    if not secrets:
        return
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if any(secret in item for secret in secrets):
                raise JiejianError(
                    "PROTOCOL_SECRET_EXPOSED",
                    "协议文档包含已知秘密",
                )
        elif isinstance(item, Mapping):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, Sequence) and not isinstance(
            item, (bytes, bytearray)
        ):
            pending.extend(item)


def _reject_inline_secret_material(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text == "secret_ref":
                if not isinstance(item, str) or re.fullmatch(
                    r"env:[A-Z][A-Z0-9_]{0,127}", item
                ) is None:
                    raise ValueError("snapshot secret references must use env:NAME")
                continue
            if _SECRET_KEY.search(key_text):
                raise ValueError("snapshot contains an inline credential field")
            _reject_inline_secret_material(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_inline_secret_material(item)
    elif isinstance(value, str) and _INLINE_SECRET.search(value):
        raise ValueError("snapshot contains inline credential material")
