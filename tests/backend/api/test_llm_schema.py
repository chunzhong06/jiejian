# 验证后端 API中的模型 Schema 边界。

from __future__ import annotations

from pydantic import ValidationError

from product.backend.api.routers.llm import (
    LLMProfileCreateRequest,
    LLMProfileUpdateRequest,
)
from product.backend.infra.llm.config import LLMProviderType


def test_llm_write_only_secret_is_not_serialized_or_represented() -> None:
    request = LLMProfileCreateRequest(
        schema_version="1",
        profile_name="local",
        provider=LLMProviderType.OPENAI,
        model="gpt-test",
        secret="not-a-real-secret",
    )
    dumped = request.model_dump(mode="json")
    assert "secret" not in dumped
    assert "not-a-real-secret" not in repr(request)


def test_llm_write_requests_carry_optional_reasoning_effort() -> None:
    create = LLMProfileCreateRequest(
        schema_version="1",
        profile_name="local",
        provider=LLMProviderType.OPENAI,
        model="gpt-5.6",
        reasoning_effort="high",
    )
    update = LLMProfileUpdateRequest(schema_version="1", reasoning_effort=None)
    assert create.reasoning_effort == "high"
    assert update.reasoning_effort is None


def test_llm_create_rejects_unknown_fields() -> None:
    try:
        LLMProfileCreateRequest(profile_name="local", provider="openai", model="gpt", key="x")
    except ValidationError:
        return
    raise AssertionError("unknown fields must be rejected")


def test_llm_dto_reuses_secret_and_url_security_validation() -> None:
    invalid_values = (
        {"secret_ref": "cred:other/name"},
        {"secret_ref": "cred:jiejian/llm/a/b"},
        {"base_url": "https://user:password@example.com/v1"},
        {"base_url": "https://example.com/v1?key=value"},
        {"base_url": "https://example.com/v1#fragment"},
        {"base_url": "ftp://example.com/v1"},
    )
    for updates in invalid_values:
        try:
            LLMProfileCreateRequest(
                schema_version="1",
                profile_name="local",
                provider="openai",
                model="gpt-test",
                **updates,
            )
        except ValidationError:
            pass
        else:
            raise AssertionError(f"invalid DTO value was accepted: {updates}")
    for updates in invalid_values:
        try:
            LLMProfileUpdateRequest(schema_version="1", **updates)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"invalid update value was accepted: {updates}")

    try:
        LLMProfileCreateRequest(
            profile_name="local",
            provider="openai",
            model="gpt-test",
            base_url="http://127.0.0.1:8080/v1",
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("local HTTP must require explicit authorization")

    update = LLMProfileUpdateRequest(
        schema_version="1",
        base_url="http://127.0.0.1:8080/v1",
        allow_local_http=None,
    )
    assert update.base_url == "http://127.0.0.1:8080/v1"
