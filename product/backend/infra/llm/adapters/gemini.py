# Gemini generateContent 的请求/响应投影。
# 边界：只构造和解析 provider 消息，实际网络约束由 LLMTransport 承担。

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from product.backend.infra.llm.config import LLMProfileConfig, LLMProviderType, reasoning_options_for
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
        *,
        reasoning_effort: str | None = None,
        json_schema: dict[str, object] | None = None,
    ) -> LLMHttpRequest:
        if profile.base_url is not None or profile.allow_local_http:
            raise LLMTransportError("invalid_request")
        if reasoning_effort is not None and reasoning_effort not in reasoning_options_for(profile.provider, profile.model):
            raise LLMTransportError("invalid_request")
        encoded_model = quote(profile.model, safe="")
        body = json_body(
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "candidateCount": 1,
                    "maxOutputTokens": max_output_tokens(profile),
                    **({"thinkingConfig": {"thinkingLevel": reasoning_effort}} if reasoning_effort is not None else {}),
                    **({"responseMimeType": "application/json", "responseJsonSchema": json_schema} if json_schema is not None else {}),
                },
            }
        )
        return LLMHttpRequest(
            method="POST",
            provider=self.provider,
            url=f"{DEFAULT_BASE_URL}/models/{encoded_model}:generateContent",
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
        texts = [part.get("text") for part in parts if isinstance(part, dict) and not part.get("thought", False)]
        if not texts or any(not isinstance(text, str) for text in texts):
            raise LLMTransportError("invalid_response")
        result = "".join(texts)
        if not result.strip():
            raise LLMTransportError("invalid_response")
        return result
