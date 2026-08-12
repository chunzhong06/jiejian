"""OpenAI、DeepSeek 和 OpenAI-compatible Chat Completions 适配器。"""

from __future__ import annotations

import json
from typing import Any

from ..config import LLMProfileConfig, LLMProviderType, normalize_llm_base_url
from .base import (
    LLMAdapter,
    LLMHttpRequest,
    LLMHttpResponse,
    LLMTransportError,
    json_body,
    max_output_tokens,
)


DEFAULT_BASE_URLS = {
    LLMProviderType.OPENAI: "https://api.openai.com/v1",
    LLMProviderType.DEEPSEEK: "https://api.deepseek.com",
}


class OpenAICompatibleAdapter:
    def __init__(self, provider: LLMProviderType) -> None:
        if provider not in {
            LLMProviderType.OPENAI,
            LLMProviderType.DEEPSEEK,
            LLMProviderType.OPENAI_COMPATIBLE,
        }:
            raise ValueError("provider is not OpenAI-compatible")
        self.provider = provider

    def build_request(
        self,
        profile: LLMProfileConfig,
        secret: str,
        prompt: str,
    ) -> LLMHttpRequest:
        base_url = profile.base_url or DEFAULT_BASE_URLS.get(self.provider)
        if base_url is None:
            raise LLMTransportError("invalid_request")
        if self.provider is LLMProviderType.OPENAI_COMPATIBLE and profile.base_url is None:
            raise LLMTransportError("invalid_request")
        normalized = normalize_llm_base_url(
            base_url,
            allow_local_http=profile.allow_local_http,
        )
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "model": profile.model,
            "n": 1,
            "stream": False,
        }
        payload[
            "max_completion_tokens"
            if self.provider is LLMProviderType.OPENAI
            else "max_tokens"
        ] = max_output_tokens(profile)
        body = json_body(payload)
        return LLMHttpRequest(
            provider=self.provider,
            url=f"{normalized.rstrip('/')}/chat/completions",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {secret}",
                "content-type": "application/json",
            },
            body=body,
            timeout_ms=profile.timeout_ms,
            max_output_bytes=profile.max_output_bytes,
        )

    def parse_response(self, response: LLMHttpResponse) -> str:
        _raise_for_status(response.status_code)
        payload = _parse_json(response.body)
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise LLMTransportError("invalid_response")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMTransportError("invalid_response")
        return content


def _parse_json(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise LLMTransportError("invalid_response") from None
    if not isinstance(value, dict):
        raise LLMTransportError("invalid_response")
    return value


def _raise_for_status(status_code: int) -> None:
    if status_code in {401, 403}:
        raise LLMTransportError("auth_failed")
    if status_code == 429:
        raise LLMTransportError("rate_limited")
    if status_code in {408, 504}:
        raise LLMTransportError("timeout")
    if 300 <= status_code < 400 or status_code >= 500:
        raise LLMTransportError("provider_unavailable")
    if not 200 <= status_code < 300:
        raise LLMTransportError("invalid_response")
