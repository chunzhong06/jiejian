# =============================================================================
# Verification 目标授权
#
# 定位
#   Verification 与 Recording 共用的每次请求前 TargetScope 安全边界
#
# 职责
#   校验 scheme/host/port｜阻止未授权私网和重定向｜返回已解析目标
#
# 调用链
#   HttpExecutor / Recording transport → TargetGuard → IPv4 / URL policy
# =============================================================================

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from .models import TargetScope, is_restricted_address
from ..errors import ErrorCode, JiejianError

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
    """保存一次授权通过的完整 URL、目标主机、端口和固定地址。"""

    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


class TargetGuard:
    """在每次请求和重定向前重新核对目标是否仍在 TargetScope 内。"""

    def __init__(self, scope: TargetScope) -> None:
        """绑定当前运行已经校验的目标授权范围。"""

        self.scope = scope

    def authorize_path(self, path: str) -> AuthorizedTarget:
        """把站内绝对路径接到 base_url，并交给完整 URL 授权。"""

        parsed = urlsplit(path)
        if not path.startswith("/") or parsed.scheme or parsed.netloc:
            raise JiejianError(
                ErrorCode.SCOPE_URL,
                "请求路径必须是当前目标下的绝对路径引用",
            )
        return self.authorize_url(f"{self.scope.base_url}{path}")

    def authorize_url(self, url: str) -> AuthorizedTarget:
        """校验完整 URL 的协议、origin、IPv4 地址和私网授权。

        数据流
            调用方 URL → 拆分 scheme/host/port → 与 TargetScope 逐项比对
            → 私网与元数据地址检查 → AuthorizedTarget。

        关键说明
            当前只接受 IPv4 字面量，因此授权结果不会在请求时再次经过 DNS。
            即使 allow_private_network 为真，云元数据、链路本地、组播和保留地址
            仍然禁止访问。

        返回
            已确认落在授权范围内、可交给网络适配器使用的 AuthorizedTarget。
        """

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
        if is_restricted_address(address) and not (
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
        """解析响应中的相对或绝对 Location，并把越界目标统一标记为重定向错误。"""

        try:
            return self.authorize_url(urljoin(current_url, location))
        except JiejianError as exc:
            raise JiejianError(
                ErrorCode.SCOPE_REDIRECT,
                "响应重定向目标越出授权范围",
                details={"cause": exc.code},
            ) from exc
