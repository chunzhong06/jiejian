# =============================================================================
# Observer 公共协议
#
# 定位
#   表达已脱敏、可校验的观察规格、观察窗口、状态和完整性结果。
#
# 职责
#   校验 Observer 配置｜约束观察关联与 provenance｜提供确定性 canonical 编码
#
# 边界
#   本模块不执行请求、不访问数据库、不决定漏洞结论；适配器只可提交有限的
#   脱敏数据。
#
# 调用链
#   Runner / Observer adapters ↔ Observer DTO → Evidence
# =============================================================================

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeVar
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


OBSERVER_JSON_MAX_BYTES = 262_144
OBSERVER_STATE_MAX_BYTES = 262_144
OBSERVER_STATE_MAX_DEPTH = 8
OBSERVER_STATE_MAX_KEYS = 256
_ID_PATTERN = r"^[a-z][a-z0-9_-]{0,63}$"
_TEXT_PATTERN = r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$"
_HEX_PATTERN = r"^[0-9a-f]{64}$"
_REASON_PATTERN = r"^[A-Z][A-Z0-9_]{0,63}$"
_SECRET_REF_PATTERN = r"^env:[A-Z_][A-Z0-9_]{0,63}$"
_PATH_PATTERN = re.compile(r"^/(?:[^{}?&#\s]|\{resource_id\})+$")


class ObserverModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["2"] = "2"


class ObserverType(StrEnum):
    OWNER_API = "OWNER_API"
    READ_ONLY_SQLITE = "READ_ONLY_SQLITE"
    STRUCTURED_AUDIT_LOG = "STRUCTURED_AUDIT_LOG"
    ASYNC_TASK_STATUS = "ASYNC_TASK_STATUS"
    AZURE_QUEUE_PEEK = "AZURE_QUEUE_PEEK"
    AZURE_BLOB_OBJECT = "AZURE_BLOB_OBJECT"


class ObservationPhase(StrEnum):
    INITIAL = "INITIAL"
    BASELINE = "BASELINE"
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    EVENTUAL = "EVENTUAL"


class ObservationCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    TIMED_OUT = "TIMED_OUT"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"


class CausalityStatus(StrEnum):
    CORRELATED = "CORRELATED"
    UNVERIFIED = "UNVERIFIED"


class ProvenanceType(StrEnum):
    OWNER_API = "OWNER_API"
    SQLITE_QUERY = "SQLITE_QUERY"
    AUDIT_LOG_WINDOW = "AUDIT_LOG_WINDOW"
    ASYNC_TASK_API = "ASYNC_TASK_API"
    AZURE_QUEUE_PEEK = "AZURE_QUEUE_PEEK"
    AZURE_BLOB_OBJECT = "AZURE_BLOB_OBJECT"


class ObserverOutcomeStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class OwnerApiLocator(ObserverModel):
    locator_type: Literal["OWNER_API"] = "OWNER_API"
    relative_path_template: str = Field(min_length=2, max_length=512)

    @field_validator("relative_path_template")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        if not _PATH_PATTERN.fullmatch(value) or value.count("{resource_id}") != 1:
            raise ValueError("owner_api locator must be a relative path with one resource_id placeholder")
        return value


class SqliteQueryLocator(ObserverModel):
    locator_type: Literal["READ_ONLY_SQLITE"] = "READ_ONLY_SQLITE"
    query_template_id: str = Field(pattern=_ID_PATTERN)
    table_or_view: str = Field(pattern=_ID_PATTERN)
    database_secret_ref: str = Field(pattern=_SECRET_REF_PATTERN)


_AZURE_ACCOUNT_PATTERN = r"^[a-z0-9]{3,24}$"
_AZURE_QUEUE_NAME_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$"
_AZURE_ALLOWED_QUEUE_FIELDS = frozenset(
    {
        "event_id",
        "case_tag",
        "resource_id",
        "sequence",
        "event_type",
        "task_id",
        "terminal_state",
        "result",
        "effect",
        "value",
    }
)
_AZURE_REQUIRED_QUEUE_FIELDS = frozenset({"event_id", "case_tag", "resource_id", "sequence"})
_AZURE_ALLOWED_METADATA_FIELDS = frozenset(
    {"case_tag", "resource_id", "revision", "result", "effect", "state"}
)
_AZURE_REQUIRED_METADATA_FIELDS = frozenset({"case_tag", "resource_id"})
_AZURE_PREFIX_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9._~-]+$")


def _validate_azure_service_url(value: str, service_suffix: str, *, allow_loopback_http: bool) -> str:
    if any(char.isspace() for char in value):
        raise ValueError("azure service_url cannot contain whitespace")
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValueError("azure service_url must not contain user information, query, or fragment")
    if parsed.hostname is None:
        raise ValueError("azure service_url must contain a host")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("azure service_url port is invalid") from exc
    hostname = parsed.hostname
    public_host_pattern = re.compile(rf"^(?P<account>{_AZURE_ACCOUNT_PATTERN[1:-1]})\.{service_suffix}\.core\.windows\.net$")
    if parsed.scheme == "https" and port is None and parsed.path == "":
        match = public_host_pattern.fullmatch(hostname)
        if match and parsed.netloc == hostname:
            return value
        raise ValueError("azure public service_url must use the exact account endpoint")
    if (
        parsed.scheme != "http"
        or not allow_loopback_http
        or hostname != "127.0.0.1"
        or port is None
        or not 1 <= port <= 65535
    ):
        raise ValueError("azure HTTP service_url requires explicit loopback authorization")
    if not re.fullmatch(_AZURE_ACCOUNT_PATTERN, parsed.path[1:] if parsed.path.startswith("/") else ""):
        raise ValueError("azure loopback service_url must contain one account path")
    account = parsed.path[1:]
    if parsed.netloc != f"127.0.0.1:{port}" or parsed.path != f"/{account}":
        raise ValueError("azure loopback service_url must be normalized")
    return f"http://127.0.0.1:{port}/{account}"


def _validate_azure_fields(values: tuple[str, ...], *, allowed: frozenset[str], required: frozenset[str], label: str) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must be unique")
    if any(not re.fullmatch(_AUDIT_FIELD_PATTERN, value) for value in values):
        raise ValueError(f"{label} must be bounded names")
    if any(value not in allowed for value in values):
        raise ValueError(f"{label} contains a field outside the allowlist")
    if not required.issubset(values):
        raise ValueError(f"{label} misses a required field")
    return tuple(sorted(values))


class QueuePeekBudget(ObserverModel):
    max_messages: int = Field(ge=1, le=32)
    max_message_bytes: int = Field(ge=1, le=OBSERVER_JSON_MAX_BYTES)
    max_total_bytes: int = Field(ge=1, le=OBSERVER_JSON_MAX_BYTES)
    max_attempts: int = Field(ge=1, le=3)
    per_request_timeout_us: int = Field(ge=1, le=120_000_000)
    retry_interval_us: int = Field(ge=0, le=120_000_000)


class AzureQueuePeekLocator(ObserverModel):
    locator_type: Literal["AZURE_QUEUE_PEEK"] = "AZURE_QUEUE_PEEK"
    allow_loopback_http: bool
    service_url: str = Field(min_length=24, max_length=256)
    queue_name: str = Field(pattern=_AZURE_QUEUE_NAME_PATTERN)
    read_only_sas_ref: str = Field(pattern=_SECRET_REF_PATTERN)
    exclusive_test_queue: Literal[True]
    allowed_fields: tuple[str, ...] = Field(min_length=len(_AZURE_REQUIRED_QUEUE_FIELDS), max_length=16)
    peek_budget: QueuePeekBudget

    @field_validator("service_url")
    @classmethod
    def validate_service_url(cls, value: str, info: Any) -> str:
        allow_loopback_http = bool(info.data.get("allow_loopback_http", False))
        return _validate_azure_service_url(value, "queue", allow_loopback_http=allow_loopback_http)

    @field_validator("queue_name")
    @classmethod
    def validate_queue_name(cls, value: str) -> str:
        if "--" in value:
            raise ValueError("azure queue name cannot contain consecutive hyphens")
        return value

    @field_validator("allowed_fields")
    @classmethod
    def validate_allowed_fields(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_azure_fields(
            values,
            allowed=_AZURE_ALLOWED_QUEUE_FIELDS,
            required=_AZURE_REQUIRED_QUEUE_FIELDS,
            label="queue allowed fields",
        )


class BlobObjectScanBudget(ObserverModel):
    page_size: int = Field(ge=1, le=5_000)
    max_pages: int = Field(ge=1, le=256)
    max_objects: int = Field(ge=1, le=10_000)
    max_object_bytes: int = Field(ge=1, le=OBSERVER_JSON_MAX_BYTES)
    max_total_bytes: int = Field(ge=1, le=OBSERVER_JSON_MAX_BYTES)
    max_attempts: int = Field(ge=1, le=3)
    per_request_timeout_us: int = Field(ge=1, le=120_000_000)
    retry_interval_us: int = Field(ge=0, le=120_000_000)


class AzureBlobObjectLocator(ObserverModel):
    locator_type: Literal["AZURE_BLOB_OBJECT"] = "AZURE_BLOB_OBJECT"
    allow_loopback_http: bool
    service_url: str = Field(min_length=24, max_length=256)
    container_name: str = Field(pattern=_AZURE_QUEUE_NAME_PATTERN)
    prefix_template: str = Field(min_length=3, max_length=256)
    read_only_sas_ref: str = Field(pattern=_SECRET_REF_PATTERN)
    exclusive_test_container: Literal[True]
    allowed_metadata_fields: tuple[str, ...] = Field(min_length=len(_AZURE_REQUIRED_METADATA_FIELDS), max_length=16)
    scan_budget: BlobObjectScanBudget

    @field_validator("service_url")
    @classmethod
    def validate_service_url(cls, value: str, info: Any) -> str:
        allow_loopback_http = bool(info.data.get("allow_loopback_http", False))
        return _validate_azure_service_url(value, "blob", allow_loopback_http=allow_loopback_http)

    @field_validator("container_name")
    @classmethod
    def validate_container_name(cls, value: str) -> str:
        if "--" in value:
            raise ValueError("azure container name cannot contain consecutive hyphens")
        return value

    @field_validator("prefix_template")
    @classmethod
    def validate_prefix_template(cls, value: str) -> str:
        if (
            not value.endswith("/")
            or value.startswith("/")
            or "\\" in value
            or "?" in value
            or "#" in value
            or "%" in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError("blob prefix must be a relative slash-terminated template")
        segments = value.split("/")[:-1]
        if segments.count("{request_marker}") != 1 or any(
            segment in {"", ".", ".."} or (segment != "{request_marker}" and not _AZURE_PREFIX_SEGMENT_PATTERN.fullmatch(segment))
            for segment in segments
        ):
            raise ValueError("blob prefix must contain one safe request_marker segment")
        return value

    @field_validator("allowed_metadata_fields")
    @classmethod
    def validate_allowed_metadata_fields(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_azure_fields(
            values,
            allowed=_AZURE_ALLOWED_METADATA_FIELDS,
            required=_AZURE_REQUIRED_METADATA_FIELDS,
            label="blob metadata fields",
        )


_AUDIT_FIELD_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
_AUDIT_FILENAME_PATTERN = r"^[a-z][a-z0-9_-]{0,48}\.jsonl$"
_AUDIT_OFFSET_FILENAME_PATTERN = r"^[a-z][a-z0-9_-]{0,48}(?:\.[1-9][0-9]{0,8})?\.jsonl$"
_AUDIT_ALLOWED_FIELDS = frozenset(
    {
        "event_id",
        "case_tag",
        "task_id",
        "event_type",
        "sequence",
        "resource_id",
        "terminal_state",
        "result",
        "effect",
        "value",
    }
)
_AUDIT_REQUIRED_FIELDS = frozenset(
    {"event_id", "case_tag", "task_id", "event_type", "sequence", "resource_id"}
)


class AuditLogScanBudget(ObserverModel):
    max_files: int = Field(ge=1, le=64)
    max_lines: int = Field(ge=1, le=100_000)
    max_line_bytes: int = Field(ge=1, le=OBSERVER_JSON_MAX_BYTES)


class StructuredAuditLogLocator(ObserverModel):
    locator_type: Literal["STRUCTURED_AUDIT_LOG"] = "STRUCTURED_AUDIT_LOG"
    authorized_root_ref: str = Field(pattern=_SECRET_REF_PATTERN)
    relative_file_pattern: str = Field(pattern=_AUDIT_FILENAME_PATTERN)
    allowed_fields: tuple[str, ...] = Field(min_length=len(_AUDIT_REQUIRED_FIELDS), max_length=16)
    scan_budget: AuditLogScanBudget

    @field_validator("allowed_fields")
    @classmethod
    def validate_allowed_fields(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("audit log allowed fields must be unique")
        if any(not re.fullmatch(_AUDIT_FIELD_PATTERN, value) for value in values):
            raise ValueError("audit log allowed fields must be bounded names")
        if any(value not in _AUDIT_ALLOWED_FIELDS for value in values):
            raise ValueError("audit log field is not allowlisted")
        if not _AUDIT_REQUIRED_FIELDS.issubset(values):
            raise ValueError("audit log allowlist misses a required field")
        return tuple(sorted(values))


_ASYNC_TASK_PATH_PATTERN = re.compile(r"^/(?:[A-Za-z0-9._~!$'()*+,;=:@-]+/)*\{request_marker\}(?:/[A-Za-z0-9._~!$'()*+,;=:@-]+)*$")


class AsyncTaskStatus(StrEnum):
    NOT_CREATED = "NOT_CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


class AsyncTaskPollBudget(ObserverModel):
    max_polls: int = Field(ge=1, le=256)
    poll_interval_us: int = Field(ge=0, le=120_000_000)
    per_request_timeout_us: int = Field(ge=1, le=120_000_000)
    max_response_bytes: int = Field(ge=1, le=OBSERVER_JSON_MAX_BYTES)


class AsyncTaskApiLocator(ObserverModel):
    locator_type: Literal["ASYNC_TASK_STATUS"] = "ASYNC_TASK_STATUS"
    base_url: str = Field(min_length=12, max_length=256)
    relative_path_template: str = Field(min_length=18, max_length=512)
    read_only_credential_ref: str = Field(pattern=_SECRET_REF_PATTERN)
    allow_private_network: bool
    allow_loopback_http: bool
    poll_budget: AsyncTaskPollBudget

    @model_validator(mode="after")
    def validate_locator(self) -> AsyncTaskApiLocator:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or parsed.username is not None or parsed.password is not None:
            raise ValueError("async task base_url must be an origin without user information")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.hostname is None:
            raise ValueError("async task base_url must be an exact origin")
        if parsed.hostname.lower() != parsed.hostname or any(char.isspace() for char in parsed.hostname):
            raise ValueError("async task base_url host must be normalized")
        try:
            address = ipaddress.IPv4Address(parsed.hostname)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except (ipaddress.AddressValueError, ValueError) as exc:
            raise ValueError("async task base_url must use an IPv4 literal") from exc
        if address.is_link_local or address.is_reserved or address.is_unspecified or address.is_multicast or address in {
            ipaddress.IPv4Address("169.254.169.254"),
            ipaddress.IPv4Address("100.100.100.200"),
        }:
            raise ValueError("async task base_url address is not allowed")
        if parsed.scheme == "http" and not (self.allow_loopback_http and address.is_loopback):
            raise ValueError("async task HTTP requires explicit loopback authorization")
        if address.is_private and not (self.allow_private_network or (self.allow_loopback_http and address.is_loopback)):
            raise ValueError("async task private network requires explicit authorization")
        if port < 1 or port > 65535:
            raise ValueError("async task base_url port is invalid")
        normalized = f"{parsed.scheme}://{address}:{port}"
        segments = self.relative_path_template.split("/")[1:]
        if (
            not _ASYNC_TASK_PATH_PATTERN.fullmatch(self.relative_path_template)
            or segments.count("{request_marker}") != 1
            or any(segment in {".", ".."} for segment in segments)
        ):
            raise ValueError("async task path must be a fixed relative request_marker template")
        object.__setattr__(self, "base_url", normalized)
        return self


ObserverLocator = Annotated[
    OwnerApiLocator
    | SqliteQueryLocator
    | StructuredAuditLogLocator
    | AsyncTaskApiLocator
    | AzureQueuePeekLocator
    | AzureBlobObjectLocator,
    Field(discriminator="locator_type"),
]


class ObserverTarget(ObserverModel):
    target_id: str = Field(pattern=_ID_PATTERN)
    locator: ObserverLocator
    normalization_id: str = Field(pattern=_ID_PATTERN)
    normalization_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,3}$")


class ObserverBudget(ObserverModel):
    timeout_us: int = Field(ge=1, le=120_000_000)
    max_rows: int = Field(ge=1, le=10_000)
    max_bytes: int = Field(ge=1, le=OBSERVER_JSON_MAX_BYTES)


# 冻结一个 Observer 的类型、定位器、预算与必需性。
class ObserverSpec(ObserverModel):
    observer_id: str = Field(pattern=_ID_PATTERN)
    observer_type: ObserverType
    protocol_version: Literal["2"] = "2"
    target: ObserverTarget
    phases: tuple[ObservationPhase, ...] = Field(min_length=1, max_length=5)
    required: bool
    budget: ObserverBudget

    @model_validator(mode="after")
    def validate_spec(self) -> ObserverSpec:
        if len(set(self.phases)) != len(self.phases):
            raise ValueError("observer phases must be unique")
        object.__setattr__(self, "phases", tuple(sorted(self.phases, key=lambda phase: phase.value)))
        locator = self.target.locator
        locator_type = self.target.locator.locator_type
        expected = {
            ObserverType.OWNER_API: "OWNER_API",
            ObserverType.READ_ONLY_SQLITE: "READ_ONLY_SQLITE",
            ObserverType.STRUCTURED_AUDIT_LOG: "STRUCTURED_AUDIT_LOG",
            ObserverType.ASYNC_TASK_STATUS: "ASYNC_TASK_STATUS",
            ObserverType.AZURE_QUEUE_PEEK: "AZURE_QUEUE_PEEK",
            ObserverType.AZURE_BLOB_OBJECT: "AZURE_BLOB_OBJECT",
        }[self.observer_type]
        if locator_type != expected:
            raise ValueError("observer type and locator type must match")
        if self.observer_type is ObserverType.OWNER_API and self.budget.max_rows != 1:
            raise ValueError("owner_api max_rows must be 1")
        if self.observer_type is ObserverType.STRUCTURED_AUDIT_LOG:
            if any(phase not in {ObservationPhase.BEFORE, ObservationPhase.AFTER, ObservationPhase.EVENTUAL} for phase in self.phases):
                raise ValueError("audit log observer phases must be BEFORE, AFTER, or EVENTUAL")
        if self.observer_type is ObserverType.ASYNC_TASK_STATUS:
            if self.phases != (ObservationPhase.EVENTUAL,):
                raise ValueError("async task observer requires the EVENTUAL phase")
            locator = self.target.locator
            if not isinstance(locator, AsyncTaskApiLocator) or locator.poll_budget.max_response_bytes > self.budget.max_bytes:
                raise ValueError("async task response budget must fit the observer byte budget")
        if self.observer_type is ObserverType.AZURE_QUEUE_PEEK:
            if not isinstance(locator, AzureQueuePeekLocator):
                raise ValueError("azure queue observer requires a queue locator")
            budget = locator.peek_budget
            request_window_us = budget.max_attempts * budget.per_request_timeout_us + max(0, budget.max_attempts - 1) * budget.retry_interval_us
            if (
                budget.max_messages > self.budget.max_rows
                or budget.max_total_bytes > self.budget.max_bytes
                or budget.max_message_bytes > self.budget.max_bytes
                or request_window_us > self.budget.timeout_us
            ):
                raise ValueError("azure queue nested budget exceeds the observer budget")
            if self.phases != (ObservationPhase.EVENTUAL,):
                raise ValueError("azure queue observer requires the EVENTUAL phase")
        if self.observer_type is ObserverType.AZURE_BLOB_OBJECT:
            if not isinstance(locator, AzureBlobObjectLocator):
                raise ValueError("azure blob observer requires a blob locator")
            budget = locator.scan_budget
            request_window_us = budget.max_attempts * budget.per_request_timeout_us + max(0, budget.max_attempts - 1) * budget.retry_interval_us
            maximum_requests = budget.max_pages + budget.max_objects * 2
            if (
                budget.max_objects > self.budget.max_rows
                or budget.max_total_bytes > self.budget.max_bytes
                or budget.max_object_bytes > self.budget.max_bytes
                or maximum_requests * request_window_us > self.budget.timeout_us
            ):
                raise ValueError("azure blob nested budget exceeds the observer budget")
            if any(phase not in {ObservationPhase.BEFORE, ObservationPhase.AFTER, ObservationPhase.EVENTUAL} for phase in self.phases):
                raise ValueError("azure blob observer phases must be BEFORE, AFTER, or EVENTUAL")
        return self


class Correlation(ObserverModel):
    case_id: str = Field(pattern=_ID_PATTERN)
    resource_id: str = Field(pattern=_ID_PATTERN)
    request_marker: str = Field(pattern=_TEXT_PATTERN)


class AuditLogStartCursor(ObserverModel):
    file_name: str = Field(pattern=_AUDIT_OFFSET_FILENAME_PATTERN)
    offset: int = Field(ge=0, le=9_223_372_036_854_775_807)
    anchor_start: int | None = Field(default=None, ge=0, le=9_223_372_036_854_775_807)
    anchor_length: int | None = Field(default=None, ge=0, le=256)
    anchor_sha256: str | None = Field(default=None, pattern=_HEX_PATTERN)

    @model_validator(mode="after")
    def validate_anchor(self) -> AuditLogStartCursor:
        anchor = (self.anchor_start, self.anchor_length, self.anchor_sha256)
        if self.offset == 0:
            if any(value is not None for value in anchor):
                raise ValueError("zero offset cannot carry an audit anchor")
        elif (
            self.anchor_start is None
            or self.anchor_length is None
            or self.anchor_length == 0
            or self.anchor_sha256 is None
            or self.anchor_start + self.anchor_length != self.offset
        ):
            raise ValueError("nonzero audit cursor requires a bounded content anchor")
        return self


class ObserverInvocation(ObserverModel):
    spec: ObserverSpec
    correlation: Correlation
    phase: ObservationPhase

    @model_validator(mode="after")
    def validate_invocation(self) -> ObserverInvocation:
        if self.spec.observer_type is ObserverType.STRUCTURED_AUDIT_LOG:
            raise ValueError("structured audit observers require AuditLogObserverInvocation")
        if self.spec.observer_type is ObserverType.ASYNC_TASK_STATUS:
            raise ValueError("async task observers require AsyncTaskObserverInvocation")
        if self.phase not in self.spec.phases:
            raise ValueError("observer invocation phase is not declared by the spec")
        return self


class AsyncTaskObserverInvocation(ObserverModel):
    spec: ObserverSpec
    correlation: Correlation
    phase: ObservationPhase

    @model_validator(mode="after")
    def validate_invocation(self) -> AsyncTaskObserverInvocation:
        if self.spec.observer_type is not ObserverType.ASYNC_TASK_STATUS:
            raise ValueError("async task invocation requires an async task observer")
        if self.phase is not ObservationPhase.EVENTUAL or self.phase not in self.spec.phases:
            raise ValueError("async task invocation requires the EVENTUAL phase")
        return self


class AuditLogObserverInvocation(ObserverModel):
    spec: ObserverSpec
    correlation: Correlation
    phase: ObservationPhase
    start_cursors: tuple[AuditLogStartCursor, ...] = ()

    @model_validator(mode="after")
    def validate_invocation(self) -> AuditLogObserverInvocation:
        if self.spec.observer_type is not ObserverType.STRUCTURED_AUDIT_LOG:
            raise ValueError("audit invocation requires a structured audit observer")
        if self.phase not in self.spec.phases:
            raise ValueError("observer invocation phase is not declared by the spec")
        if len({item.file_name for item in self.start_cursors}) != len(self.start_cursors):
            raise ValueError("audit log start cursors must be unique")
        locator = self.spec.target.locator
        if not isinstance(locator, StructuredAuditLogLocator):
            raise ValueError("audit invocation requires an audit locator")
        base = locator.relative_file_pattern[:-6]
        for item in self.start_cursors:
            if item.file_name != locator.relative_file_pattern and not (
                item.file_name.startswith(base + ".") and re.fullmatch(r"[a-z][a-z0-9_-]{0,48}\.[1-9][0-9]{0,8}\.jsonl", item.file_name)
            ):
                raise ValueError("audit log start cursor is outside the declared rotation family")
        object.__setattr__(self, "start_cursors", tuple(sorted(self.start_cursors, key=lambda item: item.file_name)))
        return self


class ObservationWindow(ObserverModel):
    phase: ObservationPhase
    started_at_us: int = Field(ge=0)
    finished_at_us: int = Field(ge=0)
    timeout_us: int = Field(ge=1, le=120_000_000)

    @model_validator(mode="after")
    def validate_window(self) -> ObservationWindow:
        if self.finished_at_us < self.started_at_us:
            raise ValueError("observation window cannot finish before it starts")
        if self.finished_at_us - self.started_at_us > self.timeout_us:
            raise ValueError("observation window exceeded its timeout")
        return self


def _reject_secret_values(value: Any, known_secrets: tuple[str, ...]) -> None:
    if isinstance(value, str):
        if any(secret and secret in value for secret in known_secrets):
            raise ValueError("known secret must not enter observer state")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("observer state keys must be strings")
            if any(secret and secret in key for secret in known_secrets):
                raise ValueError("known secret must not enter observer state")
            _reject_secret_values(item, known_secrets)
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            _reject_secret_values(item, known_secrets)


def _normalise_json_value(value: Any, *, depth: int, key_count: list[int]) -> Any:
    if depth > OBSERVER_STATE_MAX_DEPTH:
        raise ValueError("observer state nesting exceeds the limit")
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > 4096:
            raise ValueError("observer state string exceeds the limit")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("observer state cannot contain non-finite numbers")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str) or len(key) > 128:
                raise ValueError("observer state keys are bounded strings")
            key_count[0] += 1
            if key_count[0] > OBSERVER_STATE_MAX_KEYS:
                raise ValueError("observer state has too many keys")
            result[key] = _normalise_json_value(value[key], depth=depth + 1, key_count=key_count)
        return result
    if isinstance(value, (tuple, list)):
        if len(value) > OBSERVER_STATE_MAX_KEYS:
            raise ValueError("observer state array is too large")
        return [_normalise_json_value(item, depth=depth + 1, key_count=key_count) for item in value]
    raise ValueError("observer state contains a non-JSON value")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class NormalizedState(ObserverModel):
    canonical_data: dict[str, Any]
    canonical_sha256: str = Field(pattern=_HEX_PATTERN)
    byte_count: int = Field(ge=2, le=OBSERVER_STATE_MAX_BYTES)

    @model_validator(mode="after")
    def validate_hash(self) -> NormalizedState:
        normalized = _normalise_json_value(self.canonical_data, depth=0, key_count=[0])
        data = _json_bytes(normalized)
        if len(data) != self.byte_count or hashlib.sha256(data).hexdigest() != self.canonical_sha256:
            raise ValueError("normalized observer state hash or byte count does not match")
        object.__setattr__(self, "canonical_data", normalized)
        return self


def build_normalized_state(payload: Mapping[str, Any], *, known_secrets: tuple[str, ...] = ()) -> NormalizedState:
    """对脱敏 payload 生成确定性 canonical 状态；检测到秘密时立即拒绝。"""

    if not isinstance(payload, Mapping):
        raise ValueError("normalized observer state must be an object")
    _reject_secret_values(payload, known_secrets)
    normalized = _normalise_json_value(payload, depth=0, key_count=[0])
    data = _json_bytes(normalized)
    if len(data) > OBSERVER_STATE_MAX_BYTES:
        raise ValueError("normalized observer state exceeds the byte limit")
    return NormalizedState(
        canonical_data=normalized,
        canonical_sha256=hashlib.sha256(data).hexdigest(),
        byte_count=len(data),
    )


class ObservationProvenance(ObserverModel):
    provenance_type: ProvenanceType
    adapter_version: str = Field(pattern=_TEXT_PATTERN)
    target_id: str = Field(pattern=_ID_PATTERN)
    query_template_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    source_sha256: str = Field(pattern=_HEX_PATTERN)

    @model_validator(mode="after")
    def validate_provenance(self) -> ObservationProvenance:
        if self.provenance_type is ProvenanceType.SQLITE_QUERY and self.query_template_id is None:
            raise ValueError("sqlite provenance requires a query template")
        if self.provenance_type is ProvenanceType.AUDIT_LOG_WINDOW and self.query_template_id is not None:
            raise ValueError("audit log provenance cannot contain a query template")
        if self.provenance_type in {
            ProvenanceType.OWNER_API,
            ProvenanceType.AUDIT_LOG_WINDOW,
            ProvenanceType.ASYNC_TASK_API,
            ProvenanceType.AZURE_QUEUE_PEEK,
            ProvenanceType.AZURE_BLOB_OBJECT,
        } and self.query_template_id is not None:
            raise ValueError("this provenance type cannot contain a query template")
        return self


# 一次带 phase、correlation、完整性和 provenance 的不可变观察。
class ObservationEnvelope(ObserverModel):
    observer_id: str = Field(pattern=_ID_PATTERN)
    observer_type: ObserverType
    protocol_version: Literal["2"] = "2"
    phase: ObservationPhase
    target_id: str = Field(pattern=_ID_PATTERN)
    window: ObservationWindow
    correlation: Correlation
    causality: CausalityStatus
    completeness: ObservationCompleteness
    state: NormalizedState | None = None
    provenance: ObservationProvenance | None = None
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)

    @field_validator("reason_codes")
    @classmethod
    def normalize_reasons(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(_REASON_PATTERN, value) for value in values):
            raise ValueError("observer reason codes must be stable uppercase codes")
        if len(set(values)) != len(values):
            raise ValueError("observer reason codes must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_envelope(self) -> ObservationEnvelope:
        if self.phase is not self.window.phase:
            raise ValueError("envelope phase and window phase must match")
        if self.completeness is ObservationCompleteness.COMPLETE:
            if self.state is None or self.provenance is None or self.causality is not CausalityStatus.CORRELATED or self.reason_codes:
                raise ValueError("complete observation requires correlated state and provenance without failure reasons")
        elif self.completeness is ObservationCompleteness.PARTIAL:
            if not self.reason_codes:
                raise ValueError("partial observation requires a reason")
        else:
            if self.state is not None or not self.reason_codes:
                raise ValueError("incomplete observation cannot contain state and requires a reason")
        expected_provenance = {
            ObserverType.OWNER_API: ProvenanceType.OWNER_API,
            ObserverType.READ_ONLY_SQLITE: ProvenanceType.SQLITE_QUERY,
            ObserverType.STRUCTURED_AUDIT_LOG: ProvenanceType.AUDIT_LOG_WINDOW,
            ObserverType.ASYNC_TASK_STATUS: ProvenanceType.ASYNC_TASK_API,
            ObserverType.AZURE_QUEUE_PEEK: ProvenanceType.AZURE_QUEUE_PEEK,
            ObserverType.AZURE_BLOB_OBJECT: ProvenanceType.AZURE_BLOB_OBJECT,
        }[self.observer_type]
        if self.provenance is not None and self.provenance.provenance_type is not expected_provenance:
            raise ValueError("observation provenance does not match observer type")
        if self.provenance is not None and self.provenance.target_id != self.target_id:
            raise ValueError("observation provenance target does not match envelope target")
        return self


class ObserverOutcome(ObserverModel):
    observer_id: str = Field(pattern=_ID_PATTERN)
    required: bool
    status: ObserverOutcomeStatus
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)


def evaluate_observer_outcome(
    envelope: ObservationEnvelope,
    *,
    required: bool,
    adapter_error: bool = False,
) -> ObserverOutcome:
    if adapter_error:
        status = ObserverOutcomeStatus.EXECUTION_ERROR
    elif required and envelope.completeness is not ObservationCompleteness.COMPLETE:
        status = ObserverOutcomeStatus.INCONCLUSIVE
    else:
        status = ObserverOutcomeStatus.AVAILABLE
    return ObserverOutcome(
        observer_id=envelope.observer_id,
        required=required,
        status=status,
        reason_codes=envelope.reason_codes,
    )


T = TypeVar("T", bound=BaseModel)


def canonical_json_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    return _json_bytes(value)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def parse_observer_json(
    payload: bytes,
    model_type: type[T],
    *,
    known_secrets: tuple[str, ...] = (),
) -> T:
    if len(payload) > OBSERVER_JSON_MAX_BYTES or payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("observer JSON is oversized or contains a BOM")

    def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("observer JSON contains duplicate keys")
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"observer JSON contains non-finite number: {value}")

    parsed = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=reject_duplicate_pairs,
        parse_constant=reject_nonfinite,
    )
    if not isinstance(parsed, dict):
        raise ValueError("observer JSON root must be an object")
    _reject_secret_values(parsed, known_secrets)
    # 上方先在解码树中拒绝重复键、非有限数与 BOM；随后仍经 Pydantic JSON 入口
    # 解析 enum 和 tuple wire 值，以保留严格模型语义。
    return model_type.model_validate_json(payload)
