# 验证模型接入基础设施中的模型配置。

from __future__ import annotations

import pytest
from pydantic import ValidationError

import product.backend.infra.secrets.windows as secrets_module
from product.backend.infra.llm.config import (
    LLMProfileConfig,
    LLMProviderType,
    normalize_llm_base_url,
)
from product.backend.infra.secrets import WindowsCredentialManagerSecretStore


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


@pytest.mark.parametrize(
    "secret_ref",
    [
        "cred:",
        "cred:jiejian/llm/",
        "cred:jiejian/llm/a/b",
        "cred:jiejian/other/profile",
    ],
)
def test_credential_store_rejects_invalid_reference_before_win32(
    monkeypatch: pytest.MonkeyPatch, secret_ref: str
) -> None:
    monkeypatch.setattr(
        secrets_module,
        "_advapi32",
        lambda: (_ for _ in ()).throw(AssertionError("Win32 API must not be called")),
    )
    store = object.__new__(WindowsCredentialManagerSecretStore)
    with pytest.raises(ValueError):
        store.write(secret_ref, "secret")


def test_profile_is_strict_and_never_contains_a_secret_field() -> None:
    profile = _profile(provider=LLMProviderType.OPENAI_COMPATIBLE, base_url="HTTPS://Example.COM:443/v1/")
    assert profile.base_url == "https://example.com/v1/"
    assert "secret" not in profile.model_dump()
    with pytest.raises(ValidationError):
        _profile(unexpected=True)


def test_formal_provider_rejects_custom_endpoint_and_unknown_reasoning() -> None:
    with pytest.raises(ValidationError):
        _profile(base_url="https://example.com/v1")
    with pytest.raises(ValidationError):
        _profile(reasoning_effort="high")
    assert _profile(model="gpt-5.6", reasoning_effort="high").reasoning_effort == "high"


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
