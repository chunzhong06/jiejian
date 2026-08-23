# =============================================================================
# Web Workflow 公共协议
#
# 定位
#   WebExecutionProfile 与 Web Adapter 之间的受控请求和分类边界。
#
# 职责
#   限定模板数据语言｜校验 Slot 与响应提取｜定义确定性结果谓词与基线模型
#
# 边界
#   不执行工作流、不解析秘密值、不保存 Cookie，也不把 HTTP 细节带入 Core
#   的 PermissionContract 或 Verification。
#
# 调用链
#   Profile / Runner snapshot → HttpRequestTemplate / classifier → HTTP adapter
# =============================================================================

from __future__ import annotations

import html.parser
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import Field, field_validator, model_validator

from product.protocols.execution import ProtocolModel


HTTP_TEMPLATE_MAX_BYTES = 262_144
HTTP_TEMPLATE_MAX_DEPTH = 8
HTTP_TEMPLATE_MAX_FIELDS = 128
HTTP_JSON_PATH_MAX_DEPTH = 8
HTTP_SELECTOR_MAX_LENGTH = 256
HTTP_LITERAL_MAX_LENGTH = 1024
HTTP_SLOT_MAX_LENGTH = 4096
CASE_SUBJECT_IDENTITY = "CASE_SUBJECT"

_IDENTIFIER = r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$"
_PATH = r"^/[A-Za-z0-9_./{}~:@%+\-]*$"
_SECRET_NAME = re.compile(r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key)", re.I)
_CODE_MARKER = re.compile(r"(?:^|[^A-Za-z])(eval|exec|javascript:|python:|shell:|\$\{|<%|%>)(?:$|[^A-Za-z])", re.I)
_JSON_PATH = re.compile(r"^\$(?:\.[A-Za-z_][A-Za-z0-9_-]{0,63}|\[(?:0|[1-9][0-9]{0,3})\]|\[[\"'][A-Za-z_][A-Za-z0-9_-]{0,63}[\"']\]){0,8}$")
_STEP_NUMBER = re.compile(r"(?:^|[^0-9])([0-9]{1,3})$")


class HttpBodyKind(StrEnum):
    EMPTY = "EMPTY"
    JSON = "JSON"
    FORM_URLENCODED = "FORM_URLENCODED"
    MULTIPART = "MULTIPART"


class ValueSlotSource(StrEnum):
    CASE_SUBJECT_ID = "CASE_SUBJECT_ID"
    CASE_RESOURCE_ID = "CASE_RESOURCE_ID"
    FIXED_LITERAL = "FIXED_LITERAL"
    SECRET_REF = "SECRET_REF"
    PRIOR_STEP_JSON_PATH = "PRIOR_STEP_JSON_PATH"
    PRIOR_STEP_HEADER = "PRIOR_STEP_HEADER"
    PRIOR_STEP_COOKIE = "PRIOR_STEP_COOKIE"
    PRIOR_STEP_LOCATION = "PRIOR_STEP_LOCATION"


class ValueSlotConsumer(StrEnum):
    PATH = "PATH"
    QUERY = "QUERY"
    HEADER = "HEADER"
    JSON_BODY = "JSON_BODY"
    FORM_FIELD = "FORM_FIELD"
    MULTIPART_FIELD = "MULTIPART_FIELD"


class ValueType(StrEnum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    JSON = "JSON"


class ResponseExtractorKind(StrEnum):
    JSON_PATH = "JSON_PATH"
    HEADER = "HEADER"
    COOKIE = "COOKIE"
    LOCATION = "LOCATION"
    HTML_SELECTOR = "HTML_SELECTOR"
    HTML_ATTRIBUTE = "HTML_ATTRIBUTE"


class HttpPredicateKind(StrEnum):
    STATUS_IN = "STATUS_IN"
    JSON_PATH_EXISTS = "JSON_PATH_EXISTS"
    JSON_PATH_EQUALS = "JSON_PATH_EQUALS"
    JSON_PATH_IN = "JSON_PATH_IN"
    HEADER_EXISTS = "HEADER_EXISTS"
    HEADER_EQUALS = "HEADER_EQUALS"
    REDIRECT_PATH_MATCHES = "REDIRECT_PATH_MATCHES"
    HTML_SELECTOR_EXISTS = "HTML_SELECTOR_EXISTS"
    HTML_ATTRIBUTE_EQUALS = "HTML_ATTRIBUTE_EQUALS"
    BODY_CONTAINS_LITERAL = "BODY_CONTAINS_LITERAL"


class HttpOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"


def _validate_json_path(value: str) -> str:
    if len(value) > 256 or _JSON_PATH.fullmatch(value) is None:
        raise ValueError("JSON path must be a finite simple path")
    if any(token in value for token in ("..", "*", "?", "(", ")", "@", "script")):
        raise ValueError("JSON path cannot contain wildcard, filter, or code")
    return value


def _validate_literal(value: str, *, label: str = "literal") -> str:
    if not value or len(value) > HTTP_LITERAL_MAX_LENGTH or _CODE_MARKER.search(value):
        raise ValueError(f"{label} must be bounded literal data")
    return value


def _step_index(value: str | None) -> int | None:
    if value is None:
        return None
    match = _STEP_NUMBER.search(value)
    return int(match.group(1)) if match else None


class ValueSlot(ProtocolModel):
    # Slot 是单模板内唯一允许的动态值引用；跨步骤 DAG 关系由工作流编译器继续校验。
    slot_id: str = Field(pattern=_IDENTIFIER)
    source: ValueSlotSource
    consumer: ValueSlotConsumer
    value_type: ValueType = ValueType.STRING
    max_length: int = Field(default=256, ge=1, le=HTTP_SLOT_MAX_LENGTH)
    secret: bool = False
    literal: Any = None
    secret_ref: str | None = Field(default=None, pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")
    source_path: str | None = Field(default=None, max_length=256)
    producer_step_id: str | None = Field(default=None, pattern=_IDENTIFIER)
    consumer_step_id: str | None = Field(default=None, pattern=_IDENTIFIER)
    producer_step: int | None = Field(default=None, ge=0, le=255)
    consumer_step: int | None = Field(default=None, ge=0, le=255)

    @model_validator(mode="after")
    def validate_slot(self) -> ValueSlot:
        if self.source is ValueSlotSource.SECRET_REF and not self.secret:
            raise ValueError("SECRET_REF slots must be secret")
        if self.source is ValueSlotSource.FIXED_LITERAL:
            if self.literal is None or self.secret_ref is not None:
                raise ValueError("FIXED_LITERAL slots require a literal and no secret ref")
            _validate_json_value(self.literal)
        elif self.source is ValueSlotSource.SECRET_REF:
            if self.secret_ref is None or self.literal is not None:
                raise ValueError("SECRET_REF slots require a secret ref and no literal")
        elif self.literal is not None or self.secret_ref is not None:
            raise ValueError("only fixed or secret slots may carry a source value")
        if self.secret and self.consumer is ValueSlotConsumer.PATH:
            raise ValueError("secret slots cannot be placed in a path")
        if self.source in {
            ValueSlotSource.PRIOR_STEP_JSON_PATH,
            ValueSlotSource.PRIOR_STEP_HEADER,
            ValueSlotSource.PRIOR_STEP_COOKIE,
            ValueSlotSource.PRIOR_STEP_LOCATION,
        } and self.producer_step_id is None and self.producer_step is None:
            raise ValueError("prior-step slots require a producer step")
        if self.source is ValueSlotSource.PRIOR_STEP_JSON_PATH:
            if self.source_path is None:
                raise ValueError("JSON response slots require source_path")
            _validate_json_path(self.source_path)
        elif self.source in {
            ValueSlotSource.PRIOR_STEP_HEADER,
            ValueSlotSource.PRIOR_STEP_COOKIE,
            ValueSlotSource.PRIOR_STEP_LOCATION,
        } and not self.source_path:
            raise ValueError("header, cookie, and location slots require source_path")
        if self.consumer_step is not None and self.producer_step is not None and self.producer_step >= self.consumer_step:
            raise ValueError("a slot cannot consume a future or current step")
        producer_index = _step_index(self.producer_step_id)
        consumer_index = _step_index(self.consumer_step_id)
        if producer_index is not None and consumer_index is not None and producer_index >= consumer_index:
            raise ValueError("a slot cannot consume a future or current step")
        return self


class HttpParameter(ProtocolModel):
    """受控 Query/Header/Form 字段；字段值只能是 literal 或已声明 Slot。"""

    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.~\-]+$")
    literal: str | None = Field(default=None, max_length=HTTP_LITERAL_MAX_LENGTH)
    slot_id: str | None = Field(default=None, pattern=_IDENTIFIER)

    @model_validator(mode="after")
    def validate_value(self) -> HttpParameter:
        if (self.literal is None) == (self.slot_id is None):
            raise ValueError("a parameter must contain exactly one literal or slot reference")
        if self.literal is not None:
            _validate_literal(self.literal)
        return self


class MultipartPart(ProtocolModel):
    """Multipart 只允许 literal、Slot 或已登记 fixture/artifact 标识。"""

    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.~\-]+$")
    literal: str | None = Field(default=None, max_length=HTTP_LITERAL_MAX_LENGTH)
    slot_id: str | None = Field(default=None, pattern=_IDENTIFIER)
    fixture_artifact_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.:-]{0,127}$")
    filename: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    content_type: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9!#$%&'*+.^_`|~-]*/[A-Za-z0-9][A-Za-z0-9!#$%&'*+.^_`|~-]*$")

    @model_validator(mode="after")
    def validate_source(self) -> MultipartPart:
        sources = (self.literal is not None, self.slot_id is not None, self.fixture_artifact_id is not None)
        if sum(sources) != 1:
            raise ValueError("multipart part must use exactly one controlled source")
        if self.literal is not None:
            _validate_literal(self.literal)
        if self.fixture_artifact_id is not None and self.filename is None:
            raise ValueError("fixture multipart parts require a safe filename")
        return self


class EmptyBody(ProtocolModel):
    kind: Literal[HttpBodyKind.EMPTY] = HttpBodyKind.EMPTY


class JsonBody(ProtocolModel):
    kind: Literal[HttpBodyKind.JSON] = HttpBodyKind.JSON
    value: Any

    @model_validator(mode="after")
    def validate_value(self) -> JsonBody:
        _validate_json_value(self.value)
        return self


class FormUrlEncodedBody(ProtocolModel):
    kind: Literal[HttpBodyKind.FORM_URLENCODED] = HttpBodyKind.FORM_URLENCODED
    fields: tuple[HttpParameter, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)


class MultipartBody(ProtocolModel):
    kind: Literal[HttpBodyKind.MULTIPART] = HttpBodyKind.MULTIPART
    parts: tuple[MultipartPart, ...] = Field(min_length=1, max_length=HTTP_TEMPLATE_MAX_FIELDS)


HttpBody: TypeAlias = EmptyBody | JsonBody | FormUrlEncodedBody | MultipartBody


class ResponseExtractor(ProtocolModel):
    extractor_id: str = Field(pattern=_IDENTIFIER)
    kind: ResponseExtractorKind
    json_path: str | None = None
    header_name: str | None = Field(default=None, max_length=128)
    cookie_name: str | None = Field(default=None, max_length=128)
    selector: str | None = Field(default=None, max_length=HTTP_SELECTOR_MAX_LENGTH)
    attribute: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z_:][A-Za-z0-9_.:-]{0,63}$")
    max_length: int = Field(default=256, ge=1, le=HTTP_SLOT_MAX_LENGTH)
    secret: bool = False

    @model_validator(mode="after")
    def validate_extractor(self) -> ResponseExtractor:
        if self.kind is ResponseExtractorKind.JSON_PATH:
            if self.json_path is None:
                raise ValueError("JSON_PATH extractor requires json_path")
            _validate_json_path(self.json_path)
        elif self.kind is ResponseExtractorKind.HEADER and not self.header_name:
            raise ValueError("HEADER extractor requires header_name")
        elif self.kind is ResponseExtractorKind.COOKIE:
            if not self.cookie_name:
                raise ValueError("COOKIE extractor requires cookie_name")
            if not self.secret:
                raise ValueError("COOKIE extractor must be secret")
        elif self.kind is ResponseExtractorKind.LOCATION and self.attribute is not None:
            raise ValueError("LOCATION extractor cannot have an attribute")
        elif self.kind is ResponseExtractorKind.HTML_SELECTOR and not self.selector:
            raise ValueError("HTML_SELECTOR extractor requires selector")
        elif self.kind is ResponseExtractorKind.HTML_ATTRIBUTE and (not self.selector or not self.attribute):
            raise ValueError("HTML_ATTRIBUTE extractor requires selector and attribute")
        if self.selector is not None:
            _validate_selector(self.selector)
        if self.header_name is not None and _SECRET_NAME.search(self.header_name) and not self.secret:
            raise ValueError("response secret headers must be explicitly classified as secret")
        return self


class HttpRequestTemplate(ProtocolModel):
    """单请求受控模板；不接受 URL、脚本、任意文件或保留认证头。"""

    method: Literal["GET", "PATCH", "POST", "PUT", "DELETE", "HEAD"]
    path: str = Field(min_length=1, max_length=2048, pattern=_PATH)
    query: tuple[HttpParameter, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)
    headers: tuple[HttpParameter, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)
    body: HttpBody = Field(default_factory=EmptyBody, discriminator="kind")
    input_slots: tuple[ValueSlot, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)
    response_extractors: tuple[ResponseExtractor, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)

    @field_validator("headers")
    @classmethod
    def reject_reserved_headers(cls, values: tuple[HttpParameter, ...]) -> tuple[HttpParameter, ...]:
        forbidden = {"host", "content-length", "transfer-encoding", "connection", "authorization", "cookie"}
        seen: set[str] = set()
        for item in values:
            name = item.name.lower()
            if name in forbidden or name.startswith("x-jiejian-"):
                raise ValueError("request template cannot provide reserved headers")
            if name in seen:
                raise ValueError("request template headers must be unique")
            if item.literal is not None and _SECRET_NAME.search(name):
                raise ValueError("static headers cannot contain secret material")
            seen.add(name)
        return values

    @model_validator(mode="after")
    def validate_references(self) -> HttpRequestTemplate:
        slots = {item.slot_id: item for item in self.input_slots}
        if len(slots) != len(self.input_slots):
            raise ValueError("input slot IDs must be unique")
        extractors = {item.extractor_id for item in self.response_extractors}
        if len(extractors) != len(self.response_extractors):
            raise ValueError("response extractor IDs must be unique")
        path_slots = re.findall(r"\{([A-Za-z][A-Za-z0-9_.:-]{0,63})\}", self.path)
        if len(set(path_slots)) != len(path_slots):
            raise ValueError("path slot references must be unique")
        for slot_id in path_slots:
            self._validate_slot(slot_id, slots, ValueSlotConsumer.PATH)
        self._validate_parameters(self.query, slots, ValueSlotConsumer.QUERY)
        self._validate_parameters(self.headers, slots, ValueSlotConsumer.HEADER)
        if isinstance(self.body, JsonBody):
            self._validate_json_slots(self.body.value, slots)
        elif isinstance(self.body, FormUrlEncodedBody):
            self._validate_parameters(self.body.fields, slots, ValueSlotConsumer.FORM_FIELD)
        elif isinstance(self.body, MultipartBody):
            for part in self.body.parts:
                if part.slot_id is not None:
                    self._validate_slot(part.slot_id, slots, ValueSlotConsumer.MULTIPART_FIELD)
        return self

    @staticmethod
    def _validate_parameters(values: Sequence[HttpParameter], slots: Mapping[str, ValueSlot], consumer: ValueSlotConsumer) -> None:
        for item in values:
            if item.slot_id is not None:
                HttpRequestTemplate._validate_slot(item.slot_id, slots, consumer)

    @staticmethod
    def _validate_slot(slot_id: str, slots: Mapping[str, ValueSlot], consumer: ValueSlotConsumer) -> None:
        slot = slots.get(slot_id)
        if slot is None:
            raise ValueError("template references an undeclared slot")
        if slot.consumer is not consumer:
            raise ValueError("slot consumer does not match its template field")

    @classmethod
    def _validate_json_slots(cls, value: Any, slots: Mapping[str, ValueSlot], depth: int = 0) -> None:
        if depth > HTTP_TEMPLATE_MAX_DEPTH:
            raise ValueError("JSON body exceeds maximum nesting depth")
        if isinstance(value, Mapping):
            if set(value) == {"$slot"}:
                slot_id = value["$slot"]
                if not isinstance(slot_id, str):
                    raise ValueError("JSON slot reference must be a string")
                cls._validate_slot(slot_id, slots, ValueSlotConsumer.JSON_BODY)
                return
            for key, child in value.items():
                if not isinstance(key, str) or len(key) > 128 or _CODE_MARKER.search(key):
                    raise ValueError("JSON body contains an invalid field name")
                cls._validate_json_slots(child, slots, depth + 1)
        elif isinstance(value, list):
            for child in value:
                cls._validate_json_slots(child, slots, depth + 1)


class HttpPredicate(ProtocolModel):
    kind: HttpPredicateKind
    statuses: tuple[int, ...] = Field(default=(), max_length=32)
    json_path: str | None = None
    header_name: str | None = None
    expected: Any = None
    values: tuple[Any, ...] = Field(default=(), max_length=32)
    redirect_path: str | None = None
    selector: str | None = None
    attribute: str | None = None
    literal: str | None = None

    @model_validator(mode="after")
    def validate_predicate(self) -> HttpPredicate:
        if self.kind is HttpPredicateKind.STATUS_IN:
            if not self.statuses or any(not 100 <= item <= 599 for item in self.statuses):
                raise ValueError("STATUS_IN requires bounded HTTP status codes")
        elif self.kind in {HttpPredicateKind.JSON_PATH_EXISTS, HttpPredicateKind.JSON_PATH_EQUALS, HttpPredicateKind.JSON_PATH_IN}:
            if self.json_path is None:
                raise ValueError("JSON predicate requires json_path")
            _validate_json_path(self.json_path)
            if self.kind is HttpPredicateKind.JSON_PATH_IN and not self.values:
                raise ValueError("JSON_PATH_IN requires values")
            if self.kind is HttpPredicateKind.JSON_PATH_EQUALS and self.expected is None:
                raise ValueError("JSON_PATH_EQUALS requires expected")
            if self.kind is HttpPredicateKind.JSON_PATH_EQUALS:
                _validate_json_value(self.expected)
            if self.kind is HttpPredicateKind.JSON_PATH_IN:
                for value in self.values:
                    _validate_json_value(value)
        elif self.kind is HttpPredicateKind.HEADER_EXISTS:
            if not self.header_name:
                raise ValueError("HEADER_EXISTS requires header_name")
        elif self.kind is HttpPredicateKind.HEADER_EQUALS:
            if not self.header_name or self.expected is None:
                raise ValueError("HEADER_EQUALS requires header_name and expected")
            _validate_literal(str(self.expected), label="header expectation")
        elif self.kind is HttpPredicateKind.REDIRECT_PATH_MATCHES:
            if not self.redirect_path or not self.redirect_path.startswith("/") or len(self.redirect_path) > 2048:
                raise ValueError("redirect path matcher must be a bounded relative path")
        elif self.kind is HttpPredicateKind.HTML_SELECTOR_EXISTS:
            if not self.selector:
                raise ValueError("HTML_SELECTOR_EXISTS requires selector")
            _validate_selector(self.selector)
        elif self.kind is HttpPredicateKind.HTML_ATTRIBUTE_EQUALS:
            if not self.selector or not self.attribute or self.expected is None:
                raise ValueError("HTML_ATTRIBUTE_EQUALS requires selector, attribute, and expected")
            _validate_selector(self.selector)
            _validate_literal(str(self.expected), label="HTML attribute expectation")
        elif self.kind is HttpPredicateKind.BODY_CONTAINS_LITERAL:
            if self.literal is None:
                raise ValueError("BODY_CONTAINS_LITERAL requires literal")
            _validate_literal(self.literal)
        return self


class HttpOutcomeClassifier(ProtocolModel):
    accepted: tuple[HttpPredicate, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)
    denied: tuple[HttpPredicate, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)
    # completion_binding is only a declaration; the adapter must provide the observed terminal fact.
    completion_binding: str | None = Field(default=None, pattern=_IDENTIFIER)

    def classify(
        self,
        response: Any,
        *,
        terminal_completed: bool | None = None,
    ) -> HttpOutcome:
        status, headers, body, location = _response_parts(response)
        accepted = any(_predicate_matches(item, status, headers, body, location) for item in self.accepted)
        denied = any(_predicate_matches(item, status, headers, body, location) for item in self.denied)
        if status == 202 and not (self.completion_binding and terminal_completed is True):
            accepted = False
        if accepted == denied:
            return HttpOutcome.UNKNOWN
        return HttpOutcome.ACCEPTED if accepted else HttpOutcome.DENIED


class WorkflowStepPurpose(StrEnum):
    SETUP = "SETUP"
    TARGET = "TARGET"
    CLEANUP = "CLEANUP"


class WorkflowFailurePolicy(StrEnum):
    INCONCLUSIVE = "INCONCLUSIVE"
    STOP = "STOP"


class ResetStrategyKind(StrEnum):
    RESET_ENDPOINT = "RESET_ENDPOINT"
    UNIQUE_RESOURCE_WORKFLOW = "UNIQUE_RESOURCE_WORKFLOW"
    SNAPSHOT_PROVIDER = "SNAPSHOT_PROVIDER"


class BaselineIntegrityMode(StrEnum):
    EXACT_RESTORE = "EXACT_RESTORE"
    NORMALIZED_EQUIVALENCE = "NORMALIZED_EQUIVALENCE"


class LogicalResourceSlot(ProtocolModel):
    slot_id: str = Field(pattern=_IDENTIFIER)
    logical_resource_handle: str = Field(pattern=_IDENTIFIER)
    value_type: ValueType = ValueType.STRING
    max_length: int = Field(default=256, ge=1, le=HTTP_SLOT_MAX_LENGTH)
    secret: Literal[False] = False


class BaselineProjection(ProtocolModel):
    projection_id: str = Field(pattern=_IDENTIFIER)
    logical_resource_handle: str = Field(pattern=_IDENTIFIER)
    normalization_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,3}$")
    projection_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,3}$")
    required: bool = True
    expected_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    integrity_mode: BaselineIntegrityMode = BaselineIntegrityMode.EXACT_RESTORE


class ResetEndpointStrategy(ProtocolModel):
    kind: Literal[ResetStrategyKind.RESET_ENDPOINT] = ResetStrategyKind.RESET_ENDPOINT
    path: str = Field(pattern=_PATH)


class UniqueResourceWorkflowResetStrategy(ProtocolModel):
    kind: Literal[ResetStrategyKind.UNIQUE_RESOURCE_WORKFLOW] = ResetStrategyKind.UNIQUE_RESOURCE_WORKFLOW
    workflow_id: str = Field(pattern=_IDENTIFIER)


class SnapshotProviderResetStrategy(ProtocolModel):
    kind: Literal[ResetStrategyKind.SNAPSHOT_PROVIDER] = ResetStrategyKind.SNAPSHOT_PROVIDER
    provider_ref: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,127}$")


ResetStrategy: TypeAlias = Annotated[
    ResetEndpointStrategy | UniqueResourceWorkflowResetStrategy | SnapshotProviderResetStrategy,
    Field(discriminator="kind"),
]


class BaselineFingerprint(ProtocolModel):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    logical_resource_handle: str = Field(pattern=_IDENTIFIER)
    normalized_resource_state: str = Field(min_length=1, max_length=4096)
    workflow_state: str = Field(min_length=1, max_length=1024)
    relationship_projection: str = Field(min_length=1, max_length=4096)
    effect_projection: str = Field(min_length=1, max_length=4096)
    normalization_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,3}$")
    projection_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,3}$")


class BaselineIntegrity(ProtocolModel):
    mode: BaselineIntegrityMode
    expected_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    observed_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    valid: bool
    reason_codes: tuple[str, ...] = Field(default=(), max_length=16)


# 单个冻结业务请求；身份 Bootstrap 不属于这里的工作流步骤。
class HttpWorkflowStep(ProtocolModel):
    id: str = Field(pattern=_IDENTIFIER)
    purpose: WorkflowStepPurpose
    identity_id: str = Field(min_length=1, max_length=64)
    request_template: HttpRequestTemplate
    classifier: HttpOutcomeClassifier = Field(default_factory=HttpOutcomeClassifier)
    input_slots: tuple[ValueSlot, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)
    output_extractors: tuple[ResponseExtractor, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)
    depends_on_step_ids: tuple[str, ...] = Field(default=(), max_length=HTTP_TEMPLATE_MAX_FIELDS)
    failure_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.INCONCLUSIVE

    @model_validator(mode="after")
    def validate_step(self) -> HttpWorkflowStep:
        if self.identity_id != CASE_SUBJECT_IDENTITY and re.fullmatch(_IDENTIFIER, self.identity_id) is None:
            raise ValueError("workflow step identity must be CASE_SUBJECT or a declared identity ID")
        if len(set(self.depends_on_step_ids)) != len(self.depends_on_step_ids):
            raise ValueError("workflow step dependencies must be unique")
        template_slots = {item.slot_id: item for item in self.request_template.input_slots}
        step_slots = {item.slot_id: item for item in self.input_slots}
        if step_slots and template_slots and step_slots != template_slots:
            raise ValueError("step input slots must match request template slots")
        if not template_slots and step_slots:
            object.__setattr__(self, "request_template", self.request_template.model_copy(update={"input_slots": self.input_slots}))
        elif template_slots:
            object.__setattr__(self, "input_slots", tuple(template_slots.values()))
        template_extractors = {item.extractor_id: item for item in self.request_template.response_extractors}
        step_extractors = {item.extractor_id: item for item in self.output_extractors}
        if step_extractors and template_extractors and step_extractors != template_extractors:
            raise ValueError("step output extractors must match request template extractors")
        if not template_extractors and step_extractors:
            object.__setattr__(self, "request_template", self.request_template.model_copy(update={"response_extractors": self.output_extractors}))
        elif template_extractors:
            object.__setattr__(self, "output_extractors", tuple(template_extractors.values()))
        return self


# 单一当前状态化 HTTP 执行资产，指纹只覆盖不含秘密的冻结结构。
class HttpWorkflowBinding(ProtocolModel):
    workflow_id: str = Field(pattern=_IDENTIFIER)
    source_flow_id: str = Field(pattern=_IDENTIFIER)
    action_id: str = Field(pattern=_IDENTIFIER)
    steps: tuple[HttpWorkflowStep, ...] = Field(min_length=1, max_length=256)
    target_step_id: str = Field(pattern=_IDENTIFIER)
    logical_resource_slots: tuple[LogicalResourceSlot, ...] = Field(default=(), max_length=128)
    baseline_projections: tuple[BaselineProjection, ...] = Field(default=(), max_length=128)
    reset_strategy: ResetStrategy = Field(default_factory=lambda: ResetEndpointStrategy(path="/reset"), discriminator="kind")
    workflow_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_workflow(self) -> HttpWorkflowBinding:
        step_ids = tuple(step.id for step in self.steps)
        if len(set(step_ids)) != len(step_ids) or self.target_step_id not in set(step_ids):
            raise ValueError("workflow step IDs and target_step_id are inconsistent")
        targets = [step for step in self.steps if step.purpose is WorkflowStepPurpose.TARGET]
        if len(targets) != 1 or targets[0].id != self.target_step_id:
            raise ValueError("workflow must contain exactly one TARGET step")
        if len({slot.slot_id for slot in self.logical_resource_slots}) != len(self.logical_resource_slots):
            raise ValueError("logical resource slots must be unique")
        if len({item.projection_id for item in self.baseline_projections}) != len(self.baseline_projections):
            raise ValueError("baseline projections must be unique")
        graph = {step.id: set(step.depends_on_step_ids) for step in self.steps}
        if any(dependency not in graph or dependency == step_id for step_id, dependencies in graph.items() for dependency in dependencies):
            raise ValueError("workflow dependency reference is invalid")
        visiting: set[str] = set()
        visited: set[str] = set()
        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("workflow dependencies must be acyclic")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in graph[step_id]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)
        for step_id in step_ids:
            visit(step_id)
        for step in self.steps:
            for slot in step.input_slots:
                if slot.producer_step_id is not None:
                    if slot.producer_step_id not in graph or slot.producer_step_id not in _transitive_dependencies(graph, step.id):
                        raise ValueError("slot producer must be a declared prior dependency")
                    if slot.secret and graph[slot.producer_step_id] is not None:
                        producer = next(item for item in self.steps if item.id == slot.producer_step_id)
                        if producer.identity_id != step.identity_id:
                            raise ValueError("secret slots cannot cross identities")
        fingerprint = _workflow_fingerprint(self)
        if self.workflow_fingerprint is not None and self.workflow_fingerprint != fingerprint:
            raise ValueError("workflow fingerprint does not match frozen binding")
        object.__setattr__(self, "workflow_fingerprint", fingerprint)
        return self


def _transitive_dependencies(graph: Mapping[str, set[str]], step_id: str) -> set[str]:
    found: set[str] = set()
    pending = list(graph[step_id])
    while pending:
        dependency = pending.pop()
        if dependency in found:
            continue
        found.add(dependency)
        pending.extend(graph[dependency])
    return found


def _workflow_fingerprint(binding: HttpWorkflowBinding) -> str:
    payload = binding.model_dump(mode="json", exclude={"workflow_fingerprint"})
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_baseline_fingerprint(
    *,
    logical_resource_handle: str,
    normalized_resource_state: str,
    workflow_state: str,
    relationship_projection: str,
    effect_projection: str,
    normalization_version: str,
    projection_version: str,
) -> BaselineFingerprint:
    payload = {
        "logical_resource_handle": logical_resource_handle,
        "normalized_resource_state": normalized_resource_state,
        "workflow_state": workflow_state,
        "relationship_projection": relationship_projection,
        "effect_projection": effect_projection,
        "normalization_version": normalization_version,
        "projection_version": projection_version,
    }
    fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return BaselineFingerprint(fingerprint=fingerprint, **payload)


def _validate_json_value(value: Any, depth: int = 0) -> None:
    if depth > HTTP_TEMPLATE_MAX_DEPTH:
        raise ValueError("JSON body exceeds maximum nesting depth")
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and (len(value) > HTTP_LITERAL_MAX_LENGTH or _CODE_MARKER.search(value)):
            raise ValueError("JSON body contains code or oversized template data")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON body contains a non-finite number")
        return
    if isinstance(value, Mapping):
        if len(value) > HTTP_TEMPLATE_MAX_FIELDS:
            raise ValueError("JSON body contains too many fields")
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 128 or _CODE_MARKER.search(key):
                raise ValueError("JSON body contains an invalid field name")
            if set(value) == {"$slot"}:
                if not isinstance(child, str) or re.fullmatch(_IDENTIFIER, child) is None:
                    raise ValueError("JSON slot reference is invalid")
            else:
                _validate_json_value(child, depth + 1)
        return
    if isinstance(value, list):
        if len(value) > HTTP_TEMPLATE_MAX_FIELDS:
            raise ValueError("JSON body contains too many items")
        for child in value:
            _validate_json_value(child, depth + 1)
        return
    raise ValueError("JSON body only supports finite JSON values")


def _validate_selector(selector: str) -> str:
    if len(selector) > HTTP_SELECTOR_MAX_LENGTH or _CODE_MARKER.search(selector):
        raise ValueError("HTML selector must be bounded and non-executable")
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}(?:#[A-Za-z][A-Za-z0-9_-]{0,63}|\.[A-Za-z][A-Za-z0-9_-]{0,63}|\[[A-Za-z_:][A-Za-z0-9_.:-]{0,63}\])?", selector) is None:
        raise ValueError("HTML selector is outside the supported subset")
    return selector


def _response_parts(response: Any) -> tuple[int, Mapping[str, str], bytes, str | None]:
    status = int(response.status_code if hasattr(response, "status_code") else response["status_code"])
    raw_headers = response.headers if hasattr(response, "headers") else response.get("headers", {})
    headers = {str(key).lower(): str(value) for key, value in raw_headers.items()}
    if hasattr(response, "body") and response.body:
        body = response.body if isinstance(response.body, bytes) else str(response.body).encode("utf-8")
    elif hasattr(response, "data"):
        data = response.data
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8") if isinstance(data, (dict, list)) else str(data).encode("utf-8")
    else:
        raw_body = response.get("body", b"")
        body = raw_body if isinstance(raw_body, bytes) else str(raw_body).encode("utf-8")
    return status, headers, body, headers.get("location")


def _predicate_matches(predicate: HttpPredicate, status: int, headers: Mapping[str, str], body: bytes, location: str | None) -> bool:
    text = body.decode("utf-8", errors="replace")
    if predicate.kind is HttpPredicateKind.STATUS_IN:
        return status in predicate.statuses
    if predicate.kind in {HttpPredicateKind.JSON_PATH_EXISTS, HttpPredicateKind.JSON_PATH_EQUALS, HttpPredicateKind.JSON_PATH_IN}:
        try:
            current: Any = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        assert predicate.json_path is not None
        found, current = _read_json_path(current, predicate.json_path)
        if not found:
            return False
        if predicate.kind is HttpPredicateKind.JSON_PATH_EXISTS:
            return True
        if predicate.kind is HttpPredicateKind.JSON_PATH_EQUALS:
            return current == predicate.expected
        return current in predicate.values
    if predicate.kind is HttpPredicateKind.HEADER_EXISTS:
        assert predicate.header_name is not None
        return predicate.header_name.lower() in headers
    if predicate.kind is HttpPredicateKind.HEADER_EQUALS:
        assert predicate.header_name is not None
        return headers.get(predicate.header_name.lower()) == str(predicate.expected)
    if predicate.kind is HttpPredicateKind.REDIRECT_PATH_MATCHES:
        return location is not None and _safe_path_match(location.split("?", 1)[0].split("#", 1)[0], predicate.redirect_path or "")
    if predicate.kind is HttpPredicateKind.BODY_CONTAINS_LITERAL:
        assert predicate.literal is not None
        return predicate.literal in text
    return _html_matches(text, predicate)


def _read_json_path(value: Any, path: str) -> tuple[bool, Any]:
    if path == "$":
        return True, value
    current = value
    tokens = re.findall(r"\.([A-Za-z_][A-Za-z0-9_-]{0,63})|\[(?:[\"']([^\"']+)[\"']|([0-9]{1,4}))\]", path[1:])
    if len(tokens) > HTTP_JSON_PATH_MAX_DEPTH:
        return False, None
    for dotted, quoted, indexed in tokens:
        key: str | int = dotted or quoted or indexed
        if isinstance(current, Mapping):
            if key not in current:
                return False, None
            current = current[key]
        elif isinstance(current, list) and indexed is not None:
            index = int(indexed)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def _safe_path_match(actual: str, expected: str) -> bool:
    actual_parts = actual.split("/")
    expected_parts = expected.split("/")
    if len(actual_parts) != len(expected_parts):
        return False
    return all(
        actual_part != "" and re.fullmatch(r"\{[A-Za-z][A-Za-z0-9_.:-]{0,63}\}", expected_part)
        or actual_part == expected_part
        for actual_part, expected_part in zip(actual_parts, expected_parts, strict=True)
    )


class _HtmlProbe(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes.append((tag.lower(), {name.lower(): value or "" for name, value in attrs}))


def _html_matches(text: str, predicate: HttpPredicate) -> bool:
    probe = _HtmlProbe()
    try:
        probe.feed(text[:HTTP_TEMPLATE_MAX_BYTES])
    except (ValueError, AssertionError):
        return False
    selector = predicate.selector or ""
    match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*)(?:#([A-Za-z][A-Za-z0-9_-]*)|\.([A-Za-z][A-Za-z0-9_-]*)|\[([A-Za-z_:][A-Za-z0-9_.:-]*)\])?", selector)
    if match is None:
        return False
    tag, node_id, node_class, required_attr = match.groups()
    for node_tag, attrs in probe.nodes:
        if node_tag != tag.lower():
            continue
        if node_id and attrs.get("id") != node_id:
            continue
        if node_class and node_class not in attrs.get("class", "").split():
            continue
        if required_attr and required_attr.lower() not in attrs:
            continue
        if predicate.kind is HttpPredicateKind.HTML_ATTRIBUTE_EQUALS:
            assert predicate.attribute is not None
            if attrs.get(predicate.attribute.lower()) != str(predicate.expected):
                continue
        return True
    return False


# 给调用方保留直观别名，实际协议仍只有一组模型定义。
