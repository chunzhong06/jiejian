# 验证录制工作流中的录制数据清洗。

from __future__ import annotations
import json
import pytest

from product.backend.core.recording_sanitization import RecordingSanitizer
from product.protocols import RecordingBudget
from product.protocols import RecordingEvent, RecordingEventKind


def _sanitizer(secret: str) -> RecordingSanitizer:
    return RecordingSanitizer(
        RecordingBudget(
            max_duration_us=10_000_000,
            max_events=128,
            max_pages=4,
            max_contexts=2,
            max_field_chars=512,
            max_body_bytes=512,
            max_total_payload_bytes=65_536,
        ),
        (secret,),
    )


def test_known_secret_canary_is_removed_from_all_supported_fields() -> None:
    secret = "recording-known-secret-canary"
    sanitizer = _sanitizer(secret)

    url, _ = sanitizer.sanitize_url(
        f"https://example.test/{secret}?note={secret}&token={secret}#fragment"
    )
    headers, _ = sanitizer.sanitize_headers(
        {"X-Trace": secret, "Authorization": f"Bearer {secret}"}
    )
    body, _ = sanitizer.sanitize_body(
        f'{{"ordinary":"{secret}","nested":{{"path":"/{secret}"}}}}',
        "application/json",
    )

    encoded = "\n".join((url, *(header.value for header in headers), body or ""))
    assert secret not in encoded
    assert "[REDACTED]" in encoded


def test_unsafe_or_over_budget_body_never_returns_raw_content() -> None:
    sanitizer = _sanitizer("secret")

    unsafe, unsafe_omitted = sanitizer.sanitize_body_bytes(
        b"raw-secret-binary",
        "application/octet-stream",
    )
    oversized, oversized_omitted = sanitizer.sanitize_body(
        "x" * 513,
        "text/plain",
    )
    invalid_json, invalid_json_omitted = sanitizer.sanitize_body(
        '{"secret":',
        "application/json",
    )

    assert (unsafe, unsafe_omitted) == (None, True)
    assert (oversized, oversized_omitted) == (None, True)
    assert (invalid_json, invalid_json_omitted) == (None, True)


@pytest.mark.parametrize("content_type,body", [
    ("text/plain", "password=unknown-inline-canary"),
    ("text/html", '<script>const payload = {password:"unknown-inline-canary"};</script>'),
])
def test_unknown_inline_secret_body_is_omitted_without_event_failure(content_type, body):
    sanitized, truncated = _sanitizer("different-known-secret").sanitize_body(body, content_type)
    assert (sanitized, truncated) == (None, True)
    event = RecordingEvent(sequence=1, occurred_at_us=1, kind=RecordingEventKind.RESPONSE,
        identity_id="owner", body=sanitized, truncated=truncated)
    assert "unknown-inline-canary" not in event.model_dump_json()


def test_safe_text_and_json_keep_existing_redaction_contract():
    sanitizer = _sanitizer("known-canary")
    assert sanitizer.sanitize_body("业务完成", "text/plain") == ("业务完成", False)
    body, truncated = sanitizer.sanitize_body(
        '{"password":"unknown-canary","title":"保留业务字段","note":"known-canary"}', "application/json")
    assert truncated is False
    assert json.loads(body) == {"password": "[REDACTED]", "title": "保留业务字段", "note": "[REDACTED]"}
