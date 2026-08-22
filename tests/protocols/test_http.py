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


@pytest.mark.parametrize(
    "path",
    ["$..items", "$.items[*]", "$.items[?(@.ok)]", "javascript:alert(1)"],
)
def test_response_predicates_reject_unbounded_json_or_code(path: str) -> None:
    with pytest.raises(ValidationError):
        HttpPredicate(kind=HttpPredicateKind.JSON_PATH_EXISTS, json_path=path)


def test_classifier_is_deterministic_for_business_denial_conflict_and_202() -> None:
    classifier = HttpOutcomeClassifier(
        accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(201, 202)),),
        denied=(
            HttpPredicate(kind=HttpPredicateKind.JSON_PATH_EQUALS, json_path="$.success", expected=False),
            HttpPredicate(kind=HttpPredicateKind.JSON_PATH_EQUALS, json_path="$.code", expected="FORBIDDEN"),
        ),
        completion_binding="job-status",
    )
    denied = {"status_code": 200, "headers": {}, "body": b'{"success":false,"code":"FORBIDDEN"}'}
    assert classifier.classify(denied) is HttpOutcome.DENIED
    conflict = {"status_code": 200, "headers": {}, "body": b'{"success":false,"code":"FORBIDDEN"}'}
    conflicting = classifier.model_copy(update={"accepted": (HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(200,)),)})
    assert conflicting.classify(conflict) is HttpOutcome.UNKNOWN
    pending = {"status_code": 202, "headers": {}, "body": b"{}"}
    assert classifier.classify(pending) is HttpOutcome.UNKNOWN
    assert classifier.classify(pending, terminal_completed=True) is HttpOutcome.ACCEPTED


def test_classifier_covers_header_redirect_html_and_literal_predicates() -> None:
    response = {
        "status_code": 302,
        "headers": {"X-Result": "ready", "Location": "/projects/1"},
        "body": b'<main><div id="state" data-phase="ready">done</div>secret</main>',
    }
    accepted = (
        HttpPredicate(kind=HttpPredicateKind.HEADER_EQUALS, header_name="x-result", expected="ready"),
        HttpPredicate(kind=HttpPredicateKind.REDIRECT_PATH_MATCHES, redirect_path="/projects/1"),
        HttpPredicate(kind=HttpPredicateKind.HTML_SELECTOR_EXISTS, selector="div#state"),
        HttpPredicate(kind=HttpPredicateKind.HTML_ATTRIBUTE_EQUALS, selector="div#state", attribute="data-phase", expected="ready"),
        HttpPredicate(kind=HttpPredicateKind.BODY_CONTAINS_LITERAL, literal="secret"),
    )
    assert HttpOutcomeClassifier(accepted=accepted).classify(response) is HttpOutcome.ACCEPTED


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


def test_http_template_schema_is_checked_in() -> None:
    schema = json.loads(
        (Path(__file__).parents[2] / "product/protocols/schemas/execution/http.schema.json").read_text(encoding="utf-8")
    )
    assert schema == HttpRequestTemplate.model_json_schema()
