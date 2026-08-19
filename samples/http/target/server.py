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
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Literal
from urllib.parse import urlsplit


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
    ) -> None:
        if address[0] != "127.0.0.1":
            raise ValueError("authorization sample only binds to 127.0.0.1")
        self.variant = variant
        self.tokens = dict(tokens)
        self.observer_token = observer_token
        self.resources = copy.deepcopy(_INITIAL_RESOURCES)
        self.lock = threading.RLock()
        super().__init__(address, AuthorizationRequestHandler)

    def reset(self) -> None:
        """恢复固定初始数据，供每个 case 的受控 cleanup 重建隔离状态。"""

        with self.lock:
            self.resources = copy.deepcopy(_INITIAL_RESOURCES)


class AuthorizationRequestHandler(BaseHTTPRequestHandler):
    """实现被测资源接口与独立 owner 观察接口，不参与界鉴自身安全判断。"""

    server: AuthorizationSampleServer

    def do_GET(self) -> None:  # noqa: N802 - standard-library callback name
        path = urlsplit(self.path).path
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
        """仅接受本机且带测试标记的 reset 请求。"""

        if urlsplit(self.path).path != "/reset":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if self.client_address[0] != "127.0.0.1" or self.headers.get("X-Jiejian-Test-Mode") != "1":
            self._send(HTTPStatus.FORBIDDEN, {"error": "reset_requires_test_mode"})
            return
        self.server.reset()
        self._send(HTTPStatus.OK, {"status": "reset"})

    def _read_resource(self, resource_id: str) -> None:
        subject_id = self._subject_id()
        if subject_id is None:
            return
        with self.server.lock:
            resource = self.server.resources.get(resource_id)
            if resource is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            allowed = resource["owner_subject_id"] == subject_id
            self._send(HTTPStatus.OK if allowed else HTTPStatus.FORBIDDEN, copy.deepcopy(resource) if allowed else {"error": "forbidden"})

    def _observe_resource(self, resource_id: str) -> None:
        # 观察凭据与被测身份凭据分离，避免目标响应自证其授权结果。
        token = self._bearer_token()
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
            self._send(HTTPStatus.OK, copy.deepcopy(resource))

    def _subject_id(self) -> str | None:
        token = self._bearer_token()
        if token is None:
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return None
        for subject_id, expected in self.server.tokens.items():
            if hmac.compare_digest(token, expected):
                return subject_id
        self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return None

    def _bearer_token(self) -> str | None:
        value = self.headers.get("Authorization", "")
        return value.removeprefix("Bearer ") if value.startswith("Bearer ") else None

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
) -> AuthorizationSampleServer:
    """创建可嵌入测试的本机样例服务；调用者负责 ``shutdown`` 与 ``server_close``。"""

    return AuthorizationSampleServer(
        ("127.0.0.1", port),
        variant=variant,
        tokens=tokens or {"owner": "sample-owner-token", "attacker": "sample-attacker-token", "peer": "sample-peer-token"},
        observer_token=observer_token or "sample-owner-observer-token",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="官方 Authorization Web Sample Target")
    parser.add_argument("--variant", choices=("fixed", "vulnerable", "inconclusive"), required=True)
    parser.add_argument("--port", type=int, default=8765)
    arguments = parser.parse_args()
    names = {"owner": "JIEJIAN_AUTHORIZATION_OWNER_TOKEN", "attacker": "JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN", "peer": "JIEJIAN_AUTHORIZATION_PEER_TOKEN"}
    missing = tuple(name for name in (*names.values(), "JIEJIAN_AUTHORIZATION_OWNER_OBSERVER") if not os.environ.get(name))
    if missing:
        raise SystemExit("sample credentials are not configured")
    server = create_authorization_sample_server(
        variant=arguments.variant,
        port=arguments.port,
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
