# =============================================================================
# Recording Runner 进程协议
#
# 定位
#   Worker 与隔离 Recording Runner 之间的稳定版本化 Wire DTO 边界
#
# 职责
#   校验 action/session/范围和预算｜约束事件与清理结果｜编码严格 JSON 请求和结果
#
# 边界
#   不执行浏览器、不保存原始 secret；认证只允许非秘密元数据与 env 引用。
#
# 调用链
#   Recording job handler ↔ Recording JSON files ↔ recording_process
# =============================================================================

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, Literal, TypeAlias, TypeVar
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from product.backend.core.identifiers import (
    PROJECT_ID_PATTERN,
    RECORDING_ID_PATTERN,
    TEST_IDENTITY_ID_PATTERN,
)
from product.backend.core.recording import RecordingState, RecordingStateEvent
from product.protocols.web.target import WebTargetScope
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.redaction import REDACTED

RECORDING_REQUEST_MAX_BYTES = 1_048_576
RECORDING_RESULT_MAX_BYTES = 4_194_304
RECORDING_EVENT_MAX_BYTES = 262_144
RECORDING_EVENT_MAX_COUNT = 10_000

_PAGE_ID = r"^page_[0-9]{6}$"
_FRAME_ID = r"^frame_[0-9]{6}$"
_REQUEST_ID = r"^(?:request|websocket)_[0-9]{6}$"
_ACTION_ID = r"^action_[0-9]{6}$"
_REASON_CODE = r"^[A-Z][A-Z0-9_]{0,127}$"
_SESSION_REF = r"^session_[0-9a-f]{32}$"
_HEADER_NAME = r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$"
_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|"
    r"api[_-]?key|id[_-]?card|ssn|email|phone|address)",
    re.IGNORECASE,
)
_INLINE_SECRET = re.compile(
    r"(?:\bBearer\s+\S+|\b(?:authorization|cookie|credential|password|passwd|"
    r"secret|token|api[_-]?key)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


class RecordingProtocolModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )



class RecordingRunnerResultType(StrEnum):
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SAFETY_STOPPED = "SAFETY_STOPPED"


class RecordingCleanupStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class RecordingEventKind(StrEnum):
    PAGE_OPENED = "PAGE_OPENED"
    PAGE_CLOSED = "PAGE_CLOSED"
    FRAME_ATTACHED = "FRAME_ATTACHED"
    NAVIGATION = "NAVIGATION"
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    WEBSOCKET_OPENED = "WEBSOCKET_OPENED"
    WEBSOCKET_SENT = "WEBSOCKET_SENT"
    WEBSOCKET_RECEIVED = "WEBSOCKET_RECEIVED"
    CONSOLE = "CONSOLE"
    PAGE_ERROR = "PAGE_ERROR"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    UI_CLICK = "UI_CLICK"
    UI_INPUT_CHANGE = "UI_INPUT_CHANGE"
    UI_SUBMIT = "UI_SUBMIT"


class RecordingAuthMethod(StrEnum):
    COOKIE_SESSION = "COOKIE_SESSION"
    BEARER = "BEARER"


class RecordingBudget(RecordingProtocolModel):
    max_duration_us: int = Field(ge=1, le=3_600_000_000)
    max_events: int = Field(default=2_000, ge=1, le=RECORDING_EVENT_MAX_COUNT)
    max_pages: int = Field(default=8, ge=1, le=32)
    max_contexts: int = Field(default=4, ge=1, le=32)
    max_field_chars: int = Field(default=2_048, ge=64, le=8_192)
    max_body_bytes: int = Field(
        default=65_536,
        ge=256,
        le=RECORDING_EVENT_MAX_BYTES - 16_384,
    )
    max_total_payload_bytes: int = Field(
        default=2_097_152,
        ge=1_024,
        le=RECORDING_RESULT_MAX_BYTES - RECORDING_EVENT_MAX_BYTES,
    )


class RecordingCookieRef(RecordingProtocolModel):
    name: str = Field(min_length=1, max_length=256)
    domain: str = Field(min_length=1, max_length=253)
    path: str = Field(min_length=1, max_length=2_048)
    secure: bool
    http_only: bool
    same_site: Literal["STRICT", "LAX", "NONE"]
    expires_at_us: int | None = Field(default=None, ge=0)
    value_ref: str = Field(pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")

    @model_validator(mode="after")
    def validate_cookie_metadata(self) -> RecordingCookieRef:
        if self.name != self.name.strip() or any(ord(char) < 33 for char in self.name):
            raise ValueError("recording cookie name must be trimmed and printable")
        if not self.path.startswith("/"):
            raise ValueError("recording cookie path must be absolute")
        return self


class RecordingSessionRef(RecordingProtocolModel):
    test_identity_id: str = Field(pattern=TEST_IDENTITY_ID_PATTERN)
    session_ref: str = Field(pattern=_SESSION_REF)
    auth_method: RecordingAuthMethod
    cookies: tuple[RecordingCookieRef, ...] = Field(default=(), max_length=32)
    bearer_ref: str | None = Field(
        default=None,
        pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$",
    )
    expires_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_auth_boundary(self) -> RecordingSessionRef:
        refs = tuple(cookie.value_ref for cookie in self.cookies)
        if self.bearer_ref is not None:
            refs += (self.bearer_ref,)
        if len(set(refs)) != len(refs):
            raise ValueError("recording secret references must be unique")
        if self.auth_method is RecordingAuthMethod.COOKIE_SESSION:
            valid = bool(self.cookies) and self.bearer_ref is None
        else:
            valid = not self.cookies and self.bearer_ref is not None
        if not valid:
            raise ValueError("recording auth metadata is inconsistent")
        return self


# Worker 交给 Recording Runner 的冻结目标、身份引用、范围与预算。
class RecordingRunnerRequest(RecordingProtocolModel):
    schema_version: Literal["1"] = "1"
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    action_candidate_id: str = Field(pattern=r"^action_[0-9a-f]{32}$")
    created_at_us: int = Field(ge=0)
    target_scope: WebTargetScope
    sessions: tuple[RecordingSessionRef, ...] = Field(min_length=1, max_length=1)
    budget: RecordingBudget
    headless: bool = True
    trace_enabled: Literal[False] = False

    @model_validator(mode="after")
    def validate_request_boundary(self) -> RecordingRunnerRequest:
        identity_ids = {session.test_identity_id for session in self.sessions}
        session_refs = {session.session_ref for session in self.sessions}
        if len(identity_ids) != len(self.sessions):
            raise ValueError("recording identity IDs must be unique")
        if len(session_refs) != len(self.sessions):
            raise ValueError("recording session references must be unique")
        if len(self.sessions) > self.budget.max_contexts:
            raise ValueError("recording sessions exceed context budget")
        if any(session.expires_at_us <= self.created_at_us for session in self.sessions):
            raise ValueError("recording session reference must be short-lived and active")
        _reject_inline_secret_material(self.model_dump(mode="python"))
        return self


def required_recording_secret_names(request: RecordingRunnerRequest) -> tuple[str, ...]:
    """返回当前录制明确引用的环境变量名，调用方只可按此集合解析值。"""

    return tuple(
        dict.fromkeys(
            reference.removeprefix("env:")
            for session in request.sessions
            for reference in (
                *(cookie.value_ref for cookie in session.cookies),
                *((session.bearer_ref,) if session.bearer_ref is not None else ()),
            )
        )
    )


class RecordingHeader(RecordingProtocolModel):
    name: str = Field(pattern=_HEADER_NAME)
    value: str = Field(max_length=8_192)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def validate_redacted_header(self) -> RecordingHeader:
        if _SENSITIVE_KEY.search(self.name) and self.value != REDACTED:
            raise ValueError("sensitive recording header must be redacted")
        if _INLINE_SECRET.search(self.value):
            raise ValueError("recording header contains inline secret material")
        return self


class RecordingEvent(RecordingProtocolModel):
    schema_version: Literal["1"] = "1"
    sequence: int = Field(ge=1, le=RECORDING_EVENT_MAX_COUNT)
    occurred_at_us: int = Field(ge=0)
    kind: RecordingEventKind
    identity_id: str = Field(pattern=PROJECT_ID_PATTERN)
    page_id: str | None = Field(default=None, pattern=_PAGE_ID)
    frame_id: str | None = Field(default=None, pattern=_FRAME_ID)
    request_id: str | None = Field(default=None, pattern=_REQUEST_ID)
    action_id: str | None = Field(default=None, pattern=_ACTION_ID)
    caused_by_action_id: str | None = Field(default=None, pattern=_ACTION_ID)
    parent_page_id: str | None = Field(default=None, pattern=_PAGE_ID)
    element_locator: str | None = Field(default=None, max_length=2_048)
    field_name: str | None = Field(default=None, max_length=256)
    input_type: str | None = Field(default=None, max_length=64)
    url: str | None = Field(default=None, max_length=8_192)
    method: str | None = Field(default=None, pattern=r"^[A-Z]{2,16}$")
    resource_type: str | None = Field(default=None, max_length=64)
    status_code: int | None = Field(default=None, ge=100, le=599)
    headers: tuple[RecordingHeader, ...] = Field(default=(), max_length=256)
    body: str | None = Field(default=None, max_length=262_144)
    message: str | None = Field(default=None, max_length=8_192)
    reason_code: str | None = Field(default=None, pattern=_REASON_CODE)
    truncated: bool = False

    @field_validator("url")
    @classmethod
    def reject_url_userinfo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("recording event URL must not contain user information")
        return value

    @field_validator("body", "message")
    @classmethod
    def reject_inline_secret_text(cls, value: str | None) -> str | None:
        if value is not None and _INLINE_SECRET.search(value):
            raise ValueError("recording event text contains inline secret material")
        return value

    @model_validator(mode="after")
    def validate_ui_action_boundary(self) -> RecordingEvent:
        ui_kinds = {
            RecordingEventKind.UI_CLICK,
            RecordingEventKind.UI_INPUT_CHANGE,
            RecordingEventKind.UI_SUBMIT,
        }
        if self.kind in ui_kinds:
            valid = (
                self.action_id is not None
                and self.page_id is not None
                and self.frame_id is not None
                and self.element_locator is not None
                and self.request_id is None
                and self.caused_by_action_id is None
                and self.body is None
            )
        else:
            valid = (
                self.action_id is None
                and self.element_locator is None
                and self.field_name is None
                and self.input_type is None
            )
            if self.kind is not RecordingEventKind.REQUEST:
                valid = valid and self.caused_by_action_id is None
        if not valid:
            raise ValueError("recording UI event violates action boundary")
        return self


class RecordingRunnerError(RecordingProtocolModel):
    code: str = Field(pattern=_REASON_CODE)
    retryable: bool


# Recording Runner 的完成、取消、安全停止或失败结果；清理状态独立表达。
class RecordingRunnerResult(RecordingProtocolModel):
    schema_version: Literal["1"] = "1"
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    finished_at_us: int = Field(ge=0)
    result_type: RecordingRunnerResultType
    recording_state: RecordingState
    cleanup_status: RecordingCleanupStatus
    reason_codes: tuple[str, ...] = Field(default=(), max_length=64)
    state_events: tuple[RecordingStateEvent, ...] = Field(default=(), max_length=128)
    events: tuple[RecordingEvent, ...] = Field(
        default=(), max_length=RECORDING_EVENT_MAX_COUNT
    )
    error: RecordingRunnerError | None = None

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            re.fullmatch(_REASON_CODE, value) is None for value in values
        ):
            raise ValueError("recording reason codes must be unique stable codes")
        return values

    @model_validator(mode="after")
    def validate_result_matrix(self) -> RecordingRunnerResult:
        if tuple(event.sequence for event in self.events) != tuple(
            range(1, len(self.events) + 1)
        ):
            raise ValueError("recording browser event sequence must be continuous")
        if self.state_events and self.finished_at_us < self.state_events[-1].occurred_at_us:
            raise ValueError("recording result time precedes lifecycle events")
        if self.result_type is RecordingRunnerResultType.CAPTURED:
            valid = (
                self.recording_state is RecordingState.PROCESSING
                and self.cleanup_status is RecordingCleanupStatus.SUCCEEDED
                and self.error is None
            )
        elif self.result_type is RecordingRunnerResultType.CANCELLED:
            valid = (
                self.recording_state is RecordingState.CANCELLED
                and self.cleanup_status is RecordingCleanupStatus.SUCCEEDED
                and self.error is None
            )
        elif self.result_type is RecordingRunnerResultType.SAFETY_STOPPED:
            valid = (
                self.recording_state is RecordingState.SAFETY_STOPPED
                and self.cleanup_status is RecordingCleanupStatus.SUCCEEDED
                and self.error is None
                and bool(self.reason_codes)
            )
        else:
            valid = (
                self.recording_state is RecordingState.FAILED
                and self.error is not None
            )
        if not valid:
            raise ValueError("recording result violates lifecycle and cleanup matrix")
        return self


RecordingProtocolDocument: TypeAlias = (
    RecordingRunnerRequest | RecordingRunnerResult | RecordingEvent
)
RecordingProtocolT = TypeVar(
    "RecordingProtocolT",
    RecordingRunnerRequest,
    RecordingRunnerResult,
    RecordingEvent,
)


def canonical_recording_json_bytes(
    document: RecordingProtocolDocument,
    *,
    known_secrets: Sequence[str] = (),
) -> bytes:
    """生成 Recording 的唯一 UTF-8 JSON 表示并执行秘密扫描。"""

    if not isinstance(
        document,
        (RecordingRunnerRequest, RecordingRunnerResult, RecordingEvent),
    ):
        raise TypeError("recording canonical JSON requires a Recording document")
    data = document.model_dump(mode="json")
    _reject_known_secret_material(data, known_secrets)
    try:
        encoded = json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise JiejianError(
            ErrorCode.RECORD_PROTOCOL_INVALID,
            "录制协议无法规范序列化",
        ) from None
    maximum = (
        RECORDING_REQUEST_MAX_BYTES
        if isinstance(document, RecordingRunnerRequest)
        else RECORDING_RESULT_MAX_BYTES
        if isinstance(document, RecordingRunnerResult)
        else RECORDING_EVENT_MAX_BYTES
    )
    if len(encoded) > maximum:
        raise JiejianError(
            ErrorCode.RECORD_PROTOCOL_TOO_LARGE,
            "录制协议超过大小限制",
        )
    return encoded


def parse_recording_request(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> RecordingRunnerRequest:
    return _parse_recording_json(
        raw,
        RecordingRunnerRequest,
        RECORDING_REQUEST_MAX_BYTES,
        known_secrets,
    )


def parse_recording_result(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> RecordingRunnerResult:
    return _parse_recording_json(
        raw,
        RecordingRunnerResult,
        RECORDING_RESULT_MAX_BYTES,
        known_secrets,
    )


def parse_recording_event(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> RecordingEvent:
    return _parse_recording_json(
        raw,
        RecordingEvent,
        RECORDING_EVENT_MAX_BYTES,
        known_secrets,
    )


def _parse_recording_json(
    raw: bytes,
    model: type[RecordingProtocolT],
    maximum: int,
    known_secrets: Sequence[str],
) -> RecordingProtocolT:
    if not isinstance(raw, bytes):
        raise TypeError("recording protocol parser requires bytes")
    if len(raw) > maximum:
        raise JiejianError(ErrorCode.RECORD_PROTOCOL_TOO_LARGE, "录制协议超过大小限制")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError(ErrorCode.RECORD_PROTOCOL_INVALID, "录制协议不得包含 BOM")
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_non_finite,
        )
        expected_version = "1"
        if not isinstance(parsed, dict) or parsed.get("schema_version") != expected_version:
            raise JiejianError(ErrorCode.RECORD_PROTOCOL_INVALID, "录制协议版本不受支持")
        _reject_known_secret_material(parsed, known_secrets)
        return model.model_validate_json(raw, strict=True)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateKey, _NonFinite):
        raise JiejianError(ErrorCode.RECORD_PROTOCOL_INVALID, "录制协议不是严格 JSON") from None
    except ValidationError as exc:
        raise JiejianError(
            ErrorCode.RECORD_PROTOCOL_INVALID,
            "录制协议校验失败",
            details={
                "issue_count": exc.error_count(),
                "issue_types": tuple(issue["type"] for issue in exc.errors()[:64]),
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


def _reject_non_finite(_: str) -> None:
    raise _NonFinite


def _reject_known_secret_material(value: Any, known_secrets: Sequence[str]) -> None:
    if any(not isinstance(secret, str) for secret in known_secrets):
        raise TypeError("known_secrets must contain only strings")
    secrets = tuple(secret for secret in known_secrets if secret)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if any(secret in item for secret in secrets):
                raise JiejianError(
                    ErrorCode.RECORD_SECRET_EXPOSED,
                    "录制协议包含已知秘密",
                )
        elif isinstance(item, Mapping):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, Sequence) and not isinstance(item, (bytes, bytearray)):
            pending.extend(item)


def _reject_inline_secret_material(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            # 这些字段只保存经专用模型约束的认证元数据或 env:NAME 引用，不含正文。
            safe_auth_metadata = {"cookies", "bearer_ref", "value_ref", "secret_refs"}
            if str(key) not in safe_auth_metadata and _SENSITIVE_KEY.search(str(key)):
                raise ValueError("recording request contains persistent secret material")
            _reject_inline_secret_material(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_inline_secret_material(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("recording request contains non-finite data")
    elif isinstance(value, str) and _INLINE_SECRET.search(value):
        raise ValueError("recording request contains inline secret material")
