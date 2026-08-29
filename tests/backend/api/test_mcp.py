# 验证 MCP 入口使用官方 SDK、进程内 Bearer、逐 Project 分级和现有 ApplicationCore 事实。

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
from product.backend.workflows.mcp_access import MCPAccessController, MCPAccessLevel
from tests.fixtures.control_plane import TEST_CONTROL_ORIGIN, TestClient, create_app


pytestmark = pytest.mark.database


class _StubToolView(BaseModel):
    schema_version: Literal["1"] = "1"
    object_id: str


EXPECTED_MCP_TOOLS = {
    "jiejian_application_reanalyze",
    "jiejian_application_understanding",
    "jiejian_candidate_decide",
    "jiejian_check_cancel",
    "jiejian_check_prepare",
    "jiejian_check_preview",
    "jiejian_check_run",
    "jiejian_evidence_index",
    "jiejian_flow_list",
    "jiejian_flow_status",
    "jiejian_identity_list",
    "jiejian_identity_prepare_cancel",
    "jiejian_identity_prepare_confirm",
    "jiejian_identity_prepare_start",
    "jiejian_identity_preparation_status",
    "jiejian_identity_status",
    "jiejian_official_sample_start",
    "jiejian_official_sample_stop",
    "jiejian_official_sample_verify_fixed",
    "jiejian_permission_set",
    "jiejian_product_status",
    "jiejian_project_list",
    "jiejian_project_show",
    "jiejian_recording_capture_start",
    "jiejian_recording_start",
    "jiejian_recording_stop",
    "jiejian_result_history",
    "jiejian_result_presentation",
    "jiejian_system_status",
}


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


def test_mcp_access_controller_revokes_tokens_and_uses_read_default() -> None:
    access = MCPAccessController("http://127.0.0.1:8765/mcp")
    assert access.view().enabled is False
    first = access.enable()
    assert first.access_token is not None
    assert len(_token_bytes(first.access_token)) == 32
    access.authorize(f"Bearer {first.access_token}")
    assert access.level_for("proj_a") is MCPAccessLevel.READ

    access.set_level("proj_a", MCPAccessLevel.EXECUTE)
    second = access.regenerate()
    assert second.access_token is not None and second.access_token != first.access_token
    assert second.project_grants == ()
    with pytest.raises(JiejianError) as old_token:
        access.authorize(f"Bearer {first.access_token}")
    assert old_token.value.code == ErrorCode.MCP_AUTH_REQUIRED.value

    access.disable()
    with pytest.raises(JiejianError) as disabled:
        access.authorize(f"Bearer {second.access_token}")
    assert disabled.value.code == ErrorCode.MCP_DISABLED.value


def test_mcp_gui_access_api_clears_grants_on_regenerate_and_shutdown(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        initial = client.get("/api/mcp/access").json()["data"]
        assert initial == {
            "schema_version": "1",
            "enabled": False,
            "endpoint": f"{TEST_CONTROL_ORIGIN}/mcp",
            "access_token": None,
            "default_level": "READ",
            "project_grants": [],
        }
        enabled = client.post("/api/mcp/access/enable").json()["data"]
        token = enabled["access_token"]
        assert len(_token_bytes(token)) == 32

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

        regenerated = client.post("/api/mcp/access/regenerate").json()["data"]
        assert regenerated["access_token"] != token
        assert regenerated["project_grants"] == []
        current_token = regenerated["access_token"]

    assert app.state.mcp_access.view().enabled is False
    with pytest.raises(JiejianError) as stopped:
        app.state.mcp_access.authorize(f"Bearer {current_token}")
    assert stopped.value.code == ErrorCode.MCP_DISABLED.value
    token_bytes = current_token.encode("ascii")
    assert all(
        token_bytes not in path.read_bytes()
        for path in (tmp_path / "var").rglob("*")
        if path.is_file()
    )


def test_mcp_transport_rejects_disabled_wrong_token_and_wrong_origin(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path / "var", start_worker=False)

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

                token = app.state.mcp_access.enable().access_token
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


def test_official_mcp_client_reads_same_status_and_enforces_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    source = _source(tmp_path)
    connection = app.state.context.application_understanding.connect(source)
    project_id = connection.project.project_id
    expected = app.state.context.product_status.get(project_id).model_dump(mode="json")
    token = app.state.mcp_access.enable().access_token
    assert token is not None

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url=TEST_CONTROL_ORIGIN,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Origin": TEST_CONTROL_ORIGIN,
                },
                follow_redirects=True,
            ) as http_client:
                transport = streamable_http_client(
                    f"{TEST_CONTROL_ORIGIN}/mcp",
                    http_client=http_client,
                    terminate_on_close=False,
                )
                async with Client(transport) as client:
                    tools = await client.list_tools()
                    assert {item.name for item in tools.tools} == EXPECTED_MCP_TOOLS
                    status = await client.call_tool(
                        "jiejian_product_status",
                        {"project_id": project_id},
                    )
                    assert status.is_error is False
                    assert status.structured_content == expected

                    with pytest.raises(MCPError) as blocked:
                        await client.call_tool(
                            "jiejian_application_reanalyze",
                            {"project_id": project_id, "revision": 0},
                        )
                    assert blocked.value.data["error_code"] == "MCP_PERMISSION_REQUIRED"
                    assert blocked.value.data["details"] == {
                        "required_level": "PREPARE",
                        "project_id": project_id,
                    }

                    with pytest.raises(MCPError) as execute_blocked:
                        await client.call_tool(
                            "jiejian_check_run",
                            {
                                "project_id": project_id,
                                "idempotency_key": "read-cannot-run",
                            },
                        )
                    assert execute_blocked.value.data["error_code"] == "MCP_PERMISSION_REQUIRED"
                    assert execute_blocked.value.data["details"] == {
                        "required_level": "EXECUTE",
                        "project_id": project_id,
                    }

                    app.state.mcp_access.set_level(
                        project_id,
                        MCPAccessLevel.PREPARE,
                    )
                    compile_calls: list[tuple[str, str]] = []
                    monkeypatch.setattr(
                        app.state.context.security_setup,
                        "compile",
                        lambda selected_project_id, *, actor: compile_calls.append(
                            (selected_project_id, actor)
                        ),
                    )
                    source_entries = tuple(sorted(path.name for path in source.iterdir()))
                    prepared = await client.call_tool(
                        "jiejian_check_prepare",
                        {"project_id": project_id, "actor": "mcp-test"},
                    )
                    assert prepared.is_error is False
                    assert compile_calls == [(project_id, "mcp-test")]
                    assert tuple(sorted(path.name for path in source.iterdir())) == source_entries

                    with pytest.raises(MCPError) as authorization_required:
                        await client.call_tool(
                            "jiejian_application_reanalyze",
                            {"project_id": project_id, "revision": 0},
                        )
                    assert (
                        authorization_required.value.data["error_code"]
                        == "APPLICATION_ANALYSIS_NOT_AUTHORIZED"
                    )

                    run_calls: list[tuple[str, str]] = []
                    monkeypatch.setattr(
                        app.state.context.checks,
                        "submit",
                        lambda selected_project_id, *, idempotency_key: (
                            run_calls.append((selected_project_id, idempotency_key))
                            or (
                                SimpleNamespace(
                                    job=_StubToolView(object_id="job-test"),
                                    run=_StubToolView(object_id="run-test"),
                                ),
                                SimpleNamespace(schema_version="1"),
                                False,
                            )
                        ),
                    )
                    app.state.mcp_access.set_level(
                        project_id,
                        MCPAccessLevel.EXECUTE,
                    )
                    executed = await client.call_tool(
                        "jiejian_check_run",
                        {
                            "project_id": project_id,
                            "idempotency_key": "mcp-test-run",
                        },
                    )
                    assert executed.is_error is False
                    assert executed.structured_content == {
                        "schema_version": "1",
                        "job": {"schema_version": "1", "object_id": "job-test"},
                        "run": {"schema_version": "1", "object_id": "run-test"},
                    }
                    assert run_calls == [(project_id, "mcp-test-run")]

                    direct_presentation = _StubToolView(object_id="result-test")
                    monkeypatch.setattr(
                        app.state.context.result_presentation,
                        "build",
                        lambda run_id: direct_presentation,
                    )
                    presented = await client.call_tool(
                        "jiejian_result_presentation",
                        {"run_id": "run-test"},
                    )
                    assert presented.is_error is False
                    assert presented.structured_content == direct_presentation.model_dump(
                        mode="json"
                    )

                    app.state.mcp_access.disable()
                    with pytest.raises(MCPError):
                        await client.call_tool(
                            "jiejian_product_status",
                            {"project_id": project_id},
                        )

    anyio.run(scenario)


def test_mcp_application_projection_omits_source_and_log_or_body_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    connection = app.state.context.application_understanding.connect(_source(tmp_path))
    project_id = connection.project.project_id
    token = app.state.mcp_access.enable().access_token
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

                    monkeypatch.setattr(
                        app.state.context.product_flows,
                        "list",
                        lambda selected_project_id: (
                            {
                                "recording_id": "rec-test",
                                "project_id": selected_project_id,
                                "flow_id": "flow-test",
                                "state": "RECORDING",
                                "created_at_us": 1,
                                "updated_at_us": 2,
                                "browser_events": [{"request_body": "secret-body"}],
                                "job": {
                                    "job_id": "job-test",
                                    "state": "RUNNING",
                                    "failure_detail": "secret-log",
                                },
                            },
                        ),
                    )
                    flows = await client.call_tool(
                        "jiejian_flow_list",
                        {"project_id": project_id},
                    )
                    assert flows.structured_content == {
                        "result": [
                            {
                                "recording_id": "rec-test",
                                "project_id": project_id,
                                "flow_id": "flow-test",
                                "state": "RECORDING",
                                "created_at_us": 1,
                                "updated_at_us": 2,
                                "job": {"job_id": "job-test", "state": "RUNNING"},
                            }
                        ]
                    }
                    serialized = json.dumps(payload, ensure_ascii=False).casefold()
                    assert "secret_ref" not in serialized
                    assert "request_body" not in serialized
                    assert "response_body" not in serialized
                    assert "log_path" not in serialized

    anyio.run(scenario)
