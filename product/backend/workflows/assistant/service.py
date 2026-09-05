# =============================================================================
# AI surface 通用执行内核；CURRENT 事实与 dormant 算法共用执行边界。
#
# 定位
#   服务端事实 resolver 与可选模型 Provider 之间的唯一应用服务边界。
#
# 职责
#   纯读缓存｜显式生成｜单飞去重｜统一退避｜结构化调用与本地白名单复验
#
# 边界
#   GET 不连接供应商；模型失败不阻断确定性主流程，也不改变任何安全事实。
# =============================================================================

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.llm.adapters.base import LLMTransportError
from product.backend.infra.llm.profiles import LLMProfileRegistry
from product.backend.workflows.assistant.cache import AssistantCache
from product.backend.workflows.assistant.diagnosis import ErrorDiagnosis
from product.backend.workflows.assistant.surfaces import AssistantSurfaceResolver, ResolvedAssistantSurface
from product.backend.workflows.assistant.templates import (
    AssistantEntity,
    AssistantSuggestion,
    AssistantTemplateId,
    assistant_result_json_schema,
    parse_assistant_result,
    render_assistant_prompt,
)


class AssistantStatus(StrEnum):
    DISABLED = "DISABLED"
    REFRESH_NEEDED = "REFRESH_NEEDED"
    GENERATING = "GENERATING"
    READY = "READY"
    BACKOFF = "BACKOFF"


class AssistantSurfaceView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    status: AssistantStatus
    template_id: AssistantTemplateId
    template_version: str = "1"
    subject_id: str
    state_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    entities: tuple[AssistantEntity, ...]
    can_generate: bool = True
    suggestions: tuple[AssistantSuggestion, ...] = Field(default=(), max_length=3)
    retry_after_us: int | None = Field(default=None, ge=0)


class AssistantService:
    """所有 surface 共享同一 provider、缓存、并发和失败收敛内核。"""

    _BACKOFF_US = 5 * 60 * 1_000_000

    def __init__(
        self,
        var_dir,
        *,
        surfaces: AssistantSurfaceResolver,
        llm_profiles: LLMProfileRegistry,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._surfaces = surfaces
        self._llm_profiles = llm_profiles
        self._cache = AssistantCache(var_dir)
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)
        self._inflight: set[str] = set()
        self._lock = threading.Lock()

    def get_project(self, project_id: str, template_id: AssistantTemplateId, *,
                    business_actor_id: str | None = None, business_action_id: str | None = None,
                    recording_id: str | None = None) -> AssistantSurfaceView:
        focus = {key: value for key, value in {"business_actor_id": business_actor_id,
            "business_action_id": business_action_id, "recording_id": recording_id}.items() if value is not None}
        return self._get(self._surfaces.resolve_project(project_id, template_id, **focus))

    def generate_project(
        self,
        project_id: str,
        template_id: AssistantTemplateId,
        *,
        retry: bool = False,
        business_actor_id: str | None = None,
        business_action_id: str | None = None,
        recording_id: str | None = None,
    ) -> AssistantSurfaceView:
        focus = {key: value for key, value in {"business_actor_id": business_actor_id,
            "business_action_id": business_action_id, "recording_id": recording_id}.items() if value is not None}
        return self._generate_explicit(self._surfaces.resolve_project(project_id, template_id, **focus), retry=retry)

    def get_result(self, run_id: str) -> AssistantSurfaceView:
        return self._get(self._surfaces.resolve_result(run_id))

    def generate_result(self, run_id: str, *, retry: bool = False) -> AssistantSurfaceView:
        return self._generate_explicit(self._surfaces.resolve_result(run_id), retry=retry)

    def get_error(self, error_code: str, diagnosis: ErrorDiagnosis) -> AssistantSurfaceView:
        return self._get(self._surfaces.resolve_error(error_code, diagnosis))

    def generate_error(
        self,
        error_code: str,
        diagnosis: ErrorDiagnosis,
        *,
        retry: bool = False,
    ) -> AssistantSurfaceView:
        return self._generate_explicit(self._surfaces.resolve_error(error_code, diagnosis), retry=retry)

    def _get(self, resolved: ResolvedAssistantSurface) -> AssistantSurfaceView:
        if not self._configured():
            return self._view(AssistantStatus.DISABLED, resolved)
        if not resolved.can_generate:
            return self._view(AssistantStatus.READY, resolved)
        key = self._key(resolved)
        with self._lock:
            if key in self._inflight:
                return self._view(AssistantStatus.GENERATING, resolved)
        cached = self._cache.read(
            resolved.subject_id,
            resolved.surface_input.template_id,
            resolved.state_fingerprint,
            surface_input=resolved.surface_input,
        )
        if cached is None:
            return self._view(AssistantStatus.REFRESH_NEEDED, resolved)
        if cached.get("entry_type") == "success":
            return self._view(AssistantStatus.READY, resolved, cached["suggestions"])
        return self._view(AssistantStatus.BACKOFF, resolved, retry_after_us=cached["retry_after_us"])

    def _generate_explicit(
        self,
        resolved: ResolvedAssistantSurface,
        *,
        retry: bool,
    ) -> AssistantSurfaceView:
        if not self._configured():
            return self._view(AssistantStatus.DISABLED, resolved)
        if not resolved.can_generate:
            return self._view(AssistantStatus.READY, resolved)
        cached = self._cache.read(
            resolved.subject_id,
            resolved.surface_input.template_id,
            resolved.state_fingerprint,
            surface_input=resolved.surface_input,
        )
        if cached is not None:
            if cached.get("entry_type") == "success":
                return self._view(AssistantStatus.READY, resolved, cached["suggestions"])
            if not retry:
                return self._view(AssistantStatus.BACKOFF, resolved, retry_after_us=cached["retry_after_us"])
        key = self._key(resolved)
        with self._lock:
            if key in self._inflight:
                return self._view(AssistantStatus.GENERATING, resolved)
            self._inflight.add(key)
        try:
            return self._invoke(resolved)
        except (JiejianError, LLMTransportError) as exc:
            retry_after = self._clock_us() + self._BACKOFF_US
            self._cache.write_failure(
                resolved.subject_id,
                resolved.surface_input.template_id,
                resolved.state_fingerprint,
                code=_safe_failure_code(exc),
                retry_after_us=retry_after,
            )
            return self._view(AssistantStatus.BACKOFF, resolved, retry_after_us=retry_after)
        finally:
            with self._lock:
                self._inflight.discard(key)

    def _invoke(self, resolved: ResolvedAssistantSurface) -> AssistantSurfaceView:
        settings = self._llm_profiles.get_settings()
        if not settings.enabled or settings.default_profile_name is None:
            return self._view(AssistantStatus.DISABLED, resolved)
        provider = self._llm_profiles.resolve_provider(settings.default_profile_name)
        surface_input = resolved.surface_input
        result = provider.invoke(
            render_assistant_prompt(surface_input),
            json_schema=assistant_result_json_schema(surface_input),
        )
        parsed = parse_assistant_result(result.final_payload, surface_input=surface_input)
        self._cache.write_success(
            resolved.subject_id,
            surface_input.template_id,
            resolved.state_fingerprint,
            provider=provider.provider.value,
            profile=provider.profile_name,
            model=result.model,
            reasoning_setting=result.reasoning_effort,
            suggestions=parsed.suggestions,
            generated_at_us=self._clock_us(),
        )
        return self._view(AssistantStatus.READY, resolved, parsed.suggestions)

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
    def _key(resolved: ResolvedAssistantSurface) -> str:
        return f"{resolved.subject_id}:{resolved.surface_input.template_id.value}:{resolved.state_fingerprint}"

    @staticmethod
    def _view(
        status: AssistantStatus,
        resolved: ResolvedAssistantSurface,
        suggestions: tuple[AssistantSuggestion, ...] = (),
        *,
        retry_after_us: int | None = None,
    ) -> AssistantSurfaceView:
        return AssistantSurfaceView(
            status=status,
            template_id=resolved.surface_input.template_id,
            subject_id=resolved.subject_id,
            state_fingerprint=resolved.state_fingerprint,
            entities=resolved.surface_input.entities,
            can_generate=resolved.can_generate,
            suggestions=suggestions,
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
    value = error.code if isinstance(error, JiejianError) else ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE.value
    return value if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,95}", value) else ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE.value


__all__ = ["AssistantService", "AssistantStatus", "AssistantSurfaceView"]
