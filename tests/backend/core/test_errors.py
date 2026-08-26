# 验证核心领域中的错误模型。

from __future__ import annotations

import json

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.redaction import REDACTED


def test_jiejian_error_keeps_stable_external_structure() -> None:
    error = JiejianError(
        ErrorCode.CFG_INVALID,
        "配置无效",
        details={"field": "schema_version"},
    )

    assert error.code == ErrorCode.CFG_INVALID.value
    assert str(error) == "CFG_INVALID: 配置无效"
    assert error.to_dict() == {
        "code": "CFG_INVALID",
        "message": "配置无效",
        "details": {"field": "schema_version"},
    }


def test_jiejian_error_redacts_message_details_and_string_output() -> None:
    sentinel = "error-secret-value"
    error = JiejianError(
        "CUSTOM_ERROR",
        f"token={sentinel}",
        details={
            "password": sentinel,
            "nested": {"authorization": f"Bearer {sentinel}"},
        },
    )

    payload = error.to_dict()
    serialized = json.dumps(payload)
    assert error.code == "CUSTOM_ERROR"
    assert sentinel not in str(error)
    assert sentinel not in serialized
    assert payload["message"] == f"token={REDACTED}"
    assert payload["details"]["password"] == REDACTED
    assert payload["details"]["nested"]["authorization"] == REDACTED
