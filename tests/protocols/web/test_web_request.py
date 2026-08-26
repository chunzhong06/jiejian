# 验证 Web request 模板、请求体预算与秘密字段边界。

from __future__ import annotations
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from product.protocols import (
    EmptyBody,
    HttpOutcome,
    HttpOutcomeClassifier,
    HttpParameter,
    HttpPredicate,
    HttpPredicateKind,
    HttpRequestTemplate,
    JsonBody,
    MultipartBody,
    MultipartPart,
    ResponseExtractor,
    ResponseExtractorKind,
    StaticHeaderCredential,
    StaticHeadersIdentityBinding,
    ValueSlot,
    ValueSlotConsumer,
    ValueSlotSource,
)

def test_request_template_is_bounded_and_rejects_reserved_headers() -> None:
    with pytest.raises(ValidationError):
        HttpRequestTemplate(
            method="POST",
            path="https://example.test/escape",
            headers=(HttpParameter(name="Authorization", literal="nope"),),
        )
    csrf = ValueSlot(
        slot_id="csrf",
        source=ValueSlotSource.PRIOR_STEP_HEADER,
        consumer=ValueSlotConsumer.HEADER,
        secret=True,
        source_path="$.csrf",
        producer_step=1,
        consumer_step=2,
    )
    template = HttpRequestTemplate(
        method="POST",
        path="/projects",
        headers=(HttpParameter(name="X-CSRF", slot_id="csrf"),),
        body=JsonBody(value={"name": {"$slot": "name"}}),
        input_slots=(csrf, ValueSlot(slot_id="name", source=ValueSlotSource.FIXED_LITERAL, consumer=ValueSlotConsumer.JSON_BODY, literal="demo")),
    )
    assert template.body.kind.value == "JSON"
    with pytest.raises(ValidationError):
        HttpRequestTemplate(
            method="POST",
            path="/projects",
            body=JsonBody(value={"name": {"$slot": "missing"}}),
        )

def test_multipart_rejects_arbitrary_file_path() -> None:
    with pytest.raises(ValidationError):
        MultipartPart(name="file", fixture_artifact_id=r"C:\private\secret.txt", filename="secret.txt")
    body = MultipartBody(parts=(MultipartPart(name="file", fixture_artifact_id="fixture-avatar", filename="avatar.txt"),))
    assert body.kind.value == "MULTIPART"

def test_secret_extractors_and_static_identity_headers_use_explicit_secret_boundaries() -> None:
    extractor = ResponseExtractor(
        extractor_id="csrf-token",
        kind=ResponseExtractorKind.HEADER,
        header_name="X-CSRF-Token",
        secret=True,
    )
    assert extractor.secret is True
    with pytest.raises(ValidationError):
        ResponseExtractor(
            extractor_id="csrf-token",
            kind=ResponseExtractorKind.HEADER,
            header_name="X-CSRF-Token",
        )
    binding = StaticHeadersIdentityBinding(
        headers=(StaticHeaderCredential(name="X-Api-Key", secret_ref="env:API_KEY"),),
    )
    assert binding.headers[0].secret_ref == "env:API_KEY"
