# =============================================================================
# 官方 Authorization Web Sample Target
#
# 定位
# 为产品演示和闭环测试提供 fixed、vulnerable、inconclusive 三种确定性目标状态。
#
# 职责
# 模拟资源所有权｜执行授权变体｜提供状态观察与恢复接口
#
# 边界
# 只绑定 loopback，凭据只来自进程环境；它是受控样例，不代表生产目标或扫描器。
#
# 调用链
# samples 启动命令 / 产品测试 → AuthorizationSampleServer → HTTP Adapter / Observer
# =============================================================================

from __future__ import annotations

import argparse
import copy
import hmac
import json
import os
import threading
import time
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Literal
from urllib.parse import parse_qs, urlsplit


Variant = Literal["fixed", "vulnerable", "inconclusive"]
_INITIAL_RESOURCES = {
    "owner-resource": {"resource_id": "owner-resource", "owner_subject_id": "owner", "value": "initial-owner-value"},
    "attacker-resource": {"resource_id": "attacker-resource", "owner_subject_id": "attacker", "value": "initial-attacker-value"},
}


class AuthorizationSampleServer(ThreadingHTTPServer):
    """仅绑定本机的确定性权限样例；以锁保护跨请求共享资源状态。"""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        variant: Variant,
        tokens: dict[str, str],
        observer_token: str,
        fail_cleanup: bool = False,
        echo_secret: str | None = None,
        request_delay_seconds: float = 0.0,
    ) -> None:
        if address[0] != "127.0.0.1":
            raise ValueError("authorization sample only binds to 127.0.0.1")
        if request_delay_seconds < 0:
            raise ValueError("request delay must not be negative")
        self.variant = variant
        self.tokens = dict(tokens)
        self.observer_token = observer_token
        self.fail_cleanup = fail_cleanup
        self.echo_secret = echo_secret
        self.request_delay_seconds = request_delay_seconds
        self.resources = copy.deepcopy(_INITIAL_RESOURCES)
        self.lock = threading.RLock()
        self.runner_process_ids: list[int] = []
        super().__init__(address, AuthorizationRequestHandler)

    def reset(self) -> None:
        """恢复固定初始数据，供每个 case 的受控 cleanup 重建隔离状态。"""

        with self.lock:
            self.resources = copy.deepcopy(_INITIAL_RESOURCES)


class AuthorizationRequestHandler(BaseHTTPRequestHandler):
    """实现被测资源接口与独立 owner 观察接口，不参与界鉴自身安全判断。"""

    server: AuthorizationSampleServer

    def do_GET(self) -> None:  # noqa: N802 - standard-library callback name
        self._record_runner_process()
        self._delay_target_request()
        path = urlsplit(self.path).path
        if path == "/":
            self._application_page()
            return
        if path == "/login":
            self._login_page()
            return
        if path == "/health":
            self._send(HTTPStatus.OK, {"status": "ok", "variant": self.server.variant})
            return
        resource_id = self._resource_id(path, "/resources/")
        if resource_id is not None:
            self._read_resource(resource_id)
            return
        resource_id = self._resource_id(path, "/owner/resources/")
        if resource_id is not None:
            self._observe_resource(resource_id)
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_PATCH(self) -> None:  # noqa: N802 - standard-library callback name
        """按样例变体应用所有权检查，用于产生固定 vulnerable/fixed 行为。"""

        self._record_runner_process()
        self._delay_target_request()
        resource_id = self._resource_id(urlsplit(self.path).path, "/resources/")
        if resource_id is None:
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        length = self._content_length()
        if length is None:
            return
        subject_id = self._subject_id()
        body = self._read_json(length)
        if subject_id is None or body is None:
            return
        if set(body) != {"value"} or not isinstance(body["value"], str) or not body["value"] or len(body["value"]) > 128:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_body"})
            return
        with self.server.lock:
            resource = self.server.resources.get(resource_id)
            if resource is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            allowed = resource["owner_subject_id"] == subject_id
            if allowed or (self.server.variant == "vulnerable" and resource_id == "owner-resource"):
                resource["value"] = body["value"]
            payload = copy.deepcopy(resource) if allowed else {"error": "forbidden"}
        self._send(HTTPStatus.OK if allowed else HTTPStatus.FORBIDDEN, payload)

    def do_POST(self) -> None:  # noqa: N802 - standard-library callback name
        """处理样例人工登录，或接受带本机测试标记的 reset 请求。"""

        self._record_runner_process()
        path = urlsplit(self.path).path
        if path == "/login":
            self._login()
            return
        if path != "/reset":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if self.client_address[0] != "127.0.0.1" or self.headers.get("X-Jiejian-Test-Mode") != "1":
            self._send(HTTPStatus.FORBIDDEN, {"error": "reset_requires_test_mode"})
            return
        if self.server.fail_cleanup:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "cleanup_failed"})
            return
        self.server.reset()
        self._send(HTTPStatus.OK, {"status": "reset"})

    def _read_resource(self, resource_id: str) -> None:
        subject_id = self._subject_id()
        if subject_id is None:
            return
        # 不确定变体必须让普通录制可确认的所有者读取同样不可用，避免仅关闭旧观察路由后仍形成 PASS。
        if self.server.variant == "inconclusive":
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "resource_observer_unavailable"})
            return
        with self.server.lock:
            resource = self.server.resources.get(resource_id)
            if resource is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            allowed = resource["owner_subject_id"] == subject_id
            payload = self._resource_payload(resource) if allowed else {"error": "forbidden"}
            self._send(HTTPStatus.OK if allowed else HTTPStatus.FORBIDDEN, payload)

    def _observe_resource(self, resource_id: str) -> None:
        # 观察凭据与被测身份凭据分离，避免目标响应自证其授权结果。
        token = self._authorization_token()
        if token is None or not hmac.compare_digest(token, self.server.observer_token):
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        if self.server.variant == "inconclusive":
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "owner_observer_unavailable"})
            return
        with self.server.lock:
            resource = self.server.resources.get(resource_id)
            if resource is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            self._send(HTTPStatus.OK, self._resource_payload(resource))

    def _resource_payload(self, resource: dict[str, str]) -> dict:
        payload = copy.deepcopy(resource)
        if self.server.echo_secret:
            payload["ordinary_field"] = f"prefix::{self.server.echo_secret}::suffix"
            payload["nested"] = {"items": [self.server.echo_secret]}
        return payload

    def _record_runner_process(self) -> None:
        raw = self.headers.get("X-Jiejian-Runner-PID")
        if raw is None:
            return
        try:
            process_id = int(raw)
        except ValueError:
            return
        with self.server.lock:
            self.server.runner_process_ids.append(process_id)

    def _delay_target_request(self) -> None:
        if self.server.request_delay_seconds:
            time.sleep(self.server.request_delay_seconds)

    def _subject_id(self) -> str | None:
        subject_id = self._authenticated_subject_id()
        if subject_id is not None:
            return subject_id
        self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return None

    def _authenticated_subject_id(self) -> str | None:
        """只解析当前会话身份；由具体页面或 API 决定未登录时的响应形式。"""

        token = self._authorization_token()
        if token is None:
            return None
        for subject_id, expected in self.server.tokens.items():
            if hmac.compare_digest(token, expected):
                return subject_id
        return None

    def _authorization_token(self) -> str | None:
        value = self.headers.get("Authorization", "")
        if value.startswith("Bearer "):
            return value.removeprefix("Bearer ")
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except Exception:
            return None
        session = cookies.get("jiejian_sample_session")
        return session.value if session is not None else None

    def _login_page(self) -> None:
        """提供无需把长期密码交给界鉴的确定性人工登录页面。"""

        body = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>界鉴权限样例登录</title></head>
<body><main><h1>权限样例登录</h1>
<p>请使用样例账号登录；界鉴不会保存这里输入的密码。</p>
<form method="post" action="/login">
<label>账号 <select name="role"><option value="owner">所有者 owner</option><option value="attacker">攻击者 attacker</option><option value="peer">同级用户 peer</option></select></label>
<label>样例密码 <input name="password" type="password" autocomplete="current-password" required></label>
<button type="submit">登录样例</button>
</form>
<p>样例密码格式：sample-&lt;账号&gt;-password，例如 sample-owner-password。</p>
</main></body></html>""".encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _application_page(self) -> None:
        """为已登录账号提供可直接录制的最小资源修改界面。"""

        subject_id = self._authenticated_subject_id()
        if subject_id is None:
            self._login_page()
            return
        body = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>界鉴权限样例</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; color: #202124; }}
main {{ max-width: 42rem; }}
label, button {{ display: block; margin-top: 1rem; }}
input {{ min-width: 24rem; padding: .5rem; }}
button {{ padding: .55rem 1rem; }}
#result {{ margin-top: 1rem; white-space: pre-wrap; }}
</style></head>
<body><main><h1>权限样例资源</h1>
<p>当前账号：<strong>{subject_id}</strong></p>
<p>开始录制后点击一次操作按钮；样例会依次修改、独立读取、恢复并再次核对资源。</p>
<label>新的资源内容 <input id="resource-value" value="recorded-owner-value" maxlength="128"></label>
<button id="modify-resource" type="button">修改、核对并恢复所有者资源</button>
<p id="result" role="status">尚未执行</p>
<script>
const result = document.querySelector('#result');
document.querySelector('#modify-resource').addEventListener('click', async () => {{
  result.textContent = '正在执行安全录制序列……';
  try {{
    const target = await fetch('/resources/owner-resource', {{
      method: 'PATCH', credentials: 'include',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{value: document.querySelector('#resource-value').value}})
    }});
    if (!target.ok) throw new Error(`修改请求返回 ${{target.status}}`);
    const observed = await fetch('/resources/owner-resource', {{credentials: 'include'}});
    if (!observed.ok) throw new Error(`结果核对返回 ${{observed.status}}`);
    const recovery = await fetch('/resources/owner-resource', {{
      method: 'PATCH', credentials: 'include',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{value: 'initial-owner-value'}})
    }});
    if (!recovery.ok) throw new Error(`恢复请求返回 ${{recovery.status}}`);
    const restored = await fetch('/resources/owner-resource', {{credentials: 'include'}});
    if (!restored.ok) throw new Error(`恢复核对返回 ${{restored.status}}`);
    const restoredPayload = await restored.json();
    result.textContent = `修改、核对与恢复均已完成；当前值：${{restoredPayload.value}}`;
  }} catch (_error) {{
    result.textContent = _error instanceof Error ? `操作未完成：${{_error.message}}` : '操作未完成';
  }}
}});
</script></main></body></html>""".encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _login(self) -> None:
        length = self._content_length()
        if length is None:
            return
        try:
            fields = parse_qs(
                self.rfile.read(length).decode("utf-8"),
                strict_parsing=True,
            )
            role = fields["role"][0]
            password = fields["password"][0]
        except (KeyError, UnicodeDecodeError, ValueError):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_login"})
            return
        token = self.server.tokens.get(role)
        expected_password = f"sample-{role}-password"
        if token is None or not hmac.compare_digest(password, expected_password):
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "invalid_login"})
            return
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.send_header(
            "Set-Cookie",
            "jiejian_sample_session="
            f"{token}; Path=/; HttpOnly; SameSite=Lax",
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _content_length(self) -> int | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "content_length"})
            return None
        if length > 8192:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "content_length"})
            return None
        return length

    def _read_json(self, length: int) -> dict | None:
        try:
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return None
        if not isinstance(payload, dict):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return None
        return payload

    @staticmethod
    def _resource_id(path: str, prefix: str) -> str | None:
        if not path.startswith(prefix) or "/" in path.removeprefix(prefix):
            return None
        return path.removeprefix(prefix) or None

    def _send(self, status: HTTPStatus, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def create_authorization_sample_server(
    *,
    variant: Variant,
    port: int = 0,
    tokens: dict[str, str] | None = None,
    observer_token: str | None = None,
    fail_cleanup: bool = False,
    echo_secret: str | None = None,
    request_delay_seconds: float = 0.0,
) -> AuthorizationSampleServer:
    """创建可嵌入测试的本机样例服务；调用者负责 ``shutdown`` 与 ``server_close``。"""

    return AuthorizationSampleServer(
        ("127.0.0.1", port),
        variant=variant,
        tokens=tokens or {"owner": "sample-owner-token", "attacker": "sample-attacker-token", "peer": "sample-peer-token"},
        observer_token=observer_token or "sample-owner-observer-token",
        fail_cleanup=fail_cleanup,
        echo_secret=echo_secret,
        request_delay_seconds=request_delay_seconds,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="官方 Authorization Web Sample Target")
    parser.add_argument("--variant", choices=("fixed", "vulnerable", "inconclusive"), required=True)
    parser.add_argument("--port", type=int)
    arguments = parser.parse_args()
    names = {"owner": "JIEJIAN_AUTHORIZATION_OWNER_TOKEN", "attacker": "JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN", "peer": "JIEJIAN_AUTHORIZATION_PEER_TOKEN"}
    missing = tuple(name for name in (*names.values(), "JIEJIAN_AUTHORIZATION_OWNER_OBSERVER") if not os.environ.get(name))
    if missing:
        raise SystemExit("sample credentials are not configured")
    server = create_authorization_sample_server(
        variant=arguments.variant,
        port=arguments.port if arguments.port is not None else {"fixed": 8865, "vulnerable": 8766, "inconclusive": 8767}[arguments.variant],
        tokens={subject: os.environ[name] for subject, name in names.items()},
        observer_token=os.environ["JIEJIAN_AUTHORIZATION_OWNER_OBSERVER"],
    )
    try:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
