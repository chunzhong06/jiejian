# 验证 Web response 提取、谓词和结果分类边界。

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

@pytest.mark.parametrize("path", ["$..items", "$.items[*]", "$.items[?(@.ok)]", "javascript:alert(1)"])
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
