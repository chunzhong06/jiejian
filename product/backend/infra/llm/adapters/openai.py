# OpenAI Responses API 的正式 provider 适配器。
# 边界：固定官方主机并只投影最终 message/output_text，丢弃 reasoning 内容。

from __future__ import annotations

import json
from typing import Any

from product.backend.infra.llm.adapters.base import (
    LLMHttpRequest,
    LLMHttpResponse,
    LLMTransportError,
    json_body,
    max_output_tokens,
)
from product.backend.infra.llm.adapters.openai_compatible import _raise_for_status
from product.backend.infra.llm.config import LLMProfileConfig, LLMProviderType, reasoning_options_for

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAIAdapter:
    provider = LLMProviderType.OPENAI

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
        payload: dict[str, object] = {
            "model": profile.model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "store": False,
            "max_output_tokens": max_output_tokens(profile),
        }
        if reasoning_effort is not None:
            payload["reasoning"] = {"effort": reasoning_effort}
        if json_schema is not None:
            payload["text"] = {
                "format": {"type": "json_schema", "name": "jiejian_output", "schema": json_schema, "strict": True}
            }
        return LLMHttpRequest(
            method="POST",
            provider=self.provider,
            url=f"{DEFAULT_BASE_URL}/responses",
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {secret}",
                "content-type": "application/json",
            },
            body=json_body(payload),
            timeout_ms=profile.timeout_ms,
            max_output_bytes=profile.max_output_bytes,
        )

    def parse_response(self, response: LLMHttpResponse) -> str:
        _raise_for_status(response.status_code)
        payload = _parse_json(response.body)
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        output = payload.get("output")
        if not isinstance(output, list):
            raise LLMTransportError("invalid_response")
        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str):
                        texts.append(text)
        result = "".join(texts)
        if not result.strip():
            raise LLMTransportError("invalid_response")
        return result


def _parse_json(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise LLMTransportError("invalid_response") from None
    if not isinstance(value, dict):
        raise LLMTransportError("invalid_response")
    return value
