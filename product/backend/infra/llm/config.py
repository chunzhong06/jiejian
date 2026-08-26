# =============================================================================
# LLM 配置校验
#
# 定位
# provider 配置进入外部传输前的纯模型与 URL/秘密引用规范化边界。
#
# 职责
# 校验 profile 字段｜规范 provider 基址｜限制本地 HTTP 与秘密引用格式
#
# 边界
# 只处理配置结构，不读取秘密、不发起网络请求，也不接受隐式代理或任意 URL 语义。
#
# 调用链
# API / Storage → LLMProfileConfig → Provider Adapter / SecretStore
# =============================================================================

from __future__ import annotations

import ipaddress
import posixpath
import re
from enum import StrEnum
from typing import Literal
from urllib.parse import SplitResult, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.infra.secrets.refs import credential_ref


PROFILE_NAME_PATTERN = r"^[a-z][a-z0-9_-]{0,127}$"
_MODEL_NAME = r"^[^\x00-\x1f\x7f]{1,256}$"
ENV_SECRET_REF_PATTERN = r"^env:[A-Z][A-Z0-9_]{0,127}$"
_ENV_SECRET_REF = re.compile(ENV_SECRET_REF_PATTERN)
_HOSTNAME = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


class LLMProviderType(StrEnum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    OPENAI_COMPATIBLE = "openai_compatible"


class LLMConfigModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class LLMProfileConfig(LLMConfigModel):
    """只包含非秘密持久化字段的 LLM profile。"""

    profile_name: str = Field(pattern=PROFILE_NAME_PATTERN)
    provider: LLMProviderType
    model: str = Field(min_length=1, max_length=256, pattern=_MODEL_NAME)
    reasoning_effort: str | None = Field(default=None, max_length=16)
    allow_local_http: bool = False
    base_url: str | None = Field(default=None, max_length=2048)
    timeout_ms: int = Field(default=30_000, ge=100, le=300_000)
    max_input_bytes: int = Field(default=131_072, ge=1, le=1_048_576)
    max_output_bytes: int = Field(default=65_536, ge=1, le=1_048_576)
    max_budget_microusd: int = Field(default=1_000_000, ge=0, le=1_000_000_000)
    enabled: bool = True
    secret_ref: str | None = Field(default=None, max_length=256)
    created_at_us: int = Field(ge=0)
    updated_at_us: int = Field(ge=0)

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider(cls, value: object) -> LLMProviderType:
        if isinstance(value, LLMProviderType):
            return value
        if isinstance(value, str):
            try:
                return LLMProviderType(value)
            except ValueError:
                pass
        raise ValueError("unsupported LLM provider")

    @field_validator("profile_name", "model")
    @classmethod
    def validate_printable_text(cls, value: str) -> str:
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("LLM profile text must be trimmed and printable")
        return value

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return normalize_llm_base_url(
            value,
            allow_local_http=bool(info.data.get("allow_local_http", False)),
        )

    @field_validator("secret_ref")
    @classmethod
    def validate_secret_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_secret_ref(value)

    @model_validator(mode="after")
    def validate_profile(self) -> LLMProfileConfig:
        if self.updated_at_us < self.created_at_us:
            raise ValueError("LLM profile update time precedes creation")
        if self.secret_ref and self.secret_ref.startswith("cred:"):
            expected = f"cred:jiejian/llm/{self.profile_name}"
            if self.secret_ref != expected:
                raise ValueError("credential secret_ref must use the profile name")
        if self.provider is not LLMProviderType.OPENAI_COMPATIBLE and (
            self.base_url is not None or self.allow_local_http
        ):
            raise ValueError("正式供应商不得覆盖 base_url 或允许本地 HTTP")
        options = reasoning_options_for(self.provider, self.model)
        if self.reasoning_effort is not None and self.reasoning_effort not in options:
            raise ValueError("reasoning_effort 不属于当前供应商模型能力")
        return self


class AIAssistanceSettings(LLMConfigModel):
    """全局单行 AI 辅助开关；不携带项目、秘密或连接状态。"""

    enabled: bool = False
    default_profile_name: str | None = Field(default=None, pattern=PROFILE_NAME_PATTERN)
    updated_at_us: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_enabled_default(self) -> AIAssistanceSettings:
        if self.enabled and self.default_profile_name is None:
            raise ValueError("启用 AI 辅助时必须指定默认 profile")
        return self


def validate_secret_ref(value: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError("secret_ref must be an env or credential reference")
    if _ENV_SECRET_REF.fullmatch(value) is not None:
        return value
    return validate_credential_secret_ref(value)


def validate_credential_secret_ref(value: str) -> str:
    prefix = "cred:jiejian/llm/"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError("secret_ref must use the jiejian LLM credential namespace")
    profile_name = value.removeprefix(prefix)
    if re.fullmatch(PROFILE_NAME_PATTERN, profile_name) is None:
        raise ValueError("credential secret_ref profile is invalid")
    return credential_ref("llm", profile_name)


_KNOWN_REASONING_OPTIONS: dict[LLMProviderType, dict[str, tuple[str, ...]]] = {
    LLMProviderType.OPENAI: {
        model: ("none", "low", "medium", "high", "xhigh", "max")
        for model in ("gpt-5.6", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
    },
    LLMProviderType.DEEPSEEK: {
        "deepseek-v4-flash": ("high", "max"),
        "deepseek-v4-pro": ("high", "max"),
    },
    LLMProviderType.GEMINI: {
        "gemini-3.7-flash": ("low", "medium", "high"),
        "gemini-3.6-flash": ("minimal", "low", "medium", "high"),
        "gemini-3.5-flash": ("minimal", "low", "medium", "high"),
        "gemini-3.1-pro-preview": ("low", "medium", "high"),
        "gemini-3.5-flash-lite": ("minimal", "low", "medium", "high"),
        "gemini-3.1-flash-lite": ("minimal", "low", "medium", "high"),
        "gemini-3-flash-preview": ("minimal", "low", "medium", "high"),
    },
    LLMProviderType.OPENAI_COMPATIBLE: {},
}


def reasoning_options_for(provider: LLMProviderType, model: str) -> tuple[str, ...]:
    """返回后端已核验的模型能力；未知模型不做名称推测。"""

    return _KNOWN_REASONING_OPTIONS.get(provider, {}).get(model, ())


def normalize_llm_base_url(
    value: str,
    *,
    allow_local_http: bool,
    require_local_http_authorization: bool = True,
) -> str:
    """规范化并校验 provider URL，不执行 DNS 或网络访问。"""

    if not value or value != value.strip() or any(char.isspace() or ord(char) < 32 for char in value):
        raise ValueError("base_url must be trimmed and contain no whitespace")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("base_url authority is invalid") from exc
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("base_url must not contain userinfo")
    if parsed.fragment or parsed.query or parsed.scheme.lower() not in {"https", "http"}:
        raise ValueError("base_url scheme, query, and fragment are invalid")
    if not hostname:
        raise ValueError("base_url host is required")
    host = _normalize_host(hostname)
    scheme = parsed.scheme.lower()
    if scheme == "http" and require_local_http_authorization and (
        not allow_local_http or not _is_loopback_host(host)
    ):
        raise ValueError("HTTP base_url requires explicit local-loopback authorization")
    if port is not None and not 1 <= port <= 65_535:
        raise ValueError("base_url port is invalid")
    if port in ({"http": 80, "https": 443}.get(scheme), None):
        port = None
    netloc_host = f"[{host}]" if ":" in host else host
    netloc = netloc_host if port is None else f"{netloc_host}:{port}"
    path = parsed.path or "/"
    if "\\" in path or any(char.isspace() or ord(char) < 32 for char in path):
        raise ValueError("base_url path is invalid")
    normalized_path = posixpath.normpath("/" + path.lstrip("/"))
    if path.endswith("/") and normalized_path != "/":
        normalized_path += "/"
    return urlunsplit(SplitResult(scheme, netloc, normalized_path, "", ""))


def _normalize_host(hostname: str) -> str:
    try:
        return ipaddress.ip_address(hostname).compressed.lower()
    except ValueError:
        try:
            host = hostname.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError as exc:
            raise ValueError("base_url host is invalid") from exc
        if not host or ".." in host or _HOSTNAME.fullmatch(host) is None:
            raise ValueError("base_url host is invalid")
        return host


def _is_loopback_host(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
