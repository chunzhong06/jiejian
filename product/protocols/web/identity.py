# =============================================================================
# Web 身份协议
#
# 定位
#   Web Execution Profile 与身份运行时之间的无秘密 wire 边界。
#
# 职责
#   定义 Cookie/Header/Login/OAuth 绑定｜约束 Auth scope 与 Bootstrap｜收集 secret ref
#
# 边界
#   只保存环境引用，不解析秘密、不保存 Cookie，不包含业务 TARGET 或 Verification。
# =============================================================================

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from product.backend.core.identifiers import PROJECT_ID_PATTERN
from product.protocols.execution import ProtocolModel
from product.protocols.web.workflow import (
    HttpRequestTemplate,
    ValueSlotSource,
)


_IDENTIFIER = r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$"
_PATH = r"^/[A-Za-z0-9_./{}~:@%+\-]*$"


class HttpIdentityKind(StrEnum):
    BEARER = "BEARER"
    STATIC_HEADERS = "STATIC_HEADERS"
    COOKIE_SESSION = "COOKIE_SESSION"
    LOGIN_WORKFLOW = "LOGIN_WORKFLOW"
    OAUTH2_CLIENT_CREDENTIALS = "OAUTH2_CLIENT_CREDENTIALS"
    OAUTH2_REFRESH_TOKEN = "OAUTH2_REFRESH_TOKEN"


class IdentityBootstrapRequest(ProtocolModel):
    template_id: str = Field(pattern=_IDENTIFIER)
    request_template: HttpRequestTemplate


class AuthTargetScope(ProtocolModel):
    """身份端点的独立授权范围；不能借用业务目标预算。"""

    base_url: str = Field(min_length=1, max_length=2048)
    allowed_origins: tuple[str, ...] = Field(min_length=1, max_length=16)
    allowed_hosts: tuple[str, ...] = Field(min_length=1, max_length=16)
    allowed_ports: tuple[int, ...] = Field(min_length=1, max_length=16)
    allow_private_network: bool = False
    follow_redirects: Literal[False] = False
    max_requests: int = Field(default=8, ge=1, le=64)
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    max_response_bytes: int = Field(default=262_144, ge=1, le=4_194_304)

    @model_validator(mode="after")
    def validate_scope(self) -> AuthTargetScope:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("auth scope must be an HTTP origin")
        try:
            host = str(ipaddress.IPv4Address(parsed.hostname))
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except (ipaddress.AddressValueError, ValueError) as exc:
            raise ValueError("auth scope must use an IPv4 literal and valid port") from exc
        address = ipaddress.IPv4Address(host)
        if (
            address.is_link_local
            or address.is_reserved
            or address.is_unspecified
            or address.is_multicast
        ):
            raise ValueError("auth scope address is not allowed")
        if not address.is_global and not self.allow_private_network:
            raise ValueError("auth scope private network requires explicit authorization")
        origins: list[str] = []
        for raw_origin in self.allowed_origins:
            candidate = urlsplit(raw_origin)
            if (
                candidate.scheme not in {"http", "https"}
                or candidate.hostname is None
                or candidate.username
                or candidate.password
                or candidate.path not in {"", "/"}
                or candidate.query
                or candidate.fragment
            ):
                raise ValueError(
                    "auth allowed_origins must contain normalized HTTP origins"
                )
            try:
                candidate_host = str(ipaddress.IPv4Address(candidate.hostname))
                candidate_port = candidate.port or (
                    443 if candidate.scheme == "https" else 80
                )
            except (ipaddress.AddressValueError, ValueError) as exc:
                raise ValueError(
                    "auth allowed_origins must use IPv4 literals"
                ) from exc
            origins.append(
                f"{candidate.scheme}://{candidate_host}:{candidate_port}"
            )
        normalized_origins = tuple(dict.fromkeys(origins))
        normalized_hosts = tuple(
            dict.fromkeys(str(ipaddress.IPv4Address(item)) for item in self.allowed_hosts)
        )
        normalized_ports = tuple(dict.fromkeys(self.allowed_ports))
        origin = f"{parsed.scheme}://{host}:{port}"
        if (
            origin not in normalized_origins
            or host not in normalized_hosts
            or port not in normalized_ports
        ):
            raise ValueError("auth scope base origin must be explicitly allowed")
        object.__setattr__(self, "base_url", origin)
        object.__setattr__(self, "allowed_origins", normalized_origins)
        object.__setattr__(self, "allowed_hosts", normalized_hosts)
        object.__setattr__(self, "allowed_ports", normalized_ports)
        return self


class BearerIdentityBinding(ProtocolModel):
    kind: Literal[HttpIdentityKind.BEARER] = HttpIdentityKind.BEARER
    secret_ref: str = Field(pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")


class StaticHeaderCredential(ProtocolModel):
    """一个有界身份头，只持有秘密引用。"""

    name: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.~\-]+$"
    )
    secret_ref: str = Field(pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")

    @field_validator("name")
    @classmethod
    def reject_reserved_name(cls, value: str) -> str:
        name = value.lower()
        if (
            name
            in {"host", "content-length", "transfer-encoding", "connection", "cookie"}
            or name.startswith("x-jiejian-")
        ):
            raise ValueError("static identity header name is reserved")
        return value


class StaticHeadersIdentityBinding(ProtocolModel):
    kind: Literal[HttpIdentityKind.STATIC_HEADERS] = HttpIdentityKind.STATIC_HEADERS
    headers: tuple[StaticHeaderCredential, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_headers(self) -> StaticHeadersIdentityBinding:
        names: set[str] = set()
        for header in self.headers:
            if header.name.lower() in names:
                raise ValueError("static identity headers must be unique")
            names.add(header.name.lower())
        return self


class CookieSessionIdentityBinding(ProtocolModel):
    kind: Literal[HttpIdentityKind.COOKIE_SESSION] = HttpIdentityKind.COOKIE_SESSION
    bootstrap_template_ids: tuple[str, ...] = Field(default=(), max_length=32)
    csrf_slot_id: str | None = Field(default=None, pattern=_IDENTIFIER)


class LoginWorkflowIdentityBinding(ProtocolModel):
    kind: Literal[HttpIdentityKind.LOGIN_WORKFLOW] = HttpIdentityKind.LOGIN_WORKFLOW
    workflow_id: str = Field(pattern=_IDENTIFIER)
    csrf_slot_id: str | None = Field(default=None, pattern=_IDENTIFIER)


class OAuth2ClientCredentialsIdentityBinding(ProtocolModel):
    kind: Literal[HttpIdentityKind.OAUTH2_CLIENT_CREDENTIALS] = (
        HttpIdentityKind.OAUTH2_CLIENT_CREDENTIALS
    )
    token_path: str = Field(pattern=_PATH)
    client_id_ref: str = Field(pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")
    client_secret_ref: str = Field(pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")
    scope: str | None = Field(default=None, max_length=256)
    auth_scope: AuthTargetScope


class OAuth2RefreshTokenIdentityBinding(ProtocolModel):
    kind: Literal[HttpIdentityKind.OAUTH2_REFRESH_TOKEN] = (
        HttpIdentityKind.OAUTH2_REFRESH_TOKEN
    )
    token_path: str = Field(pattern=_PATH)
    client_id_ref: str = Field(pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")
    refresh_token_ref: str = Field(pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")
    auth_scope: AuthTargetScope


HttpIdentityBinding: TypeAlias = Annotated[
    BearerIdentityBinding
    | StaticHeadersIdentityBinding
    | CookieSessionIdentityBinding
    | LoginWorkflowIdentityBinding
    | OAuth2ClientCredentialsIdentityBinding
    | OAuth2RefreshTokenIdentityBinding,
    Field(discriminator="kind"),
]


class WebExecutionIdentity(ProtocolModel):
    """Web 执行配置中的身份，只保存非秘密环境引用。"""

    identity_id: str = Field(pattern=PROJECT_ID_PATTERN)
    role: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, min_length=1, max_length=128)
    binding: HttpIdentityBinding
    bootstrap_requests: tuple[IdentityBootstrapRequest, ...] = Field(
        default=(), max_length=32
    )

    @model_validator(mode="after")
    def validate_bootstrap(self) -> WebExecutionIdentity:
        ids = tuple(item.template_id for item in self.bootstrap_requests)
        if len(set(ids)) != len(ids):
            raise ValueError("identity bootstrap request IDs must be unique")
        if isinstance(self.binding, CookieSessionIdentityBinding):
            if ids != self.binding.bootstrap_template_ids or not ids:
                raise ValueError(
                    "COOKIE_SESSION bootstrap requests must exactly match declared template IDs"
                )
        elif isinstance(self.binding, LoginWorkflowIdentityBinding):
            if not ids:
                raise ValueError("LOGIN_WORKFLOW requires frozen bootstrap requests")
        elif self.binding.kind in {
            HttpIdentityKind.BEARER,
            HttpIdentityKind.STATIC_HEADERS,
            HttpIdentityKind.OAUTH2_CLIENT_CREDENTIALS,
            HttpIdentityKind.OAUTH2_REFRESH_TOKEN,
        } and ids:
            raise ValueError(
                "this identity kind cannot carry business-origin bootstrap requests"
            )
        csrf_slot_id = getattr(self.binding, "csrf_slot_id", None)
        completed: set[str] = set()
        produced: dict[str, str] = {}
        prior_sources = {
            ValueSlotSource.PRIOR_STEP_JSON_PATH,
            ValueSlotSource.PRIOR_STEP_HEADER,
            ValueSlotSource.PRIOR_STEP_COOKIE,
            ValueSlotSource.PRIOR_STEP_LOCATION,
        }
        for request in self.bootstrap_requests:
            for slot in request.request_template.input_slots:
                if slot.source in {
                    ValueSlotSource.CASE_SUBJECT_ID,
                    ValueSlotSource.CASE_RESOURCE_ID,
                }:
                    raise ValueError(
                        "identity bootstrap cannot consume business case slots"
                    )
                if slot.source in prior_sources and (
                    slot.producer_step_id not in completed
                    or produced.get(slot.slot_id) != slot.producer_step_id
                ):
                    raise ValueError(
                        "identity bootstrap slot must reference an earlier declared extractor"
                    )
            for extractor in request.request_template.response_extractors:
                produced[extractor.extractor_id] = request.template_id
            completed.add(request.template_id)
        if csrf_slot_id is not None:
            extractors = {
                item.extractor_id: item
                for request in self.bootstrap_requests
                for item in request.request_template.response_extractors
            }
            extractor = extractors.get(csrf_slot_id)
            if extractor is None or not extractor.secret:
                raise ValueError(
                    "CSRF slot must come from an explicitly secret bootstrap extractor"
                )
        return self


def binding_secret_refs(value: Any) -> tuple[str, ...]:
    found: list[str] = []
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                if (
                    isinstance(key, str)
                    and key.endswith("_ref")
                    and isinstance(child, str)
                ):
                    found.append(child)
                pending.append(child)
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
    return tuple(found)


def required_identity_secret_refs(
    identity: WebExecutionIdentity,
) -> tuple[str, ...]:
    references = list(binding_secret_refs(identity.binding.model_dump(mode="python")))
    references.extend(
        binding_secret_refs(
            tuple(
                item.model_dump(mode="python")
                for item in identity.bootstrap_requests
            )
        )
    )
    return tuple(dict.fromkeys(references))
