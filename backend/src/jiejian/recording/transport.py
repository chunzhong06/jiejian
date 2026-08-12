# =============================================================================
# Recording 路由传输
#
# 定位
#   Playwright route 与授权目标之间的受控单跳 HTTP 适配器
#
# 职责
#   每跳重新授权｜禁用自动重定向｜限制响应字节并显式关闭连接
#
# 调用链
#   RecordingEventCollector → BoundedRouteTransport → TargetGuard / httpx
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import httpx
from playwright.sync_api import BrowserContext, Request

from ..verification.models import TargetScope
from ..errors import ErrorCode, JiejianError
from ..verification.safety import TargetGuard

_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@dataclass(frozen=True, slots=True)
class BoundedHTTPResponse:
    """已经在内存预算内完整校验、可以交给浏览器的单跳响应。"""

    status_code: int
    headers: dict[str, str]
    body: bytes


class BoundedRouteTransport:
    """保持浏览器请求语义，并在读取正文前执行响应能力检查。"""

    def __init__(self, scope: TargetScope) -> None:
        self._scope = scope

    def fetch(
        self,
        request: Request,
        context: BrowserContext,
        guard: TargetGuard,
    ) -> BoundedHTTPResponse:
        guard.authorize_url(request.url)
        headers = self._end_to_end_headers(request.headers)
        if "cookie" not in headers:
            cookies = context.cookies(request.url)
            if cookies:
                headers["cookie"] = "; ".join(
                    f"{cookie['name']}={cookie['value']}" for cookie in cookies
                )
        timeout = httpx.Timeout(self._scope.timeout_seconds)
        try:
            with httpx.Client(
                follow_redirects=False,
                timeout=timeout,
                trust_env=False,
            ) as client:
                with client.stream(
                    request.method,
                    request.url,
                    headers=headers,
                    content=request.post_data_buffer,
                ) as response:
                    response_headers = self._validate_headers(
                        request.url,
                        request.method,
                        response.status_code,
                        response.headers,
                        guard,
                    )
                    body = self._read_bounded_body(response)
                    self._apply_response_cookies(
                        context,
                        request.url,
                        response,
                    )
                    return BoundedHTTPResponse(
                        status_code=response.status_code,
                        headers=response_headers,
                        body=body,
                    )
        except JiejianError:
            raise
        except httpx.HTTPError:
            raise JiejianError(
                ErrorCode.RECORD_INTERACTION_FAILED,
                "浏览器单跳请求失败",
            ) from None

    def _validate_headers(
        self,
        request_url: str,
        request_method: str,
        status_code: int,
        headers: httpx.Headers,
        guard: TargetGuard,
    ) -> dict[str, str]:
        location = headers.get("location")
        if 300 <= status_code < 400 and location:
            guard.authorize_redirect(request_url, location)

        reason = self._unsupported_reason(request_method, headers)
        if reason is not None:
            raise JiejianError(
                ErrorCode.RECORD_RESPONSE_UNSUPPORTED,
                "浏览器响应不属于 V1 有界普通 HTTP 能力范围",
            )

        return self._end_to_end_headers(
            dict(headers.items()),
            excluded={"set-cookie"},
        )

    def _unsupported_reason(
        self,
        request_method: str,
        headers: Mapping[str, str],
    ) -> str | None:
        content_type = headers.get("content-type", "").casefold()
        disposition = headers.get("content-disposition", "").casefold()
        transfer_encoding = headers.get("transfer-encoding", "").casefold()
        content_encoding = headers.get("content-encoding", "").casefold()
        if request_method == "HEAD":
            return "HEAD_UNSUPPORTED"
        if content_type.startswith("text/event-stream"):
            return "SSE_UNSUPPORTED"
        if "attachment" in disposition:
            return "DOWNLOAD_UNSUPPORTED"
        if transfer_encoding:
            return "STREAMING_UNSUPPORTED"
        if content_encoding not in {"", "identity"}:
            return "ENCODING_UNSUPPORTED"
        raw_length = headers.get("content-length")
        if raw_length is None:
            return "CONTENT_LENGTH_REQUIRED"
        try:
            length = int(raw_length)
        except ValueError:
            return "CONTENT_LENGTH_INVALID"
        if length < 0 or length > self._scope.max_response_bytes:
            return "CONTENT_LENGTH_EXCEEDED"
        return None

    def _read_bounded_body(self, response: httpx.Response) -> bytes:
        expected = int(response.headers["content-length"])
        body = bytearray()
        try:
            for chunk in response.iter_raw(
                chunk_size=min(65_536, self._scope.max_response_bytes + 1)
            ):
                if len(body) + len(chunk) > expected:
                    raise JiejianError(
                        ErrorCode.RECORD_RESPONSE_UNSUPPORTED,
                        "浏览器响应不属于 V1 有界普通 HTTP 能力范围",
                    )
                body.extend(chunk)
        except JiejianError:
            raise
        except httpx.HTTPError:
            raise JiejianError(
                ErrorCode.RECORD_RESPONSE_UNSUPPORTED,
                "浏览器响应不属于 V1 有界普通 HTTP 能力范围",
            ) from None
        if len(body) != expected:
            raise JiejianError(
                ErrorCode.RECORD_RESPONSE_UNSUPPORTED,
                "浏览器响应不属于 V1 有界普通 HTTP 能力范围",
            )
        return bytes(body)

    @staticmethod
    def _end_to_end_headers(
        headers: Mapping[str, str],
        *,
        excluded: set[str] | None = None,
    ) -> dict[str, str]:
        blocked = set(_HOP_BY_HOP_HEADERS)
        blocked.update(excluded or ())
        connection = headers.get("connection", "")
        blocked.update(
            token.strip().casefold() for token in connection.split(",") if token.strip()
        )
        return {
            name: value
            for name, value in headers.items()
            if name.casefold() not in blocked
        }

    @staticmethod
    def _apply_response_cookies(
        context: BrowserContext,
        request_url: str,
        response: httpx.Response,
    ) -> None:
        cookies: list[dict[str, object]] = []
        for cookie in response.cookies.jar:
            item: dict[str, object] = {
                "name": cookie.name,
                "value": cookie.value,
                "secure": cookie.secure,
                "httpOnly": any(
                    name.casefold() == "httponly" for name in cookie._rest
                ),
            }
            if cookie.domain_specified:
                item["domain"] = cookie.domain
                item["path"] = cookie.path or "/"
            else:
                item["url"] = request_url
            if cookie.expires is not None:
                item["expires"] = float(cookie.expires)
            same_site = next(
                (
                    str(value).casefold()
                    for name, value in cookie._rest.items()
                    if name.casefold() == "samesite"
                ),
                "",
            )
            if same_site in {"strict", "lax", "none"}:
                item["sameSite"] = same_site.title()
            cookies.append(item)
        if cookies:
            context.add_cookies(cookies)
