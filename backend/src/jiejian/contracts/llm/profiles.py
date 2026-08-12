"""LLM profile CRUD、秘密解析和显式连接测试应用服务。"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...errors import ErrorCode, JiejianError
from ...storage import StorageUnitOfWork
from .adapters.base import LLMAdapter, LLMTransport, LLMTransportError
from .adapters.gemini import GeminiAdapter
from .adapters.openai_compatible import OpenAICompatibleAdapter
from .config import LLMProfileConfig, LLMProviderType
from .secrets import (
    LLMSecretStore,
    WindowsCredentialManagerSecretStore,
    credential_ref_for,
)


ConnectionStatus = Literal["testing", "configured", "available", "unavailable", "unknown"]


class LLMProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    schema_version: Literal["1"] = "1"
    profile_name: str
    provider: LLMProviderType
    model: str
    base_url: str | None = None
    timeout_ms: int
    max_input_bytes: int
    max_output_bytes: int
    max_budget_microusd: int
    enabled: bool
    secret_ref: str | None = None
    allow_local_http: bool
    created_at_us: int
    updated_at_us: int
    secret_configured: bool
    connection_status: ConnectionStatus = "unknown"
    tested_at_us: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    error_message: str | None = None


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
        prompt_bytes = prompt.encode("utf-8")
        if len(prompt_bytes) > self.input_max_bytes or self.budget_limit_microusd <= 0:
            raise LLMTransportError("budget_exceeded")
        request = self._adapter.build_request(self._profile, self._secret, prompt)
        if len(request.body) > self.input_max_bytes:
            raise LLMTransportError("budget_exceeded")
        response = self._transport.send(request)
        if len(response.body) > self.output_max_bytes:
            raise LLMTransportError("response_too_large")
        return self._adapter.parse_response(response)

class UnavailableCredentialStore:
    """非 Windows 默认边界；离线启动可用，显式 cred 访问返回稳定错误。"""

    def write(self, secret_ref: str, secret: str) -> None:
        raise JiejianError(ErrorCode.LLM_SECRET_UNAVAILABLE, "本机秘密存储不可用")

    def read(self, secret_ref: str) -> str | None:
        raise JiejianError(ErrorCode.LLM_SECRET_UNAVAILABLE, "本机秘密存储不可用")

    def delete(self, secret_ref: str) -> None:
        raise JiejianError(ErrorCode.LLM_SECRET_UNAVAILABLE, "本机秘密存储不可用")

    def configured(self, secret_ref: str | None) -> bool:
        if secret_ref is None:
            return False
        raise JiejianError(ErrorCode.LLM_SECRET_UNAVAILABLE, "本机秘密存储不可用")


def default_credential_store() -> LLMSecretStore:
    if os.name == "nt":
        return WindowsCredentialManagerSecretStore()
    return UnavailableCredentialStore()


class LLMProfileApplicationService:
    """Profile 配置编排；供应商 JSON 解析始终留在 adapter。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        transport: LLMTransport,
        secret_store: LLMSecretStore | None = None,
        environ: Mapping[str, str] | None = None,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._transport = transport
        self._secret_store = secret_store or default_credential_store()
        self._environ = os.environ if environ is None else environ
        self._clock_us = clock_us or (lambda: time.time_ns() // 1000)
        self._states: dict[str, _ConnectionState] = {}
        self._test_locks: dict[str, threading.Lock] = {}
        self._test_locks_guard = threading.Lock()

    @property
    def available(self) -> bool:
        return any(
            item.enabled and item.secret_configured
            for item in self.list()
        )

    def list(self) -> tuple[LLMProfileView, ...]:
        with self._uow_factory() as work:
            profiles = work.llm_profiles.list()
        return tuple(self._view(profile) for profile in profiles)

    def get(self, profile_name: str) -> LLMProfileView:
        with self._uow_factory() as work:
            profile = work.llm_profiles.get(profile_name)
        if profile is None:
            raise JiejianError(ErrorCode.LLM_PROFILE_NOT_FOUND, "模型 profile 不存在")
        return self._view(profile)

    def create(self, values: Mapping[str, object], *, secret: str | None = None) -> LLMProfileView:
        payload = dict(values)
        now = self._clock_us()
        payload.setdefault("created_at_us", now)
        payload.setdefault("updated_at_us", now)
        profile = self._build_profile(payload, secret=secret)
        known_secrets = self._known_secrets(profile, secret)
        with self._uow_factory(known_secrets=known_secrets) as work:
            if work.llm_profiles.get(profile.profile_name) is not None:
                raise JiejianError(ErrorCode.LLM_PROFILE_INVALID, "模型 profile 已存在")
        previous_credential = (
            self._credential_value(profile.secret_ref) if secret is not None else None
        )
        try:
            self._write_credential(profile.secret_ref, secret)
        except Exception:
            raise JiejianError(ErrorCode.LLM_SECRET_UNAVAILABLE, "秘密存储不可用") from None
        try:
            with self._uow_factory(known_secrets=known_secrets) as work:
                work.llm_profiles.add(profile)
                work.commit()
        except JiejianError:
            self._restore_credential(profile.secret_ref, previous_credential)
            raise
        except Exception:
            self._restore_credential(profile.secret_ref, previous_credential)
            raise _safe_profile_error()
        self._states.pop(profile.profile_name, None)
        return self._view(profile)

    def update(
        self,
        profile_name: str,
        values: Mapping[str, object],
        *,
        secret: str | None = None,
    ) -> LLMProfileView:
        with self._uow_factory() as work:
            current = work.llm_profiles.get(profile_name)
        if current is None:
            raise JiejianError(ErrorCode.LLM_PROFILE_NOT_FOUND, "模型 profile 不存在")
        merged = current.model_dump(mode="python")
        merged.update({key: value for key, value in values.items() if key in values})
        if secret is not None:
            if current.secret_ref is not None and current.secret_ref.startswith("env:"):
                raise JiejianError(ErrorCode.LLM_PROFILE_INVALID, "更新秘密时不得覆盖环境变量引用")
            merged.pop("secret_ref", None)
        merged["profile_name"] = profile_name
        merged["created_at_us"] = current.created_at_us
        merged["updated_at_us"] = self._clock_us()
        profile = self._build_profile(merged, secret=secret)
        old_credential = (
            self._credential_value(current.secret_ref) if secret is not None else None
        )
        known_secrets = self._known_secrets(profile, secret, fallback=old_credential)
        try:
            self._write_credential(profile.secret_ref, secret)
        except Exception:
            raise JiejianError(ErrorCode.LLM_SECRET_UNAVAILABLE, "秘密存储不可用") from None
        try:
            with self._uow_factory(known_secrets=known_secrets) as work:
                work.llm_profiles.replace(profile)
                work.commit()
        except JiejianError:
            self._restore_credential(profile.secret_ref, old_credential)
            raise
        except Exception:
            self._restore_credential(profile.secret_ref, old_credential)
            raise _safe_profile_error()
        self._states.pop(profile.profile_name, None)
        return self._view(profile)

    def test_connection(self, profile_name: str) -> LLMProfileView:
        with self._uow_factory() as work:
            profile = work.llm_profiles.get(profile_name)
        if profile is None:
            raise JiejianError(ErrorCode.LLM_PROFILE_NOT_FOUND, "模型 profile 不存在")
        with self._test_locks_guard:
            lock = self._test_locks.setdefault(profile_name, threading.Lock())
            if not lock.acquire(blocking=False):
                raise JiejianError(ErrorCode.LLM_TEST_IN_PROGRESS, "模型连接测试正在进行")
            self._states[profile_name] = _ConnectionState(status="testing")
        try:
            started = self._clock_us()
            try:
                secret = self._resolve_secret(profile.secret_ref)
                prompt = "ping"
                if len(prompt.encode("utf-8")) > min(profile.max_input_bytes, 64):
                    raise LLMTransportError("budget_exceeded")
                if profile.max_budget_microusd <= 0:
                    raise LLMTransportError("budget_exceeded")
                adapter = self._adapter(profile.provider)
                request = adapter.build_request(profile, secret, prompt)
                if len(request.body) > profile.max_input_bytes:
                    raise LLMTransportError("budget_exceeded")
                response = self._transport.send(request)
                if len(response.body) > profile.max_output_bytes:
                    raise LLMTransportError("response_too_large")
                adapter.parse_response(response)
            except JiejianError as exc:
                self._record_failure(profile_name, started, exc.code)
                raise
            except LLMTransportError as exc:
                code = _error_for_transport(exc.kind)
                self._record_failure(profile_name, started, code.value)
                raise JiejianError(code, "模型连接测试失败") from None
            duration_ms = max(0, (self._clock_us() - started) // 1000)
            self._states[profile_name] = _ConnectionState(
                status="available",
                tested_at_us=self._clock_us(),
                duration_ms=duration_ms,
            )
            return self._view(profile)
        finally:
            lock.release()

    def resolve_provider(self, profile_name: str) -> ResolvedLLMProvider:
        with self._uow_factory() as work:
            profile = work.llm_profiles.get(profile_name)
        if profile is None:
            raise JiejianError(ErrorCode.LLM_PROFILE_NOT_FOUND, "模型 profile 不存在")
        if not profile.enabled:
            raise JiejianError(ErrorCode.LLM_PROVIDER_UNAVAILABLE, "模型 profile 不可用")
        secret = self._resolve_secret(profile.secret_ref)
        adapter = self._adapter(profile.provider)
        return ResolvedLLMProvider(
            provider=profile.provider,
            profile_name=profile.profile_name,
            model=profile.model,
            adapter_version="1",
            prompt_version="1",
            input_max_bytes=profile.max_input_bytes,
            output_max_bytes=profile.max_output_bytes,
            budget_limit_microusd=profile.max_budget_microusd,
            _adapter=adapter,
            _transport=self._transport,
            _secret=secret,
            _profile=profile,
            known_secrets=(secret,),
        )

    def _build_profile(self, values: Mapping[str, object], *, secret: str | None) -> LLMProfileConfig:
        payload = dict(values)
        if secret is not None:
            if payload.get("secret_ref") is not None:
                raise JiejianError(ErrorCode.LLM_PROFILE_INVALID, "secret 与 secret_ref 不能同时提供")
            profile_name = payload.get("profile_name")
            if not isinstance(profile_name, str):
                raise JiejianError(ErrorCode.LLM_PROFILE_INVALID, "模型 profile 名称无效")
            payload["secret_ref"] = f"cred:jiejian/llm/{profile_name}"
        try:
            return LLMProfileConfig.model_validate(payload)
        except Exception:
            raise JiejianError(ErrorCode.LLM_PROFILE_INVALID, "模型 profile 配置无效") from None

    def _resolve_secret(self, secret_ref: str | None) -> str:
        if secret_ref is None:
            raise JiejianError(ErrorCode.LLM_SECRET_UNAVAILABLE, "模型秘密未配置")
        if secret_ref.startswith("env:"):
            value = self._environ.get(secret_ref.removeprefix("env:"))
        else:
            try:
                value = self._secret_store.read(secret_ref)
            except Exception:
                raise JiejianError(
                    ErrorCode.LLM_SECRET_UNAVAILABLE,
                    "模型秘密存储不可用",
                ) from None
        if not value:
            raise JiejianError(ErrorCode.LLM_SECRET_UNAVAILABLE, "模型秘密未配置")
        return value

    def _credential_value(self, secret_ref: str | None) -> str | None:
        if secret_ref is None or not secret_ref.startswith("cred:"):
            return None
        try:
            return self._secret_store.read(secret_ref)
        except Exception:
            raise JiejianError(
                ErrorCode.LLM_SECRET_UNAVAILABLE,
                "模型秘密存储不可用",
            ) from None

    def _known_secrets(
        self,
        profile: LLMProfileConfig,
        secret: str | None,
        *,
        fallback: str | None = None,
    ) -> tuple[str, ...]:
        value = secret
        if value is None and profile.secret_ref is not None:
            if profile.secret_ref.startswith("env:"):
                value = self._environ.get(profile.secret_ref.removeprefix("env:"))
            else:
                value = fallback
        return (value,) if value else ()

    def _write_credential(self, secret_ref: str | None, secret: str | None) -> None:
        if secret is not None:
            if secret_ref is None:
                raise JiejianError(ErrorCode.LLM_PROFILE_INVALID, "秘密引用缺失")
            self._secret_store.write(secret_ref, secret)

    def _restore_credential(self, secret_ref: str | None, previous: str | None) -> None:
        if secret_ref is None:
            return
        try:
            if previous is None:
                self._secret_store.delete(secret_ref)
            else:
                self._secret_store.write(secret_ref, previous)
        except Exception:
            raise JiejianError(ErrorCode.LLM_SECRET_UNAVAILABLE, "秘密补偿失败") from None

    def _record_failure(self, profile_name: str, started: int, code: str) -> LLMProfileView:
        duration_ms = max(0, (self._clock_us() - started) // 1000)
        status: ConnectionStatus = "unavailable"
        self._states[profile_name] = _ConnectionState(
            status=status,
            tested_at_us=self._clock_us(),
            duration_ms=duration_ms,
            error_code=code,
            error_message="模型连接测试失败",
        )
        return self.get(profile_name)

    def _adapter(self, provider: LLMProviderType) -> LLMAdapter:
        if provider is LLMProviderType.GEMINI:
            return GeminiAdapter()
        return OpenAICompatibleAdapter(provider)

    def _view(self, profile: LLMProfileConfig) -> LLMProfileView:
        state = self._states.get(profile.profile_name)
        configured = self._secret_configured(profile.secret_ref)
        status = state.status if state else ("configured" if configured else "unknown")
        if not configured and status in {"configured", "available"}:
            status = "unknown"
        return LLMProfileView(
            **profile.model_dump(mode="python"),
            secret_configured=configured,
            connection_status=status,
            tested_at_us=state.tested_at_us if state else None,
            duration_ms=state.duration_ms if state else None,
            error_code=state.error_code if state else None,
            error_message=state.error_message if state else None,
        )

    def _secret_configured(self, secret_ref: str | None) -> bool:
        if secret_ref is None:
            return False
        if secret_ref.startswith("env:"):
            return bool(self._environ.get(secret_ref.removeprefix("env:")))
        try:
            return self._secret_store.configured(secret_ref)
        except Exception:
            return False


def _error_for_transport(kind: str) -> ErrorCode:
    return {
        "auth_failed": ErrorCode.LLM_AUTH_FAILED,
        "rate_limited": ErrorCode.LLM_RATE_LIMITED,
        "timeout": ErrorCode.LLM_TIMEOUT,
        "invalid_response": ErrorCode.LLM_INVALID_RESPONSE,
        "budget_exceeded": ErrorCode.LLM_BUDGET_EXCEEDED,
        "response_too_large": ErrorCode.LLM_BUDGET_EXCEEDED,
        "invalid_request": ErrorCode.LLM_BUDGET_EXCEEDED,
        "provider_unavailable": ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE,
        "network": ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE,
    }.get(kind, ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE)


def _safe_profile_error() -> JiejianError:
    return JiejianError(ErrorCode.LLM_PROFILE_STORAGE_FAILED, "模型 profile 保存失败")
