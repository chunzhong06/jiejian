# 通过官方 MCP SDK 验证当前精确工具集、项目临时权限、真实检查提交取消与源码声明登记。
import anyio
import httpx2
import pytest
from mcp import MCPError
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from product.backend.workflows.mcp_access import MCPAccessLevel
from tests.fixtures.action_preparation import MemorySecretStore
from tests.fixtures.check_service import ready_check_harness
from tests.fixtures.control_plane import create_app, TEST_CONTROL_ORIGIN


TOOLS = {"jiejian_project_list","jiejian_project_show","jiejian_application_understanding","jiejian_business_boundary",
    "jiejian_intent_show","jiejian_identity_list","jiejian_system_status","jiejian_change_show","jiejian_check_status",
    "jiejian_result_show","jiejian_repair_show","jiejian_change_submit","jiejian_check_run","jiejian_check_cancel"}


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
    from tests.backend.workflows.test_current_official_sample import prepare_sample, prepare_changed_sample
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
            (Path(source) / "additional_logic.py").write_text("# 独立业务修改测试。\ndef value(): return 1\n", encoding="utf-8")
            access = app.state.mcp_access
            token = access.pair().access_token
            access.set_level(project, MCPAccessLevel.PREPARE)
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=TEST_CONTROL_ORIGIN,
                headers={"Authorization": "Bearer " + token, "Origin": TEST_CONTROL_ORIGIN}, follow_redirects=True) as http:
                async with Client(streamable_http_client(TEST_CONTROL_ORIGIN + "/mcp", http_client=http, terminate_on_close=False)) as client:
                    changed = await client.call_tool("jiejian_change_submit", {"project_id": project, "reason": "登记通用代码修改", "claimed_paths": ["additional_logic.py"]})
                    assert not changed.is_error
                    change_id = changed.structured_content["change_id"]
                    with pytest.raises(MCPError):
                        await client.call_tool("jiejian_check_run", {"project_id": project, "change_id": change_id, "idempotency_key": "prepare-cannot-execute"})
                    prepare_changed_sample(core, project)
                    access.set_level(project, MCPAccessLevel.EXECUTE)
                    submitted = await client.call_tool("jiejian_check_run", {"project_id": project, "change_id": change_id, "idempotency_key": "generic-change"})
                    assert not submitted.is_error
                    run_id = submitted.structured_content["run_id"]
                    request = core.checks.pending_request(run_id)
                    assert request.change_context.change_id == change_id
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
                    (harness.source_root/"actual.py").write_text("def changed(): return True\n",encoding="utf-8")
                    changed = await client.call_tool("jiejian_change_submit",{"project_id":project,"reason":"修改业务实现","claimed_paths":["claimed.py"]})
                    assert not changed.is_error
                    payload = changed.structured_content
                    assert payload["claimed_paths"]==["claimed.py"]
                    assert "source_fingerprint" not in str(payload) and str(harness.source_root) not in str(payload)
                    # 缺少旧快照时只登记 NO_BASELINE，不将 claimed path 当作真实文件变化。
                    assert "claimed.py" not in payload["added_paths"]
                    access.pause()
                    access.resume()
                    assert access.level_for(project) is MCPAccessLevel.READ
                    with pytest.raises(MCPError):
                        await client.call_tool("jiejian_change_submit",{"project_id":project,"reason":"再次修改"})
    anyio.run(scenario)
