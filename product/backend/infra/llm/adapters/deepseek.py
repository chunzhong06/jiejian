# DeepSeek Chat Completions / Responses 的正式 provider 适配器。
# 边界：结构化输出只走供应商 Schema 约束，只保留最终正文并丢弃 reasoning。

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

DEFAULT_BASE_URL = "https://api.deepseek.com"


class DeepSeekAdapter:
    provider = LLMProviderType.DEEPSEEK

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
        if json_schema is not None and profile.model == "deepseek-v4-flash":
            payload: dict[str, object] = {
                "model": profile.model,
                "input": prompt,
                "stream": False,
                "max_output_tokens": _responses_max_output_tokens(
                    profile,
                    reasoning_effort=reasoning_effort,
                ),
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "jiejian_output",
                        "schema": json_schema,
                    }
                },
            }
            if reasoning_effort is not None:
                payload["reasoning"] = {"effort": reasoning_effort}
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
        payload: dict[str, object] = {
            "messages": [{"role": "user", "content": prompt}],
            "model": profile.model,
            "n": 1,
            "stream": False,
            "max_tokens": max_output_tokens(profile),
        }
        if reasoning_effort is not None:
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = reasoning_effort
        if json_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        return LLMHttpRequest(
            method="POST",
            provider=self.provider,
            url=f"{DEFAULT_BASE_URL}/chat/completions",
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
        if payload.get("object") == "response":
            return _parse_responses_output(payload)
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise LLMTransportError("invalid_response")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMTransportError("invalid_response")
        return content


def _parse_responses_output(payload: dict[str, Any]) -> str:
    if payload.get("status") != "completed" or payload.get("error") is not None:
        raise LLMTransportError("invalid_response")
    output = payload.get("output")
    if not isinstance(output, list):
        raise LLMTransportError("invalid_response")
    final_text: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            raise LLMTransportError("invalid_response")
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "output_text":
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                final_text.append(text)
    if len(final_text) != 1:
        raise LLMTransportError("invalid_response")
    return final_text[0]


def _responses_max_output_tokens(
    profile: LLMProfileConfig,
    *,
    reasoning_effort: str | None,
) -> int:
    visible_budget = max_output_tokens(profile)
    if reasoning_effort is None:
        return visible_budget
    # DeepSeek Responses 把 reasoning 和最终正文计入同一 token 上限；字节硬限仍在传输层独立生效。
    reasoning_aware_budget = min(profile.max_output_bytes // 8, 4_096)
    return max(visible_budget, reasoning_aware_budget)


def _parse_json(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise LLMTransportError("invalid_response") from None
    if not isinstance(value, dict):
        raise LLMTransportError("invalid_response")
    return value
