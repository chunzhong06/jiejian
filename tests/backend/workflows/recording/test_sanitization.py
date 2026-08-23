from __future__ import annotations

from product.backend.workflows.recording.sanitization import RecordingSanitizer
from product.protocols import RecordingBudget


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
