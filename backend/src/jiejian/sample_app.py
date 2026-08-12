# 仅用于本机黄金场景的标准库 HTTP 样例应用。

from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
import time
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Literal
from urllib.parse import urlsplit

_INITIAL_RESOURCES = {
    "owner-resource": {
        "id": "owner-resource",
        "owner_id": "owner",
        "role": "user",
        "value": "initial-owner-value",
        "last_case_id": None,
    },
    "attacker-resource": {
        "id": "attacker-resource",
        "owner_id": "attacker",
        "role": "user",
        "value": "initial-attacker-value",
        "last_case_id": None,
    },
}


class SampleServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        variant: Literal["safe", "vulnerable"],
        tokens: dict[str, str],
        fail_cleanup: bool = False,
        echo_secret: str | None = None,
        request_delay_seconds: float = 0.0,
    ) -> None:
        if address[0] != "127.0.0.1":
            raise ValueError("样例应用只允许绑定 127.0.0.1")
        self.variant = variant
        self.tokens = dict(tokens)
        self.fail_cleanup = fail_cleanup
        self.echo_secret = echo_secret
        self.request_delay_seconds = request_delay_seconds
        self.lock = threading.RLock()
        self.resources = deepcopy(_INITIAL_RESOURCES)
        self.runner_process_ids: list[int] = []
        super().__init__(address, SampleRequestHandler)

    def reset(self) -> None:
        with self.lock:
            self.resources = deepcopy(_INITIAL_RESOURCES)


class SampleRequestHandler(BaseHTTPRequestHandler):
    server: SampleServer

    def do_GET(self) -> None:  # noqa: N802 - 标准库回调名称
        self._record_runner_process()
        self._delay_target_request()
        path = urlsplit(self.path).path
        if path == "/health":
            self._send(HTTPStatus.OK, {"status": "ok", "variant": self.server.variant})
            return
        resource_id = self._resource_id(path, "/resources/")
        if resource_id is not None:
            self._read_resource(resource_id, trusted_observer=False)
            return
        resource_id = self._resource_id(path, "/owner/resources/")
        if resource_id is not None:
            self._read_resource(resource_id, trusted_observer=True)
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_PATCH(self) -> None:  # noqa: N802 - 标准库回调名称
        self._record_runner_process()
        self._delay_target_request()
        resource_id = self._resource_id(urlsplit(self.path).path, "/resources/")
        if resource_id is None:
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        actor = self._actor()
        if actor is None:
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        body = self._read_json()
        if body is None:
            return
        if not set(body).issubset({"value", "owner_id", "role"}):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "unknown_field"})
            return
        with self.server.lock:
            resource = self.server.resources.get(resource_id)
            if resource is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            authorized = actor == resource["owner_id"] and not {
                "owner_id",
                "role",
            }.intersection(body)
            if authorized or self.server.variant == "vulnerable":
                for key in ("value", "owner_id", "role"):
                    if key in body:
                        resource[key] = body[key]
                resource["last_case_id"] = self.headers.get("X-Jiejian-Case-ID")
            status = HTTPStatus.OK if authorized else HTTPStatus.FORBIDDEN
            payload = deepcopy(resource) if authorized else {"error": "forbidden"}
        self._send(status, payload)

    def do_POST(self) -> None:  # noqa: N802 - 标准库回调名称
        self._record_runner_process()
        if urlsplit(self.path).path != "/reset":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if (
            self.headers.get("X-Jiejian-Test-Mode") != "1"
            or self.client_address[0] != "127.0.0.1"
        ):
            self._send(HTTPStatus.FORBIDDEN, {"error": "test_only"})
            return
        if self.server.fail_cleanup:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "cleanup_failed"})
            return
        self.server.reset()
        self._send(HTTPStatus.NO_CONTENT, None)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _actor(self) -> str | None:
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return None
        candidate = authorization.removeprefix("Bearer ")
        for identity_id, token in self.server.tokens.items():
            if hmac.compare_digest(candidate, token):
                return identity_id
        return None

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

    def _read_resource(self, resource_id: str, *, trusted_observer: bool) -> None:
        actor = self._actor()
        if actor is None:
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        with self.server.lock:
            resource = self.server.resources.get(resource_id)
            if resource is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            initial_owner = _INITIAL_RESOURCES[resource_id]["owner_id"]
            allowed = actor == (initial_owner if trusted_observer else resource["owner_id"])
            payload = deepcopy(resource) if allowed else {"error": "forbidden"}
            if allowed and self.server.echo_secret:
                payload["ordinary_field"] = (
                    f"prefix::{self.server.echo_secret}::suffix"
                )
                payload["nested"] = {"items": [self.server.echo_secret]}
        self._send(HTTPStatus.OK if allowed else HTTPStatus.FORBIDDEN, payload)

    def _read_json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "content_length"})
            return None
        if length < 1 or length > 8192:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body_size"})
            return None
        try:
            body = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "json"})
            return None
        if not isinstance(body, dict):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "json_object"})
            return None
        return body

    def _resource_id(self, path: str, prefix: str) -> str | None:
        if not path.startswith(prefix):
            return None
        resource_id = path.removeprefix(prefix)
        return resource_id if resource_id and "/" not in resource_id else None

    def _send(self, status: HTTPStatus, payload: dict[str, Any] | None) -> None:
        encoded = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if encoded:
            self.wfile.write(encoded)


def create_sample_server(
    *,
    variant: Literal["safe", "vulnerable"],
    port: int = 0,
    tokens: dict[str, str] | None = None,
    fail_cleanup: bool = False,
    echo_secret: str | None = None,
    request_delay_seconds: float = 0.0,
) -> SampleServer:
    selected_tokens = tokens or {
        "owner": os.environ.get("JIEJIAN_SAMPLE_OWNER_TOKEN", "sample-owner-token"),
        "attacker": os.environ.get(
            "JIEJIAN_SAMPLE_ATTACKER_TOKEN", "sample-attacker-token"
        ),
    }
    return SampleServer(
        ("127.0.0.1", port),
        variant=variant,
        tokens=selected_tokens,
        fail_cleanup=fail_cleanup,
        echo_secret=echo_secret,
        request_delay_seconds=request_delay_seconds,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="界鉴阶段 1 本机样例应用")
    parser.add_argument("--variant", choices=("safe", "vulnerable"), required=True)
    parser.add_argument("--port", type=int, default=8765)
    arguments = parser.parse_args()
    server = create_sample_server(variant=arguments.variant, port=arguments.port)
    try:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
