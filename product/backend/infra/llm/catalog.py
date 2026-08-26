# LLM 动态模型目录；临时发现与已保存 profile 刷新共用同一受控传输边界。
# 安全边界：本模块不持久化 API Key，不记录响应正文，并对模型数量和分页做硬上限。

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.llm.adapters.base import LLMHttpRequest, LLMTransport, LLMTransportError
from product.backend.infra.llm.adapters.openai_compatible import _raise_for_status
from product.backend.infra.llm.config import LLMProfileConfig, LLMProviderType, reasoning_options_for


@dataclass(frozen=True, slots=True)
class LLMModelOption:
    model: str
    display_name: str | None
    reasoning_options: tuple[str, ...]
    reasoning_default_label: str = "跟随模型默认"
    structured_output_mode: str = "unsupported"


@dataclass(frozen=True, slots=True)
class LLMModelCatalog:
    provider: LLMProviderType
    models: tuple[LLMModelOption, ...]
    manual_model_allowed: bool = False
    truncated: bool = False


_MAX_MODELS = 512
_MAX_GEMINI_PAGES = 8
_BASE_URLS = {
    LLMProviderType.OPENAI: "https://api.openai.com/v1",
    LLMProviderType.DEEPSEEK: "https://api.deepseek.com",
    LLMProviderType.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
}


class LLMModelCatalogService:
    def __init__(self, transport: LLMTransport) -> None:
        self._transport = transport

    def discover(
        self,
        provider: LLMProviderType,
        secret: str,
        *,
        base_url: str | None = None,
        allow_local_http: bool = False,
    ) -> LLMModelCatalog:
        if provider is LLMProviderType.OPENAI_COMPATIBLE:
            return self._discover_compatible(provider, secret, base_url, allow_local_http)
        url = f"{_BASE_URLS[provider]}/models"
        if provider is LLMProviderType.GEMINI:
            return self._discover_gemini(secret, url)
        response = self._send_get(provider, url, secret, max_output_bytes=1_048_576)
        _raise_for_status(response.status_code)
        return self._parse_openai_style(provider, response.body)

    def refresh(self, profile: LLMProfileConfig, secret: str) -> LLMModelCatalog:
        return self.discover(
            profile.provider,
            secret,
            base_url=profile.base_url,
            allow_local_http=profile.allow_local_http,
        )

    def _discover_gemini(self, secret: str, url: str) -> LLMModelCatalog:
        values: list[LLMModelOption] = []
        next_token: str | None = None
        truncated = False
        for page in range(_MAX_GEMINI_PAGES):
            page_url = url if next_token is None else f"{url}?{urlencode({'pageToken': next_token})}"
            response = self._send_get(LLMProviderType.GEMINI, page_url, secret, max_output_bytes=1_048_576)
            _raise_for_status(response.status_code)
            payload = _parse_json(response.body)
            models = payload.get("models")
            if not isinstance(models, list):
                raise LLMTransportError("invalid_response")
            for item in models:
                if not isinstance(item, dict):
                    raise LLMTransportError("invalid_response")
                methods = item.get("supportedGenerationMethods", item.get("supportedActions"))
                if not isinstance(methods, list):
                    raise LLMTransportError("invalid_response")
                if "generateContent" not in methods:
                    continue
                model = item.get("baseModelId")
                if not isinstance(model, str) or not model:
                    name = item.get("name")
                    model = name.removeprefix("models/") if isinstance(name, str) else None
                values.append(_model_option(LLMProviderType.GEMINI, model, item.get("displayName")))
                if len(values) > _MAX_MODELS:
                    values = values[:_MAX_MODELS]
                    truncated = True
                    break
            if truncated:
                break
            token = payload.get("nextPageToken")
            if token is None:
                next_token = None
                break
            if not isinstance(token, str) or not token.strip():
                raise LLMTransportError("invalid_response")
            next_token = token
            if page == _MAX_GEMINI_PAGES - 1:
                truncated = True
        return _catalog(LLMProviderType.GEMINI, values, truncated=truncated)

    def _discover_compatible(
        self,
        provider: LLMProviderType,
        secret: str,
        base_url: str | None,
        allow_local_http: bool,
    ) -> LLMModelCatalog:
        if base_url is None:
            raise LLMTransportError("invalid_request")
        from product.backend.infra.llm.config import normalize_llm_base_url

        url = f"{normalize_llm_base_url(base_url, allow_local_http=allow_local_http).rstrip('/')}/models"
        response = self._send_get(provider, url, secret, max_output_bytes=1_048_576)
        if response.status_code in {404, 405, 501}:
            return LLMModelCatalog(provider, (), manual_model_allowed=True)
        _raise_for_status(response.status_code)
        return self._parse_openai_style(provider, response.body)

    def _parse_openai_style(self, provider: LLMProviderType, body: bytes) -> LLMModelCatalog:
        payload = _parse_json(body)
        values = payload.get("data")
        if not isinstance(values, list):
            raise LLMTransportError("invalid_response")
        models = []
        for item in values:
            if not isinstance(item, dict):
                raise LLMTransportError("invalid_response")
            models.append(_model_option(provider, item.get("id"), item.get("display_name", item.get("owned_by"))))
        truncated = len(models) > _MAX_MODELS
        return _catalog(provider, models[:_MAX_MODELS], truncated=truncated)

    def _send_get(self, provider: LLMProviderType, url: str, secret: str, *, max_output_bytes: int):
        request = LLMHttpRequest(
            method="GET",
            provider=provider,
            url=url,
            headers={
                "accept": "application/json",
                **({"x-goog-api-key": secret} if provider is LLMProviderType.GEMINI else {"authorization": f"Bearer {secret}"}),
            },
            body=b"",
            timeout_ms=30_000,
            max_output_bytes=max_output_bytes,
        )
        return self._transport.send(request)


def _model_option(provider: LLMProviderType, model: object, display_name: object) -> LLMModelOption:
    if not isinstance(model, str) or not 1 <= len(model.strip()) <= 256 or model != model.strip() or any(ord(c) < 32 or ord(c) == 127 for c in model):
        raise LLMTransportError("invalid_response")
    if display_name is not None and (
        not isinstance(display_name, str)
        or not 1 <= len(display_name) <= 128
        or display_name != display_name.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in display_name)
    ):
        raise LLMTransportError("invalid_response")
    return LLMModelOption(
        model=model,
        display_name=display_name,
        reasoning_options=reasoning_options_for(provider, model),
        structured_output_mode={
            LLMProviderType.OPENAI: "json_schema",
            LLMProviderType.DEEPSEEK: (
                "json_schema" if model == "deepseek-v4-flash" else "json_object"
            ),
            LLMProviderType.GEMINI: "json_schema",
            LLMProviderType.OPENAI_COMPATIBLE: "unsupported",
        }[provider],
    )


def _catalog(provider: LLMProviderType, models: list[LLMModelOption], *, truncated: bool) -> LLMModelCatalog:
    if provider is not LLMProviderType.GEMINI and len({item.model for item in models}) != len(models):
        raise LLMTransportError("invalid_response")
    deduplicated = {item.model: item for item in models}
    return LLMModelCatalog(provider, tuple(deduplicated[key] for key in sorted(deduplicated)), truncated=truncated)


def _parse_json(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise LLMTransportError("invalid_response") from None
    if not isinstance(value, dict):
        raise LLMTransportError("invalid_response")
    return value
