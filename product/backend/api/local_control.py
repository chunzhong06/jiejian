# =============================================================================
# 本地控制面安全门
#
# 定位
#   浏览器、静态界面与所有 API Router 之前的单实例访问边界
#
# 职责
#   固定 Host｜签发进程内控制会话｜验证写请求精确同源 Origin
#
# 边界
#   令牌只驻留当前服务内存与 HttpOnly Cookie；不信任代理头，也不参与业务授权。
#
# 调用链
#   Browser / TestClient → LocalControlGuard → FastAPI Router / StaticFiles
# =============================================================================

from __future__ import annotations

import secrets
from dataclasses import dataclass
from hmac import compare_digest
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from product.backend.core.errors import ErrorCode, JiejianError


@dataclass(frozen=True, slots=True)
class LocalControlDecision:
    allowed: bool
    issue_session: bool = False


class LocalControlGuard:
    """把一次服务进程绑定到唯一 IPv4 loopback origin 和随机浏览器会话。"""

    cookie_name = "jiejian_control_session"
    _unsafe_methods = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def __init__(
        self,
        control_origin: str,
        *,
        session_token: str | None = None,
    ) -> None:
        self.origin, self.host = self._normalize_origin(control_origin)
        token = session_token or secrets.token_urlsafe(32)
        if len(token.encode("utf-8")) < 32 or "\x00" in token:
            raise ValueError("local control session token is too short or invalid")
        self._session_token = token

    def authorize(self, request: Request) -> LocalControlDecision:
        """拒绝跨 Host、跨实例或跨站写请求；根页面负责取得当前实例 Cookie。"""

        if request.headers.get("host", "").casefold() != self.host:
            return LocalControlDecision(allowed=False)
        if request.url.path == "/" and request.method == "GET":
            return LocalControlDecision(allowed=True, issue_session=True)
        if request.url.path != "/api" and not request.url.path.startswith("/api/"):
            return LocalControlDecision(allowed=True)
        presented = request.cookies.get(self.cookie_name)
        if presented is None or not compare_digest(presented, self._session_token):
            return LocalControlDecision(allowed=False)
        if (
            request.method in self._unsafe_methods
            and request.headers.get("origin") != self.origin
        ):
            return LocalControlDecision(allowed=False)
        return LocalControlDecision(allowed=True)

    def issue_session_cookie(self, response: Response) -> None:
        """覆盖浏览器可能保留的旧实例 Cookie，不把令牌暴露给前端脚本。"""

        response.set_cookie(
            key=self.cookie_name,
            value=self._session_token,
            httponly=True,
            secure=False,
            samesite="strict",
            path="/api",
        )

    @staticmethod
    def rejected_response(trace_id: str) -> JSONResponse:
        error = JiejianError(
            ErrorCode.API_CONTROL_REJECTED,
            "本地控制请求未通过当前界鉴实例校验，请从界鉴页面重试",
        )
        return JSONResponse(
            status_code=403,
            content={
                "schema_version": "1",
                "error": error.to_dict(),
                "trace_id": trace_id,
            },
        )

    @staticmethod
    def _normalize_origin(value: str) -> tuple[str, str]:
        parsed = urlsplit(value)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("local control origin has an invalid port") from exc
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or port is None
            or not 1 <= port <= 65535
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "local control origin must be an explicit IPv4 loopback HTTP origin"
            )
        origin = f"http://127.0.0.1:{port}"
        if value.rstrip("/") != origin:
            raise ValueError("local control origin must already be normalized")
        return origin, f"127.0.0.1:{port}"
