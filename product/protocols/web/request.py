# Web 请求模板、ValueSlot 与受控请求体模型。

from __future__ import annotations


import math


import re


from collections.abc import Mapping, Sequence


from enum import StrEnum


from typing import Any, Literal, TypeAlias


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


def _validate_json_value(value: Any, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError("JSON body nesting exceeds the supported depth")
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > HTTP_SLOT_MAX_LENGTH:
            raise ValueError("JSON body string is too long")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON body cannot contain non-finite numbers")
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


class HttpRequestTemplate(ProtocolModel):
    """单请求受控模板；不接受 URL、脚本、任意文件或保留认证头。"""

    schema_version: Literal["1"] = "1"
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


__all__ = [name for name in globals() if not name.startswith("__")]
