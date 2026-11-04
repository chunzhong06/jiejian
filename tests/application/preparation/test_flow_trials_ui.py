"""同一无源码应用经真实GUI与MCP连续维护、试运行、检查和原题再验。"""
import asyncio
import json
import socket
from pathlib import Path
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import httpx
import httpx2
import pytest
import uvicorn
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from playwright.sync_api import sync_playwright,expect
from product.backend.interfaces.http.app import create_app
from product.backend.application.agent_access.service import MCPAccessLevel
from product.backend.application.checks.routines import SaveCheckRoutine
from product.protocols.checks.execution_request import PermissionReference
from tests.support.secrets import MemorySecrets
from tests.support.builders.runtime.runtime_environment import runtime_identity_environment
from tests.support.builders.preparation.external_application import external_application
from tests.support.official import until
from tests.support.browser_review import settled

pytestmark=[pytest.mark.level4,pytest.mark.browser,pytest.mark.process]


def test_continuous_source_scene_trial_check_and_external_recheck():
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text(encoding='utf-8'))
    output=root/'var/audit/flow-trial-workflow'/uuid4().hex
    output.mkdir(parents=True)
    instance=output/'instance'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    web=create_app(instance,control_origin=origin,control_session_token=uuid4().hex*2,
        frontend_dir=Path(receipt['frontend']['dist']),secret_store=MemorySecrets(),environ=runtime_identity_environment(instance))
    core=web.state.context
    server=uvicorn.Server(uvicorn.Config(web,host='127.0.0.1',port=port,log_level='error'))
    errors=[];observations=[];stages=[];responses=[]
    with external_application(output/'ordinary',core=core) as app:
        thread=Thread(target=server.run,daemon=True);thread.start()
        project=app.project_id
        boundary=core.business_boundaries.view(project)
        permissions=boundary.permission_intents
        denied=next(item for item in permissions if item.expectation.value=='DENY')
        reference_rule=PermissionReference(intent_id=denied.intent_id,revision=denied.revision,intent_hash=denied.intent_hash)
        core.check_routines.save(project,SaveCheckRoutine(operation_id=uuid4().hex,name='订单权限日常检查',selected_permissions=[reference_rule]))
        routines=core.check_routines.list(project)
        token=web.state.mcp_access.pair().access_token
        web.state.mcp_access.set_level(project,MCPAccessLevel.PREPARE)
        try:
            with httpx.Client(base_url=origin,headers={'Origin':origin},trust_env=False,timeout=30) as http:
                until(lambda:server.started,bool,seconds=30)
                assert http.get('/').status_code==200
                # 在同一应用接续净化集合；原OpenAPI与权限要求继续保留。
                source_id='src_'+uuid4().hex
                collection={'info':{'name':'订单请求集合','schema':'https://schema.getpostman.com/json/collection/v2.1.0/collection.json'},'item':[{'name':'订单详情','request':{'method':'GET','url':app.origin+'/orders/{id}'}}]}
                initial=core.application_sources.preview(project,kind='POSTMAN',raw=json.dumps(collection))
                core.application_sources.accept(project,candidate_id=initial['candidate_id'],name='订单请求集合',source_id=source_id,expected_revision=0,expected_fingerprint=initial['fingerprint'])
                collection['item'].append({'name':'订单访问记录','request':{'method':'GET','url':app.origin+'/orders/{id}/audit'}})
                candidate=core.application_sources.preview(project,kind='POSTMAN',raw=json.dumps(collection))
                action=app.flow.business_action_id
                async def update_sources():
                    async with httpx2.AsyncClient(base_url=origin,headers={'Authorization':'Bearer '+token,'Origin':origin},trust_env=False) as transport:
                        async with Client(streamable_http_client(origin+'/mcp',http_client=transport,terminate_on_close=False)) as client:
                            created=await client.call_tool('jiejian_collaboration_create',dict(project_id=project,operation_id=uuid4().hex,goal='维护订单场景并核对原问题',purpose='CHECK'))
                            task=created.structured_content['task_id']
                            diff=await client.call_tool('jiejian_collaboration_action',dict(project_id=project,task_id=task,operation_id=uuid4().hex,capability='sources.preview',arguments=dict(candidate_id=candidate['candidate_id'],source_id=source_id)))
                            assert diff.structured_content['state']=='SUCCEEDED'
                            difference=diff.structured_content['result']
                            assert difference['previous_revision']==1 and len(difference['added'])==1
                            assert not difference['changed'] and not difference['removed']
                            result=await client.call_tool('jiejian_collaboration_action',dict(project_id=project,task_id=task,operation_id=uuid4().hex,capability='sources.accept',arguments=dict(candidate_id=candidate['candidate_id'],source_id=source_id,name='订单请求集合',expected_revision=1,expected_fingerprint=candidate['fingerprint'])))
                            assert result.structured_content['state']=='SUCCEEDED'
                            context=await client.call_tool('jiejian_collaboration_read',dict(project_id=project,task_id=task,capability='sources.read',arguments={}))
                            source=next(item for item in context.structured_content['result']['sources'] if item['source_id']==source_id)
                            request=next(item for item in source['requests'] if item['path']=='/orders/{id}')
                            reference=next(item for item in context.structured_content['result']['request_references'] if item['source_id']==source_id and item['item_id']==request['item_id'])
                            assert reference['revision']==2
                            result=await client.call_tool('jiejian_collaboration_action',dict(project_id=project,task_id=task,operation_id=uuid4().hex,capability='sources.annotate',arguments=dict(source_id=source_id,item_id=reference['item_id'],label='订单可见字段',action_id=action,expected_revision=0)))
                            assert result.structured_content['state']=='SUCCEEDED'
                            return task,reference
                # 同步Playwright持有自己的事件循环；MCP客户端使用独立线程，避免嵌套运行循环。
                def mcp_call(callback):
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        return pool.submit(lambda:asyncio.run(callback())).result(timeout=30)
                task,reference=mcp_call(update_sources)
                with sync_playwright() as engine:
                    browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
                    try:
                        page=browser.new_page(viewport={'width':1512,'height':980},device_scale_factor=1)
                        page.on('pageerror',lambda error:errors.append(type(error).__name__))
                        def record_response(response):
                            if '/operation-flows' in response.url and response.request.method in {'POST','PUT'}:
                                responses.append(dict(status=response.status,url=response.url.split(origin)[-1],input=response.request.post_data_json,output=response.json()))
                        page.on('response',record_response)
                        def visit(path):
                            page.goto(origin+'/?workflow='+uuid4().hex+'#'+path+('&' if '?' in path else '?')+'project_id='+project)
                        def capture(name):
                            for theme in ('light','dark'):
                                if page.locator('html').get_attribute('data-studio-theme')!=theme:
                                    page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                                for width in (1512,800,375):
                                    page.set_viewport_size({'width':width,'height':980});page.evaluate('scrollTo(0,0)');settled(page)
                                    geometry=page.locator('.jj-flow-review').evaluate('''root=>({overflow:document.documentElement.scrollWidth>innerWidth,clipped:[...root.querySelectorAll('button,input,select,code')].filter(node=>{const r=node.getBoundingClientRect();return r.width&&r.height&&(r.left<0||r.right>innerWidth+1)}).map(node=>node.tagName)})''')
                                    assert not geometry['overflow'] and not geometry['clipped'],geometry
                                    alignment=page.locator('.jj-flow-trial-heading').evaluate('node=>{const [a,b]=[...node.children].map(child=>child.getBoundingClientRect());return Math.abs(a.y+a.height/2-b.y-b.height/2)}')
                                    assert alignment<1,alignment
                                    observations.append(dict(state=name,theme=theme,width=width,heading_alignment=alignment,**geometry))
                                    page.screenshot(path=str(output/f'{name}-{theme}-{width}.png'),full_page=True)
                            page.set_viewport_size({'width':1512,'height':980})
                        visit('/testing?action_id='+action+'&source_id='+source_id+'&request_id='+reference['item_id'])
                        page.get_by_label('用于测试的数据编号',exact=True).fill('order-1')
                        page.get_by_role('button',name='下一步：设置执行步骤',exact=True).click()
                        page.get_by_label('接口路径',exact=True).fill('/orders/{case_resource_id}')
                        page.get_by_role('button',name='添加查询参数',exact=True).click()
                        page.get_by_label('参数名称',exact=True).fill('view')
                        page.get_by_label('发送的值',exact=True).fill('detail')
                        page.get_by_role('tab',name='请求头 0',exact=True).click()
                        page.get_by_role('button',name='添加请求头',exact=True).click()
                        page.get_by_label('参数名称',exact=True).fill('Accept')
                        page.get_by_label('发送的值',exact=True).fill('application/json')
                        page.get_by_role('button',name='下一步：结果与恢复',exact=True).click()
                        page.get_by_role('checkbox',name='订单备注可见',exact=True).check()
                        page.get_by_label('所有者查询路径',exact=True).fill('/owner/orders/{case_resource_id}')
                        page.get_by_role('button',name='下一步：核对操作',exact=True).click()
                        page.get_by_role('button',name='保存操作设置',exact=True).click()
                        expect(page.get_by_role('button',name='预览试运行',exact=True)).to_be_visible()
                        capture('trial-selection')
                        page.get_by_role('button',name='预览试运行',exact=True).click()
                        expect(page.get_by_role('heading',name='确认本次执行范围',exact=True)).to_be_visible()
                        expect(page.get_by_role('button',name='确认用于检查',exact=True)).to_be_disabled()
                        capture('trial-preview')
                        page.get_by_role('button',name='确认执行一次',exact=True).click()
                        expect(page.get_by_text('请求被接受',exact=True)).to_be_visible(timeout=45000)
                        flows=core.operation_flows.context(project)['flows']
                        saved=next(item['document'] for item in flows if item['document']['source_request']['revision']==2)
                        original=core.operation_flows.context(project)
                        assert saved['workflow']['steps'][0]['request_template']['query'][0]['literal']=='detail'
                        assert app.state['inputs'][-1]==dict(query='view=detail',accept='application/json')
                        # 重新打开准确修订后编辑，查询和请求头值仍在，旧试运行仍引用修订1。
                        visit('/testing?action_id='+action)
                        page.get_by_role('button',name='核对这份操作',exact=True).click()
                        page.get_by_role('button',name='修改设置',exact=True).click()
                        page.get_by_role('button',name='下一步：设置执行步骤',exact=True).click()
                        expect(page.get_by_label('发送的值',exact=True)).to_have_value('detail')
                        page.get_by_label('发送的值',exact=True).fill('summary')
                        page.get_by_role('tab',name='请求头 1',exact=True).click()
                        expect(page.get_by_label('发送的值',exact=True)).to_have_value('application/json')
                        page.get_by_role('button',name='下一步：结果与恢复',exact=True).click()
                        page.get_by_role('button',name='下一步：核对操作',exact=True).click()
                        page.get_by_role('button',name='保存操作设置',exact=True).click()
                        expect(page.locator('.jj-flow-trial > header').get_by_text('第 2 修订',exact=True)).to_be_visible()
                        saved=next(item['document'] for item in core.operation_flows.context(project)['flows'] if item['document']['id']==saved['id'])
                        assert saved['revision']==2
                        async def queue_trial():
                            async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+token,'Origin':origin},trust_env=False) as transport:
                                async with Client(streamable_http_client(origin+'/mcp',http_client=transport,terminate_on_close=False)) as client:
                                    selection=dict(flow_id=saved['id'],revision=2,subject_identity_id=app.identities['member'])
                                    preview=await client.call_tool('jiejian_collaboration_read',dict(project_id=project,task_id=task,capability='flows.trial.preview',arguments=selection))
                                    plan=preview.structured_content['result']
                                    operation=uuid4().hex
                                    result=await client.call_tool('jiejian_collaboration_action',dict(project_id=project,task_id=task,operation_id=operation,capability='flows.trial.start',arguments=dict(selection=selection,plan_hash=plan['plan_hash'],confirmed=True)))
                                    assert result.structured_content['state']=='WAITING_USER'
                                    assert core.flow_trials.requested(project,operation) is None
                                    return operation
                        operation=mcp_call(queue_trial)
                        visit('/workspace?view=collaboration&task_id='+task)
                        expect(page.locator('.jj-collaboration-entry')).to_contain_text('Agent 协作')
                        expect(page.locator('.jj-collaboration-entry')).to_contain_text('待你确认')
                        expect(page.get_by_role('heading',name='执行已确认的场景试运行',exact=True)).to_be_visible()
                        expect(page.get_by_text(app.origin,exact=True)).to_be_visible()
                        page.get_by_role('button',name='确认并执行',exact=True).click()
                        trial=until(lambda:core.flow_trials.requested(project,operation),lambda value:value is not None and value['state'] in {'SUCCEEDED','FAILED','CANCELLED'},seconds=45)
                        assert trial['state']=='SUCCEEDED' and trial['report']['steps'][0]['classification']=='DENIED',trial
                        assert app.state['target_calls']==2 and app.state['inputs'][-1]['query']=='view=summary'
                        visit('/testing?action_id='+action+'&trial_id='+trial['request']['trial_id'])
                        expect(page.get_by_text('请求被拒绝',exact=True)).to_be_visible()
                        capture('trial-history')
                        page.get_by_role('button',name='确认用于检查',exact=True).click()
                        expect(page.get_by_role('heading',name='操作已准备好',exact=True)).to_be_visible()
                        visit('/reports?view=plan')
                        expect(page.get_by_role('button',name='开始检查',exact=True)).to_be_enabled()
                        page.get_by_text('保存与沿用检查范围',exact=True).click()
                        page.get_by_role('combobox',name='沿用检查范围',exact=True).press('ArrowDown')
                        page.get_by_role('option',name='订单权限日常检查',exact=True).click()
                        expect(page.get_by_role('heading',name='必要正常对照',exact=True)).to_be_visible()
                        expect(page.get_by_role('button',name='开始检查',exact=True)).to_be_enabled()
                        page.get_by_role('button',name='开始检查',exact=True).click()
                        page.wait_for_url(lambda url:'run_id=' in url,timeout=15000)
                        run_id=page.url.split('run_id=')[1].split('&')[0]
                        status=until(lambda:core.check_results.status(run_id,project_id=project),lambda value:value.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED'},seconds=45)
                        assert status.run.verdict.value=='BLOCK',status
                        story=core.check_story.build(run_id,include_repair=False,project_id=project)
                        stages.append(dict(run_id=run_id,verdict='BLOCK'))
                        app.state['vulnerable']=False
                        visit('/issues')
                        page.get_by_role('button',name='按原问题再次验证',exact=True).click()
                        page.get_by_label('本次部署或处理说明',exact=True).fill('普通订单应用已限制他人读取，核对原问题及本人正常访问')
                        page.get_by_role('button',name='预览原问题与正常对照',exact=True).click()
                        page.get_by_role('button',name='确认范围并开始',exact=True).click()
                        page.wait_for_url(lambda url:'run_id=' in url and run_id not in url,timeout=15000)
                        repeated=page.url.split('run_id=')[1].split('&')[0]
                        status=until(lambda:core.check_results.status(repeated,project_id=project),lambda value:value.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED'},seconds=45)
                        assert status.run.verdict.value=='PASS',status
                        assert core.check_story.build(run_id,include_repair=False,project_id=project)==story
                        assert core.check_repairs.verification(repeated).verification_scope=='EXTERNAL_OBSERVATION'
                        stages.append(dict(run_id=repeated,verdict='PASS'))
                        expect(page.get_by_text('本次检查的适用范围',exact=True)).to_be_visible(timeout=45000)
                        page.evaluate('scrollTo(0,0)');settled(page);page.screenshot(path=str(output/'external-recheck.png'),full_page=True)
                        assert not errors,errors
                        assert app.state['target_calls']==6
                        assert core.application_understanding.get(project).source_root is None
                        for artifact in output.rglob('*'):
                            if artifact.is_file() and artifact.suffix in {'.json','.jsonl','.log','.txt'}:
                                content=artifact.read_bytes()
                                assert b'confidential-order-note' not in content
                                assert all(token.encode() not in content for token in app.tokens)
                        assert core.check_routines.list(project)==routines
                        assert core.business_boundaries.view(project).permission_intents==permissions
                        assert next(item for item in core.operation_flows.context(project)['flows'] if item['document']['id']==app.flow.id)==next(item for item in original['flows'] if item['document']['id']==app.flow.id)
                        # 从旧试运行继续编辑应生成最新修订之后的新草稿，不覆盖仍在采用的修订2。
                        first_trial=next(item for item in core.flow_trials.history(project) if item['request']['plan']['flow']['id']==saved['id'] and item['request']['plan']['flow']['revision']==1)
                        visit('/testing?action_id='+action+'&trial_id='+first_trial['request']['trial_id'])
                        page.get_by_role('button',name='从此修订继续编辑',exact=True).click()
                        expect(page.get_by_label('发送的值',exact=True)).to_have_value('detail')
                        page.get_by_role('button',name='下一步：结果与恢复',exact=True).click()
                        page.get_by_role('button',name='下一步：核对操作',exact=True).click()
                        page.get_by_role('button',name='保存操作设置',exact=True).click()
                        expect(page.locator('.jj-flow-trial > header').get_by_text('第 3 修订',exact=True)).to_be_visible()
                        final=core.operation_flows.context(project)['flows']
                        assert any(item['document']['id']==saved['id'] and item['document']['revision']==2 and item['in_use'] for item in final)
                        assert any(item['document']['id']==saved['id'] and item['document']['revision']==3 and not item['in_use'] for item in final)
                    except BaseException:
                        import traceback
                        (output/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
                        raise
                    finally:
                        if not page.is_closed():
                            page.screenshot(path=str(output/'last-view.png'),full_page=True)
                            (output/'last-view.txt').write_text(page.locator('main').inner_text(),encoding='utf-8')
                        (output/'flow-requests.json').write_text(json.dumps(responses,ensure_ascii=False,indent=2),encoding='utf-8')
                        browser.close()
        finally:
            server.should_exit=True;thread.join(timeout=35)
            assert not thread.is_alive()
            (output/'workflow.json').write_text(json.dumps(dict(schema_version='1',stages=stages,geometry=observations,page_errors=errors),ensure_ascii=False,indent=2),encoding='utf-8')
