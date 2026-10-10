# MCP读取同一已发布证据投影，READ授权不得越过项目归属或公开完整运行秘密。
import sqlite3
import anyio
import httpx2
import pytest
from mcp import MCPError
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from product.backend.infra.artifacts.checks.check_publication import CheckPublisher
from product.backend.workflows.agent_access.service import MCPAccessLevel
from tests.fixtures.checks.check_publication import package_parts,NOW
from tests.fixtures.control_plane import create_app,TEST_CONTROL_ORIGIN
from tests.fixtures.preparation.action_preparation import MemorySecretStore


def test_evidence_sdk_read_uses_exact_project_case_and_bounded_fragment(package_parts,worker_services):
    var_dir,factory,job,staging,_=package_parts
    package=CheckPublisher(var_dir,factory,clock_us=lambda:NOW+20).publish(staging)
    (var_dir/'data').mkdir(exist_ok=True)
    with sqlite3.connect(worker_services.database_path) as source,sqlite3.connect(var_dir/'data/jiejian.db') as target:source.backup(target)
    app=create_app(var_dir,start_worker=False,secret_store=MemorySecretStore(),environ={})
    access=app.state.mcp_access;token=access.pair().access_token;project=package.request.project_id
    document=package.evidence[0]
    arguments=dict(project_id=project,run_id=job.run_id,case_id=document.case.case_id,evidence_id=document.evidence_id)
    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),base_url=TEST_CONTROL_ORIGIN,
                headers={'Authorization':'Bearer '+token,'Origin':TEST_CONTROL_ORIGIN},follow_redirects=True) as http:
                async with Client(streamable_http_client(TEST_CONTROL_ORIGIN+'/mcp',http_client=http,terminate_on_close=False)) as client:
                    access.set_level(project,MCPAccessLevel.READ)
                    story=await client.call_tool('jiejian_result_show',dict(project_id=project,run_id=job.run_id))
                    assert not story.is_error
                    action=next(item for item in story.structured_content['actions'] if item['case_id']==document.case.case_id)
                    assert document.evidence_id in action['evidence_refs']
                    assert job.run_id in action['review_url'] and document.case.case_id in action['review_url']
                    index=await client.call_tool('jiejian_evidence_show',arguments)
                    assert not index.is_error
                    selected=index.structured_content['records'][0]['record_id']
                    result=await client.call_tool('jiejian_evidence_show',arguments|dict(record_ref=selected))
                    assert not result.is_error and len(result.structured_content['verification'])==6
                    payload=str(result.structured_content)
                    assert 'lease_owner' not in payload and 'request_nonce' not in payload and str(var_dir) not in payload
                    with pytest.raises(MCPError):await client.call_tool('jiejian_evidence_show',arguments|dict(project_id='other-project'))
                    with pytest.raises(MCPError):await client.call_tool('jiejian_evidence_show',arguments|dict(record_ref='missing'))
    anyio.run(scenario)
