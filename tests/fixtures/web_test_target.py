# 中性 Web 测试目标的本机 HTTP 夹具。
#
# 职责
# 提供受控文档读写、独立观察、登录、恢复和预算测试能力。
#
# 边界
# 只绑定 loopback；凭据由测试调用者注入，不保存预设答案或安全结论。

from __future__ import annotations

import copy
import hmac
import json
import os
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping
from urllib.parse import parse_qs, urlsplit


_INITIAL_DOCUMENTS = {
    "document": {
        "resource_id": "document",
        "resource_subject_id": "member",
        "value": "initial-document-value",
    }
}


class WebTestTarget(ThreadingHTTPServer):
    """提供单一中性文档目标，保护跨请求状态并记录 Runner 进程标识。"""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        tokens: Mapping[str, str],
        observer_token: str,
        passwords: Mapping[str, str] | None = None,
        sessions: Mapping[str, str] | None = None,
        fail_cleanup: bool = False,
        echo_secret: str | None = None,
        request_delay_seconds: float = 0.0,
    ) -> None:
        if address[0] != "127.0.0.1":
            raise ValueError("web test target only binds to 127.0.0.1")
        if request_delay_seconds < 0:
            raise ValueError("request delay must not be negative")
        self.tokens = dict(tokens)
        self.observer_token = observer_token
        self.passwords = dict(passwords or {})
        self.sessions = dict(sessions or tokens)
        self.fail_cleanup = fail_cleanup
        self.echo_secret = echo_secret
        self.request_delay_seconds = request_delay_seconds
        self.documents = copy.deepcopy(_INITIAL_DOCUMENTS)
        self.lock = threading.RLock()
        self.runner_process_ids: list[int] = []
        super().__init__(address, WebTestRequestHandler)

    def reset(self) -> None:
        """恢复中性文档状态，供清理测试复用。"""

        with self.lock:
            self.documents = copy.deepcopy(_INITIAL_DOCUMENTS)


class WebTestRequestHandler(BaseHTTPRequestHandler):
    """实现中性文档目标与独立观察端点，不参与界鉴安全判定。"""

    server: WebTestTarget

    def do_GET(self) -> None:  # noqa: N802 - standard-library callback name
        self._record_runner_process()
        self._delay_target_request()
        path = urlsplit(self.path).path
        if path == "/health":
            self._send(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/":
            self._application_page()
            return
        if path == "/login":
            self._login_page()
            return
        resource_id = self._resource_id(path, "/resources/")
        if resource_id is not None:
            self._read_document(resource_id)
            return
        resource_id = self._resource_id(path, "/observations/")
        if resource_id is not None:
            self._observe_document(resource_id)
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_PATCH(self) -> None:  # noqa: N802 - standard-library callback name
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
            document = self.server.documents.get(resource_id)
            if document is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            if document["resource_subject_id"] != subject_id:
                self._send(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            document["value"] = body["value"]
            payload = copy.deepcopy(document)
        self._send(HTTPStatus.OK, payload)

    def do_POST(self) -> None:  # noqa: N802 - standard-library callback name
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
        self._send(HTTPStatus.NO_CONTENT, None)

    def _read_document(self, resource_id: str) -> None:
        subject_id = self._subject_id()
        if subject_id is None:
            return
        with self.server.lock:
            document = self.server.documents.get(resource_id)
            if document is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            if document["resource_subject_id"] != subject_id:
                self._send(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            self._send(HTTPStatus.OK, self._document_payload(document))

    def _observe_document(self, resource_id: str) -> None:
        token = self._authorization_token()
        if token is None or not hmac.compare_digest(token, self.server.observer_token):
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        with self.server.lock:
            document = self.server.documents.get(resource_id)
            if document is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            self._send(HTTPStatus.OK, self._document_payload(document))

    def _document_payload(self, document: dict[str, str]) -> dict:
        payload = copy.deepcopy(document)
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
        if subject_id is None:
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return subject_id

    def _authenticated_subject_id(self) -> str | None:
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
        session = cookies.get("jiejian_web_test_session")
        return session.value if session is not None else None

    def _login_page(self) -> None:
        body = (
            "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<title>Web 测试目标</title></head><body><main>"
            "<h1>Web 测试目标登录</h1><form method=\"post\" action=\"/login\">"
            "<label>账号 <select name=\"account\"><option value=\"member\">member</option>"
            "<option value=\"reader\">reader</option></select></label>"
            "<label>密码 <input name=\"password\" type=\"password\"></label>"
            "<button type=\"submit\">登录</button></form></main></body></html>"
        ).encode("utf-8")
        self._send_bytes(HTTPStatus.OK, body, "text/html; charset=utf-8", cache_control="no-store")

    def _application_page(self) -> None:
        body = (
            "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<title>Web 测试目标</title></head><body><main>"
            "<h1>文档测试目标</h1><p>用于验证受控文档操作。</p>"
            "</main></body></html>"
        ).encode("utf-8")
        self._send_bytes(HTTPStatus.OK, body, "text/html; charset=utf-8", cache_control="no-store")

    def _login(self) -> None:
        length = self._content_length()
        if length is None:
            return
        try:
            fields = parse_qs(self.rfile.read(length).decode("utf-8"), strict_parsing=True)
            account = fields["account"][0]
            password = fields["password"][0]
        except (KeyError, UnicodeDecodeError, ValueError):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_login"})
            return
        expected = self.server.passwords.get(account)
        session = self.server.sessions.get(account)
        if expected is None or session is None or not hmac.compare_digest(password, expected):
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "invalid_login"})
            return
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.send_header("Set-Cookie", f"jiejian_web_test_session={session}; Path=/; HttpOnly; SameSite=Lax")
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

    def _send(self, status: HTTPStatus, payload: dict | None) -> None:
        if payload is None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send_bytes(status, encoded, "application/json")

    def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str, *, cache_control: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if cache_control is not None:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def create_web_test_target(
    *,
    port: int = 0,
    tokens: Mapping[str, str] | None = None,
    observer_token: str = "observer-token",
    passwords: Mapping[str, str] | None = None,
    sessions: Mapping[str, str] | None = None,
    fail_cleanup: bool = False,
    echo_secret: str | None = None,
    request_delay_seconds: float = 0.0,
) -> WebTestTarget:
    """创建本机中性目标；调用者负责 ``shutdown`` 和 ``server_close``。"""

    return WebTestTarget(
        ("127.0.0.1", port),
        tokens=tokens or {"member": "member-token", "reader": "reader-token"},
        observer_token=observer_token,
        passwords=passwords,
        sessions=sessions,
        fail_cleanup=fail_cleanup,
        echo_secret=echo_secret,
        request_delay_seconds=request_delay_seconds,
    )


def main() -> None:
    """以环境注入凭据启动中性测试目标。"""

    import argparse

    parser = argparse.ArgumentParser(description="Loopback Web test target")
    parser.add_argument("--port", type=int, default=0)
    arguments = parser.parse_args()
    names = {
        "member": "JIEJIAN_WEB_TEST_MEMBER_TOKEN",
        "reader": "JIEJIAN_WEB_TEST_READER_TOKEN",
    }
    observer_name = "JIEJIAN_WEB_TEST_OBSERVER_TOKEN"
    missing = tuple(name for name in (*names.values(), observer_name) if not os.environ.get(name))
    if missing:
        raise SystemExit("web test target credentials are not configured")
    server = create_web_test_target(
        port=arguments.port,
        tokens={subject: os.environ[name] for subject, name in names.items()},
        observer_token=os.environ[observer_name],
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
