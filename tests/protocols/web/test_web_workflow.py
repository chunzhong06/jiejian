# 验证 Web workflow 协议 Schema 与基线绑定边界。

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

def test_http_template_schema_is_checked_in() -> None:
    schema = json.loads(
            (Path(__file__).parents[3] / "product/protocols/schemas/execution/http.schema.json").read_text(encoding="utf-8")
    )
    assert schema == HttpRequestTemplate.model_json_schema()
