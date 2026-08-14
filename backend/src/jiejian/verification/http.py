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
#   SnapshotRunExecutor → HttpExecutor → TargetGuard / httpx
# =============================================================================

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from ..errors import ErrorCode, JiejianError
from ..redaction import redact_known_secrets
from .safety import TargetGuard


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """保存目标返回的状态码和已解析、已脱敏响应数据。"""

    status_code: int
    data: dict[str, Any]


class HttpExecutor:
    """作为 Verification 唯一主动 HTTP 边界，统一执行授权和资源限制。"""

    def __init__(
        self,
        guard: TargetGuard,
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

        self.guard = guard
        self.requests_used = 0
        self.cleanup_reserve = cleanup_reserve
        self.known_secrets = known_secrets
        self.cancellation_requested = cancellation_requested or (lambda: False)
        self.executor_process_id = executor_process_id
        self.client = httpx.Client(
            follow_redirects=False,
            timeout=guard.scope.timeout_seconds,
            trust_env=False,
        )

    def close(self) -> None:
        """关闭底层 httpx 客户端并释放连接资源。"""

        self.client.close()

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
