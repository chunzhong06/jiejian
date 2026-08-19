# =============================================================================
# Verification HTTP 执行
#
# 定位
#   所有 Verification 目标请求的受控网络适配器
#
# 职责
#   逐次目标授权｜请求与响应预算｜重定向、超时和取消处理
#
# 调用链
#   Runner → HttpExecutionAdapter → TargetGuard / httpx
# =============================================================================

from __future__ import annotations

import json
import ipaddress
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.redaction import redact_known_secrets
from product.backend.core.verification.facts import ExecutionFact, ExecutionOutcome, TargetType
from product.protocols.runner import ActionExecutionBinding, WebTargetDefinition

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
class HttpResponse:
    """保存目标返回的状态码和已解析、已脱敏响应数据。"""

    status_code: int
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AuthorizedTarget:
    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


class WebTargetGuard:
    """在 HTTP 适配器边界内执行 Web scope、重定向和私网安全校验。"""

    def __init__(self, target: WebTargetDefinition) -> None:
        self.target = target
        self.scope = target.scope

    def authorize_path(self, path: str) -> AuthorizedTarget:
        parsed = urlsplit(path)
        if not path.startswith("/") or parsed.scheme or parsed.netloc:
            raise JiejianError(ErrorCode.SCOPE_URL, "请求路径必须是当前目标下的绝对路径引用")
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
            raise JiejianError(ErrorCode.SCOPE_HOST, "可执行目标必须使用 IPv4 字面量") from exc
        if address in _METADATA_ADDRESSES or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified:
            raise JiejianError(ErrorCode.SCOPE_PRIVATE_NETWORK, "目标地址属于禁止访问的本地或元数据范围")
        if not address.is_global and not (
            self.scope.allow_private_network
            and any(address in network for network in _EXPLICIT_PRIVATE_NETWORKS)
        ):
            raise JiejianError(ErrorCode.SCOPE_PRIVATE_NETWORK, "目标地址不属于显式允许的公网、私网或环回范围")
        return AuthorizedTarget(url=url, host=host, port=port, addresses=(str(address),))

    def authorize_redirect(self, current_url: str, location: str) -> AuthorizedTarget:
        try:
            return self.authorize_url(urljoin(current_url, location))
        except JiejianError as exc:
            raise JiejianError(ErrorCode.SCOPE_REDIRECT, "响应重定向目标越出授权范围", details={"cause": exc.code}) from exc


class HttpExecutionAdapter:
    """作为 Verification 唯一主动 HTTP 边界，统一执行授权和资源限制。"""

    def __init__(
        self,
        target: WebTargetDefinition,
        *,
        cleanup_reserve: int = 0,
        known_secrets: tuple[str, ...] = (),
        cancellation_requested: Callable[[], bool] | None = None,
        executor_process_id: int | None = None,
    ) -> None:
        """创建不读取代理环境、不自动跟随重定向的有界 HTTP 客户端。

        关键说明
            cleanup_reserve 从总请求预算中提前留给清理操作；known_secrets 只在内存中
            用于响应脱敏，不会写入请求结果或工件。
        """

        self.target_type = TargetType.WEB
        self.guard = WebTargetGuard(target)
        self.requests_used = 0
        self.cleanup_reserve = cleanup_reserve
        self.known_secrets = known_secrets
        self.cancellation_requested = cancellation_requested or (lambda: False)
        self.executor_process_id = executor_process_id
        self.client = httpx.Client(
            follow_redirects=False,
            timeout=target.scope.timeout_seconds,
            trust_env=False,
        )

    def close(self) -> None:
        """关闭底层 httpx 客户端并释放连接资源。"""

        self.client.close()

    def execute(
        self,
        binding: ActionExecutionBinding,
        *,
        case_id: str,
        action_id: str,
        bearer_token: str | None = None,
    ) -> ExecutionFact:
        """执行 Web binding，并在 HTTP 边界内归约为通用 ExecutionFact。"""

        request_payload = {
            "action_id": action_id,
            "method": binding.method,
            "relative_path_template": binding.relative_path_template,
            "json_body": binding.json_body,
        }
        input_hash = _sha256_json(request_payload)
        empty_hash = _sha256_bytes(b"")
        try:
            response = self.request(
                binding.method,
                binding.relative_path_template,
                case_id=case_id,
                bearer_token=bearer_token,
                json_body=binding.json_body,
            )
        except JiejianError as exc:
            if exc.code in {
                ErrorCode.EXEC_TIMEOUT.value,
                ErrorCode.EXEC_REQUEST.value,
            }:
                return ExecutionFact(
                    case_id=case_id,
                    action_id=action_id,
                    target_type=self.target_type,
                    outcome=ExecutionOutcome.FAILED,
                    execution_marker=case_id,
                    input_hash=input_hash,
                    output_hash=empty_hash,
                    reason_codes=("TRANSPORT_FAILURE",),
                )
            raise
        output_hash = _sha256_json({"status": response.status_code, "data": response.data})
        if response.status_code in binding.accepted_statuses:
            outcome = ExecutionOutcome.ACCEPTED
        elif response.status_code in binding.denied_statuses:
            outcome = ExecutionOutcome.DENIED
        else:
            outcome = ExecutionOutcome.UNKNOWN
        return ExecutionFact(
            case_id=case_id,
            action_id=action_id,
            target_type=self.target_type,
            outcome=outcome,
            execution_marker=case_id,
            input_hash=input_hash,
            output_hash=output_hash,
            reason_codes=() if outcome is not ExecutionOutcome.UNKNOWN else ("UNINTERPRETED_RESPONSE",),
        )

    def cleanup(self, path: str, *, case_id: str) -> None:
        response = self.request("POST", path, case_id=case_id, cleanup_request=True, test_mode=True)
        if not 200 <= response.status_code < 300:
            raise JiejianError("EXECUTION_CLEANUP_FAILED", "目标清理失败")

    def request(
        self,
        method: str,
        path: str,
        *,
        case_id: str,
        bearer_token: str | None = None,
        json_body: dict[str, Any] | None = None,
        cleanup_request: bool = False,
        test_mode: bool = False,
    ) -> HttpResponse:
        """在授权、取消和预算限制下发送一次目标请求。

        数据流
            相对路径 → TargetGuard 授权 → 构造因果标记和可选身份头
            → 流式读取有界响应 → 校验重定向 → 脱敏并返回 HttpResponse。

        关键说明
            普通请求收到取消信号后不再发送；清理请求仍可使用预留预算完成恢复。
            客户端不会自动跟随重定向，Location 只用于确认目标没有越出授权范围。

        返回
            包含 HTTP 状态码，以及已限制大小、解析并脱敏的数据对象。
        """

        if not cleanup_request and self.cancellation_requested():
            raise JiejianError(ErrorCode.EXEC_CANCELLED, "运行已请求取消")
        target = self.guard.authorize_path(path)
        # 普通请求不能占用清理预留，保证异常或取消后仍能恢复测试状态。
        remaining_for_normal = self.guard.scope.max_requests - self.cleanup_reserve
        if self.requests_used >= self.guard.scope.max_requests or (
            not cleanup_request and self.requests_used >= remaining_for_normal
        ):
            raise JiejianError(ErrorCode.EXEC_BUDGET, "HTTP 请求预算已耗尽")
        self.requests_used += 1
        if cleanup_request and self.cleanup_reserve:
            self.cleanup_reserve -= 1
        # case ID 贯穿目标请求和样例状态，便于把副作用关联回当前攻击用例。
        headers = {"X-Jiejian-Case-ID": case_id}
        if self.executor_process_id is not None:
            headers["X-Jiejian-Runner-PID"] = str(self.executor_process_id)
        if bearer_token is not None:
            headers["Authorization"] = f"Bearer {bearer_token}"
        if test_mode:
            headers["X-Jiejian-Test-Mode"] = "1"
        try:
            with self.client.stream(
                method,
                target.url,
                headers=headers,
                json=json_body if json_body else None,
            ) as response:
                # 流式累计响应，避免先把超限内容完整读入内存。
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > self.guard.scope.max_response_bytes:
                        raise JiejianError(
                            ErrorCode.EXEC_RESPONSE_TOO_LARGE,
                            "响应体超过安全预算",
                        )
                location = response.headers.get("location")
                if 300 <= response.status_code < 400 and location:
                    self.guard.authorize_redirect(target.url, location)
                # 目标可能回显凭据，必须在离开网络边界前完成已知秘密脱敏。
                data = redact_known_secrets(
                    _decode_response(bytes(content)),
                    self.known_secrets,
                )
                return HttpResponse(status_code=response.status_code, data=data)
        except httpx.TimeoutException as exc:
            raise JiejianError(ErrorCode.EXEC_TIMEOUT, "目标请求超时") from exc
        except httpx.RequestError as exc:
            raise JiejianError(
                ErrorCode.EXEC_REQUEST,
                "目标请求失败",
                details={"reason": type(exc).__name__},
            ) from exc


def _decode_response(content: bytes) -> dict[str, Any]:
    """把响应统一转换为字典；非对象 JSON 和普通文本使用包装字段保存。"""

    if not content:
        return {}
    try:
        decoded = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"text": content.decode("utf-8", errors="replace")}
    return decoded if isinstance(decoded, dict) else {"value": decoded}


def _sha256_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))
