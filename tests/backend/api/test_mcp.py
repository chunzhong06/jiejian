# 验证 MCP 入口使用官方 SDK、长期 Bearer 配对、逐 Project 临时分级和现有 ApplicationCore 事实。

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import anyio
import httpx2
import pytest
from mcp import MCPError
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.repair import RepairContractReference
from product.backend.workflows.mcp_access import (
    MCP_PAIRING_SECRET_REF,
    MCPAccessController,
    MCPAccessLevel,
    MCPConnectionState,
)
from tests.fixtures.control_plane import TEST_CONTROL_ORIGIN, TestClient, create_app


pytestmark = pytest.mark.database


class _StubToolView(BaseModel):
    schema_version: Literal["1"] = "1"
    object_id: str


class _StubSourceChangeView(BaseModel):
    change_id: str
    project_id: str
    actual_changed_path_count: int
    claimed_paths: tuple[str, ...]
    added_paths: tuple[str, ...]
    modified_paths: tuple[str, ...]
    removed_paths: tuple[str, ...]
    summary: str


class _StubRepairContract(BaseModel):
    project_id: str
    source_run_id: str
    source_finding_id: str
    repair_fingerprint: str


from tests.backend.api.test_current_mcp import TOOLS as EXPECTED_MCP_TOOLS


class _MemorySecretStore:
    """在 MCP 直接测试内模拟跨 controller 共享的精确秘密引用。"""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def write(self, secret_ref: str, secret: str) -> None:
        self.values[secret_ref] = secret

    def read(self, secret_ref: str) -> str | None:
        return self.values.get(secret_ref)

    def delete(self, secret_ref: str) -> None:
        self.values.pop(secret_ref, None)

    def configured(self, secret_ref: str | None) -> bool:
        return secret_ref is not None and secret_ref in self.values


def _source(root: Path) -> Path:
    source = root / "source"
    source.mkdir()
    (source / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "MCP fixture", "version": "1"},
                "paths": {},
            }
        ),
        encoding="utf-8",
    )
    return source


def _token_bytes(token: str) -> bytes:
    return base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))


def test_mcp_server_instructions_use_one_completed_user_task_as_change_boundary(
    tmp_path: Path,
) -> None:
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        secret_store=_MemorySecretStore(),
    )
    instructions = app.state.mcp_server.instructions

    assert "READ读取既有事实" in instructions
    assert "PREPARE只登记代码变化声明" in instructions
    assert "完整当前权限" in instructions
    assert "不修改权限或检查结论" in instructions
    app.state.context.close()



def test_mcp_access_controller_restores_pairing_without_restoring_grants() -> None:
    store = _MemorySecretStore()
    access = MCPAccessController("http://127.0.0.1:8765/mcp", store)
    assert access.view().paired is False
    assert access.view().connection_state is MCPConnectionState.DISABLED
    first = access.pair()
    assert first.connection_state is MCPConnectionState.CREDENTIAL_READY
    assert first.access_token is not None
    assert len(_token_bytes(first.access_token)) == 32
    assert "access_token" not in access.view().model_dump()
    access.authorize(f"Bearer {first.access_token}")
    assert access.view().connection_state is MCPConnectionState.AUTHENTICATED
    access.note_activity(None, None)
    metadata_free_activity = access.view()
    assert metadata_free_activity.connection_state is MCPConnectionState.CONNECTED
    assert metadata_free_activity.client_connected is True
    assert metadata_free_activity.client_name is None
    assert metadata_free_activity.client_version is None
    assert metadata_free_activity.last_seen_at_us is not None
    access.note_activity("Codex", "1.2.3")
    access.note_activity(None, None)
    assert access.view().client_name == "Codex"
    assert access.view().client_version == "1.2.3"
    assert access.level_for("proj_a") is MCPAccessLevel.READ

    access.set_level("proj_a", MCPAccessLevel.EXECUTE)
    restarted = MCPAccessController("http://127.0.0.1:8765/mcp", store)
    assert restarted.view().paired is True
    assert restarted.view().accepting_connections is True
    assert restarted.view().project_grants == ()
    assert restarted.view().connection_state is MCPConnectionState.CREDENTIAL_READY
    restarted.authorize(f"Bearer {first.access_token}")
    assert restarted.view().connection_state is MCPConnectionState.AUTHENTICATED
    assert restarted.level_for("proj_a") is MCPAccessLevel.READ

    second = restarted.rotate()
    assert second.access_token is not None and second.access_token != first.access_token
    assert second.project_grants == ()
    with pytest.raises(JiejianError) as old_token:
        restarted.authorize(f"Bearer {first.access_token}")
    assert old_token.value.code == ErrorCode.MCP_AUTH_REQUIRED.value
    assert restarted.view().connection_state is MCPConnectionState.CREDENTIAL_REJECTED

    restarted.pause()
    assert restarted.view().connection_state is MCPConnectionState.PAUSED
    with pytest.raises(JiejianError) as disabled:
        restarted.authorize(f"Bearer {second.access_token}")
    assert disabled.value.code == ErrorCode.MCP_DISABLED.value
    assert restarted.resume().connection_state is MCPConnectionState.CREDENTIAL_READY
    assert store.values[MCP_PAIRING_SECRET_REF] == second.access_token


def test_mcp_gui_access_api_controls_credentials_and_restores_after_shutdown(
    tmp_path: Path,
) -> None:
    store = _MemorySecretStore()
    app = create_app(tmp_path / "var", start_worker=False, secret_store=store)
    with TestClient(app) as client:
        initial = client.get("/api/mcp/access").json()["data"]
        assert initial == {
            "schema_version": "1",
            "paired": False,
            "accepting_connections": False,
            "endpoint": f"{TEST_CONTROL_ORIGIN}/mcp",
            "default_level": "READ",
            "project_grants": [],
            "client_connected": False,
            "client_name": None,
            "client_version": None,
            "last_seen_at_us": None,
            "connection_state": "DISABLED",
            "last_authenticated_at_us": None,
            "last_auth_failure_at_us": None,
        }
        paired = client.post("/api/mcp/access/pair").json()["data"]
        token = paired["access_token"]
        assert len(_token_bytes(token)) == 32
        assert paired["connection_state"] == "CREDENTIAL_READY"
        status = client.get("/api/mcp/access")
        assert "access_token" not in status.json()["data"]
        assert token not in status.text

        connected = client.post(
            "/api/applications/connect",
            json={"schema_version": "1", "source_root": str(_source(tmp_path))},
        ).json()["data"]
        project_id = connected["project"]["project_id"]
        granted = client.put(
            f"/api/mcp/access/projects/{project_id}",
            json={"schema_version": "1", "level": "PREPARE"},
        ).json()["data"]
        assert granted["project_grants"] == [
            {"project_id": project_id, "level": "PREPARE"}
        ]

        rotated = client.post("/api/mcp/access/rotate").json()["data"]
        assert rotated["access_token"] != token
        assert rotated["project_grants"] == []
        current_token = rotated["access_token"]
        assert client.post("/api/mcp/access/reveal").json()["data"]["access_token"] == current_token
        paused = client.post("/api/mcp/access/pause").json()["data"]
        assert paused["connection_state"] == "PAUSED"
        resumed = client.post("/api/mcp/access/resume").json()["data"]
        assert resumed["connection_state"] == "CREDENTIAL_READY"

    assert app.state.mcp_access.view().paired is False
    with pytest.raises(JiejianError) as stopped:
        app.state.mcp_access.authorize(f"Bearer {current_token}")
    assert stopped.value.code == ErrorCode.MCP_DISABLED.value
    restarted = create_app(tmp_path / "restart-var", start_worker=False, secret_store=store)
    with TestClient(restarted) as client:
        restored = restarted.state.mcp_access.view()
        assert restored.paired is True
        assert restored.accepting_connections is True
        assert restored.project_grants == ()
        assert restored.connection_state is MCPConnectionState.CREDENTIAL_READY
        restarted.state.mcp_access.authorize(f"Bearer {current_token}")
        assert restarted.state.mcp_access.view().connection_state is MCPConnectionState.AUTHENTICATED
        forgotten = client.post("/api/mcp/access/forget").json()["data"]
        assert forgotten["paired"] is False
        assert forgotten["accepting_connections"] is False
        assert forgotten["connection_state"] == "DISABLED"
        assert MCP_PAIRING_SECRET_REF not in store.values
        with pytest.raises(JiejianError) as forgotten_token:
            restarted.state.mcp_access.authorize(f"Bearer {current_token}")
        assert forgotten_token.value.code == ErrorCode.MCP_DISABLED.value
    token_bytes = current_token.encode("ascii")
    assert all(
        token_bytes not in path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    )


def test_mcp_transport_rejects_disabled_wrong_token_and_wrong_origin(
    tmp_path: Path,
) -> None:
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        secret_store=_MemorySecretStore(),
    )

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url=TEST_CONTROL_ORIGIN,
            ) as client:
                request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "server/discover",
                    "params": {},
                }
                disabled = await client.post("/mcp", json=request)
                assert disabled.status_code == 403
                assert disabled.json()["error"]["code"] == "MCP_DISABLED"

                token = app.state.mcp_access.pair().access_token
                assert token is not None
                wrong = await client.post(
                    "/mcp",
                    json=request,
                    headers={"Authorization": "Bearer wrong"},
                )
                assert wrong.status_code == 401
                assert wrong.json()["error"]["code"] == "MCP_AUTH_REQUIRED"
                assert wrong.headers["www-authenticate"] == "Bearer"

                cookie_only = await client.post(
                    "/mcp",
                    json=request,
                    headers={"Cookie": f"jiejian_session={token}"},
                )
                assert cookie_only.status_code == 401
                assert cookie_only.json()["error"]["code"] == "MCP_AUTH_REQUIRED"

                wrong_origin = await client.post(
                    "/mcp",
                    json=request,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Origin": "https://evil.example",
                    },
                )
                assert wrong_origin.status_code == 403
                assert wrong_origin.text == "Invalid Origin header"

                async with httpx2.AsyncClient(
                    transport=httpx2.ASGITransport(app=app.state.mcp_app),
                    base_url=TEST_CONTROL_ORIGIN,
                ) as sdk_client:
                    wrong_host = await sdk_client.post(
                        "/mcp",
                        json=request,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Host": "evil.example",
                            "Origin": TEST_CONTROL_ORIGIN,
                        },
                    )
                    assert (wrong_host.status_code, wrong_host.text) == (
                        421,
                        "Invalid Host header",
                    )

    anyio.run(scenario)


def test_official_sdk_never_exposes_old_or_permission_writer_tools(tmp_path):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=_MemorySecretStore())
    token = app.state.mcp_access.pair().access_token
    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=TEST_CONTROL_ORIGIN,
                headers={"Authorization": "Bearer " + token}, follow_redirects=True) as http:
                async with Client(streamable_http_client(TEST_CONTROL_ORIGIN + "/mcp", http_client=http, terminate_on_close=False)) as client:
                    listed = (await client.list_tools()).tools
                    assert {tool.name for tool in listed} == EXPECTED_MCP_TOOLS
                    assert all(tool.input_schema["additionalProperties"] is False for tool in listed)
                    for name in ("jiejian_intent_propose", "jiejian_check_prepare", "jiejian_official_sample_apply_fix", "jiejian_flow_list"):
                        rejected = await client.call_tool(name, {"project_id": "unknown"})
                        assert rejected.is_error
    anyio.run(scenario)


def test_mcp_application_projection_omits_source_and_log_or_body_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        secret_store=_MemorySecretStore(),
    )
    connection = app.state.context.application_understanding.connect(_source(tmp_path))
    project_id = connection.project.project_id
    token = app.state.mcp_access.pair().access_token
    assert token is not None

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url=TEST_CONTROL_ORIGIN,
                headers={"Authorization": f"Bearer {token}"},
                follow_redirects=True,
            ) as http_client:
                async with Client(
                    streamable_http_client(
                        f"{TEST_CONTROL_ORIGIN}/mcp",
                        http_client=http_client,
                        terminate_on_close=False,
                    )
                ) as client:
                    result = await client.call_tool(
                        "jiejian_application_understanding",
                        {"project_id": project_id},
                    )
                    payload = result.structured_content
                    assert payload is not None
                    assert "source_root" not in payload
                    assert "source_fingerprint" not in payload
                    assert "endpoint_source_fingerprint" not in payload
                    assert all(
                        "evidence" not in candidate
                        for field in ("role_candidates", "action_candidates")
                        for candidate in payload[field]
                    )

                    serialized = json.dumps(payload, ensure_ascii=False).casefold()
                    assert "secret_ref" not in serialized
                    assert "request_body" not in serialized
                    assert "response_body" not in serialized
                    assert "log_path" not in serialized

    anyio.run(scenario)
