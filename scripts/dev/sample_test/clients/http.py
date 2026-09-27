# 绑定本轮页面会话的 HTTP 客户端；秘密仅在内存。
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from playwright.sync_api import Page
import scripts.dev.sample_test.harness.state as sample_harness_state


class ApiClient:
    """访问单个 loopback 控制面的严格 JSON envelope 客户端。"""

    def __init__(self, origin: str) -> None:
        self.origin = origin.rstrip("/")
        self._page: Page | None = None

    def bind_page(self, page: Page) -> None:
        """把后续业务请求绑定到已由根页面取得的 HttpOnly 控制会话。"""

        self._page = page

    def call(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        *,
        accepted: tuple[int, ...] = (200,),
    ) -> Any:
        if self._page is not None:
            result = self._page.evaluate(
                """async ({method, path, body}) => {
                    const options = {method, headers: {Accept: 'application/json'}};
                    if (body !== null) {
                        options.headers['Content-Type'] = 'application/json';
                        options.body = JSON.stringify(body);
                    }
                    const response = await fetch(path, options);
                    return {status: response.status, text: await response.text()};
                }""",
                {"method": method, "path": path, "body": body},
            )
            status = int(result["status"])
            raw = str(result["text"]).encode("utf-8")
        else:
            encoded = None
            headers = {"Accept": "application/json"}
            if body is not None:
                encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
                headers["Content-Type"] = "application/json"
            request = Request(
                self.origin + path,
                data=encoded,
                headers=headers,
                method=method,
            )
            try:
                with urlopen(request, timeout=20) as response:
                    status = response.status
                    raw = response.read()
            except HTTPError as exc:
                raw = exc.read()
                raise sample_harness_state.SampleTestError(
                    f"{method} {path} 返回 {exc.code}: {_public_error(raw)}"
                ) from None
            except (OSError, URLError) as exc:
                raise sample_harness_state.SampleTestError(f"{method} {path} 无法访问: {type(exc).__name__}") from None
        if status not in accepted:
            raise sample_harness_state.SampleTestError(
                f"{method} {path} 返回非预期状态 {status}: {_public_error(raw)}"
            )
        try:
            payload = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            raise sample_harness_state.SampleTestError(f"{method} {path} 未返回有效 JSON") from None
        if not isinstance(payload, dict) or payload.get("schema_version") != "1" or "data" not in payload:
            raise sample_harness_state.SampleTestError(f"{method} {path} 返回的 envelope 无效")
        return payload["data"]

    def raw(self, path: str) -> bytes:
        if self._page is not None:
            result = self._page.evaluate(
                """async (path) => {
                    const response = await fetch(path, {headers: {Accept: '*/*'}});
                    return {status: response.status, text: await response.text()};
                }""",
                path,
            )
            if int(result["status"]) != 200:
                raise sample_harness_state.SampleTestError(f"GET {path} 返回非预期状态 {result['status']}")
            return str(result["text"]).encode("utf-8")
        try:
            with urlopen(self.origin + path, timeout=20) as response:
                return response.read()
        except (HTTPError, OSError, URLError) as exc:
            raise sample_harness_state.SampleTestError(f"GET {path} 无法读取: {type(exc).__name__}") from None

    def readiness(self) -> dict[str, object]:
        """读取不使用业务 envelope 的标准就绪探针。"""

        raw = self.raw("/ready")
        try:
            payload = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            raise sample_harness_state.SampleTestError("GET /ready 未返回有效 JSON") from None
        if not isinstance(payload, dict) or payload.get("schema_version") != "1":
            raise sample_harness_state.SampleTestError("GET /ready 返回格式无效")
        return payload


def _public_error(raw: bytes) -> str:
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        return "响应无法解析"
    if not isinstance(payload, dict):
        return "响应格式无效"
    detail = payload.get("detail")
    if isinstance(detail, dict):
        return str(detail.get("code") or "请求失败")
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("code") or "请求失败")
    return str(payload.get("code") or "请求失败")
