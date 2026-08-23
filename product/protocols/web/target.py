# =============================================================================
# Web Target 协议
#
# 定位
#   Web Runtime 的业务目标与授权 scope wire 模型。
#
# 职责
#   规范化 Web origin/host/port｜约束私网、请求和响应预算｜冻结 reset 入口
#
# 边界
#   不包含身份、HTTP Workflow、Verification 或未来 Target 定义。
# =============================================================================

from __future__ import annotations

import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from product.protocols.execution import ProtocolModel


class WebTargetScope(ProtocolModel):
    """Web 目标的协议级授权范围。"""

    base_url: str
    allowed_origins: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    allowed_ports: tuple[int, ...]
    allow_private_network: bool = False
    follow_redirects: Literal[False] = False
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    max_requests: int = Field(default=64, ge=1, le=500)
    max_response_bytes: int = Field(default=262_144, ge=1, le=4_194_304)

    @field_validator("allowed_hosts")
    @classmethod
    def normalize_hosts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(value.strip().lower() for value in values))
        if not normalized or any(not value for value in normalized):
            raise ValueError("allowed_hosts must contain explicit hosts")
        try:
            return tuple(str(ipaddress.IPv4Address(value)) for value in normalized)
        except ipaddress.AddressValueError as exc:
            raise ValueError("allowed_hosts must be IPv4 literals") from exc

    @field_validator("allowed_ports")
    @classmethod
    def normalize_ports(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        normalized = tuple(dict.fromkeys(values))
        if not normalized or any(port < 1 or port > 65535 for port in normalized):
            raise ValueError("allowed_ports must contain valid explicit ports")
        return normalized

    @model_validator(mode="after")
    def validate_scope(self) -> WebTargetScope:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(
                "base_url must be an HTTP origin without user information"
            )
        if (
            parsed.hostname is None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an origin without path, query, or fragment")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            host = str(ipaddress.IPv4Address(parsed.hostname.lower()))
        except (ValueError, ipaddress.AddressValueError) as exc:
            raise ValueError("base_url must use an IPv4 literal and valid port") from exc
        if host not in self.allowed_hosts or port not in self.allowed_ports:
            raise ValueError("base_url is outside the declared host or port allowlist")
        origins: list[str] = []
        for raw_origin in self.allowed_origins:
            origin = urlsplit(raw_origin)
            if (
                origin.scheme not in {"http", "https"}
                or origin.hostname is None
                or origin.username is not None
                or origin.password is not None
                or origin.path not in {"", "/"}
                or origin.query
                or origin.fragment
            ):
                raise ValueError(
                    "allowed_origins must contain normalized HTTP origins"
                )
            try:
                origin_port = origin.port or (
                    443 if origin.scheme == "https" else 80
                )
                origin_host = str(ipaddress.IPv4Address(origin.hostname.lower()))
            except (ValueError, ipaddress.AddressValueError) as exc:
                raise ValueError(
                    "allowed_origins must use IPv4 literals and valid ports"
                ) from exc
            origins.append(f"{origin.scheme}://{origin_host}:{origin_port}")
        normalized_origins = tuple(dict.fromkeys(origins))
        if f"{parsed.scheme}://{host}:{port}" not in normalized_origins:
            raise ValueError("base_url origin is outside allowed_origins")
        if not self.allow_private_network and not ipaddress.IPv4Address(host).is_global:
            raise ValueError(
                "private or local base_url requires explicit authorization"
            )
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        object.__setattr__(self, "allowed_origins", normalized_origins)
        return self


class WebTargetDefinition(ProtocolModel):
    scope: WebTargetScope
    reset_path: str = Field(pattern=r"^/[A-Za-z0-9_./{}-]{1,255}$")

