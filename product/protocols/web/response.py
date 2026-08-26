# Web 响应提取、谓词匹配与结果分类模型。

from __future__ import annotations

import html.parser
import json
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, TypeAlias

from pydantic import Field, model_validator
from product.protocols.execution import ProtocolModel
from .request import (
    EmptyBody,
    FormUrlEncodedBody,
    JsonBody,
    MultipartBody,
    HTTP_JSON_PATH_MAX_DEPTH,
    HTTP_SELECTOR_MAX_LENGTH,
    HTTP_SLOT_MAX_LENGTH,
    HTTP_TEMPLATE_MAX_BYTES,
    HTTP_TEMPLATE_MAX_FIELDS,
    _CODE_MARKER,
    _IDENTIFIER,
    _SECRET_NAME,
    _validate_json_path,
    _validate_json_value,
    _validate_literal,
)

def _validate_selector(selector: str) -> str:
    if len(selector) > HTTP_SELECTOR_MAX_LENGTH or _CODE_MARKER.search(selector):
        raise ValueError("HTML selector must be bounded and non-executable")
    if re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_-]{0,31}(?:#[A-Za-z][A-Za-z0-9_-]{0,63}|\.[A-Za-z][A-Za-z0-9_-]{0,63}|\[[A-Za-z_:][A-Za-z0-9_.:-]{0,63}\])?",
        selector,
    ) is None:
        raise ValueError("HTML selector is outside the supported subset")
    return selector


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
