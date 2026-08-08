"""阶段 1 所有 HTTP 请求共用的目标范围安全边界。"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from .domain.stage1 import TargetScope, _is_restricted_address
from .errors import ErrorCode, JiejianError

_METADATA_ADDRESSES = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
}
_EXPLICIT_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "fc00::/7", "::1/128")
)


@dataclass(frozen=True, slots=True)
class AuthorizedTarget:
    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


class TargetGuard:
    """在发出请求前重新解析并授权目标，不允许调用方绕过。"""

    def __init__(self, scope: TargetScope) -> None:
        self.scope = scope

    def authorize_path(self, path: str) -> AuthorizedTarget:
        parsed = urlsplit(path)
        if not path.startswith("/") or parsed.scheme or parsed.netloc:
            raise JiejianError(
                ErrorCode.SCOPE_URL,
                "请求路径必须是当前目标下的绝对路径引用",
            )
        return self.authorize_url(f"{self.scope.base_url}{path}")

    def authorize_url(self, url: str) -> AuthorizedTarget:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise JiejianError(ErrorCode.SCOPE_URL, "只允许 HTTP 或 HTTPS 目标")
        if parsed.username is not None or parsed.password is not None:
            raise JiejianError(ErrorCode.SCOPE_URL, "目标 URL 不得包含用户信息")
        if parsed.hostname is None:
            raise JiejianError(ErrorCode.SCOPE_URL, "目标 URL 缺少主机")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise JiejianError(ErrorCode.SCOPE_PORT, "目标端口无效") from exc
        host = parsed.hostname.lower()
        if host not in self.scope.allowed_hosts:
            raise JiejianError(ErrorCode.SCOPE_HOST, "目标主机不在授权范围")
        if port not in self.scope.allowed_ports:
            raise JiejianError(ErrorCode.SCOPE_PORT, "目标端口不在授权范围")
        origin = f"{parsed.scheme}://{host}:{port}"
        if origin not in self.scope.allowed_origins:
            raise JiejianError(ErrorCode.SCOPE_HOST, "目标 origin 不在授权范围")

        try:
            address = ipaddress.IPv4Address(host)
        except ipaddress.AddressValueError as exc:
            raise JiejianError(
                ErrorCode.SCOPE_HOST,
                "阶段 1 可执行目标必须使用 IPv4 字面量",
            ) from exc
        if (
            address in _METADATA_ADDRESSES
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise JiejianError(
                ErrorCode.SCOPE_PRIVATE_NETWORK,
                "目标地址属于禁止访问的本地或元数据范围",
            )
        if _is_restricted_address(address) and not (
            self.scope.allow_private_network
            and any(address in network for network in _EXPLICIT_PRIVATE_NETWORKS)
        ):
            raise JiejianError(
                ErrorCode.SCOPE_PRIVATE_NETWORK,
                "目标地址不属于显式允许的公网、私网或环回范围",
            )
        return AuthorizedTarget(
            url=url,
            host=host,
            port=port,
            addresses=(str(address),),
        )

    def authorize_redirect(self, current_url: str, location: str) -> AuthorizedTarget:
        try:
            return self.authorize_url(urljoin(current_url, location))
        except JiejianError as exc:
            raise JiejianError(
                ErrorCode.SCOPE_REDIRECT,
                "响应重定向目标越出授权范围",
                details={"cause": exc.code},
            ) from exc
