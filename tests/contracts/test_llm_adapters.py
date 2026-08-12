from __future__ import annotations

import json

import httpx
import pytest

from jiejian.contracts.llm.adapters.base import (
    LLMHttpResponse,
    LLMTransportError,
)
from jiejian.contracts.llm.adapters.gemini import GeminiAdapter
from jiejian.contracts.llm.adapters.httpx_transport import HttpxLLMTransport
from jiejian.contracts.llm.adapters.openai_compatible import OpenAICompatibleAdapter
from jiejian.contracts.llm.config import LLMProfileConfig, LLMProviderType


def _profile(provider: LLMProviderType, **updates: object) -> LLMProfileConfig:
    values: dict[str, object] = {
        "profile_name": "adapter-test",
        "provider": provider,
        "model": "model/name",
        "created_at_us": 1,
        "updated_at_us": 1,
        "max_output_bytes": 1024,
    }
    values.update(updates)
    return LLMProfileConfig(**values)


@pytest.mark.parametrize(
    "provider,base_url",
    [
        (LLMProviderType.OPENAI, "https://api.openai.com/v1"),
        (LLMProviderType.DEEPSEEK, "https://api.deepseek.com"),
        (LLMProviderType.OPENAI_COMPATIBLE, "https://example.test/v1"),
    ],
)
def test_openai_family_request_boundary(provider: LLMProviderType, base_url: str) -> None:
    profile = _profile(provider, base_url=base_url)
    request = OpenAICompatibleAdapter(provider).build_request(profile, "secret", "ping")
    payload = json.loads(request.body)
    assert request.url == f"{base_url}/chat/completions"
    assert request.headers["authorization"] == "Bearer secret"
    expected = {
        "messages": [{"role": "user", "content": "ping"}],
        "model": "model/name",
        "n": 1,
        "stream": False,
        "max_completion_tokens"
        if provider is LLMProviderType.OPENAI
        else "max_tokens": 256,
    }
    assert payload == expected
    assert "secret" not in request.url


def test_openai_compatible_requires_explicit_base_url() -> None:
    with pytest.raises(LLMTransportError) as captured:
        OpenAICompatibleAdapter(LLMProviderType.OPENAI_COMPATIBLE).build_request(
            _profile(LLMProviderType.OPENAI_COMPATIBLE, base_url=None), "s", "ping"
        )
    assert captured.value.kind == "invalid_request"


def test_gemini_request_and_response_boundary() -> None:
    profile = _profile(LLMProviderType.GEMINI)
    request = GeminiAdapter().build_request(profile, "secret", "ping")
    payload = json.loads(request.body)
    assert request.url.endswith("/models/model%2Fname:generateContent")
    assert request.headers["x-goog-api-key"] == "secret"
    assert "?key=" not in request.url
    assert payload == {
        "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
        "generationConfig": {"candidateCount": 1, "maxOutputTokens": 256},
    }
    assert GeminiAdapter().parse_response(
        LLMHttpResponse(
            200,
            json.dumps(
                {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
            ).encode(),
        )
    ) == "ok"


@pytest.mark.parametrize(
    "status,kind",
    [
        (401, "auth_failed"),
        (403, "auth_failed"),
        (429, "rate_limited"),
        (408, "timeout"),
        (504, "timeout"),
        (302, "provider_unavailable"),
        (500, "provider_unavailable"),
    ],
)
def test_provider_status_mapping_is_stable(status: int, kind: str) -> None:
    with pytest.raises(LLMTransportError) as captured:
        OpenAICompatibleAdapter(LLMProviderType.OPENAI).parse_response(
            LLMHttpResponse(status, b"bad")
        )
    assert captured.value.kind == kind


def test_httpx_transport_disables_redirects_and_bounds_streamed_response() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://other.test"})

    transport = HttpxLLMTransport(client_transport=httpx.MockTransport(handler))
    request = OpenAICompatibleAdapter(LLMProviderType.OPENAI).build_request(
        _profile(LLMProviderType.OPENAI), "secret", "ping"
    )
    response = transport.send(request)
    assert response.status_code == 302
    assert len(calls) == 1
    assert "authorization" in calls[0].headers

    def oversized(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1025)

    bounded = HttpxLLMTransport(client_transport=httpx.MockTransport(oversized))
    with pytest.raises(LLMTransportError) as captured:
        bounded.send(request)
    assert captured.value.kind == "response_too_large"
