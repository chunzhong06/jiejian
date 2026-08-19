# Gemini generateContent 的请求/响应投影。
# 边界：只构造和解析 provider 消息，实际网络约束由 LLMTransport 承担。

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from product.backend.infra.llm.config import LLMProfileConfig, LLMProviderType, normalize_llm_base_url
from product.backend.infra.llm.adapters.base import LLMHttpRequest, LLMHttpResponse, LLMTransportError, json_body, max_output_tokens
from product.backend.infra.llm.adapters.openai_compatible import _raise_for_status


DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiAdapter:
    provider = LLMProviderType.GEMINI

    def build_request(
        self,
        profile: LLMProfileConfig,
        secret: str,
        prompt: str,
    ) -> LLMHttpRequest:
        normalized = normalize_llm_base_url(
            profile.base_url or DEFAULT_BASE_URL,
            allow_local_http=profile.allow_local_http,
        )
        encoded_model = quote(profile.model, safe="")
        body = json_body(
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "candidateCount": 1,
                    "maxOutputTokens": max_output_tokens(profile),
                },
            }
        )
        return LLMHttpRequest(
            provider=self.provider,
            url=f"{normalized.rstrip('/')}/models/{encoded_model}:generateContent",
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "x-goog-api-key": secret,
            },
            body=body,
            timeout_ms=profile.timeout_ms,
            max_output_bytes=profile.max_output_bytes,
        )

    def parse_response(self, response: LLMHttpResponse) -> str:
        _raise_for_status(response.status_code)
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            raise LLMTransportError("invalid_response") from None
        if not isinstance(payload, dict):
            raise LLMTransportError("invalid_response")
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 1:
            raise LLMTransportError("invalid_response")
        content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list) or not parts:
            raise LLMTransportError("invalid_response")
        texts = [part.get("text") for part in parts if isinstance(part, dict)]
        if len(texts) != len(parts) or any(not isinstance(text, str) for text in texts):
            raise LLMTransportError("invalid_response")
        result = "".join(texts)
        if not result.strip():
            raise LLMTransportError("invalid_response")
        return result
