# 为完整 FastAPI 应用测试注入确定性的 IPv4 control origin 与进程会话。

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient as FastAPITestClient

from product.backend.api import create_app as create_product_app
from product.backend.api.local_control import LocalControlGuard


TEST_CONTROL_ORIGIN = "http://127.0.0.1:8765"
TEST_CONTROL_SESSION_TOKEN = "test-control-session-" + "0" * 44


def create_app(*args: Any, **kwargs: Any):
    """只为测试装配固定身份；生产 app factory 仍要求显式真实 origin。"""

    kwargs["control_origin"] = TEST_CONTROL_ORIGIN
    kwargs["control_session_token"] = TEST_CONTROL_SESSION_TOKEN
    return create_product_app(*args, **kwargs)


class TestClient(FastAPITestClient):
    """让直接 API 测试携带与浏览器同等的 Cookie 和写请求 Origin。"""

    def __init__(self, app: Any, **kwargs: Any) -> None:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Origin", TEST_CONTROL_ORIGIN)
        cookies = dict(kwargs.pop("cookies", {}) or {})
        cookies.setdefault(
            LocalControlGuard.cookie_name,
            TEST_CONTROL_SESSION_TOKEN,
        )
        kwargs.setdefault("base_url", TEST_CONTROL_ORIGIN)
        super().__init__(app, headers=headers, cookies=cookies, **kwargs)
