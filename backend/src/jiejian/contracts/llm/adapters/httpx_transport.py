"""httpx 单请求、禁重定向、流式有界响应传输。"""

from __future__ import annotations

import httpx

from .base import LLMHttpRequest, LLMHttpResponse, LLMTransportError


class HttpxLLMTransport:
    def __init__(self, *, client_transport: httpx.BaseTransport | None = None) -> None:
        self._client_transport = client_transport

    def send(self, request: LLMHttpRequest) -> LLMHttpResponse:
        timeout = httpx.Timeout(request.timeout_ms / 1000)
        try:
            with httpx.Client(
                follow_redirects=False,
                trust_env=False,
                timeout=timeout,
                transport=self._client_transport,
            ) as client:
                with client.stream(
                    "POST",
                    request.url,
                    headers=request.headers,
                    content=request.body,
                ) as response:
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > request.max_output_bytes:
                            raise LLMTransportError("response_too_large")
                    return LLMHttpResponse(response.status_code, bytes(body))
        except LLMTransportError:
            raise
        except httpx.TimeoutException:
            raise LLMTransportError("timeout") from None
        except httpx.RequestError:
            raise LLMTransportError("network") from None
