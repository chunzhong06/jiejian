# 通过官方 MCP SDK 验证当前精确工具集、项目临时权限、真实检查提交取消与源码声明登记。
import anyio
from copy import deepcopy
import httpx2
import pytest
from mcp import MCPError
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from product.backend.application.agent_access.service import MCPAccessLevel
from tests.support.builders.preparation.action_preparation import MemorySecretStore
from tests.support.builders.checks.check_service import ready_check_harness
from tests.support.builders.control_plane import create_app, TEST_CONTROL_ORIGIN
from tests.contracts.http.system._support_current_mcp import TOOLS, start_task


def test_sdk_candidate_projection_errors_are_actionable_and_private(tmp_path):
    from copy import deepcopy
    from uuid import uuid4
    from jsonschema import Draft202012Validator
    from tests.support.builders.boundary_candidates import _content

    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    source = tmp_path / "source"
    source.mkdir()
    core = app.state.context
    project = core.application_understanding.connect(str(source), project_name="投影合同核对").project.project_id
    access = app.state.mcp_access
    token = access.pair().access_token
    access.set_level(project, MCPAccessLevel.PREPARE)

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=TEST_CONTROL_ORIGIN,
                headers={"Authorization": "Bearer " + token, "Origin": TEST_CONTROL_ORIGIN}, follow_redirects=True) as http:
                async with Client(streamable_http_client(TEST_CONTROL_ORIGIN + "/mcp", http_client=http, terminate_on_close=False)) as client:
                    context = (await client.call_tool("jiejian_rule_context", {"project_id": project})).structured_content
                    content = _content()
                    effect = content["actions"][0]["effect_catalog"][0]
                    effect.update(effect_kind="DATA_DISCLOSURE", expected_state=None)
                    request = {"operation_id": uuid4().hex, "expected_basis_id": context["basis_id"], "content": content}
                    validator = Draft202012Validator(context["candidate_input_schema"])
                    assert not validator.is_valid(request)
                    with pytest.raises(MCPError) as failure:
                        await client.call_tool("jiejian_rule_candidate_save", {"project_id": project, "candidate": request})
                    assert "actions[0].effect_catalog[0].protected_projection" in str(failure.value)
                    assert "DATA_DISCLOSURE" in str(failure.value)
                    # 未声明键本身也可能携带秘密，不能只净化错误中的value。
                    invalid = deepcopy(request)
                    invalid["secret-canary-unknown-key"] = "secret-canary-value"
                    with pytest.raises(MCPError) as secret_failure:
                        await client.call_tool("jiejian_rule_candidate_save", {"project_id": project, "candidate": invalid})
                    assert "secret-canary" not in str(secret_failure.value)
                    effect["protected_projection"] = ["title", "summary"]
                    assert validator.is_valid(request)
                    saved = await client.call_tool("jiejian_rule_candidate_save", {"project_id": project, "candidate": request})
                    assert saved.structured_content["assessment"] == "REVIEWABLE"
                    assert core.business_boundaries.view(project).policy_epoch == 0
                    # SDK须收到精确修订和字段位置，而不是候选原文或泛泛的返回GUI提示。
                    revision_request = deepcopy(request)
                    revision_request.update(operation_id=uuid4().hex, candidate_id=saved.structured_content['candidate']['candidate_id'], expected_revision=1)
                    revision_request['content']['unresolved_questions']=['secret-canary-question-one', 'secret-canary-question-two']
                    await client.call_tool('jiejian_rule_candidate_save', {'project_id':project,'candidate':revision_request})
                    revision_request.update(operation_id=uuid4().hex, expected_revision=2)
                    revision_request['content']['unresolved_questions']=[]
                    with pytest.raises(MCPError) as revision_failure:
                        await client.call_tool('jiejian_rule_candidate_save', {'project_id':project,'candidate':revision_request})
                    diagnostic=revision_failure.value.data
                    assert diagnostic['details']['reason']=='CANDIDATE_QUESTION_REVIEW_REQUIRED'
                    assert diagnostic['details']['revision']==2
                    assert [issue['path'] for issue in diagnostic['details']['issues']]==[
                        'candidate.content.unresolved_questions[0]','candidate.content.unresolved_questions[1]']
                    assert '保存成功后' in diagnostic['recovery']
                    assert 'secret-canary' not in str(revision_failure.value) + str(diagnostic)
                    latest=(await client.call_tool('jiejian_rule_candidate_show', {'project_id':project,'candidate_id':revision_request['candidate_id']})).structured_content
                    assert latest['candidate']['revision']==2
                    assert latest['revision_guidance']==context['revision_guidance']
                    permission=deepcopy(content['permissions'][0])
                    base_scene={'scenario_id':'rsc_'+'1'*16,'original_excerpt':content['original_text'],'question':'如何确认发布范围？',
                        'options':[{'option_id':'rop_'+str(index)*16,'label':label,'explanation':label,'replacements':[deepcopy(permission)]}
                            for index,label in [(1,'核对公开资料'),(2,'核对内部资料')]]}
                    cases=[('excerpt','scenario_excerpt_mismatch','content.scenarios[0].original_excerpt'),
                        ('outside','scenario_replacement_outside','content.scenarios[0].options[0].replacements'),
                        ('set','scenario_replacement_set_mismatch','content.scenarios[0].options'),
                        ('replacement','scenario_replacement_duplicate','content.scenarios[0].options[0].replacements'),
                        ('option','scenario_option_duplicate','content.scenarios[0].options'),
                        ('scenario','scenario_id_duplicate','content.scenarios')]
                    for fault,code,path in cases:
                        invalid=deepcopy(request);invalid['operation_id']=uuid4().hex
                        scene=deepcopy(base_scene);invalid['content']['scenarios']=[scene]
                        if fault=='excerpt':scene['original_excerpt']='secret-canary-unmatched-excerpt'
                        elif fault=='outside':
                            for option in scene['options']:option['replacements'][0]['item_id']='pperm_'+'2'*16
                        elif fault=='set':scene['options'][0]['replacements'][0]['item_id']='pperm_'+'2'*16
                        elif fault=='replacement':scene['options'][0]['replacements'].append(deepcopy(permission))
                        elif fault=='option':scene['options'][1]['option_id']=scene['options'][0]['option_id']
                        elif fault=='scenario':invalid['content']['scenarios'].append(deepcopy(scene))
                        with pytest.raises(MCPError) as scene_failure:
                            await client.call_tool('jiejian_rule_candidate_save', {'project_id':project,'candidate':invalid})
                        issues=scene_failure.value.data['details']['issues']
                        assert issues[0]['code']==code
                        assert issues[0]['path']=='candidate.'+path
                        assert 'secret-canary' not in str(scene_failure.value)+str(scene_failure.value.data)
                    effect["effect_kind"] = "STATE_MUTATION"
                    assert not validator.is_valid(request)
                    with pytest.raises(MCPError) as wrong_kind:
                        await client.call_tool("jiejian_rule_candidate_save", {"project_id": project, "candidate": request})
                    assert "只有DATA_DISCLOSURE" in str(wrong_kind.value)
    anyio.run(scenario)




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


@pytest.mark.process
@pytest.mark.slow
def test_sdk_generic_change_id_submits_full_current_question_after_human_rebind(tmp_path):
    from pathlib import Path
    from tests.support.builders.runtime.runtime_environment import runtime_identity_environment
    from tests.support.builders.runtime.official_preparation import prepare_sample, prepare_changed_sample
    var_dir = tmp_path / "var"
    app = create_app(var_dir, start_worker=False, secret_store=MemorySecretStore(),
        environ=runtime_identity_environment(var_dir),
        official_sample_root=Path(__file__).resolve().parents[4] / "samples/web/digital_gallery")
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
                    (Path(source) / "additional_logic.mjs").write_text("// 独立业务修改测试。\nexport function value() { return 1; }\n", encoding="utf-8")
                    changed = await client.call_tool("jiejian_change_submit", {"project_id": project, **delivery, "reason": "登记通用代码修改", "claimed_paths": ["additional_logic.mjs"]})
                    assert not changed.is_error
                    change_id = changed.structured_content["change_id"]
                    with pytest.raises(MCPError):
                        await client.call_tool("jiejian_check_run", {"project_id": project, "change_id": change_id, "idempotency_key": "prepare-cannot-execute", "expected_plan_fingerprint": "0"*64})
                    from uuid import uuid4
                    preview = core.checks.preview(project, change_id=change_id)
                    assert not preview.can_execute
                    from product.backend.domain.errors import JiejianError
                    fingerprint = core.application_understanding.get(project).source_fingerprint
                    with pytest.raises(JiejianError) as stale:
                        core.node_runtime.require_loaded_delivery(project, fingerprint)
                    assert stale.value.to_dict()['details']['reason'] == 'RUNTIME_SOURCE_NOT_LOADED'
                    activation = core.runtime_activation.activate(project, changed.structured_content["delivery_id"],
                        operation_id=uuid4().hex, expected_version=changed.structured_content["task_version"])
                    import time
                    deadline = time.monotonic() + 30
                    while activation.status == "PENDING" and time.monotonic() < deadline:
                        await anyio.sleep(.1)
                        activation = core.runtime_activation.receipt(project, activation.operation_id)
                    assert activation.status == "SUCCEEDED"
                    prepare_changed_sample(core, project)
                    access.set_level(project, MCPAccessLevel.EXECUTE)
                    plan = await client.call_tool("jiejian_check_preview", {"project_id": project, "change_id": change_id})
                    submitted = await client.call_tool("jiejian_check_run", {"project_id": project, "change_id": change_id, "idempotency_key": "generic-change", "expected_plan_fingerprint": plan.structured_content["plan_fingerprint"]})
                    assert not submitted.is_error
                    run_id = submitted.structured_content["run_id"]
                    request = core.checks.pending_request(run_id)
                    assert request.change_context.change_id == change_id
                    with core.uow_factory() as work:
                        assert work.development.latest_check_run(project, changed.structured_content["delivery_id"]) == run_id
                    assert len(request.actions) == 3
                    assert sum(len(action.cases) for action in request.actions) == 5
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
                    assert access.view().connection_state.value == 'CONNECTED'
                    for stage in ('RULES','MATERIALS'):
                        collaboration = await client.call_tool('jiejian_agent_context',{'project_id':project,'stage':stage})
                        assert not collaboration.is_error
                        assert collaboration.structured_content['context_id'].startswith('awc_')
                    rule = app.state.context.business_boundaries.view(project).permission_intents[0]
                    preview = await client.call_tool("jiejian_rule_preview", {"project_id": project,
                        "reference": {"kind": "APPROVED", "rules": [{"intent_id": rule.intent_id, "revision": rule.revision}]},
                        "situation": {"subject_id": rule.subject_actor_id, "owner_id": rule.resource_owner_actor_id,
                            "relation": rule.relation.value, "action_id": rule.business_action_id, "effect_id": rule.protected_effect_ids[0]}})
                    assert preview.structured_content["coverage"] == rule.expectation.value
                    assert access.level_for(project) is MCPAccessLevel.READ
                    materials=await client.call_tool('jiejian_preparation_context',{'project_id':project})
                    advice={'operation_id':'7'*32,'expected_basis_id':materials.structured_content['suggestion_context']['basis_id'],
                        'content':{'items':[{'item_id':'psi_'+'1'*16,
                            'target':{'kind':'APPROVED','action_id':rule.business_action_id,'action_revision':rule.action_revision,
                                'actor_id':rule.subject_actor_id,'actor_revision':rule.subject_actor_revision},
                            'material':{'kind':'identity','account_requirement':'继续核对现有账号'},'description':'保留原测试账号',
                            'source':{'classification':'HYPOTHESIS','explanation':'按当前要求整理'},'handler':'USER'}]}}
                    with pytest.raises(MCPError):
                        await client.call_tool('jiejian_preparation_suggestion_save',{'project_id':project,'suggestion':advice})
                    access.set_level(project,MCPAccessLevel.PREPARE)
                    malformed = deepcopy(advice)
                    malformed['operation_id'] = 'invalid operation'
                    with pytest.raises(MCPError) as rejected:
                        await client.call_tool('jiejian_preparation_suggestion_save',{'project_id':project,'suggestion':malformed})
                    assert 'suggestion.operation_id' in str(rejected.value)
                    assert 'invalid operation' not in str(rejected.value)
                    saved=await client.call_tool('jiejian_preparation_suggestion_save',{'project_id':project,'suggestion':advice})
                    assert not saved.is_error
                    access.set_level(project,MCPAccessLevel.READ)
                    saved_id=saved.structured_content['suggestion']['suggestion_id']
                    read=await client.call_tool('jiejian_preparation_suggestion_show',{'project_id':project,'suggestion_id':saved_id,'revision':1})
                    receipt=await client.call_tool('jiejian_preparation_suggestion_receipt',{'project_id':project,'operation_id':advice['operation_id']})
                    assert read.structured_content['suggestion']==saved.structured_content['suggestion']
                    assert receipt.structured_content['status']=='FOUND'
                    assert str(harness.source_root) not in str(read.structured_content)
                    unavailable = await client.call_tool("jiejian_rule_candidate_decide", {"project_id": project})
                    assert unavailable.is_error
                    status = await client.call_tool("jiejian_check_status",{"project_id":project})
                    assert status.structured_content["can_execute"]
                    assert "plan_fingerprint" not in status.structured_content
                    plan = await client.call_tool("jiejian_check_preview",{"project_id":project})
                    with pytest.raises(MCPError):
                        await client.call_tool("jiejian_check_run",{"project_id":project,"idempotency_key":"sdk-run","expected_plan_fingerprint":plan.structured_content["plan_fingerprint"]})
                    access.set_level(project,MCPAccessLevel.EXECUTE)
                    created = await client.call_tool("jiejian_check_run",{"project_id":project,"idempotency_key":"sdk-run","expected_plan_fingerprint":plan.structured_content["plan_fingerprint"]})
                    assert not created.is_error
                    run_id = created.structured_content["run_id"]
                    same = await client.call_tool("jiejian_check_run",{"project_id":project,"idempotency_key":"sdk-run","expected_plan_fingerprint":plan.structured_content["plan_fingerprint"]})
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
    from tests.support.builders.control_plane import TestClient
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

pytestmark = [pytest.mark.level4]
