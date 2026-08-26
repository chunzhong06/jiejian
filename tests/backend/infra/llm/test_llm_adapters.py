# 验证多供应商模型适配器、动态目录与受控 HTTP 传输边界。

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from product.backend.infra.llm.adapters.base import LLMHttpResponse, LLMTransportError
from product.backend.infra.llm.adapters.deepseek import DeepSeekAdapter
from product.backend.infra.llm.adapters.gemini import GeminiAdapter
from product.backend.infra.llm.adapters.httpx_transport import HttpxLLMTransport
from product.backend.infra.llm.adapters.openai import OpenAIAdapter
from product.backend.infra.llm.adapters.openai_compatible import OpenAICompatibleAdapter
from product.backend.infra.llm.catalog import LLMModelCatalogService
from product.backend.infra.llm.config import LLMProfileConfig, LLMProviderType


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


def test_openai_uses_responses_and_final_message_only() -> None:
    request = OpenAIAdapter().build_request(_profile(LLMProviderType.OPENAI, model="gpt-5.6"), "secret", "ping", reasoning_effort="high")
    payload = json.loads(request.body)
    assert request.method == "POST"
    assert request.url == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == "Bearer secret"
    assert payload["store"] is False
    assert payload["reasoning"] == {"effort": "high"}
    response = LLMHttpResponse(200, json.dumps({"output": [{"type": "reasoning", "summary": "hidden"}, {"type": "message", "content": [{"type": "output_text", "text": "final"}]}]}).encode())
    assert OpenAIAdapter().parse_response(response) == "final"
    assert "secret" not in repr(request)


def test_deepseek_native_capability_and_reasoning_boundary() -> None:
    profile = _profile(LLMProviderType.DEEPSEEK, model="deepseek-v4-pro")
    request = DeepSeekAdapter().build_request(profile, "secret", "ping", reasoning_effort="max", json_schema={"type": "object"})
    payload = json.loads(request.body)
    assert request.url == "https://api.deepseek.com/chat/completions"
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "max"
    assert payload["response_format"] == {"type": "json_object"}
    response = LLMHttpResponse(200, b'{"choices":[{"message":{"reasoning_content":"hidden","content":"final"}}]}')
    assert DeepSeekAdapter().parse_response(response) == "final"
    with pytest.raises(LLMTransportError, match="invalid_request"):
        DeepSeekAdapter().build_request(profile, "secret", "ping", reasoning_effort="xhigh")

    flash_request = DeepSeekAdapter().build_request(
        _profile(
            LLMProviderType.DEEPSEEK,
            model="deepseek-v4-flash",
            max_output_bytes=65_536,
        ),
        "secret",
        "ping",
        reasoning_effort="high",
        json_schema={"type": "object", "additionalProperties": False},
    )
    flash_payload = json.loads(flash_request.body)
    assert flash_request.url == "https://api.deepseek.com/responses"
    assert flash_payload["reasoning"] == {"effort": "high"}
    assert flash_payload["max_output_tokens"] == 4_096
    assert flash_payload["text"]["format"] == {
        "type": "json_schema",
        "name": "jiejian_output",
        "schema": {"type": "object", "additionalProperties": False},
    }
    flash_response = LLMHttpResponse(200, json.dumps({
        "object": "response",
        "status": "completed",
        "error": None,
        "output": [
            {"type": "reasoning", "content": [{"type": "reasoning_text", "text": "hidden"}]},
            {"type": "message", "content": [{"type": "output_text", "text": "structured-final"}]},
        ],
    }).encode())
    assert DeepSeekAdapter().parse_response(flash_response) == "structured-final"


def test_gemini_filters_generate_content_and_thought_parts() -> None:
    request = GeminiAdapter().build_request(_profile(LLMProviderType.GEMINI, model="gemini-3.7-flash"), "secret", "ping", reasoning_effort="high")
    payload = json.loads(request.body)
    assert request.method == "POST"
    assert request.url.endswith("/models/gemini-3.7-flash:generateContent")
    assert "?key=" not in request.url
    assert request.headers["x-goog-api-key"] == "secret"
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "high"}
    response = LLMHttpResponse(200, b'{"candidates":[{"content":{"parts":[{"text":"hidden","thought":true},{"text":"final"}]}}]}')
    assert GeminiAdapter().parse_response(response) == "final"


def test_formal_adapters_reject_custom_endpoint_and_compatible_is_separate() -> None:
    with pytest.raises(ValueError):
        _profile(LLMProviderType.OPENAI, base_url="https://example.test")
    request = OpenAICompatibleAdapter(LLMProviderType.OPENAI_COMPATIBLE).build_request(
        _profile(LLMProviderType.OPENAI_COMPATIBLE, base_url="https://example.test/v1"), "s", "p"
    )
    assert request.url == "https://example.test/v1/chat/completions"


@pytest.mark.parametrize("status,kind", [(401, "auth_failed"), (429, "rate_limited"), (408, "timeout"), (500, "provider_unavailable")])
def test_provider_status_mapping_is_stable(status: int, kind: str) -> None:
    with pytest.raises(LLMTransportError) as captured:
        OpenAIAdapter().parse_response(LLMHttpResponse(status, b"bad"))
    assert captured.value.kind == kind


class _CatalogTransport:
    def __init__(self, responses: list[LLMHttpResponse]) -> None:
        self.responses = responses
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def test_catalog_parses_dynamic_models_and_compatible_missing_endpoint() -> None:
    transport = _CatalogTransport([LLMHttpResponse(200, b'{"data":[{"id":"gpt-5.6"},{"id":"custom"}]}')])
    catalog = LLMModelCatalogService(transport).discover(LLMProviderType.OPENAI, "secret")
    assert [item.model for item in catalog.models] == ["custom", "gpt-5.6"]
    assert next(item for item in catalog.models if item.model == "gpt-5.6").reasoning_options == ("none", "low", "medium", "high", "xhigh", "max")
    assert all("secret" not in repr(request) for request in transport.requests)
    deepseek = LLMModelCatalogService(_CatalogTransport([LLMHttpResponse(
        200,
        b'{"data":[{"id":"deepseek-v4-pro"},{"id":"deepseek-v4-flash"}]}',
    )])).discover(LLMProviderType.DEEPSEEK, "secret")
    assert {item.model: item.structured_output_mode for item in deepseek.models} == {
        "deepseek-v4-flash": "json_schema",
        "deepseek-v4-pro": "json_object",
    }
    fallback = LLMModelCatalogService(_CatalogTransport([LLMHttpResponse(404, b"missing")])).discover(
        LLMProviderType.OPENAI_COMPATIBLE, "secret", base_url="https://example.test"
    )
    assert fallback.manual_model_allowed is True

    unsafe_display = _CatalogTransport([
        LLMHttpResponse(200, b'{"data":[{"id":"safe-model","display_name":"unsafe\\nname"}]}')
    ])
    with pytest.raises(LLMTransportError) as captured:
        LLMModelCatalogService(unsafe_display).discover(LLMProviderType.OPENAI, "secret")
    assert captured.value.kind == "invalid_response"


def test_gemini_catalog_paginates_filters_and_rejects_bad_duplicate_ids() -> None:
    transport = _CatalogTransport([
        LLMHttpResponse(200, b'{"models":[{"name":"models/ignored","supportedGenerationMethods":["embedContent"]},{"name":"models/gemini-3.7-flash","displayName":"Flash","supportedGenerationMethods":["generateContent"]}],"nextPageToken":"next"}'),
        LLMHttpResponse(200, b'{"models":[{"baseModelId":"gemini-3.6-flash","supportedActions":["generateContent"]}]}'),
    ])
    catalog = LLMModelCatalogService(transport).discover(LLMProviderType.GEMINI, "secret")
    assert [item.model for item in catalog.models] == ["gemini-3.6-flash", "gemini-3.7-flash"]
    assert [request.method for request in transport.requests] == ["GET", "GET"]
    assert "secret" not in transport.requests[1].url
    duplicate = _CatalogTransport([LLMHttpResponse(200, b'{"data":[{"id":"same"},{"id":"same"}]}')])
    with pytest.raises(LLMTransportError) as captured:
        LLMModelCatalogService(duplicate).discover(LLMProviderType.OPENAI, "secret")
    assert captured.value.kind == "invalid_response"


def test_httpx_transport_uses_request_method_and_bounds_response() -> None:
    calls: list[httpx.Request] = []
    transport = HttpxLLMTransport(client_transport=httpx.MockTransport(lambda request: (calls.append(request) or httpx.Response(200, content=b"{}"))))
    request = OpenAICompatibleAdapter(LLMProviderType.OPENAI_COMPATIBLE).build_request(
        _profile(LLMProviderType.OPENAI_COMPATIBLE, base_url="https://example.test"), "secret", "ping"
    )
    transport.send(request)
    assert calls[0].method == "POST"
    bounded = HttpxLLMTransport(client_transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 1025)))
    with pytest.raises(LLMTransportError) as captured:
        bounded.send(request)
    assert captured.value.kind == "response_too_large"
