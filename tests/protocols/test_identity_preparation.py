# 验证测试身份准备 wire 文档严格往返且不承载登录秘密正文。

from __future__ import annotations

import json
from pathlib import Path

import pytest

from product.backend.core.test_identity import TestIdentityAuthMethod as IdentityAuthMethod
from product.protocols import (
    IdentityPreparationRequest,
    IdentityPreparationResult,
    IdentityPreparationResultType,
    PreparedCookieRef,
    canonical_identity_preparation_json_bytes,
    parse_identity_preparation_request,
    parse_identity_preparation_result,
)
from product.protocols.web.target import WebTargetScope


def _request() -> IdentityPreparationRequest:
    return IdentityPreparationRequest(
        schema_version="1",
        preparation_id="prep_0123456789abcdef0123456789abcdef",
        project_id="sample-project",
        identity_id="tid_0123456789abcdef0123456789abcdef",
        target_scope=WebTargetScope(
            base_url="http://127.0.0.1:8865",
            allowed_origins=("http://127.0.0.1:8865",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(8865,),
            allow_private_network=True,
        ),
    )


def test_identity_preparation_request_and_result_round_trip_without_secret() -> None:
    request = _request()
    assert parse_identity_preparation_request(
        canonical_identity_preparation_json_bytes(request)
    ) == request

    result = IdentityPreparationResult(
        schema_version="1",
        preparation_id=request.preparation_id,
        project_id=request.project_id,
        identity_id=request.identity_id,
        result_type=IdentityPreparationResultType.PREPARED,
        auth_method=IdentityAuthMethod.COOKIE_SESSION,
        cookies=(
            PreparedCookieRef(
                name="session",
                domain="127.0.0.1",
                path="/",
                secure=False,
                http_only=True,
                same_site="LAX",
                value_secret_ref=(
                    "cred:jiejian/test-identity/sample-project/"
                    "tid_0123456789abcdef0123456789abcdef/cookie-00"
                ),
            ),
        ),
        prepared_at_us=12,
    )
    raw = canonical_identity_preparation_json_bytes(result)
    assert b"session-secret-value" not in raw
    assert parse_identity_preparation_result(raw) == result


def test_prepared_result_rejects_secret_ref_from_another_identity() -> None:
    request = _request()
    with pytest.raises(ValueError):
        IdentityPreparationResult(
            schema_version="1",
            preparation_id=request.preparation_id,
            project_id=request.project_id,
            identity_id=request.identity_id,
            result_type=IdentityPreparationResultType.PREPARED,
            auth_method=IdentityAuthMethod.BEARER,
            bearer_secret_ref=(
                "cred:jiejian/test-identity/sample-project/"
                "tid_ffffffffffffffffffffffffffffffff/bearer"
            ),
            prepared_at_us=12,
        )


def test_checked_in_identity_preparation_schemas_have_no_drift() -> None:
    schema_root = (
        Path(__file__).parents[2] / "product/protocols/schemas/identity"
    )
    for name, model in (
        ("identity-preparation-request.schema.json", IdentityPreparationRequest),
        ("identity-preparation-result.schema.json", IdentityPreparationResult),
    ):
        checked_in = json.loads((schema_root / name).read_text(encoding="utf-8"))
        assert checked_in == model.model_json_schema()
