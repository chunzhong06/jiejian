from __future__ import annotations

import pytest
from pydantic import ValidationError

from product.backend.infra.llm.config import (
    LLMProfileConfig,
    LLMProviderType,
    normalize_llm_base_url,
)


def _profile(**updates: object) -> LLMProfileConfig:
    values: dict[str, object] = {
        "profile_name": "local-dev",
        "provider": LLMProviderType.OPENAI,
        "model": "gpt-test",
        "created_at_us": 10,
        "updated_at_us": 10,
        "secret_ref": "env:OPENAI_KEY",
    }
    values.update(updates)
    return LLMProfileConfig(**values)


def test_profile_is_strict_and_never_contains_a_secret_field() -> None:
    profile = _profile(base_url="HTTPS://Example.COM:443/v1/")
    assert profile.base_url == "https://example.com/v1/"
    assert "secret" not in profile.model_dump()
    with pytest.raises(ValidationError):
        _profile(unexpected=True)


@pytest.mark.parametrize(
    "value",
    [
        "https://user:password@example.com/v1",
        "http://192.0.2.1/v1",
        "https://example.com/v1#fragment",
        "https://example.com/v1?key=value",
    ],
)
def test_base_url_rejects_userinfo_insecure_http_and_non_endpoint_parts(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_llm_base_url(value, allow_local_http=False)


def test_local_http_requires_profile_and_loopback_authorization() -> None:
    with pytest.raises(ValueError):
        normalize_llm_base_url("http://127.0.0.1:80/v1", allow_local_http=False)
    assert normalize_llm_base_url("http://127.0.0.1:80/v1", allow_local_http=True) == "http://127.0.0.1/v1"
    with pytest.raises(ValueError):
        normalize_llm_base_url("http://[::1]:8080/v1", allow_local_http=False)
    assert normalize_llm_base_url("http://[::1]:8080/v1", allow_local_http=True) == "http://[::1]:8080/v1"


def test_credential_reference_is_stable_and_profile_bound() -> None:
    assert _profile(secret_ref="cred:jiejian/llm/local-dev").secret_ref == "cred:jiejian/llm/local-dev"
    with pytest.raises(ValidationError):
        _profile(secret_ref="cred:jiejian/llm/other")
    with pytest.raises(ValidationError):
        _profile(secret_ref="plain-secret")
