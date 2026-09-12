# 官方 SDK 的 current Oracle 不变量：任意工具级别都不能成为权限审批者。
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


@pytest.mark.parametrize("level", list(MCPAccessLevel))
def test_current_sdk_grants_cannot_mutate_permission_or_select_cases(tmp_path, level):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    harness = ready_check_harness(tmp_path, core=app.state.context)
    core, project = harness.core, harness.project_id
    before = core.business_boundaries.view(project)
    access = app.state.mcp_access
    token = access.pair().access_token
    access.set_level(project, level)
    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=TEST_CONTROL_ORIGIN,
                headers={"Authorization": "Bearer " + token, "Origin": TEST_CONTROL_ORIGIN}, follow_redirects=True) as http:
                async with Client(streamable_http_client(TEST_CONTROL_ORIGIN + "/mcp", http_client=http, terminate_on_close=False)) as client:
                    for name in ("jiejian_permission_approve", "jiejian_intent_propose", "jiejian_boundary_approve"):
                        rejected = await client.call_tool(name, {"project_id": project})
                        assert rejected.is_error
                    for field in ("case_ids", "permission_ids", "effect_ids", "repair_context"):
                        with pytest.raises(MCPError):
                            await client.call_tool("jiejian_check_run", {"project_id": project, "idempotency_key": "forbidden-selection", field: []})
                    with pytest.raises(MCPError):
                        await client.call_tool("jiejian_check_cancel", {"project_id": "foreign-project", "run_id": "run_" + "f" * 32})
                    after = core.business_boundaries.view(project)
                    assert after.policy_epoch == before.policy_epoch
                    assert after.permission_intents == before.permission_intents
                    with core.uow_factory() as work:
                        assert all(job.operation_type != "CHECK" for job in work.jobs.list_for_project(project))
    anyio.run(scenario)
