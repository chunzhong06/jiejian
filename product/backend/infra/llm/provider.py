# =============================================================================
# LLM Provider 运行时
#
# 定位
# 已解析 profile、SecretStore 与供应商 adapter 之间的单次运行时边界。
#
# 职责
# 组装正式 adapter｜执行有界 invoke/probe｜映射稳定 transport 错误
#
# 边界
# 不持久化或回显秘密，不决定安全结论；连接只由显式服务调用触发。
#
# 调用链
# LLMProfileRegistry / assistant service → provider → adapter / transport
# =============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.llm.adapters.base import LLMAdapter, LLMInvokeResult, LLMTransport, LLMTransportError
from product.backend.infra.llm.adapters.deepseek import DeepSeekAdapter
from product.backend.infra.llm.adapters.gemini import GeminiAdapter
from product.backend.infra.llm.adapters.openai import OpenAIAdapter
from product.backend.infra.llm.adapters.openai_compatible import OpenAICompatibleAdapter
from product.backend.infra.llm.config import (
    LLMProfileConfig,
    LLMProviderType,
    reasoning_options_for,
)


ConnectionStatus = Literal["testing", "configured", "available", "unavailable", "unknown"]


@dataclass(frozen=True, slots=True)
class _ConnectionState:
    status: ConnectionStatus
    tested_at_us: int | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None

@dataclass(frozen=True, slots=True)
class ResolvedLLMProvider:
    """已解析秘密的单次 provider；repr 不包含秘密、请求或响应。"""

    provider: LLMProviderType
    profile_name: str
    model: str
    adapter_version: str
    prompt_version: str
    input_max_bytes: int
    output_max_bytes: int
    budget_limit_microusd: int
    _adapter: LLMAdapter = field(repr=False)
    _transport: LLMTransport = field(repr=False)
    _secret: str = field(repr=False)
    _profile: LLMProfileConfig = field(repr=False)
    known_secrets: tuple[str, ...] = field(default=(), repr=False)

    def __call__(self, prompt: str) -> str:
        return self.invoke(prompt).final_payload

    def invoke(
        self,
        prompt: str,
        *,
        reasoning_effort: str | None = None,
        json_schema: dict[str, object] | None = None,
    ) -> LLMInvokeResult:
        prompt_bytes = prompt.encode("utf-8")
        if len(prompt_bytes) > self.input_max_bytes or self.budget_limit_microusd <= 0:
            raise LLMTransportError("budget_exceeded")
        started = time.monotonic_ns()
        actual_reasoning = self._profile.reasoning_effort if reasoning_effort is None else reasoning_effort
        if actual_reasoning is not None and actual_reasoning not in reasoning_options_for(self.provider, self.model):
            raise LLMTransportError("invalid_request")
        request = self._adapter.build_request(
            self._profile,
            self._secret,
            prompt,
            reasoning_effort=actual_reasoning,
            json_schema=json_schema,
        )
        if len(request.body) > self.input_max_bytes:
            raise LLMTransportError("budget_exceeded")
        response = self._transport.send(request)
        if len(response.body) > self.output_max_bytes:
            raise LLMTransportError("response_too_large")
        final_payload = self._adapter.parse_response(response)
        mode = "text"
        if json_schema is not None:
            mode = {
                LLMProviderType.OPENAI: "json_schema",
                LLMProviderType.DEEPSEEK: (
                    "json_schema" if self.model == "deepseek-v4-flash" else "json_object"
                ),
                LLMProviderType.GEMINI: "json_schema",
                LLMProviderType.OPENAI_COMPATIBLE: "unsupported",
            }[self.provider]
        return LLMInvokeResult(
            model=self.model,
            reasoning_effort=actual_reasoning,
            structured_output_mode=mode,
            final_payload=final_payload,
            usage=None,
            latency_ms=max(0, (time.monotonic_ns() - started) // 1_000_000),
        )

def adapter_for(provider: LLMProviderType) -> LLMAdapter:
    """按后端 provider 枚举组装正式或高级兼容 adapter。"""

    if provider is LLMProviderType.OPENAI:
        return OpenAIAdapter()
    if provider is LLMProviderType.DEEPSEEK:
        return DeepSeekAdapter()
    if provider is LLMProviderType.GEMINI:
        return GeminiAdapter()
    return OpenAICompatibleAdapter(provider)


def probe_provider(
    transport: LLMTransport,
    profile: LLMProfileConfig,
    secret: str,
    *,
    prompt: str = "ping",
) -> None:
    """执行一次有界连接探测；预算或 provider 错误原样交给 registry 映射。"""

    adapter = adapter_for(profile.provider)
    request = adapter.build_request(
        profile,
        secret,
        prompt,
        reasoning_effort=profile.reasoning_effort,
    )
    if len(request.body) > profile.max_input_bytes:
        raise LLMTransportError("budget_exceeded")
    response = transport.send(request)
    if len(response.body) > profile.max_output_bytes:
        raise LLMTransportError("response_too_large")
    adapter.parse_response(response)

def _error_for_transport(kind: str) -> ErrorCode:
    return {
        "auth_failed": ErrorCode.LLM_AUTH_FAILED,
        "rate_limited": ErrorCode.LLM_RATE_LIMITED,
        "timeout": ErrorCode.LLM_TIMEOUT,
        "invalid_response": ErrorCode.LLM_INVALID_RESPONSE,
        "budget_exceeded": ErrorCode.LLM_BUDGET_EXCEEDED,
        "response_too_large": ErrorCode.LLM_BUDGET_EXCEEDED,
        "invalid_request": ErrorCode.LLM_PROFILE_INVALID,
        "provider_unavailable": ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE,
        "network": ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE,
    }.get(kind, ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE)

def _safe_profile_error() -> JiejianError:
    return JiejianError(ErrorCode.LLM_PROFILE_STORAGE_FAILED, "模型 profile 保存失败")

def _jiejian_error_for_transport(kind: str) -> JiejianError:
    return JiejianError(_error_for_transport(kind), "模型服务请求失败")
