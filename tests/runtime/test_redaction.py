from __future__ import annotations

import json

from product.backend.core.redaction import REDACTED, redact


def test_redaction_removes_secret_keys_and_inline_values() -> None:
    sentinel = "top-secret-value"
    payload = {
        "password": sentinel,
        "nested": {
            "api_key": sentinel,
            "authorization": f"Bearer {sentinel}",
            "message": f"token={sentinel}",
        },
        "safe": "visible",
    }

    result = redact(payload)
    serialized = json.dumps(result)

    assert sentinel not in serialized
    assert result["password"] == REDACTED
    assert result["safe"] == "visible"
