# 协作空间 Sample 的本机 Web 服务、会话边界与导出业务入口。
# 真实运行数据由 storage/background 负责落入受控 runtime root；本模块不调用界鉴 Verification。

from __future__ import annotations

import argparse
import base64
import hmac
import json
import os
import runpy
import secrets
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal, Mapping
from urllib.parse import parse_qs, unquote, urlsplit
from xml.sax.saxutils import escape as xml_escape

if __package__:
    from .background import ExportWorker
    from .page import APPLICATION_PAGE
    from .storage import CollaborationStorage, PROJECT_ID, PROJECT_NAME, RESOURCE_ID
else:
    # 正式 Sample 以 source 为模块根运行，仓库测试则通过命名空间包导入。
    from background import ExportWorker
    from page import APPLICATION_PAGE
    from storage import CollaborationStorage, PROJECT_ID, PROJECT_NAME, RESOURCE_ID


AuthorizationOrder = Literal["ENQUEUE_BEFORE_AUTHORIZE", "AUTHORIZE_BEFORE_ENQUEUE"]
BlobObservation = Literal["AVAILABLE", "UNAVAILABLE"]
OwnerObservation = Literal["AVAILABLE", "UNAVAILABLE"]
ValidationBreakMode = Literal[
    "object_tenant_check_missing",
    "new_entry_inheritance",
    "feature_authorization_bypass",
    "delegation_authority_expansion",
    "deny_async_consequence",
]
ValidationImplementation = Literal["MODE_FAULT_PRESENT", "MODE_GUARD_ACTIVE"]

_VALIDATION_BREAK_MODES = {
    "object_tenant_check_missing",
    "new_entry_inheritance",
    "feature_authorization_bypass",
    "delegation_authority_expansion",
    "deny_async_consequence",
}

_MARKER_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-")
_SECRET_ENV = {
    "alice": "JIEJIAN_SAMPLE_ALICE_PASSWORD",
    "bob": "JIEJIAN_SAMPLE_BOB_PASSWORD",
}
_SESSION_ENV = {
    "alice": "JIEJIAN_SAMPLE_ALICE_SESSION",
    "bob": "JIEJIAN_SAMPLE_BOB_SESSION",
}
_OWNER_OBSERVER_ENV = "JIEJIAN_SAMPLE_OWNER_OBSERVER"
_ACCOUNT_DISPLAY_NAMES = {"alice": "项目负责人", "bob": "普通成员"}


def _read_secret_map(
    explicit: Mapping[str, str] | None,
    names: Mapping[str, str],
    *,
    required: bool,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for account, env_name in names.items():
        value = (explicit or {}).get(account) or os.environ.get(env_name)
        if value:
            values[account] = value
        elif required:
            raise ValueError(f"missing injected credential for {account}")
    return values


def _valid_marker(value: str) -> bool:
    return 1 <= len(value) <= 128 and value[0].isalpha() and all(char in _MARKER_CHARS for char in value)


def _new_marker() -> str:
    return "manual-" + secrets.token_hex(16)


def _valid_sas(value: str | None, expected: str | None, *, resource: str) -> bool:
    if not value or not expected:
        return False
    try:
        actual = parse_qs(value.lstrip("?"), keep_blank_values=False, strict_parsing=True)
        wanted = parse_qs(expected.lstrip("?"), keep_blank_values=False, strict_parsing=True)
    except ValueError:
        return False
    required = {"sr": "q", "sp": "r"} if resource == "queue" else {"sr": "c", "sp": "rl"}
    if any(actual.get(key) != wanted.get(key, [default]) for key, default in required.items()):
        return False
    return all(actual.get(key) == values for key, values in wanted.items())


class CollaborationSpaceServer(ThreadingHTTPServer):
    """只绑定 loopback 的协作空间应用；关闭和 reset 都会回收自己的后台 worker。"""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        address: tuple[str, int],
        *,
        authorization_order: AuthorizationOrder = "AUTHORIZE_BEFORE_ENQUEUE",
        owner_observation: OwnerObservation = "AVAILABLE",
        blob_observation: BlobObservation = "AVAILABLE",
        validation_mode: ValidationBreakMode | None = None,
        validation_implementation: ValidationImplementation | None = None,
        runtime_root: str | Path | None = None,
        authorization_policy_path: str | Path | None = None,
        passwords: Mapping[str, str] | None = None,
        session_material: Mapping[str, str] | None = None,
        queue_sas: str | None = None,
        blob_sas: str | None = None,
        task_bearer: str | None = None,
        owner_observer: str | None = None,
    ) -> None:
        if address[0] != "127.0.0.1":
            raise ValueError("collaboration sample only binds to 127.0.0.1")
        if authorization_order not in {"ENQUEUE_BEFORE_AUTHORIZE", "AUTHORIZE_BEFORE_ENQUEUE"}:
            raise ValueError("invalid authorization order")
        if owner_observation not in {"AVAILABLE", "UNAVAILABLE"}:
            raise ValueError("invalid owner observation mode")
        if blob_observation not in {"AVAILABLE", "UNAVAILABLE"}:
            raise ValueError("invalid blob observation mode")
        if (validation_mode is None) != (validation_implementation is None):
            raise ValueError("validation mode and implementation must be provided together")
        if validation_mode is not None and validation_mode not in _VALIDATION_BREAK_MODES:
            raise ValueError("invalid validation break mode")
        if validation_implementation not in {None, "MODE_FAULT_PRESENT", "MODE_GUARD_ACTIVE"}:
            raise ValueError("invalid validation implementation")
        self.validation_mode = validation_mode
        self.validation_implementation = validation_implementation
        self.passwords = _read_secret_map(passwords, _SECRET_ENV, required=True)
        injected_sessions = _read_secret_map(session_material, _SESSION_ENV, required=False)
        self.sessions = {account: injected_sessions.get(account, secrets.token_urlsafe(24)) for account in _SECRET_ENV}
        self.queue_sas = queue_sas or os.environ.get("JIEJIAN_SAMPLE_QUEUE_SAS")
        self.blob_sas = blob_sas or os.environ.get("JIEJIAN_SAMPLE_BLOB_SAS")
        self.task_bearer = task_bearer or os.environ.get("JIEJIAN_SAMPLE_TASK_BEARER")
        self.owner_observer = owner_observer or os.environ.get(_OWNER_OBSERVER_ENV)
        self.runtime_root = Path(runtime_root or os.environ.get("JIEJIAN_SAMPLE_RUNTIME_ROOT", "var/runtime/samples/collaboration-space")).resolve()
        self._authorization_policy_path = Path(
            authorization_policy_path or Path(__file__).with_name("authorization_policy.py")
        ).resolve()
        super().__init__(address, CollaborationRequestHandler)
        self.storage = CollaborationStorage(self.runtime_root)
        self._control_path = self.runtime_root / "control.json"
        if not self._control_path.is_file():
            self._write_control(
                authorization_order,
                owner_observation,
                blob_observation,
            )
        self._read_control()
        self.worker = ExportWorker(self.storage)
        self._case_actors: dict[str, str] = {}
        self._write_environment_descriptor()

    def _write_environment_descriptor(self) -> None:
        origin = f"http://127.0.0.1:{self.server_port}"
        descriptor = {
            "application": {
                "origin": origin,
                "project_id": PROJECT_ID,
                "resource_id": RESOURCE_ID,
            },
            "owner_api": {
                "origin": origin,
                "relative_path_template": "/api/observer/resources/{resource_id}",
                "credential_ref": f"env:{_OWNER_OBSERVER_ENV}",
            },
            "sqlite": {
                "relative_path": "database/collaboration-space.sqlite3",
                "database_secret_ref": "env:JIEJIAN_SAMPLE_SQLITE_DATABASE",
                "query_template_id": "resource-state",
                "table_or_view": "resource_state",
            },
            "audit": {
                "relative_path": "audit/events.jsonl",
                "authorized_root_ref": "env:JIEJIAN_SAMPLE_AUDIT_ROOT",
                "relative_file_pattern": "events.jsonl",
                "allowed_fields": [
                    "case_tag",
                    "effect",
                    "event_id",
                    "event_type",
                    "kind",
                    "parent_event_id",
                    "actor_id",
                    "authorization_decision",
                    "delegated_from_event_id",
                    "credential_source",
                    "effect_id",
                    "origin_authorization_event_id",
                    "recorded_at_us",
                    "resource_id",
                    "result",
                    "semantic_key",
                    "sequence",
                    "source_component",
                    "source_location",
                    "subject_id",
                    "task_id",
                ],
            },
            "task": {
                "base_url": origin,
                "relative_path_template": "/api/tasks/{request_marker}",
                "read_only_credential_ref": "env:JIEJIAN_SAMPLE_TASK_BEARER",
            },
            "queue": {
                "service_url": f"{origin}/collaboration",
                "account": "collaboration",
                "queue_name": "export-events",
                "read_only_sas_ref": "env:JIEJIAN_SAMPLE_QUEUE_SAS",
                "allowed_fields": [
                    "case_tag",
                    "effect",
                    "event_id",
                    "event_type",
                    "resource_id",
                    "result",
                    "sequence",
                    "task_id",
                ],
            },
            "blob": {
                "service_url": f"{origin}/collaboration",
                "account": "collaboration",
                "container_name": "exports",
                "prefix_template": "{request_marker}/",
                "read_only_sas_ref": "env:JIEJIAN_SAMPLE_BLOB_SAS",
                "allowed_metadata_fields": ["case_tag", "resource_id"],
            },
        }
        path = self.runtime_root / "environment.json"
        temporary = path.with_name(".environment.json.tmp")
        temporary.write_text(json.dumps(descriptor, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, path)

    def _read_control(
        self,
    ) -> tuple[AuthorizationOrder, OwnerObservation, BlobObservation]:
        """读取源码中的授权顺序和两项关键观察开关；这些控制项不进入 Observer descriptor。"""

        try:
            value = json.loads(self._control_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("sample control is unavailable") from exc
        if type(value) is not dict or set(value) != {
            "schema_version",
            "authorization_order",
            "owner_observation",
            "blob_observation",
        } or value["schema_version"] != "1":
            raise ValueError("sample control has invalid fields")
        authorization_order = self._read_authorization_policy()
        owner_observation = value["owner_observation"]
        blob_observation = value["blob_observation"]
        if value["authorization_order"] != authorization_order:
            raise ValueError("sample control and source authorization order differ")
        if owner_observation not in {"AVAILABLE", "UNAVAILABLE"}:
            raise ValueError("invalid owner observation mode")
        if blob_observation not in {"AVAILABLE", "UNAVAILABLE"}:
            raise ValueError("invalid blob observation mode")
        return authorization_order, owner_observation, blob_observation

    def _read_authorization_policy(self) -> AuthorizationOrder:
        """每次执行前读取受控源码，使 Agent 修改真实决定当前业务顺序。"""

        try:
            namespace = runpy.run_path(str(self._authorization_policy_path))
            resolve = namespace["export_authorization_order"]
            authorization_order = resolve()
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("sample authorization source is unavailable") from exc
        if authorization_order not in {
            "ENQUEUE_BEFORE_AUTHORIZE",
            "AUTHORIZE_BEFORE_ENQUEUE",
        }:
            raise ValueError("invalid authorization order")
        return authorization_order

    def _write_control(
        self,
        authorization_order: AuthorizationOrder,
        owner_observation: OwnerObservation,
        blob_observation: BlobObservation,
    ) -> None:
        payload = {
            "schema_version": "1",
            "authorization_order": authorization_order,
            "owner_observation": owner_observation,
            "blob_observation": blob_observation,
        }
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        temporary = self.runtime_root / ".control.json.tmp"
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, self._control_path)

    @property
    def authorization_order(self) -> AuthorizationOrder:
        return self._read_control()[0]

    @property
    def owner_observation(self) -> OwnerObservation:
        return self._read_control()[1]

    @property
    def blob_observation(self) -> BlobObservation:
        return self._read_control()[2]

    def reset(self) -> None:
        self.worker.stop()
        self.storage.reset()
        self._case_actors.clear()
        self.worker = ExportWorker(self.storage)
        self._write_environment_descriptor()

    def record_case_actor(self, marker: str, account: str) -> None:
        """只在内存中关联本次请求主体，供受控观察故障按 Case 生效。"""

        self._case_actors[marker] = account

    def case_actor(self, marker: str) -> str | None:
        return self._case_actors.get(marker)

    def forget_case(self, marker: str) -> None:
        self._case_actors.pop(marker, None)

    def server_close(self) -> None:
        worker = getattr(self, "worker", None)
        if worker is not None:
            worker.stop()
        super().server_close()


class CollaborationRequestHandler(BaseHTTPRequestHandler):
    """提供登录、项目、导出和六面本地数据源兼容端点，不记录请求正文或查询秘密。"""

    server: CollaborationSpaceServer

    def do_GET(self) -> None:  # noqa: N802 - standard-library callback name
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/health":
            self._json(HTTPStatus.OK, {"code": "HEALTHY"})
            return
        if path in {"/", "/login"}:
            self._page()
            return
        if path == "/api/session":
            self._get_session()
            return
        if path == f"/api/observer/resources/{RESOURCE_ID}":
            if not self._authorized_bearer(
                self.server.owner_observer,
                code="OWNER_OBSERVER_ACCESS_DENIED",
            ):
                return
            marker = self.headers.get("X-Jiejian-Case-ID", "")
            # 初始面与 BEFORE 面尚未记录主体，仍返回可靠基线；Bob 的目标请求到达后，
            # 证据受限版才关闭只读业务状态，让结论诚实停留在“证据不足”。
            if (
                self.server.owner_observation == "UNAVAILABLE"
                and self.server.case_actor(marker) == "bob"
            ):
                self._json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"code": "OWNER_OBSERVER_UNAVAILABLE"},
                )
                return
            self._json(HTTPStatus.OK, self.server.storage.resource_state())
            return
        if path == "/api/projects":
            if self._session_account() is None:
                return
            self._json(
                HTTPStatus.OK,
                {"projects": [self.server.storage.project_catalog_entry()]},
            )
            return
        if path == f"/api/projects/{PROJECT_ID}":
            account = self._session_account()
            if account is None:
                return
            if self.server.storage.member_role(account) is None:
                self._forbidden("PROJECT_MEMBER_REQUIRED")
                return
            self._json(HTTPStatus.OK, self.server.storage.project_detail())
            return
        if path == f"/api/projects/{PROJECT_ID}/collaboration":
            account = self._session_account()
            if account is None:
                return
            if self.server.storage.member_role(account) is None:
                self._forbidden("PROJECT_MEMBER_REQUIRED")
                return
            # 该端点只承载成员日常查看能力，避免把导出任务状态误当成
            # DATA_DISCLOSURE 的受保护内容。
            self._json(
                HTTPStatus.OK,
                self.server.storage.collaboration_materials(),
            )
            return
        if path.startswith(f"/api/projects/{PROJECT_ID}/exports/"):
            account = self._session_account()
            if account is None:
                return
            if self.server.storage.member_role(account) is None:
                self._forbidden("PROJECT_MEMBER_REQUIRED")
                return
            resource_ids = parse_qs(
                parsed.query,
                keep_blank_values=True,
            ).get("resource_id", [])
            if resource_ids and resource_ids != [RESOURCE_ID]:
                self._json(HTTPStatus.BAD_REQUEST, {"code": "EXPORT_RESOURCE_INVALID"})
                return
            marker = unquote(path.rsplit("/", 1)[-1])
            record = self.server.storage.find_job(marker)
            self._json(HTTPStatus.OK, {"code": "EXPORT_STATUS", "request_marker": marker, "export": record})
            return
        if path.startswith("/api/tasks/"):
            self._get_task(path)
            return
        if self._handle_queue(path):
            return
        if self._handle_blob(path, method="GET"):
            return
        self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND"})

    def do_HEAD(self) -> None:  # noqa: N802 - standard-library callback name
        if self._handle_blob(urlsplit(self.path).path, method="HEAD"):
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - standard-library callback name
        path = urlsplit(self.path).path
        if path == "/api/session":
            self._create_session()
            return
        if path == "/api/demo-session":
            self._create_demo_session()
            return
        if path == f"/api/projects/{PROJECT_ID}/exports":
            self._create_export()
            return
        if path in {"/reset", "/api/reset"}:
            if self.client_address[0] != "127.0.0.1" or self.headers.get("X-Jiejian-Test-Mode") != "1":
                self._forbidden("RESET_LOOPBACK_ONLY")
                return
            self.server.reset()
            self._json(HTTPStatus.OK, {"code": "RESET_COMPLETE"})
            return
        self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND"})

    def do_DELETE(self) -> None:  # noqa: N802 - standard-library callback name
        path = urlsplit(self.path).path
        if path == f"/api/projects/{PROJECT_ID}/exports":
            self._revoke_export()
            return
        if path != "/api/session":
            self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND"})
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Set-Cookie", "jiejian_sample_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _create_session(self) -> None:
        body = self._read_json_or_form()
        account = body.get("username") or body.get("account") or body.get("role")
        password = body.get("password")
        if not isinstance(account, str) or account not in self.server.passwords or not isinstance(password, str):
            self._json(HTTPStatus.UNAUTHORIZED, {"code": "LOGIN_FAILED"})
            return
        if not hmac.compare_digest(password, self.server.passwords[account]):
            self._json(HTTPStatus.UNAUTHORIZED, {"code": "LOGIN_FAILED"})
            return
        self._finish_session(account)

    def _create_demo_session(self) -> None:
        """为本机演示页建立真实会话；身份选择不承担认证产品语义。"""

        if self.client_address[0] != "127.0.0.1":
            self._forbidden("DEMO_SESSION_LOOPBACK_ONLY")
            return
        account = self._read_json_or_form().get("account")
        if not isinstance(account, str) or account not in self.server.sessions:
            self._json(HTTPStatus.BAD_REQUEST, {"code": "DEMO_IDENTITY_INVALID"})
            return
        self._finish_session(account)

    def _finish_session(self, account: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Set-Cookie", f"jiejian_sample_session={self.server.sessions[account]}; Path=/; HttpOnly; SameSite=Lax")
        self.send_header("Cache-Control", "no-store")
        self._finish_json({"code": "SESSION_CREATED", "account": account, "role": _ACCOUNT_DISPLAY_NAMES[account]})

    def _create_export(self) -> None:
        account = self._session_account()
        if account is None:
            return
        if self.server.storage.member_role(account) is None:
            self._forbidden("PROJECT_MEMBER_REQUIRED")
            return
        requested_resource = self._read_json_or_form().get("resource_id", RESOURCE_ID)
        if requested_resource != RESOURCE_ID:
            self._json(HTTPStatus.BAD_REQUEST, {"code": "EXPORT_RESOURCE_INVALID"})
            return
        marker = self.headers.get("X-Jiejian-Case-ID") or _new_marker()
        if not _valid_marker(marker):
            self._json(HTTPStatus.BAD_REQUEST, {"code": "REQUEST_MARKER_INVALID"})
            return
        self.server.record_case_actor(marker, account)
        request_event_id = self.server.storage.append_audit(
            marker=marker,
            task_id=marker,
            event_type="request_received",
            sequence=1,
            result="received",
            effect="REQUESTED",
            kind="ENTRY",
            semantic_key="request_received",
            subject_id=account,
            actor_id=account,
            credential_source="session-cookie",
            source_component="collaboration-server",
            source_location="api:/projects/export",
        )
        identity_event_id = self.server.storage.append_audit(
            marker=marker,
            task_id=marker,
            event_type="server_identity_resolved",
            sequence=2,
            result="resolved",
            effect="IDENTIFIED",
            parent_event_id=request_event_id,
            kind="IDENTITY",
            semantic_key="server_identity_resolved",
            subject_id=account,
            actor_id="collaboration-server",
            credential_source="session-cookie",
            source_component="collaboration-server",
            source_location="session:account",
        )
        if self.server.validation_mode is not None:
            self._create_validation_export(
                account=account,
                marker=marker,
                identity_event_id=identity_event_id,
            )
            return
        if account == "bob" and self.server.authorization_order == "AUTHORIZE_BEFORE_ENQUEUE":
            self.server.storage.append_audit(
                marker=marker,
                task_id=marker,
                event_type="authorization_decided",
                sequence=3,
                result="denied",
                effect="DENY",
                parent_event_id=identity_event_id,
                kind="AUTHORIZATION",
                semantic_key="authorization_decided",
                subject_id=account,
                actor_id="authorization-policy",
                authorization_decision="DENY",
                source_component="collaboration-server",
                source_location="policy:project-owner",
            )
            self._forbidden("EXPORT_PERMISSION_REQUIRED")
            return
        job = self.server.storage.create_job(marker, account)
        if not job["_created"]:
            if job["state"] == "REVOKED":
                self._json(
                    HTTPStatus.CONFLICT,
                    {"code": "EXPORT_MARKER_REVOKED", "request_marker": marker},
                )
                return
            if account == "bob":
                self._forbidden("EXPORT_PERMISSION_REQUIRED")
                return
            self._json(
                HTTPStatus.ACCEPTED,
                {"code": "EXPORT_ALREADY_ACCEPTED", "request_marker": marker, "task_id": job["task_id"]},
            )
            return
        self.server.storage.write_task(job)
        created_event_id = self.server.storage.append_audit(
            marker=marker,
            task_id=str(job["task_id"]),
            event_type="export_request_created",
            sequence=3,
            result="created",
            effect="PENDING",
            parent_event_id=identity_event_id,
            kind="PERSISTENT_EFFECT",
            semantic_key="export_request_created",
            subject_id=account,
            actor_id="collaboration-server",
            source_component="collaboration-server",
            source_location="storage:export-job",
        )
        decision = "DENY" if account == "bob" else "ALLOW"
        decision_event_id = self.server.storage.append_audit(
            marker=marker,
            task_id=str(job["task_id"]),
            event_type="authorization_decided",
            sequence=4,
            result=decision.casefold(),
            effect=decision,
            parent_event_id=created_event_id,
            kind="AUTHORIZATION",
            semantic_key="authorization_decided",
            subject_id=account,
            actor_id="authorization-policy",
            authorization_decision=decision,
            source_component="collaboration-server",
            source_location="policy:project-owner",
        )
        self.server.storage.append_audit(
            marker=marker,
            task_id=str(job["task_id"]),
            event_type="export_message_sent",
            sequence=5,
            result="queued",
            effect="PENDING",
            parent_event_id=decision_event_id,
            kind="MESSAGE",
            semantic_key="export_message_sent",
            subject_id=account,
            actor_id="collaboration-server",
            origin_authorization_event_id=decision_event_id,
            source_component="collaboration-server",
            source_location="queue:export-events",
        )
        self.server.storage.append_queue_message(
            marker=marker,
            task_id=str(job["task_id"]),
            event_type="EXPORT_ENQUEUED",
            sequence=1,
            result="queued",
            effect="PENDING",
        )
        self.server.worker.enqueue(job)
        if account == "bob":
            self._forbidden("EXPORT_PERMISSION_REQUIRED")
            return
        self._json(HTTPStatus.ACCEPTED, {"code": "EXPORT_ACCEPTED", "request_marker": marker, "task_id": job["task_id"]})

    def _create_validation_export(
        self,
        *,
        account: str,
        marker: str,
        identity_event_id: str,
    ) -> None:
        """仅供 competition validation 选择真实权限实现；普通 Official Sample 不进入此分支。"""

        implementation = self.server.validation_implementation
        mode = self.server.validation_mode
        if implementation is None or mode is None:
            raise RuntimeError("validation configuration is incomplete")
        if account == "alice":
            authorization_id = self.server.storage.append_audit(
                marker=marker,
                task_id=marker,
                event_type="authorization_decided",
                sequence=3,
                result="allow",
                effect="ALLOW",
                parent_event_id=identity_event_id,
                kind="AUTHORIZATION",
                semantic_key="authorization_decided",
                subject_id=account,
                actor_id="authorization-policy",
                authorization_decision="ALLOW",
                source_component="collaboration-server",
                source_location="policy:project-owner",
            )
            job = self._enqueue_validation_export(
                account=account,
                marker=marker,
                parent_event_id=authorization_id,
                first_sequence=4,
                origin_authorization_event_id=authorization_id,
            )
            self._json(
                HTTPStatus.ACCEPTED,
                {
                    "code": "EXPORT_ACCEPTED",
                    "request_marker": marker,
                    "task_id": job["task_id"],
                },
            )
            return

        if implementation == "MODE_GUARD_ACTIVE":
            self.server.storage.append_audit(
                marker=marker,
                task_id=marker,
                event_type="authorization_decided",
                sequence=3,
                result="denied",
                effect="DENY",
                parent_event_id=identity_event_id,
                kind="AUTHORIZATION",
                semantic_key="authorization_decided",
                subject_id=account,
                actor_id="authorization-policy",
                authorization_decision="DENY",
                source_component="collaboration-server",
                source_location=f"policy:{mode}",
            )
            self._forbidden("EXPORT_PERMISSION_REQUIRED")
            return

        if mode in {"object_tenant_check_missing", "new_entry_inheritance"}:
            job = self._enqueue_validation_export(
                account=account,
                marker=marker,
                parent_event_id=identity_event_id,
                first_sequence=3,
                origin_authorization_event_id=None,
            )
            self._json(
                HTTPStatus.ACCEPTED,
                {
                    "code": "EXPORT_ACCEPTED",
                    "request_marker": marker,
                    "task_id": job["task_id"],
                },
            )
            return

        authorization_id = self.server.storage.append_audit(
            marker=marker,
            task_id=marker,
            event_type="authorization_decided",
            sequence=3,
            result="denied",
            effect="DENY",
            parent_event_id=identity_event_id,
            kind="AUTHORIZATION",
            semantic_key="authorization_decided",
            subject_id=account,
            actor_id="authorization-policy",
            authorization_decision="DENY",
            source_component="collaboration-server",
            source_location=f"policy:{mode}",
        )
        parent_id = authorization_id
        first_sequence = 4
        if mode == "feature_authorization_bypass":
            parent_id = self.server.storage.append_audit(
                marker=marker,
                task_id=marker,
                event_type="feature_export_entered",
                sequence=4,
                result="continued",
                effect="PENDING",
                parent_event_id=authorization_id,
                kind="MESSAGE",
                semantic_key="feature_export_entered",
                subject_id=account,
                actor_id="collaboration-server",
                origin_authorization_event_id=authorization_id,
                source_component="collaboration-server",
                source_location="feature:quick-export",
            )
            first_sequence = 5
        elif mode == "delegation_authority_expansion":
            parent_id = self.server.storage.append_audit(
                marker=marker,
                task_id=marker,
                event_type="service_authority_expanded",
                sequence=4,
                result="delegated",
                effect="PENDING",
                parent_event_id=authorization_id,
                kind="DELEGATION",
                semantic_key="service_authority_expanded",
                subject_id=account,
                actor_id="export-worker",
                origin_authorization_event_id=authorization_id,
                delegated_from_event_id=authorization_id,
                source_component="export-worker",
                source_location="service:export-authority",
            )
            first_sequence = 5
        elif mode == "deny_async_consequence":
            parent_id = self.server.storage.append_audit(
                marker=marker,
                task_id=marker,
                event_type="denied_request_dispatched",
                sequence=4,
                result="queued",
                effect="PENDING",
                parent_event_id=authorization_id,
                kind="MESSAGE",
                semantic_key="denied_request_dispatched",
                subject_id=account,
                actor_id="collaboration-server",
                origin_authorization_event_id=authorization_id,
                source_component="collaboration-server",
                source_location="queue:denied-export",
            )
            first_sequence = 5
        self._enqueue_validation_export(
            account=account,
            marker=marker,
            parent_event_id=parent_id,
            first_sequence=first_sequence,
            origin_authorization_event_id=authorization_id,
        )
        self._forbidden("EXPORT_PERMISSION_REQUIRED")

    def _enqueue_validation_export(
        self,
        *,
        account: str,
        marker: str,
        parent_event_id: str,
        first_sequence: int,
        origin_authorization_event_id: str | None,
    ) -> dict[str, Any]:
        """让验证模式仍经过真实 Job、Queue、Worker 与最终资料包副作用。"""

        job = self.server.storage.create_job(marker, account)
        if not job["_created"]:
            raise RuntimeError("validation export marker must be fresh")
        self.server.storage.write_task(job)
        created_event_id = self.server.storage.append_audit(
            marker=marker,
            task_id=str(job["task_id"]),
            event_type="export_request_created",
            sequence=first_sequence,
            result="created",
            effect="PENDING",
            parent_event_id=parent_event_id,
            kind="PERSISTENT_EFFECT",
            semantic_key="export_request_created",
            subject_id=account,
            actor_id="collaboration-server",
            source_component="collaboration-server",
            source_location="storage:export-job",
        )
        self.server.storage.append_audit(
            marker=marker,
            task_id=str(job["task_id"]),
            event_type="export_message_sent",
            sequence=first_sequence + 1,
            result="queued",
            effect="PENDING",
            parent_event_id=created_event_id,
            kind="MESSAGE",
            semantic_key="export_message_sent",
            subject_id=account,
            actor_id="collaboration-server",
            origin_authorization_event_id=origin_authorization_event_id,
            source_component="collaboration-server",
            source_location="queue:export-events",
        )
        self.server.storage.append_queue_message(
            marker=marker,
            task_id=str(job["task_id"]),
            event_type="EXPORT_ENQUEUED",
            sequence=1,
            result="queued",
            effect="PENDING",
        )
        self.server.worker.enqueue(job)
        return job

    def _revoke_export(self) -> None:
        """由项目负责人逻辑撤销当前交付物，已发生的导出历史继续保留。"""

        account = self._session_account()
        if account is None:
            return
        if account != "alice":
            self._forbidden("PROJECT_OWNER_REQUIRED")
            return
        marker = self.headers.get("X-Jiejian-Case-ID", "")
        if not _valid_marker(marker):
            self._json(HTTPStatus.BAD_REQUEST, {"code": "REQUEST_MARKER_INVALID"})
            return
        result = self.server.storage.revoke_export(marker)
        if result["code"] == "EXPORT_NOT_READY_FOR_REVOKE":
            self._json(HTTPStatus.CONFLICT, result)
            return
        if result["code"] in {"EXPORT_REVOKED", "EXPORT_ALREADY_REVOKED"}:
            self.server.forget_case(marker)
        self._json(HTTPStatus.OK, result)

    def _get_task(self, path: str) -> None:
        if not self._authorized_bearer(
            self.server.task_bearer,
            code="TASK_ACCESS_DENIED",
        ):
            return
        parts = path.strip("/").split("/")
        if len(parts) not in {3, 4} or parts[0:2] != ["api", "tasks"] or (len(parts) == 4 and parts[3] != "status"):
            self._json(HTTPStatus.NOT_FOUND, {"code": "NOT_FOUND"})
            return
        marker = unquote(parts[2])
        task = self.server.storage.task_for_marker(marker)
        if task is None:
            task = {"schema_version": "1", "case_tag": marker, "resource_id": RESOURCE_ID, "task_id": None, "state": "NOT_CREATED", "final_result": None}
        self._json(HTTPStatus.OK, task)

    def _handle_queue(self, path: str) -> bool:
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "collaboration" or parts[2] != "messages":
            return False
        query = urlsplit(self.path).query
        if not _valid_sas(query, self.server.queue_sas, resource="queue"):
            self._json(HTTPStatus.UNAUTHORIZED if not query else HTTPStatus.FORBIDDEN, {"code": "QUEUE_ACCESS_DENIED"})
            return True
        payload = []
        for record in self.server.storage.queue_records():
            encoded = base64.b64encode(json.dumps(record, separators=(",", ":"), sort_keys=True).encode("utf-8")).decode("ascii")
            payload.append(f"<QueueMessage><MessageId>{xml_escape(str(record['event_id']))}</MessageId><MessageText>{encoded}</MessageText></QueueMessage>")
        self._bytes(HTTPStatus.OK, ("<QueueMessagesList>" + "".join(payload) + "</QueueMessagesList>").encode("utf-8"), "application/xml; charset=utf-8")
        return True

    def _handle_blob(self, path: str, *, method: str) -> bool:
        parts = path.strip("/").split("/")
        if not parts or parts[0] != "collaboration" or len(parts) < 2 or parts[1] != "exports":
            return False
        query = urlsplit(self.path).query
        sas_only = query.split("&restype=", 1)[0].split("&comp=", 1)[0]
        if not _valid_sas(sas_only, self.server.blob_sas, resource="blob"):
            self._json(HTTPStatus.UNAUTHORIZED if not query else HTTPStatus.FORBIDDEN, {"code": "BLOB_ACCESS_DENIED"})
            return True
        marker = (
            parse_qs(query).get("prefix", [""])[0].split("/", 1)[0]
            if len(parts) == 2
            else unquote(parts[2])
        )
        # BEFORE 发生在 Target 之前，此时还没有主体关联，仍可可靠确认初始为空；
        # 只有 Bob 的目标请求已经实际到达后，证据不足场景才让关键读取面失效。
        if (
            self.server.blob_observation == "UNAVAILABLE"
            and self.server.case_actor(marker) == "bob"
        ):
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"code": "BLOB_UNAVAILABLE"})
            return True
        if len(parts) == 2:
            prefix = parse_qs(query).get("prefix", [""])[0]
            objects = [item for item in self.server.storage.blob_objects() if item["name"].startswith(prefix)]
            entries = [
                "<Blob><Name>{}</Name><Properties><Etag>\"{}\"</Etag><Content-Length>{}</Content-Length></Properties><Metadata><case_tag>{}</case_tag><resource_id>{}</resource_id></Metadata></Blob>".format(
                    xml_escape(item["name"]), item["etag"], item["length"], xml_escape(item["case_tag"]), RESOURCE_ID
                )
                for item in objects
            ]
            body = ("<EnumerationResults><Blobs>" + "".join(entries) + "</Blobs><NextMarker></NextMarker></EnumerationResults>").encode("utf-8")
            self._bytes(HTTPStatus.OK, body, "application/xml; charset=utf-8")
            return True
        name = "/".join(parts[2:])
        item = next((entry for entry in self.server.storage.blob_objects() if entry["name"] == name), None)
        if item is None:
            self._json(HTTPStatus.NOT_FOUND, {"code": "BLOB_NOT_FOUND"})
            return True
        body = item["path"].read_bytes()
        etag = f'"{item["etag"]}"'
        if method == "HEAD":
            self.send_response(HTTPStatus.OK)
            self.send_header("Etag", etag)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("x-ms-meta-case_tag", item["case_tag"])
            self.send_header("x-ms-meta-resource_id", RESOURCE_ID)
            self.end_headers()
            return True
        selected = body
        range_value = self.headers.get("Range", "")
        status = HTTPStatus.OK
        if range_value.startswith("bytes=0-"):
            try:
                selected = body[
                    : min(len(body), int(range_value.removeprefix("bytes=0-")) + 1)
                ]
                status = HTTPStatus.PARTIAL_CONTENT
            except ValueError:
                pass
        self.send_response(status)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(selected)))
        self.send_header("Etag", etag)
        self.send_header("x-ms-meta-case_tag", item["case_tag"])
        self.send_header("x-ms-meta-resource_id", RESOURCE_ID)
        self.end_headers()
        self.wfile.write(selected)
        return True

    def _session_account(self) -> str | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            self._json(HTTPStatus.UNAUTHORIZED, {"code": "SESSION_INVALID"})
            return None
        value = cookie.get("jiejian_sample_session")
        if value is None:
            self._json(HTTPStatus.UNAUTHORIZED, {"code": "SESSION_REQUIRED"})
            return None
        for account, session in self.server.sessions.items():
            if hmac.compare_digest(value.value, session):
                return account
        self._json(HTTPStatus.UNAUTHORIZED, {"code": "SESSION_INVALID"})
        return None

    def _get_session(self) -> None:
        account = self._session_account()
        if account is not None:
            self._json(HTTPStatus.OK, {"code": "SESSION_ACTIVE", "account": account, "role": _ACCOUNT_DISPLAY_NAMES[account]})

    def _authorized_bearer(self, expected: str | None, *, code: str) -> bool:
        value = self.headers.get("Authorization", "")
        if expected and value.startswith("Bearer ") and hmac.compare_digest(value[7:], expected):
            return True
        self._json(HTTPStatus.UNAUTHORIZED, {"code": code})
        return False

    def _read_json_or_form(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            return {}
        if length < 1 or length > 8192:
            return {}
        raw = self.rfile.read(length)
        try:
            if self.headers.get("Content-Type", "").startswith("application/json"):
                value = json.loads(raw.decode("utf-8"))
                return value if isinstance(value, dict) else {}
            fields = parse_qs(raw.decode("utf-8"), strict_parsing=True)
            return {key: values[0] for key, values in fields.items() if values}
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return {}

    def _page(self) -> None:
        body = APPLICATION_PAGE.encode("utf-8")
        self._bytes(HTTPStatus.OK, body, "text/html; charset=utf-8")

    def _forbidden(self, code: str) -> None:
        self._json(HTTPStatus.FORBIDDEN, {"code": code})

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self._bytes(status, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), "application/json; charset=utf-8")

    def _finish_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def create_collaboration_space_server(
    *,
    port: int = 0,
    authorization_order: AuthorizationOrder = "AUTHORIZE_BEFORE_ENQUEUE",
    owner_observation: OwnerObservation = "AVAILABLE",
    blob_observation: BlobObservation = "AVAILABLE",
    validation_mode: ValidationBreakMode | None = None,
    validation_implementation: ValidationImplementation | None = None,
    runtime_root: str | Path | None = None,
    authorization_policy_path: str | Path | None = None,
    passwords: Mapping[str, str] | None = None,
    session_material: Mapping[str, str] | None = None,
    queue_sas: str | None = None,
    blob_sas: str | None = None,
    task_bearer: str | None = None,
    owner_observer: str | None = None,
) -> CollaborationSpaceServer:
    """创建协作空间服务；密码、会话材料和只读凭据必须来自调用者或环境。"""

    return CollaborationSpaceServer(
        ("127.0.0.1", port),
        authorization_order=authorization_order,
        owner_observation=owner_observation,
        blob_observation=blob_observation,
        validation_mode=validation_mode,
        validation_implementation=validation_implementation,
        runtime_root=runtime_root,
        authorization_policy_path=authorization_policy_path,
        passwords=passwords,
        session_material=session_material,
        queue_sas=queue_sas,
        blob_sas=blob_sas,
        task_bearer=task_bearer,
        owner_observer=owner_observer,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="协作空间 Sample Target")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    arguments = parser.parse_args()
    server = create_collaboration_space_server(
        port=arguments.port,
        runtime_root=arguments.runtime_root,
    )
    try:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
