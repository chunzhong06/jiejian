# 通过官方 MCP SDK 验证当前精确工具集、项目临时权限、真实检查提交取消与源码声明登记。
import anyio
import httpx2
import pytest
from mcp import MCPError
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from product.backend.workflows.agent_access.service import MCPAccessLevel
from tests.fixtures.action_preparation import MemorySecretStore
from tests.fixtures.check_service import ready_check_harness
from tests.fixtures.control_plane import create_app, TEST_CONTROL_ORIGIN
from tests.backend.api._support_current_mcp import (
    TOOLS,
    start_task,
)




@pytest.mark.parametrize("fault,expected", [("token", 401), ("origin", 403), ("host", 421), ("paused", 403), ("rotated", 401), ("closed", 403)])
def test_sdk_transport_rejects_invalid_or_revoked_connection(tmp_path, fault, expected):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    access = app.state.mcp_access
    token = access.pair().access_token
    headers = {"Authorization": "Bearer " + token, "Origin": TEST_CONTROL_ORIGIN}
    if fault == "token":
        headers["Authorization"] = "Bearer invalid"
    elif fault == "origin":
        headers["Origin"] = "https://invalid.example"
    elif fault == "host":
        headers["Host"] = "invalid.example"
    elif fault == "paused":
        access.pause()
    elif fault == "rotated":
        access.rotate()
    elif fault == "closed":
        access.close()
    async def scenario():
        responses = []
        async def record(response):
            responses.append(response.status_code)
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app.state.mcp_app),
                base_url=TEST_CONTROL_ORIGIN, headers=headers, event_hooks={"response": [record]}, follow_redirects=True) as http:
                # 错误必须来自 SDK 的真实连接请求，不手写 JSON-RPC 绕过客户端。
                with pytest.raises(Exception):
                    async with Client(streamable_http_client(TEST_CONTROL_ORIGIN + "/mcp", http_client=http, terminate_on_close=False)) as client:
                        await client.list_tools()
        assert expected in responses, responses
    anyio.run(scenario)


@pytest.mark.parametrize("reset", ["pause", "resume", "rotate", "forget", "close"])
def test_connection_reset_clears_all_project_grants(tmp_path, reset):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    access = app.state.mcp_access
    access.pair()
    access.set_level("project-a", MCPAccessLevel.EXECUTE)
    access.set_level("project-b", MCPAccessLevel.PREPARE)
    getattr(access, reset)()
    assert access.level_for("project-a") is MCPAccessLevel.READ
    assert access.level_for("project-b") is MCPAccessLevel.READ
    app.state.context.close()


def test_sdk_generic_change_id_submits_full_current_question_after_human_rebind(tmp_path):
    from pathlib import Path
    from tests.fixtures.runtime_environment import runtime_identity_environment
    from tests.backend.workflows._support_current_official_sample import prepare_sample, prepare_changed_sample
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=False, secret_store=MemorySecretStore(),
        environ=runtime_identity_environment(var_dir),
        official_sample_root=Path(__file__).resolve().parents[3] / "samples/web/collaboration_space")
    core = app.state.context
    async def scenario():
        async with app.router.lifespan_context(app):
            project = prepare_sample(core)
            before = core.business_boundaries.view(project)
            source = core.application_understanding.get(project).source_root
            access = app.state.mcp_access
            token = access.pair().access_token
            access.set_level(project, MCPAccessLevel.PREPARE)
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=TEST_CONTROL_ORIGIN,
                headers={"Authorization": "Bearer " + token, "Origin": TEST_CONTROL_ORIGIN}, follow_redirects=True) as http:
                async with Client(streamable_http_client(TEST_CONTROL_ORIGIN + "/mcp", http_client=http, terminate_on_close=False)) as client:
                    delivery = await start_task(client, project)
                    (Path(source) / "additional_logic.py").write_text("# 独立业务修改测试。\ndef value(): return 1\n", encoding="utf-8")
                    changed = await client.call_tool("jiejian_change_submit", {"project_id": project, **delivery, "reason": "登记通用代码修改", "claimed_paths": ["additional_logic.py"]})
                    assert not changed.is_error
                    change_id = changed.structured_content["change_id"]
                    with pytest.raises(MCPError):
                        await client.call_tool("jiejian_check_run", {"project_id": project, "change_id": change_id, "idempotency_key": "prepare-cannot-execute"})
                    prepare_changed_sample(core, project)
                    from uuid import uuid4
                    preview = core.checks.preview(project, change_id=change_id)
                    assert not preview.can_execute
                    assert any(gap.reason == "RUNTIME_SOURCE_NOT_LOADED" for gap in preview.gaps)
                    activation = core.runtime_activation.activate(project, changed.structured_content["delivery_id"],
                        operation_id=uuid4().hex, expected_version=changed.structured_content["task_version"])
                    assert activation.status == "SUCCEEDED"
                    access.set_level(project, MCPAccessLevel.EXECUTE)
                    submitted = await client.call_tool("jiejian_check_run", {"project_id": project, "change_id": change_id, "idempotency_key": "generic-change"})
                    assert not submitted.is_error
                    run_id = submitted.structured_content["run_id"]
                    request = core.checks.pending_request(run_id)
                    assert request.change_context.change_id == change_id
                    with core.uow_factory() as work:
                        assert work.development.latest_check_run(project, changed.structured_content["delivery_id"]) == run_id
                    assert len(request.actions) == 2
                    assert sum(len(action.cases) for action in request.actions) == 3
                    after = core.business_boundaries.view(project)
                    assert after.policy_epoch == before.policy_epoch
                    assert after.permission_intents == before.permission_intents
                    await client.call_tool("jiejian_check_cancel", {"project_id": project, "run_id": run_id})
    anyio.run(scenario)


def test_current_sdk_exact_tools_real_submit_cancel_change_and_grant_reset(tmp_path):
    app = create_app(tmp_path/"var",start_worker=False,secret_store=MemorySecretStore(),environ={})
    harness = ready_check_harness(tmp_path,core=app.state.context)
    access = app.state.mcp_access
    token = access.pair().access_token
    project = harness.project_id
    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),base_url=TEST_CONTROL_ORIGIN,
                headers={"Authorization":"Bearer "+token,"Origin":TEST_CONTROL_ORIGIN},follow_redirects=True) as http:
                async with Client(streamable_http_client(TEST_CONTROL_ORIGIN+"/mcp",http_client=http,terminate_on_close=False)) as client:
                    assert {tool.name for tool in (await client.list_tools()).tools} == TOOLS
                    status = await client.call_tool("jiejian_check_status",{"project_id":project})
                    assert status.structured_content["can_execute"]
                    assert "plan_fingerprint" not in status.structured_content
                    with pytest.raises(MCPError):
                        await client.call_tool("jiejian_check_run",{"project_id":project,"idempotency_key":"sdk-run"})
                    access.set_level(project,MCPAccessLevel.EXECUTE)
                    created = await client.call_tool("jiejian_check_run",{"project_id":project,"idempotency_key":"sdk-run"})
                    assert not created.is_error
                    run_id = created.structured_content["run_id"]
                    same = await client.call_tool("jiejian_check_run",{"project_id":project,"idempotency_key":"sdk-run"})
                    assert same.structured_content["run_id"]==run_id
                    with pytest.raises(MCPError):
                        await client.call_tool("jiejian_check_status",{"project_id":"other-project","run_id":run_id})
                    cancelled = await client.call_tool("jiejian_check_cancel",{"project_id":project,"run_id":run_id})
                    assert cancelled.structured_content["job"]["cancel_requested"]
                    current = app.state.context.application_understanding.get(project)
                    app.state.context.application_understanding.analyze_source_for_change(project, revision=current.revision)
                    delivery = await start_task(client, project)
                    (harness.source_root/"actual.py").write_text("def changed(): return True\n",encoding="utf-8")
                    changed = await client.call_tool("jiejian_change_submit",{"project_id":project, **delivery,"reason":"修改业务实现","claimed_paths":["claimed.py"]})
                    assert not changed.is_error
                    saved = await client.call_tool("jiejian_change_show", {"project_id": project, "change_id": changed.structured_content["change_id"]})
                    payload = saved.structured_content["change"]
                    assert payload["claimed_paths"]==["claimed.py"]
                    assert "source_fingerprint" not in str(payload) and str(harness.source_root) not in str(payload)
                    # 开工上下文给出比较起点，claimed path 仍不等于真实变化。
                    assert "claimed.py" not in payload["added_paths"]
                    access.pause()
                    access.resume()
                    assert access.level_for(project) is MCPAccessLevel.READ
                    with pytest.raises(MCPError):
                        await client.call_tool("jiejian_change_submit",{"project_id":project, **delivery,"reason":"再次修改"})
    anyio.run(scenario)


def test_lightweight_mcp_registration_requires_prepare_without_task_handshake(tmp_path):
    from uuid import uuid4
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    harness = ready_check_harness(tmp_path, core=app.state.context)
    core, project, access = app.state.context, harness.project_id, app.state.mcp_access
    current = core.application_understanding.get(project)
    core.application_understanding.analyze_source_for_change(project, revision=current.revision)
    token = access.pair().access_token
    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=TEST_CONTROL_ORIGIN,
                headers={"Authorization": "Bearer " + token, "Origin": TEST_CONTROL_ORIGIN}, follow_redirects=True) as http:
                async with Client(streamable_http_client(TEST_CONTROL_ORIGIN + "/mcp", http_client=http, terminate_on_close=False)) as client:
                    preview = (await client.call_tool("jiejian_change_registration_preview", {"project_id": project})).structured_content
                    assert core.development.active(project) is None
                    payload = dict(project_id=project, operation_id=uuid4().hex, expected_registration_fingerprint=preview["fingerprint"], reason="一次登记")
                    with pytest.raises(MCPError):
                        await client.call_tool("jiejian_change_register", payload)
                    access.set_level(project, MCPAccessLevel.PREPARE)
                    first = (await client.call_tool("jiejian_change_register", payload)).structured_content
                    replay = (await client.call_tool("jiejian_change_register", payload)).structured_content
                    assert first == replay
                    assert core.development.view(project, first["task_id"])["acceptance"] is None
                    saved = await client.call_tool("jiejian_receipt_show", {"project_id": project, "kind": "DELIVER", "operation_id": payload["operation_id"]})
                    assert saved.structured_content["receipt"]["change_id"] == first["change_id"]
                    assert str(harness.source_root) not in str(first)
    anyio.run(scenario)


def test_lightweight_http_registration_contract_and_local_guard(tmp_path):
    from uuid import uuid4
    from tests.fixtures.control_plane import TestClient
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    harness = ready_check_harness(tmp_path, core=app.state.context)
    core, project = app.state.context, harness.project_id
    current = core.application_understanding.get(project)
    core.application_understanding.analyze_source_for_change(project, revision=current.revision)
    with TestClient(app) as client:
        base = f"/api/projects/{project}/source-changes"
        preview = client.get(base + "/registration-preview").json()["data"]
        body = dict(schema_version="1", operation_id=uuid4().hex, expected_registration_fingerprint=preview["fingerprint"])
        assert client.post(base + "/register", json={"schema_version": "1"}).status_code == 422
        first = client.post(base + "/register", json=body)
        assert first.status_code == 201
        assert client.post(base + "/register", json=body).json()["data"] == first.json()["data"]
        assert core.development.view(project, first.json()["data"]["task_id"])["acceptance"] is None
        client.cookies.clear()
        assert client.post(base + "/register", json={**body, "operation_id": uuid4().hex}).status_code == 403
