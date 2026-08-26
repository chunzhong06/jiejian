# =============================================================================
# FlowDraft 协议
#
# 定位
#   脱敏 Recording Event 与可执行 Verification Flow 之间的审阅数据边界
#
# 职责
#   表达 action/步骤/变量｜约束 TARGET 与资源确认｜提供规范 JSON 与稳定摘要
#
# 边界
#   推荐保持未确认状态；协议不执行 Flow，也不接受任意资源脚本或敏感值。
#
# 调用链
#   Recording processing / review ↔ FlowDraft → confirmed Verification Flow
# =============================================================================

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias
from urllib.parse import parse_qsl, urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from product.backend.core.identifiers import PROJECT_ID_PATTERN, RECORDING_ID_PATTERN
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.redaction import REDACTED
from product.protocols.web.workflow import ValueSlotConsumer

FLOW_DRAFT_MAX_BYTES = 4_194_304
FLOW_DRAFT_COMMAND_MAX_BYTES = 262_144

_ACTION_ID = r"^action_[0-9]{6}$"
_REQUEST_ID = r"^request_[0-9]{6}$"
_JSON_PATH = r"^\$(?:\.[A-Za-z_][A-Za-z0-9_-]*|\[[0-9]+\])*$|^\$location(?:\.[A-Za-z0-9_-]+)*$"
_SENSITIVE_FIELD = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|"
    r"api[_-]?key|id[_-]?card|ssn|email|phone|address|full[_-]?name)",
    re.IGNORECASE,
)


class FlowDraftProtocolModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )



class FlowDraftVariableStatus(StrEnum):
    INFERRED = "INFERRED"
    UNCONFIRMED = "UNCONFIRMED"
    CONFIRMED = "CONFIRMED"


class FlowDraftVariableSource(FlowDraftProtocolModel):
    source_step_id: str = Field(pattern=PROJECT_ID_PATTERN)
    source_event_sequence: int = Field(ge=1)
    json_path: str = Field(pattern=_JSON_PATH, max_length=512)


class FlowDraftVariable(FlowDraftProtocolModel):
    name: str = Field(pattern=PROJECT_ID_PATTERN)
    placeholder: str = Field(pattern=r"^\{[a-z][a-z0-9_-]{0,63}\}$")
    status: FlowDraftVariableStatus
    candidate_sources: tuple[FlowDraftVariableSource, ...] = Field(
        min_length=1,
        max_length=128,
    )
    confirmed_source: FlowDraftVariableSource | None = None
    consumer_step_ids: tuple[str, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_source_state(self) -> FlowDraftVariable:
        candidates = {
            (source.source_step_id, source.source_event_sequence, source.json_path)
            for source in self.candidate_sources
        }
        if len(candidates) != len(self.candidate_sources):
            raise ValueError("flow draft variable sources must be unique")
        if len(set(self.consumer_step_ids)) != len(self.consumer_step_ids):
            raise ValueError("flow draft variable consumers must be unique")
        expected_placeholder = "{" + self.name + "}"
        if self.placeholder != expected_placeholder:
            raise ValueError("flow draft variable placeholder must match its name")
        if self.status is FlowDraftVariableStatus.CONFIRMED:
            valid = self.confirmed_source is not None and (
                self.confirmed_source.source_step_id,
                self.confirmed_source.source_event_sequence,
                self.confirmed_source.json_path,
            ) in candidates
        else:
            valid = self.confirmed_source is None
        if not valid:
            raise ValueError("flow draft variable confirmation is inconsistent")
        return self


class FlowDraftResourceCandidate(FlowDraftProtocolModel):
    candidate_id: str = Field(pattern=r"^resource-[0-9a-f]{16}$")
    consumer: ValueSlotConsumer
    location: str = Field(min_length=1, max_length=512)
    label: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_resource_location(self) -> FlowDraftResourceCandidate:
        if self.consumer not in {
            ValueSlotConsumer.PATH,
            ValueSlotConsumer.QUERY,
            ValueSlotConsumer.JSON_BODY,
        }:
            raise ValueError("flow draft resource candidate location is unsupported")
        if self.consumer is ValueSlotConsumer.PATH:
            valid = re.fullmatch(r"path\[[0-9]{1,3}\]", self.location) is not None
        elif self.consumer is ValueSlotConsumer.QUERY:
            valid = re.fullmatch(r"query\.[A-Za-z0-9_.~-]{1,128}", self.location) is not None
        else:
            valid = re.fullmatch(_JSON_PATH, self.location) is not None
        if not valid:
            raise ValueError("flow draft resource candidate location is invalid")
        return self


class FlowDraftStep(FlowDraftProtocolModel):
    id: str = Field(pattern=PROJECT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=128)
    method: Literal["GET", "PATCH", "POST", "PUT", "DELETE"] | None = None
    path: str | None = Field(default=None, max_length=8_192)
    json_body: dict[str, Any] = Field(default_factory=dict)
    expected_statuses: tuple[int, ...] = Field(default=(), max_length=32)
    request_id: str | None = Field(default=None, pattern=_REQUEST_ID)
    source_event_sequences: tuple[int, ...] = Field(min_length=1, max_length=512)
    depends_on_step_ids: tuple[str, ...] = Field(default=(), max_length=128)
    sensitive_fields: tuple[str, ...] = Field(default=(), max_length=256)
    resource_candidates: tuple[FlowDraftResourceCandidate, ...] = Field(
        default=(),
        max_length=128,
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            not value.startswith("/")
            or value.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or any(segment in {".", ".."} for segment in parsed.path.split("/"))
        ):
            raise ValueError("flow draft path must be an absolute-path reference")
        for key, item in parse_qsl(parsed.query, keep_blank_values=True):
            if _SENSITIVE_FIELD.search(key) and item != REDACTED:
                raise ValueError("flow draft sensitive query value must be redacted")
        return value

    @model_validator(mode="after")
    def validate_step_boundary(self) -> FlowDraftStep:
        if tuple(sorted(set(self.source_event_sequences))) != self.source_event_sequences:
            raise ValueError("flow draft source sequences must be sorted and unique")
        if len(set(self.depends_on_step_ids)) != len(self.depends_on_step_ids):
            raise ValueError("flow draft dependencies must be unique")
        if len(set(self.sensitive_fields)) != len(self.sensitive_fields):
            raise ValueError("flow draft sensitive fields must be unique")
        if len({item.candidate_id for item in self.resource_candidates}) != len(
            self.resource_candidates
        ):
            raise ValueError("flow draft resource candidates must be unique")
        if self.method is None:
            request_valid = (
                self.path is None
                and self.request_id is None
                and not self.json_body
                and not self.expected_statuses
                and not self.resource_candidates
            )
        else:
            request_valid = (
                self.path is not None
                and self.request_id is not None
                and bool(self.expected_statuses)
            )
        if not request_valid:
            raise ValueError("flow draft HTTP step fields are inconsistent")
        _reject_unredacted_sensitive_values(self.json_body)
        return self


# Recording 事件生成的版本化审阅对象；未确认变量和绑定保持显式状态。
class FlowDraft(FlowDraftProtocolModel):
    schema_version: Literal["1"] = "1"
    recording_id: str = Field(pattern=RECORDING_ID_PATTERN)
    flow_id: str = Field(pattern=PROJECT_ID_PATTERN)
    action_candidate_id: str = Field(pattern=r"^action_[0-9a-f]{32}$")
    revision: int = Field(ge=1)
    steps: tuple[FlowDraftStep, ...] = Field(min_length=1, max_length=2_000)
    variables: tuple[FlowDraftVariable, ...] = Field(default=(), max_length=2_000)
    recommended_target_step_id: str | None = Field(
        default=None,
        pattern=PROJECT_ID_PATTERN,
    )
    target_step_id: str | None = Field(default=None, pattern=PROJECT_ID_PATTERN)
    resource_candidate_id: str | None = Field(
        default=None,
        pattern=r"^resource-[0-9a-f]{16}$",
    )

    @model_validator(mode="after")
    def validate_draft_graph(self) -> FlowDraft:
        step_ids = tuple(step.id for step in self.steps)
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("flow draft step IDs must be unique")
        known = set(step_ids)
        request_ids = tuple(
            step.request_id for step in self.steps if step.request_id is not None
        )
        if len(set(request_ids)) != len(request_ids):
            raise ValueError("flow draft causal IDs must be unique")
        graph = {step.id: set(step.depends_on_step_ids) for step in self.steps}
        if any(
            dependency not in known or dependency == step_id
            for step_id, dependencies in graph.items()
            for dependency in dependencies
        ):
            raise ValueError("flow draft dependency reference is invalid")
        variable_names = {variable.name for variable in self.variables}
        if len(variable_names) != len(self.variables):
            raise ValueError("flow draft variable names must be unique")
        if any(
            source.source_step_id not in known
            for variable in self.variables
            for source in variable.candidate_sources
        ) or any(
            consumer not in known
            for variable in self.variables
            for consumer in variable.consumer_step_ids
        ):
            raise ValueError("flow draft variable reference is invalid")
        if self.recommended_target_step_id is not None:
            recommended = next(
                (step for step in self.steps if step.id == self.recommended_target_step_id),
                None,
            )
            if recommended is None or recommended.method is None:
                raise ValueError("flow draft target recommendation is invalid")
        if self.target_step_id is None:
            if self.resource_candidate_id is not None:
                raise ValueError("flow draft resource cannot precede target confirmation")
        else:
            target = next((step for step in self.steps if step.id == self.target_step_id), None)
            if target is None or target.method is None:
                raise ValueError("flow draft confirmed target is invalid")
            candidate_ids = {item.candidate_id for item in target.resource_candidates}
            if (
                self.resource_candidate_id is not None
                and self.resource_candidate_id not in candidate_ids
            ):
                raise ValueError("flow draft resource candidate does not belong to target")
        _reject_cycles(graph)
        return self


class DeleteFlowDraftStep(FlowDraftProtocolModel):
    schema_version: Literal["1"] = "1"
    operation: Literal["DELETE_STEP"]
    step_id: str = Field(pattern=PROJECT_ID_PATTERN)


class MergeFlowDraftSteps(FlowDraftProtocolModel):
    schema_version: Literal["1"] = "1"
    operation: Literal["MERGE_ADJACENT_STEPS"]
    left_step_id: str = Field(pattern=PROJECT_ID_PATTERN)
    right_step_id: str = Field(pattern=PROJECT_ID_PATTERN)


class RenameFlowDraftStep(FlowDraftProtocolModel):
    schema_version: Literal["1"] = "1"
    operation: Literal["RENAME_STEP"]
    step_id: str = Field(pattern=PROJECT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=128)


class ConfirmFlowDraftVariable(FlowDraftProtocolModel):
    schema_version: Literal["1"] = "1"
    operation: Literal["CONFIRM_VARIABLE_SOURCE"]
    variable_name: str = Field(pattern=PROJECT_ID_PATTERN)
    source_event_sequence: int = Field(ge=1)
    source_json_path: str = Field(pattern=_JSON_PATH, max_length=512)


class ConfirmFlowDraftTarget(FlowDraftProtocolModel):
    schema_version: Literal["1"] = "1"
    operation: Literal["CONFIRM_TARGET_STEP"]
    step_id: str = Field(pattern=PROJECT_ID_PATTERN)


class ConfirmFlowDraftResource(FlowDraftProtocolModel):
    schema_version: Literal["1"] = "1"
    operation: Literal["CONFIRM_RESOURCE_SLOT"]
    candidate_id: str = Field(pattern=r"^resource-[0-9a-f]{16}$")


FlowDraftReviewCommand: TypeAlias = Annotated[
    DeleteFlowDraftStep
    | MergeFlowDraftSteps
    | RenameFlowDraftStep
    | ConfirmFlowDraftVariable
    | ConfirmFlowDraftTarget
    | ConfirmFlowDraftResource,
    Field(discriminator="operation"),
]
_COMMAND_ADAPTER = TypeAdapter(FlowDraftReviewCommand)
_COMMAND_TYPES = (
    DeleteFlowDraftStep,
    MergeFlowDraftSteps,
    RenameFlowDraftStep,
    ConfirmFlowDraftVariable,
    ConfirmFlowDraftTarget,
    ConfirmFlowDraftResource,
)


def canonical_flow_draft_json_bytes(
    document: FlowDraft | FlowDraftReviewCommand,
    *,
    known_secrets: Sequence[str] = (),
) -> bytes:
    """生成草稿或审阅命令的规范 JSON，并拒绝已知秘密。"""

    if not isinstance(document, (FlowDraft, *_COMMAND_TYPES)):
        raise TypeError("flow draft canonical JSON requires a current document")
    data = document.model_dump(mode="json")
    _reject_known_secrets(data, known_secrets)
    encoded = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    maximum = (
        FLOW_DRAFT_MAX_BYTES
        if isinstance(document, FlowDraft)
        else FLOW_DRAFT_COMMAND_MAX_BYTES
    )
    if len(encoded) > maximum:
        raise JiejianError(ErrorCode.RECORD_PROTOCOL_TOO_LARGE, "Flow 草稿协议超过大小限制")
    return encoded


def parse_flow_draft(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> FlowDraft:
    parsed = _strict_json(raw, FLOW_DRAFT_MAX_BYTES, known_secrets)
    if parsed.get("schema_version") != "1":
        raise JiejianError(ErrorCode.RECORD_PROTOCOL_INVALID, "Flow 草稿版本不受支持")
    try:
        return FlowDraft.model_validate_json(raw, strict=True)
    except ValidationError as exc:
        raise _validation_error(exc) from None


def parse_flow_draft_review_command(
    raw: bytes,
    *,
    known_secrets: Sequence[str] = (),
) -> FlowDraftReviewCommand:
    parsed = _strict_json(raw, FLOW_DRAFT_COMMAND_MAX_BYTES, known_secrets)
    if parsed.get("schema_version") != "1":
        raise JiejianError(ErrorCode.RECORD_PROTOCOL_INVALID, "Flow 审阅命令版本不受支持")
    try:
        return _COMMAND_ADAPTER.validate_json(raw, strict=True)
    except ValidationError as exc:
        raise _validation_error(exc) from None


def flow_draft_review_command_schema() -> dict[str, Any]:
    return _COMMAND_ADAPTER.json_schema()


class _DuplicateKey(ValueError):
    pass


class _NonFinite(ValueError):
    pass


def _strict_json(raw: bytes, maximum: int, known_secrets: Sequence[str]) -> Any:
    if not isinstance(raw, bytes):
        raise TypeError("flow draft parser requires bytes")
    if len(raw) > maximum:
        raise JiejianError(ErrorCode.RECORD_PROTOCOL_TOO_LARGE, "Flow 草稿协议超过大小限制")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise JiejianError(ErrorCode.RECORD_PROTOCOL_INVALID, "Flow 草稿协议不得包含 BOM")
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(_NonFinite()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateKey, _NonFinite):
        raise JiejianError(ErrorCode.RECORD_PROTOCOL_INVALID, "Flow 草稿协议不是严格 JSON") from None
    _reject_known_secrets(parsed, known_secrets)
    return parsed


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey
        result[key] = value
    return result


def _reject_known_secrets(value: Any, known_secrets: Sequence[str]) -> None:
    if any(not isinstance(secret, str) for secret in known_secrets):
        raise TypeError("known_secrets must contain only strings")
    secrets = tuple(secret for secret in known_secrets if secret)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str) and any(secret in item for secret in secrets):
            raise JiejianError(ErrorCode.RECORD_SECRET_EXPOSED, "Flow 草稿协议包含已知秘密")
        if isinstance(item, Mapping):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            pending.extend(item)


def _reject_unredacted_sensitive_values(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _SENSITIVE_FIELD.search(str(key)) and item != REDACTED:
                raise ValueError("flow draft sensitive JSON value must be redacted")
            _reject_unredacted_sensitive_values(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_unredacted_sensitive_values(item)


def _reject_cycles(graph: Mapping[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise ValueError("flow draft dependencies must be acyclic")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency in graph[step_id]:
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in graph:
        visit(step_id)


def _validation_error(exc: ValidationError) -> JiejianError:
    return JiejianError(
        ErrorCode.RECORD_PROTOCOL_INVALID,
        "Flow 草稿协议校验失败",
        details={
            "issue_count": exc.error_count(),
            "issue_types": tuple(issue["type"] for issue in exc.errors()[:64]),
        },
    )
