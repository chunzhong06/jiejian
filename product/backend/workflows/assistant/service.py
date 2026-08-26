# =============================================================================
# AI 辅助应用服务
#
# 定位
#   确定性 Guidance 与可选模型 Provider 之间的唯一应用服务边界
#
# 职责
#   纯读状态查询｜显式刷新与并发去重｜严格解析后缓存白名单结果
#
# 边界
#   GET 不连接供应商；模型失败不阻断确定性主流程，也不产生权限或安全结论。
#
# 调用链
#   Assistant API → AssistantService → Guidance / LLMProfileRegistry / AssistantCache
# =============================================================================

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.llm.adapters.base import LLMTransportError
from product.backend.infra.llm.profiles import LLMProfileRegistry
from product.backend.workflows.assistant.cache import AssistantCache
from product.backend.workflows.assistant.guidance import GuidanceOptionKind, GuidanceQueryService, GuidanceSnapshot
from product.backend.workflows.assistant.templates import (
    ASSISTANT_TEMPLATES,
    AssistantFactField,
    AssistantRecommendation,
    AssistantTemplateId,
    build_template_input,
    parse_assistant_result,
    render_assistant_prompt,
)


class AssistantStatus(StrEnum):
    DISABLED = "DISABLED"
    REFRESH_NEEDED = "REFRESH_NEEDED"
    GENERATING = "GENERATING"
    READY = "READY"
    BACKOFF = "BACKOFF"


class AssistantGuidanceView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    status: AssistantStatus
    template_id: AssistantTemplateId = AssistantTemplateId.NEXT_STEP
    template_version: Literal["1"] = "1"
    guidance: GuidanceSnapshot
    recommendations: tuple[AssistantRecommendation, ...] = Field(default=(), max_length=3)
    retry_after_us: int | None = Field(default=None, ge=0)


class AssistantService:
    """只允许受控模板调用模型，并以事实指纹隔离缓存和失败退避。"""

    _TEMPLATE = AssistantTemplateId.NEXT_STEP
    _BACKOFF_US = 5 * 60 * 1_000_000

    def __init__(
        self,
        var_dir,
        *,
        guidance: GuidanceQueryService,
        llm_profiles: LLMProfileRegistry,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._guidance = guidance
        self._llm_profiles = llm_profiles
        self._cache = AssistantCache(var_dir)
        self._clock_us = clock_us or (lambda: time.time_ns() // 1000)
        self._inflight: set[str] = set()
        self._lock = threading.Lock()

    def get(self, project_id: str) -> AssistantGuidanceView:
        guidance = self._guidance.get(project_id)
        if not self._configured():
            return self._view(AssistantStatus.DISABLED, guidance)
        key = self._key(project_id, guidance)
        with self._lock:
            # 并发页面共享同一生成资格，非持有者只观察 GENERATING，不能重复产生费用。
            if key in self._inflight:
                return self._view(AssistantStatus.GENERATING, guidance)
        cached = self._cache.read(
            project_id,
            self._TEMPLATE,
            guidance.state_fingerprint,
            allowed_option_ids=self._allowed_option_ids(guidance),
        )
        if cached is not None:
            if cached.get("entry_type") == "success":
                return self._view(AssistantStatus.READY, guidance, cached["recommendations"])
            return self._view(AssistantStatus.BACKOFF, guidance, retry_after_us=cached["retry_after_us"])
        return self._view(AssistantStatus.REFRESH_NEEDED, guidance)

    def refresh(self, project_id: str, *, retry: bool = False) -> AssistantGuidanceView:
        guidance = self._guidance.get(project_id)
        if not self._configured():
            return self._view(AssistantStatus.DISABLED, guidance)
        key = self._key(project_id, guidance)
        cached = self._cache.read(
            project_id,
            self._TEMPLATE,
            guidance.state_fingerprint,
            allowed_option_ids=self._allowed_option_ids(guidance),
        )
        if cached is not None:
            if cached.get("entry_type") == "success":
                return self._view(AssistantStatus.READY, guidance, cached["recommendations"])
            if not retry:
                return self._view(AssistantStatus.BACKOFF, guidance, retry_after_us=cached["retry_after_us"])
        with self._lock:
            if key in self._inflight:
                return self._view(AssistantStatus.GENERATING, guidance)
            self._inflight.add(key)
        try:
            return self._generate(project_id, guidance)
        except (JiejianError, LLMTransportError) as exc:
            code = _safe_failure_code(exc)
            retry_after = self._clock_us() + self._BACKOFF_US
            self._cache.write_failure(
                project_id,
                self._TEMPLATE,
                guidance.state_fingerprint,
                code=code,
                retry_after_us=retry_after,
            )
            return self._view(AssistantStatus.BACKOFF, guidance, retry_after_us=retry_after)
        finally:
            with self._lock:
                self._inflight.discard(key)

    def _generate(self, project_id: str, guidance: GuidanceSnapshot) -> AssistantGuidanceView:
        settings = self._llm_profiles.get_settings()
        if not settings.enabled or settings.default_profile_name is None:
            return self._view(AssistantStatus.DISABLED, guidance)
        provider = self._llm_profiles.resolve_provider(settings.default_profile_name)
        options = guidance.options[:16]
        facts = {
            AssistantFactField.PHASE: guidance.phase.value,
            AssistantFactField.CURRENT_SCOPE_RUNNABLE: guidance.current_scope_runnable,
            AssistantFactField.REMAINING_GAP_COUNT: guidance.remaining_gap_count,
            AssistantFactField.LATEST_RESULT_AVAILABLE: any(
                item.kind is GuidanceOptionKind.OPEN_LATEST_RESULT for item in guidance.options
            ),
        }
        template_input = build_template_input(self._TEMPLATE, facts=facts, options=options)
        prompt = render_assistant_prompt(template_input)
        spec = ASSISTANT_TEMPLATES[self._TEMPLATE]
        allowed_option_ids = tuple(item.option_id for item in options)
        result = provider.invoke(
            prompt,
            json_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "schema_version": {"type": "string", "enum": ["1"]},
                    "template_id": {"type": "string", "enum": [self._TEMPLATE.value]},
                    "template_version": {"type": "string", "enum": ["1"]},
                    "recommendations": {
                        "type": "array",
                        "maxItems": spec.max_recommendations,
                        "uniqueItems": True,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "option_id": {
                                    "type": "string",
                                    "enum": list(allowed_option_ids),
                                },
                                "explanation": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": spec.max_explanation_chars,
                                },
                            },
                            "required": ["option_id", "explanation"],
                        },
                    },
                },
                "required": ["schema_version", "template_id", "template_version", "recommendations"],
            },
        )
        parsed = parse_assistant_result(
            result.final_payload,
            template_id=self._TEMPLATE,
            allowed_option_ids=allowed_option_ids,
        )
        self._cache.write_success(
            project_id,
            self._TEMPLATE,
            guidance.state_fingerprint,
            provider=provider.provider.value,
            profile=provider.profile_name,
            model=result.model,
            reasoning_setting=result.reasoning_effort,
            recommendations=parsed.recommendations,
            generated_at_us=self._clock_us(),
        )
        return self._view(AssistantStatus.READY, guidance, parsed.recommendations)

    def _configured(self) -> bool:
        settings = self._llm_profiles.get_settings()
        if not settings.enabled or settings.default_profile_name is None:
            return False
        try:
            profile = self._llm_profiles.get(settings.default_profile_name)
        except JiejianError:
            return False
        return profile.enabled and profile.secret_configured

    @staticmethod
    def _allowed_option_ids(guidance: GuidanceSnapshot) -> tuple[str, ...]:
        return tuple(item.option_id for item in guidance.options[:16])

    @staticmethod
    def _key(project_id: str, guidance: GuidanceSnapshot) -> str:
        return f"{project_id}:jiejian.next_step:{guidance.state_fingerprint}"

    @staticmethod
    def _view(
        status: AssistantStatus,
        guidance: GuidanceSnapshot,
        recommendations: tuple[AssistantRecommendation, ...] = (),
        *,
        retry_after_us: int | None = None,
    ) -> AssistantGuidanceView:
        return AssistantGuidanceView(
            status=status,
            guidance=guidance,
            recommendations=recommendations,
            retry_after_us=retry_after_us,
        )


def _safe_failure_code(error: Exception) -> str:
    if isinstance(error, LLMTransportError):
        return {
            "auth_failed": ErrorCode.LLM_AUTH_FAILED.value,
            "rate_limited": ErrorCode.LLM_RATE_LIMITED.value,
            "timeout": ErrorCode.LLM_TIMEOUT.value,
            "invalid_response": ErrorCode.LLM_INVALID_RESPONSE.value,
            "budget_exceeded": ErrorCode.LLM_BUDGET_EXCEEDED.value,
            "response_too_large": ErrorCode.LLM_BUDGET_EXCEEDED.value,
            "network": ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE.value,
            "provider_unavailable": ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE.value,
        }.get(error.kind, ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE.value)
    if isinstance(error, JiejianError):
        value = error.code
    else:
        value = ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE.value
    return value if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,95}", value) else ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE.value


__all__ = ["AssistantGuidanceView", "AssistantService", "AssistantStatus"]
