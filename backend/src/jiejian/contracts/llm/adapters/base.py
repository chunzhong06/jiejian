"""不依赖 httpx/provider SDK 的 LLM 传输协议类型。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from ..config import LLMProfileConfig, LLMProviderType


@dataclass(frozen=True, slots=True)
class LLMHttpRequest:
    """一次请求的内部边界；repr 不包含 headers、body 或 secret。"""

    provider: LLMProviderType
    url: str
    headers: dict[str, str]
    body: bytes
    timeout_ms: int
    max_output_bytes: int

    def __repr__(self) -> str:
        return (
            "LLMHttpRequest(" 
            f"provider={self.provider.value!r}, url='<redacted>', "
            f"timeout_ms={self.timeout_ms}, max_output_bytes={self.max_output_bytes})"
        )


@dataclass(frozen=True, slots=True)
class LLMHttpResponse:
    status_code: int
    body: bytes

    def __repr__(self) -> str:
        return f"LLMHttpResponse(status_code={self.status_code}, body='<redacted>')"


class LLMTransport(Protocol):
    def send(self, request: LLMHttpRequest) -> LLMHttpResponse: ...


class LLMTransportError(Exception):
    """不携带 URL、headers、body 或上游错误文本的传输失败。"""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(kind)


class LLMAdapter(Protocol):
    provider: LLMProviderType

    def build_request(
        self,
        profile: LLMProfileConfig,
        secret: str,
        prompt: str,
    ) -> LLMHttpRequest: ...

    def parse_response(self, response: LLMHttpResponse) -> str: ...


def json_body(payload: object) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise LLMTransportError("invalid_request") from None


def max_output_tokens(profile: LLMProfileConfig) -> int:
    """从字节预算推导保守、固定且有上限的 token 预算。"""

    return max(1, min(profile.max_output_bytes // 4, 256))
