# =============================================================================
# Complex permission test Target/fixture.
#
# The target is loopback-only, keeps opaque credentials in memory, and exposes
# reset only to loopback callers carrying the test-mode header. It is a sample
# process for the current HTTP execution and observation tests, not a product
# Verification implementation.
# =============================================================================

from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import json
import re
import sqlite3
import threading
import time
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit


Variant = Literal["fixed", "vulnerable", "inconclusive"]
_CASE_TAG_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_ASYNC_TASK_MAX = 64
_ASYNC_RESOURCE_ID = "document-b"
_ASYNC_PATH_PREFIX = "/observer/tasks/document-b/by-case/"

_INITIAL_RESOURCES: dict[str, dict[str, Any]] = {
    "document-a": {
        "resource_id": "document-a",
        "tenant_id": "tenant-a",
        "department_id": "dept-a",
        "owner_subject_id": "member-a",
        "workflow_state": "DRAFT",
        "value": "a-initial",
        "version": 1,
    },
    "document-a-child": {
        "resource_id": "document-a-child",
        "tenant_id": "tenant-a",
        "department_id": "dept-a",
        "owner_subject_id": "member-a",
        "parent_resource_id": "document-a",
        "workflow_state": "DRAFT",
        "value": "a-child-initial",
        "version": 1,
    },
    "document-a-pending": {
        "resource_id": "document-a-pending",
        "tenant_id": "tenant-a",
        "department_id": "dept-a",
        "owner_subject_id": "member-a",
        "workflow_state": "PENDING",
        "value": "a-pending-initial",
        "version": 1,
    },
    "document-a-approved": {
        "resource_id": "document-a-approved",
        "tenant_id": "tenant-a",
        "department_id": "dept-a",
        "owner_subject_id": "member-a",
        "workflow_state": "APPROVED",
        "value": "a-approved-initial",
        "version": 1,
    },
    "document-b": {
        "resource_id": "document-b",
        "tenant_id": "tenant-b",
        "department_id": "dept-b",
        "owner_subject_id": "member-b",
        "workflow_state": "DRAFT",
        "value": "b-initial",
        "version": 1,
    },
    "document-a2": {
        "resource_id": "document-a2",
        "tenant_id": "tenant-a",
        "department_id": "dept-a2",
        "owner_subject_id": "member-a2",
        "workflow_state": "DRAFT",
        "value": "a2-initial",
        "version": 1,
    },
}


_SUBJECTS: dict[str, dict[str, Any]] = {
    "member-a": {"tenant_id": "tenant-a", "department_id": "dept-a", "role": "member", "admin_level": 0},
    "member-a2": {"tenant_id": "tenant-a", "department_id": "dept-a2", "role": "member", "admin_level": 0},
    "peer-a": {"tenant_id": "tenant-a", "department_id": "dept-a", "role": "guest", "admin_level": 0},
    "dept-admin-a": {"tenant_id": "tenant-a", "department_id": "dept-a", "role": "department-admin", "admin_level": 1},
    "tenant-admin-a": {"tenant_id": "tenant-a", "department_id": "dept-a", "role": "tenant-admin", "admin_level": 2},
    "member-b": {"tenant_id": "tenant-b", "department_id": "dept-b", "role": "member", "admin_level": 0},
    "dept-admin-a2": {"tenant_id": "tenant-a", "department_id": "dept-a2", "role": "department-admin", "admin_level": 1},
}


class ComplexPermissionTestServer(ThreadingHTTPServer):
    variant: Variant
    tokens: dict[str, str]
    resources: dict[str, dict[str, Any]]
    database_path: Path | None
    audit_root: Path | None
    observer_token: str | None
    lock: threading.RLock

    def __init__(
        self,
        address: tuple[str, int],
        *,
        variant: Variant,
        tokens: dict[str, str],
        database_path: str | Path | None = None,
        audit_root: str | Path | None = None,
        observer_token: str | None = None,
    ) -> None:
        if address[0] != "127.0.0.1":
            raise ValueError("complex permission test target only binds to 127.0.0.1")
        self.variant = variant
        self.tokens = dict(tokens)
        self.resources = copy.deepcopy(_INITIAL_RESOURCES)
        self.database_path = None if database_path is None else Path(database_path).resolve()
        self.audit_root = None if audit_root is None else Path(audit_root).resolve()
        self.observer_token = observer_token
        self.lock = threading.RLock()
        self._audit_lock = threading.Lock()
        self._accepted_async_cases: set[str] = set()
        self._async_tasks: dict[str, dict[str, Any]] = {}
        self._async_events: dict[str, threading.Event] = {}
        self._async_threads: dict[str, threading.Thread] = {}
        super().__init__(address, ComplexPermissionTestRequestHandler)
        self._reset_database()
        if self.audit_root is not None:
            self.audit_root.mkdir(parents=True, exist_ok=True)

    def reset(self) -> None:
        with self.lock:
            self.resources = copy.deepcopy(_INITIAL_RESOURCES)
            self._reset_database()

    def _reset_database(self) -> None:
        if self.database_path is None:
            return
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS resource_state "
                "(resource_id TEXT PRIMARY KEY, workflow_state TEXT NOT NULL, value TEXT NOT NULL)"
            )
            connection.execute("DELETE FROM resource_state")
            connection.executemany(
                "INSERT INTO resource_state(resource_id, workflow_state, value) VALUES (?, ?, ?)",
                [(resource["resource_id"], resource["workflow_state"], resource["value"]) for resource in self.resources.values()],
            )

    def persist_resource(self, resource: dict[str, Any]) -> None:
        if self.database_path is None:
            return
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE resource_state SET workflow_state = ?, value = ? WHERE resource_id = ?",
                (resource["workflow_state"], resource["value"], resource["resource_id"]),
            )

    def _append_audit(self, record: dict[str, Any]) -> None:
        if self.audit_root is None:
            return
        line = (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        with self._audit_lock:
            self.audit_root.mkdir(parents=True, exist_ok=True)
            with (self.audit_root / "audit.jsonl").open("ab") as stream:
                stream.write(line)
                stream.flush()

    @staticmethod
    def _event_id(case_tag: str, event_type: str, sequence: int) -> str:
        digest = hashlib.sha256(f"{case_tag}:{event_type}:{sequence}".encode("utf-8")).hexdigest()[:24]
        return f"event-{digest}"

    def _audit_event(self, case_tag: str, task_id: str, event_type: str, sequence: int, **fields: Any) -> None:
        record = {
            "event_id": self._event_id(case_tag, event_type, sequence),
            "case_tag": case_tag,
            "task_id": task_id,
            "event_type": event_type,
            "sequence": sequence,
            "resource_id": _ASYNC_RESOURCE_ID,
            **fields,
        }
        self._append_audit(record)

    def _start_async_task(self, case_tag: str, value: str, task_id: str) -> None:
        event = threading.Event()
        self._async_events[case_tag] = event
        task = {"task_id": task_id, "state": "QUEUED", "final_result": None, "value": value}
        self._async_tasks[case_tag] = task
        self._audit_event(case_tag, task_id, "TASK_STATE", 2)
        worker = threading.Thread(target=self._run_async_task, args=(case_tag,), daemon=True)
        self._async_threads[case_tag] = worker
        worker.start()

    def _run_async_task(self, case_tag: str) -> None:
        try:
            with self.lock:
                task = self._async_tasks[case_tag]
                task["state"] = "RUNNING"
                self._audit_event(case_tag, task["task_id"], "TASK_STATE", 3)
                resource = self.resources[_ASYNC_RESOURCE_ID]
                resource["value"] = task["value"]
                resource["version"] += 1
                self.persist_resource(resource)
                self._audit_event(case_tag, task["task_id"], "SIDE_EFFECT", 4, effect="APPLIED")
                task["state"] = "SUCCESS"
                task["final_result"] = {"effect": "APPLIED"}
                self._audit_event(
                    case_tag,
                    task["task_id"],
                    "TASK_STATE",
                    5,
                    terminal_state="SUCCESS",
                    result="SUCCESS",
                    effect="APPLIED",
                )
        finally:
            with self.lock:
                event = self._async_events.get(case_tag)
                if event is not None:
                    event.set()
                self._async_threads.pop(case_tag, None)

    def _task_snapshot(self, case_tag: str) -> dict[str, Any] | None:
        with self.lock:
            task = self._async_tasks.get(case_tag)
            if task is None:
                return None
            return {
                "schema_version": "1",
                "case_tag": case_tag,
                "resource_id": _ASYNC_RESOURCE_ID,
                "task_id": task["task_id"],
                "state": task["state"],
                "final_result": copy.deepcopy(task["final_result"]),
            }

    def server_close(self) -> None:
        with self.lock:
            threads = tuple(self._async_threads.values())
        deadline = time.monotonic() + 1.0
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        super().server_close()


class ComplexPermissionTestRequestHandler(BaseHTTPRequestHandler):
    server: ComplexPermissionTestServer

    def do_GET(self) -> None:  # noqa: N802 - 标准库回调名称
        path = urlsplit(self.path).path
        if path.startswith(_ASYNC_PATH_PREFIX):
            self._observer_task(path)
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
            self._owner_observe(resource_id)
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_PATCH(self) -> None:  # noqa: N802 - 标准库回调名称
        resource_id = self._resource_id(urlsplit(self.path).path, "/resources/")
        if resource_id is None:
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        subject_id = self._subject_id()
        body = self._read_json()
        if subject_id is None or body is None:
            return
        if set(body) != {"value"} or not isinstance(body["value"], str) or len(body["value"]) > 128:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_body"})
            return
        with self.server.lock:
            resource = self.server.resources.get(resource_id)
            if resource is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            allowed = self._can_modify(subject_id, resource)
            if allowed or self.server.variant == "vulnerable":
                resource["value"] = body["value"]
                resource["version"] += 1
                self.server.persist_resource(resource)
            payload = copy.deepcopy(resource) if allowed else {"error": "forbidden"}
        self._send(HTTPStatus.OK if allowed else HTTPStatus.FORBIDDEN, payload)

    def do_POST(self) -> None:  # noqa: N802 - 标准库回调名称
        path = urlsplit(self.path).path
        if path == "/reset":
            self._reset()
            return
        if path == "/resources/batch":
            self._batch_modify()
            return
        if path == "/resources/document-b/async-modify":
            self._async_modify()
            return
        if path.startswith("/resources/") and path.endswith("/approve"):
            self._approve(path.removeprefix("/resources/").removesuffix("/approve"))
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _async_modify(self) -> None:
        subject_id = self._subject_id()
        case_tag = self.headers.get("X-Jiejian-Case-ID", "")
        if subject_id is None:
            return
        if not _CASE_TAG_PATTERN.fullmatch(case_tag):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_case_tag"})
            return
        body = self._read_json()
        if body is None:
            return
        if set(body) != {"value"} or not isinstance(body["value"], str) or not body["value"] or len(body["value"]) > 128:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_body"})
            return
        with self.server.lock:
            resource = self.server.resources.get(_ASYNC_RESOURCE_ID)
            if resource is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            if case_tag in self.server._accepted_async_cases:
                self._send(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            if len(self.server._accepted_async_cases) >= _ASYNC_TASK_MAX:
                self._send(HTTPStatus.TOO_MANY_REQUESTS, {"error": "task_limit"})
                return
            self.server._accepted_async_cases.add(case_tag)
            if self.server.audit_root is not None:
                self.server._audit_event(case_tag, "", "REQUEST", 1)
            if self.server.variant != "fixed":
                task_id = "task-" + hashlib.sha256(case_tag.encode("utf-8")).hexdigest()[:24]
                self.server._start_async_task(case_tag, body["value"], task_id)
        self._send(HTTPStatus.FORBIDDEN, {"error": "forbidden"})

    def _observer_task(self, path: str) -> None:
        raw_tag = path.removeprefix(_ASYNC_PATH_PREFIX)
        case_tag = unquote(raw_tag)
        if not _CASE_TAG_PATTERN.fullmatch(case_tag) or self.server.observer_token is None:
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        raw = self.headers.get("Authorization", "")
        token = raw.removeprefix("Bearer ") if raw.startswith("Bearer ") else ""
        if not hmac.compare_digest(token, self.server.observer_token):
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        if self.server.variant == "inconclusive":
            event = self.server._async_events.get(case_tag)
            if event is not None:
                event.wait(timeout=1.0)
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "task_observer_unavailable"})
            return
        snapshot = self.server._task_snapshot(case_tag)
        if snapshot is None:
            snapshot = {
                "schema_version": "1",
                "case_tag": case_tag,
                "resource_id": _ASYNC_RESOURCE_ID,
                "task_id": None,
                "state": "NOT_CREATED",
                "final_result": None,
            }
        self._send(HTTPStatus.OK, snapshot)

    def _read_resource(self, resource_id: str) -> None:
        subject_id = self._subject_id()
        if subject_id is None:
            return
        with self.server.lock:
            resource = self.server.resources.get(resource_id)
            if resource is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            allowed = self._can_view(subject_id, resource)
            payload = copy.deepcopy(resource) if allowed else {"error": "forbidden"}
        self._send(HTTPStatus.OK if allowed else HTTPStatus.FORBIDDEN, payload)

    def _owner_observe(self, resource_id: str) -> None:
        raw = self.headers.get("Authorization", "")
        token = raw.removeprefix("Bearer ") if raw.startswith("Bearer ") else ""
        if self.server.observer_token is not None:
            authorized = hmac.compare_digest(token, self.server.observer_token)
        else:
            authorized = self._subject_id() is not None
        if not authorized:
            if self.server.observer_token is not None:
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

    def _approve(self, resource_id: str) -> None:
        subject_id = self._subject_id()
        if subject_id is None:
            return
        with self.server.lock:
            resource = self.server.resources.get(resource_id)
            if resource is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            subject = _SUBJECTS[subject_id]
            allowed = subject["role"] == "tenant-admin" and subject["tenant_id"] == resource["tenant_id"] and resource["workflow_state"] == "PENDING"
            if self.server.variant == "vulnerable":
                allowed = subject["role"] == "tenant-admin" and subject["tenant_id"] == resource["tenant_id"]
            if allowed:
                resource["workflow_state"] = "APPROVED"
                resource["version"] += 1
                self.server.persist_resource(resource)
            payload = copy.deepcopy(resource) if allowed else {"error": "forbidden"}
        self._send(HTTPStatus.OK if allowed else HTTPStatus.FORBIDDEN, payload)

    def _batch_modify(self) -> None:
        subject_id = self._subject_id()
        body = self._read_json()
        if subject_id is None or body is None:
            return
        resource_ids = body.get("resource_ids")
        value = body.get("value")
        if set(body) != {"resource_ids", "value"} or not isinstance(resource_ids, list) or not 2 <= len(resource_ids) <= 16 or len(set(resource_ids)) != len(resource_ids) or not all(isinstance(item, str) for item in resource_ids) or not isinstance(value, str) or len(value) > 128:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_body"})
            return
        with self.server.lock:
            resources = [self.server.resources.get(resource_id) for resource_id in resource_ids]
            if any(resource is None for resource in resources):
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            assert all(resource is not None for resource in resources)
            allowed = all(self._can_modify(subject_id, resource) for resource in resources)
            if allowed:
                for resource in resources:
                    resource["value"] = value
                    resource["version"] += 1
                    self.server.persist_resource(resource)
            elif self.server.variant == "vulnerable":
                for resource in resources:
                    if self._can_modify(subject_id, resource):
                        resource["value"] = value
                        resource["version"] += 1
                        self.server.persist_resource(resource)
            payload = {"resource_ids": resource_ids, "changed": [resource["resource_id"] for resource in resources if resource["value"] == value]}
        self._send(HTTPStatus.OK if allowed else HTTPStatus.FORBIDDEN, payload)

    def _reset(self) -> None:
        if self.headers.get("X-Jiejian-Test-Mode") != "1" or self.client_address[0] != "127.0.0.1":
            self._send(HTTPStatus.FORBIDDEN, {"error": "test_only"})
            return
        self.server.reset()
        self._send(HTTPStatus.NO_CONTENT, None)

    def _can_view(self, subject_id: str, resource: dict[str, Any]) -> bool:
        subject = _SUBJECTS[subject_id]
        return (
            subject_id == resource["owner_subject_id"]
            or (
                subject["role"] in {"department-admin", "tenant-admin"}
                and subject["department_id"] == resource["department_id"]
            )
            or (
                subject["role"] == "tenant-admin"
                and subject["tenant_id"] == resource["tenant_id"]
            )
        )

    def _can_modify(self, subject_id: str, resource: dict[str, Any]) -> bool:
        subject = _SUBJECTS[subject_id]
        return (
            resource["workflow_state"] == "DRAFT"
            and (
                subject_id == resource["owner_subject_id"]
                or (
                    subject["role"] == "department-admin"
                    and subject["department_id"] == resource["department_id"]
                )
                or (
                    subject["role"] == "tenant-admin"
                    and subject["tenant_id"] == resource["tenant_id"]
                )
            )
        )

    def _subject_id(self) -> str | None:
        raw = self.headers.get("Authorization", "")
        if not raw.startswith("Bearer "):
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return None
        token = raw.removeprefix("Bearer ")
        for subject_id, expected in self.server.tokens.items():
            if hmac.compare_digest(token, expected):
                return subject_id
        self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return None

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

    @staticmethod
    def _resource_id(path: str, prefix: str) -> str | None:
        if not path.startswith(prefix):
            return None
        resource_id = path.removeprefix(prefix)
        return resource_id if resource_id and "/" not in resource_id else None

    def _send(self, status: HTTPStatus, payload: dict[str, Any] | None) -> None:
        encoded = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if encoded:
            self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def create_complex_permission_test_server(
    *,
    variant: Variant,
    port: int = 0,
    tokens: dict[str, str] | None = None,
    database_path: str | Path | None = None,
    audit_root: str | Path | None = None,
    observer_token: str | None = None,
) -> ComplexPermissionTestServer:
    selected_tokens = tokens or {
        subject_id: f"permission-{subject_id}-token"
        for subject_id in _SUBJECTS
    }
    return ComplexPermissionTestServer(
        ("127.0.0.1", port),
        variant=variant,
        tokens=selected_tokens,
        database_path=database_path,
        audit_root=audit_root,
        observer_token=observer_token,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="界鉴复杂权限测试 Target")
    parser.add_argument("--variant", choices=("fixed", "vulnerable", "inconclusive"), required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database-path", type=Path, default=None)
    parser.add_argument("--audit-root", type=Path, default=None)
    arguments = parser.parse_args()
    environment_refs = {
        "member-a": "JIEJIAN_PERMISSION_MEMBER_A",
        "member-a2": "JIEJIAN_PERMISSION_MEMBER_A2",
        "member-b": "JIEJIAN_PERMISSION_MEMBER_B",
        "dept-admin-a": "JIEJIAN_PERMISSION_DEPT_ADMIN_A",
        "dept-admin-a2": "JIEJIAN_PERMISSION_DEPT_ADMIN_A2",
        "tenant-admin-a": "JIEJIAN_PERMISSION_TENANT_ADMIN_A",
        "peer-a": "JIEJIAN_PERMISSION_PEER_A",
    }
    missing = tuple(name for name in (*environment_refs.values(), "JIEJIAN_PERMISSION_OWNER_OBSERVER") if not os.environ.get(name))
    if missing:
        raise SystemExit("sample credentials are not configured")
    server = create_complex_permission_test_server(
        variant=arguments.variant,
        port=arguments.port,
        tokens={subject_id: os.environ[name] for subject_id, name in environment_refs.items()},
        observer_token=os.environ["JIEJIAN_PERMISSION_OWNER_OBSERVER"],
        database_path=arguments.database_path,
        audit_root=arguments.audit_root,
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
