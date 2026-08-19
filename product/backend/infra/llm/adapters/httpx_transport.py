# =============================================================================
# LLM HTTP 传输
#
# 定位
# provider 请求模型与 httpx 单次网络调用之间的受控传输边界。
#
# 职责
# 禁用环境代理与重定向｜执行有时限请求｜按字节预算读取响应
#
# 边界
# 只接受已规范化请求，不记录 header/body，并把网络失败归一为脱敏传输错误。
#
# 调用链
# LLMAdapter → HttpxLLMTransport → provider HTTPS endpoint
# =============================================================================

from __future__ import annotations

import httpx

from product.backend.infra.llm.adapters.base import LLMHttpRequest, LLMHttpResponse, LLMTransportError


class HttpxLLMTransport:
    """禁用环境代理和自动重定向的有界 LLM HTTP 传输。"""

    def __init__(self, *, client_transport: httpx.BaseTransport | None = None) -> None:
        self._client_transport = client_transport

    def send(self, request: LLMHttpRequest) -> LLMHttpResponse:
        """发送一次请求并流式限制响应大小；只返回稳定传输错误分类。"""

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
                    # 流式计数可在完整响应进入内存前终止超预算 provider 输出。
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
