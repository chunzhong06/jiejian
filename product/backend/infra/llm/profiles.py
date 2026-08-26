# =============================================================================
# LLM Profile 治理
#
# 定位
#   控制面、非秘密 profile 存储与全局 AI 设置的事务边界。
#
# 职责
#   管理 profile 元数据｜执行秘密补偿｜维护连接状态视图
#
# 边界
#   不在响应中返回秘密，不在 GET/读取路径联网；provider 运行时由 provider 模块负责。
# =============================================================================

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.llm.adapters.base import LLMAdapter, LLMInvokeResult, LLMTransport, LLMTransportError
from product.backend.infra.llm.catalog import LLMModelCatalog, LLMModelCatalogService
from product.backend.infra.llm.config import AIAssistanceSettings, LLMProfileConfig, LLMProviderType, reasoning_options_for
from product.backend.infra.secrets import SecretStore, credential_ref, default_secret_store
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.infra.llm.provider import (
    ResolvedLLMProvider, _ConnectionState, _error_for_transport,
    _jiejian_error_for_transport, _safe_profile_error, adapter_for, probe_provider,
)

ConnectionStatus = Literal["testing", "configured", "available", "unavailable", "unknown"]

class LLMProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    profile_name: str
    provider: LLMProviderType
    model: str
    reasoning_effort: str | None = None
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

class LLMProfileRegistry:
    """Profile 配置编排；供应商 JSON 解析始终留在 adapter。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        transport: LLMTransport,
        secret_store: SecretStore | None = None,
        environ: Mapping[str, str] | None = None,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._transport = transport
        self._secret_store = secret_store or default_secret_store()
        self._environ = os.environ if environ is None else environ
        self._clock_us = clock_us or (lambda: time.time_ns() // 1000)
        self._catalog = LLMModelCatalogService(transport)
        self._states: dict[str, _ConnectionState] = {}
        self._test_locks: dict[str, threading.Lock] = {}
        self._test_locks_guard = threading.Lock()

    @property
    def available(self) -> bool:
        return any(
            item.enabled and item.secret_configured
            for item in self.list()
        )

    def get_settings(self) -> AIAssistanceSettings:
        with self._uow_factory() as work:
            return work.ai_assistance_settings.get()

    def update_settings(self, *, enabled: bool, default_profile_name: str | None) -> AIAssistanceSettings:
        if enabled and default_profile_name is None:
            raise JiejianError(ErrorCode.LLM_PROFILE_INVALID, "启用 AI 辅助时必须指定默认 profile")
        if default_profile_name is not None:
            with self._uow_factory() as work:
                profile = work.llm_profiles.get(default_profile_name)
            if profile is None:
                raise JiejianError(ErrorCode.LLM_PROFILE_INVALID, "默认 profile 不存在")
            if enabled and (not profile.enabled or not self._secret_configured(profile.secret_ref)):
                raise JiejianError(ErrorCode.LLM_PROFILE_INVALID, "默认 profile 不可用")
        settings = AIAssistanceSettings(
            enabled=enabled,
            default_profile_name=default_profile_name,
            updated_at_us=self._clock_us(),
        )
        with self._uow_factory() as work:
            work.ai_assistance_settings.replace(settings)
            work.commit()
        return settings

    def discover_models(
        self,
        provider: LLMProviderType,
        secret: str,
        *,
        base_url: str | None = None,
        allow_local_http: bool = False,
    ) -> LLMModelCatalog:
        try:
            return self._catalog.discover(provider, secret, base_url=base_url, allow_local_http=allow_local_http)
        except LLMTransportError as exc:
            raise _jiejian_error_for_transport(exc.kind) from None
        except ValueError:
            raise _jiejian_error_for_transport("invalid_request") from None

    def refresh_models(self, profile_name: str) -> LLMModelCatalog:
        with self._uow_factory() as work:
            profile = work.llm_profiles.get(profile_name)
        if profile is None:
            raise JiejianError(ErrorCode.LLM_PROFILE_NOT_FOUND, "模型 profile 不存在")
        try:
            return self._catalog.refresh(profile, self._resolve_secret(profile.secret_ref))
        except LLMTransportError as exc:
            raise _jiejian_error_for_transport(exc.kind) from None
        except ValueError:
            raise _jiejian_error_for_transport("invalid_request") from None

    def save_default_profile(
        self,
        values: Mapping[str, object],
        *,
        secret: str | None = None,
    ) -> LLMProfileView:
        """普通配置先做一次有界 probe，再把 profile、设置和秘密补偿式保存。"""

        # 默认目标由全局单行设置决定；首次配置才使用固定的 assistant-default。
        payload = dict(values)
        now = self._clock_us()
        with self._uow_factory() as work:
            settings = work.ai_assistance_settings.get()
            target_name = settings.default_profile_name or "assistant-default"
            current = work.llm_profiles.get(target_name)
        payload["profile_name"] = target_name
        if current is not None:
            merged = current.model_dump(mode="python")
            merged.update(payload)
            merged["created_at_us"] = current.created_at_us
            merged["updated_at_us"] = now
            payload = merged
            if secret is not None:
                if current.secret_ref is not None and current.secret_ref.startswith("env:"):
                    raise JiejianError(ErrorCode.LLM_PROFILE_INVALID, "更新秘密时不得覆盖环境变量引用")
                payload.pop("secret_ref", None)
        else:
            payload.setdefault("created_at_us", now)
            payload.setdefault("updated_at_us", now)
        profile = self._build_profile(payload, secret=secret)
        if secret is not None:
            probe_secret = secret
        else:
            probe_secret = self._resolve_secret(profile.secret_ref)
        try:
            probe_provider(self._transport, profile, probe_secret)
        except LLMTransportError as exc:
            raise _jiejian_error_for_transport(exc.kind) from None
        except ValueError:
            raise _jiejian_error_for_transport("invalid_request") from None
        previous = self._credential_value(profile.secret_ref) if secret is not None else None
        known_secrets = self._known_secrets(profile, secret, fallback=probe_secret)
        # 已有默认 profile 的普通编辑只更新模型配置，不能因保存动作重开用户已关闭的 AI。
        next_enabled = True if settings.default_profile_name is None else settings.enabled
        try:
            self._write_credential(profile.secret_ref, secret)
            with self._uow_factory(known_secrets=known_secrets) as work:
                if current is None:
                    work.llm_profiles.add(profile)
                else:
                    work.llm_profiles.replace(profile)
                work.ai_assistance_settings.replace(
                    AIAssistanceSettings(
                        enabled=next_enabled,
                        default_profile_name=target_name,
                        updated_at_us=self._clock_us(),
                    )
                )
                work.commit()
        except JiejianError:
            if secret is not None:
                self._restore_credential(profile.secret_ref, previous)
            raise
        except Exception:
            if secret is not None:
                self._restore_credential(profile.secret_ref, previous)
            raise _safe_profile_error()
        self._states.pop(profile.profile_name, None)
        return self._view(profile)

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
        """创建非秘密 profile，并在数据库失败时恢复此前的凭据状态。"""

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
        # 凭据管理器和数据库无法共享事务，因此显式保存旧值作为补偿回滚点。
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
        """更新 profile；秘密写入失败或持久化失败时保持原配置和凭据一致。"""

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
        """以最小 ``ping`` 请求测试连接；同一 profile 只允许一个并发测试。"""

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
                probe_provider(self._transport, profile, secret, prompt=prompt)
            except JiejianError as exc:
                self._record_failure(profile_name, started, exc.code)
                raise
            except LLMTransportError as exc:
                code = _error_for_transport(exc.kind)
                self._record_failure(profile_name, started, code.value)
                raise JiejianError(code, "模型连接测试失败") from None
            except ValueError:
                code = _error_for_transport("invalid_request")
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
            # 所有失败分支都必须释放 profile 级锁，否则后续测试会永久显示进行中。
            lock.release()

    def resolve_provider(self, profile_name: str) -> ResolvedLLMProvider:
        """解析单次调用对象；返回值持有秘密但其 repr、持久化和错误均不暴露秘密。"""

        with self._uow_factory() as work:
            profile = work.llm_profiles.get(profile_name)
        if profile is None:
            raise JiejianError(ErrorCode.LLM_PROFILE_NOT_FOUND, "模型 profile 不存在")
        if not profile.enabled:
            raise JiejianError(ErrorCode.LLM_PROVIDER_UNAVAILABLE, "模型 profile 不可用")
        secret = self._resolve_secret(profile.secret_ref)
        adapter = adapter_for(profile.provider)
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
