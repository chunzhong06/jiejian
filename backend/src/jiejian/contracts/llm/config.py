"""LLM profile 的配置、URL 和秘密引用边界。"""

from __future__ import annotations

import ipaddress
import posixpath
import re
from enum import StrEnum
from typing import Literal
from urllib.parse import SplitResult, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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

    schema_version: Literal["1"] = "1"


class LLMProfileConfig(LLMConfigModel):
    """只包含非秘密持久化字段的 LLM profile。"""

    profile_name: str = Field(pattern=PROFILE_NAME_PATTERN)
    provider: LLMProviderType
    model: str = Field(min_length=1, max_length=256, pattern=_MODEL_NAME)
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
    return f"{prefix}{profile_name}"


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
