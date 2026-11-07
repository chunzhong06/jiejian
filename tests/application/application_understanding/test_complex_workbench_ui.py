"""真实工作面校准：两主题、窄窗、键盘与共享控件；只输出三个修改工作面的重点截图。"""
import json
from pathlib import Path
from uuid import uuid4

import pytest


def test_complex_workbenches_use_shared_controls_and_preserve_theme():
    from playwright.sync_api import sync_playwright,expect
    from tests.support.runtime_server import launch
    from tests.support.official import OfficialScenario
    from tests.support.browser_review import navigate,settled
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/audit/phase-b/build/runtime/source/receipt.json').read_text(encoding='utf-8'))
    output=root/'var/audit/phase-b/review'/uuid4().hex
    errors=[];metrics=[]
    with launch(output,Path(receipt['frontend']['dist'])) as server,sync_playwright() as engine:
        scenario=OfficialScenario(server.client);scenario.start();scenario.check('BASELINE')
        prefix=f'/api/projects/{scenario.project_id}'
        context=scenario.request('GET',prefix+'/business-scenarios/context')
        action=next(item for item in context['actions'] if any(case['permission']['expectation']=='DENY' for case in item['cases']))
        def node(expectation):
            case=next(case for case in action['cases'] if case['permission']['expectation']==expectation)
            return dict(id='download',label=action['label'],items=[dict(id='resource',resource_id=case['resource_id'],
                subject_identity_id=case['subject_test_identity_id'],permission={key:case['permission'][key] for key in ('intent_id','revision','intent_hash')})])
        document=dict(document_type='jiejian.business-scenario',schema_version='1',id='bsc_'+uuid4().hex,
            project_id=scenario.project_id,revision=1,label='共享资料的身份对照',description='沿用已有操作与测试资源，检查不同账号下的文件交付。',experiments=[
                dict(id='normal',label='正常业务',kind='NORMAL',invocations=[node('ALLOW')]),
                dict(id='other',label='切换操作账号',kind='CHANGE_SUBJECT',control_experiment_id='normal',invocations=[node('DENY')])])
        scenario.request('PUT',prefix+'/business-scenarios',document)
        proofs=scenario.request('GET',prefix+'/proof-preparation')
        file=next(item for item in proofs['sources'] if item['config']['source_kind']=='REFERENCE_FILE')
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980},device_scale_factor=1)
            page.set_default_timeout(30000);page.on('pageerror',lambda error:errors.append(type(error).__name__))
            def theme(value):
                if page.locator('html').get_attribute('data-studio-theme')!=value:
                    page.get_by_role('button',name='切换雾蓝深色' if value=='dark' else '切换浅色',exact=True).click()
                settled(page)
            def layout(name):
                # ResizeObserver 在布局帧内校准选择标记；先完成两帧再等待其过渡，避免读取上一宽度的位置。
                page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                settled(page)
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1'),name
                for panel in page.get_by_role('dialog').all():
                    overflow=panel.evaluate('node=>node.scrollWidth>node.clientWidth+1')
                    if overflow:
                        # 保留失败时的真实尺寸，不靠重新运行一次通过来判断其为时序问题。
                        diagnostic=panel.evaluate('''node=>({viewport:innerWidth,client:node.clientWidth,scroll:node.scrollWidth,children:[...node.querySelectorAll('*')].map(item=>{const box=item.getBoundingClientRect();return {tag:item.tagName,classes:String(item.className),left:box.left,right:box.right,width:box.width,client:item.clientWidth,scroll:item.scrollWidth}})})''')
                        (output/'dialog-overflow.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
                        page.screenshot(path=str(output/'dialog-overflow.png'),full_page=True)
                    assert not overflow,name
                    expect(panel.get_by_role('button',name='关闭',exact=True)).to_be_in_viewport()
                metrics.append(dict(page=name,width=page.viewport_size['width'],theme=page.locator('html').get_attribute('data-studio-theme'),font=page.locator('html').get_attribute('data-ui-font')))
            def snapshot(name):
                # 全页截图前归零文档滚动，避免固定导航按当前滚动位置出现在图中间。
                page.mouse.move(220,80)
                page.evaluate("document.activeElement?.blur();scrollTo({top:0,left:0,behavior:'instant'})");settled(page)
                page.screenshot(path=str(output/name),full_page=True)
            navigate(page,server.origin,'/testing?scenario='+document['id']+'&project_id='+scenario.project_id)
            expect(page.get_by_role('heading',name='组合业务场景',exact=True)).to_be_visible()
            tabs=page.get_by_role('tablist',name='业务实验',exact=True)
            tabs.get_by_role('tab',name='正常业务',exact=True).focus();page.keyboard.press('ArrowRight')
            expect(tabs.get_by_role('tab',name='切换操作账号',exact=True)).to_have_attribute('aria-selected','true')
            for value in ('light','dark'):
                theme(value)
                for width in (1512,1040,760,420):page.set_viewport_size({'width':width,'height':980});layout('业务场景')
            page.set_viewport_size({'width':1512,'height':980});settled(page)
            index=page.get_by_label('执行顺序',exact=True).bounding_box()
            append=page.get_by_role('button',name='添加动作',exact=True).bounding_box()
            assert append['y']-(index['y']+index['height'])>=24

            # 比较表沿用共享选中表面；只改草稿，不把不支持的文件批量冒充可执行计划。
            def choose(label,option):
                page.get_by_role('combobox',name=label,exact=True).press('ArrowDown')
                page.get_by_role('option',name=option,exact=True).click()
            choose('本步调用方式','一次批量 · 整批原子')
            page.get_by_role('button',name='添加资源',exact=True).click()
            expect(page.get_by_role('table')).to_be_visible()
            page.get_by_role('button',name='编辑第 2 项资源',exact=True).click()
            denied=next(item for item in action['cases'] if item['permission']['expectation']=='DENY')
            identity=next(item['label'] for item in context['identities'] if item['identity_id']==denied['subject_test_identity_id'])
            choose('调整所选资源与规则',action['label']+' · '+identity+' · '+denied['resource_id']+' · 禁止')
            for value in ('light','dark'):
                theme(value)
                for width in (1512,760,420):page.set_viewport_size({'width':width,'height':980});layout('批量资源比较')
            page.set_viewport_size({'width':1512,'height':980})
            snapshot('batch-preparation-dark.png')
            choose('本步调用方式','单项请求')
            tabs.get_by_role('tab',name='正常业务',exact=True).click()
            page.get_by_role('button',name='预览到此步骤',exact=True).click()
            expect(page.get_by_role('heading',name='核对本次检查范围',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='返回业务场景',exact=True)).to_be_visible()
            page.get_by_role('button',name='开始检查',exact=True).click()
            expect(page.get_by_role('table',name='逐项业务场景结果',exact=True)).to_be_visible(timeout=90000)
            for value in ('light','dark'):
                theme(value)
                for width in (1512,760,420):page.set_viewport_size({'width':width,'height':980});layout('场景结果比较')
            page.set_viewport_size({'width':1512,'height':980});settled(page)
            page.get_by_role('button',name='交给 Agent 解读',exact=True).click()
            page.get_by_role('button',name='进入协作任务',exact=True).click()
            expect(page.get_by_role('heading',name='Agent 协作',exact=True)).to_be_visible()
            expect(page.get_by_role('tab',name='产物与上下文',exact=True)).to_be_visible()
            for value in ('light','dark'):
                theme(value)
                for width in (1512,760,420):page.set_viewport_size({'width':width,'height':980});layout('准确报告交接')
            page.set_viewport_size({'width':1512,'height':980})

            navigate(page,server.origin,'/permissions?project_id='+scenario.project_id)
            page.get_by_role('button',name='编辑权限要求',exact=True).click()
            row=page.locator('tbody tr').filter(has_text='评审').first
            row.get_by_role('button',name='编辑',exact=False).click()
            condition_editor=page.get_by_role('region',name='的适用条件',exact=False)
            expect(condition_editor).to_be_visible()
            assert condition_editor.evaluate('node=>node.closest("td").colSpan')==4
            assert row.bounding_box()['height']<180
            assert condition_editor.evaluate('node=>getComputedStyle(node).animationName')=='jj-content-enter'
            page.emulate_media(reduced_motion='reduce')
            assert condition_editor.evaluate('node=>getComputedStyle(node).animationName')=='none'
            page.emulate_media(reduced_motion='no-preference')
            choose('补充关系条件','有限委托');choose('适用状态','授权已撤销')
            for value in ('light','dark'):
                theme(value)
                for width in (1512,760,420):page.set_viewport_size({'width':width,'height':980});layout('委托撤销条件')
            page.set_viewport_size({'width':1512,'height':980})
            condition_editor.get_by_role('button',name='移除条件',exact=True).click()
            choose('补充关系条件','组织成员与层级')
            choose('组织范围','操作人组织是资源组织的上级')
            page.get_by_label('最多经过的层级',exact=True).fill('3')
            expect(page.get_by_label('最多经过的层级',exact=True)).to_have_value('3')
            assert page.get_by_role('combobox',name='补充关系条件',exact=True).evaluate('node=>node.closest(".jj-choice").textContent').strip()=='选择需要核对的关系'
            assert page.get_by_role('combobox',name='组织范围',exact=True).evaluate('node=>node.closest(".jj-choice").clientWidth')>=250
            layout('组织层级条件')
            snapshot('permission-conditions-dark.png')

            path='/preparation?proof_sources=1&configure=edit&source_id='+file['source_id']+'&action_id='+file['config']['action_id']+'&project_id='+scenario.project_id
            navigate(page,server.origin,path)
            dialog=page.get_by_role('dialog',name='设置结果判断依据',exact=True)
            expect(dialog).to_be_visible()
            delivery=dialog.get_by_role('combobox',name='交付方式',exact=True)
            delivery.focus();delivery.press('ArrowDown');delivery.press('ArrowDown');delivery.press('Enter')
            dialog.get_by_role('textbox',name='任务查询路径',exact=True).fill('/exports/{task_id}')
            async_tabs=dialog.get_by_role('tablist',name='异步导出配置',exact=True)
            async_tabs.get_by_role('tab',name='任务与文件',exact=True).focus();page.keyboard.press('ArrowRight')
            expect(async_tabs.get_by_role('tab',name='状态映射',exact=True)).to_have_attribute('aria-selected','true')
            for value in ('dark','light'):
                if page.locator('html').get_attribute('data-studio-theme')!=value:
                    page.keyboard.press('Escape');expect(dialog).not_to_be_visible();theme(value)
                    page.get_by_role('tab',name='来源与管理',exact=True).click()
                    page.get_by_role('button',name='调整判断方式',exact=True).click();expect(dialog).to_be_visible()
                theme(value)
                for width in (1512,760,420,760,420,760,420):page.set_viewport_size({'width':width,'height':980});layout('异步文件配置')
            page.set_viewport_size({'width':1512,'height':980});async_tabs.get_by_role('tab',name='任务与文件',exact=True).click()
            expect(dialog.get_by_role('textbox',name='任务查询路径',exact=True)).to_have_value('/exports/{task_id}')
            settled(page)
            dialog.get_by_role('button',name='取消',exact=True).click()
            expect(page.get_by_role('heading',name='读取位置与范围',exact=True)).to_be_visible()
            expect(page.get_by_role('heading',name='判断方式',exact=True)).to_be_visible()
            for value in ('light','dark'):
                theme(value)
                for width in (1512,760,420):page.set_viewport_size({'width':width,'height':980});layout('来源设置的对象归属')
            page.set_viewport_size({'width':1512,'height':980})

            source=output/'node-source';source.mkdir();(source/'app.mjs').write_text("import http from 'node:http';http.createServer((req,res)=>res.end('test')).listen(Number(process.env.PORT),'127.0.0.1');",encoding='utf-8')
            project=scenario.request('POST','/api/applications/connect',dict(schema_version='1',source_root=str(source),project_name='数据库连接审阅'))['project']['project_id']
            understanding=scenario.request('GET','/api/projects/'+project+'/application-understanding')
            scenario.request('PUT','/api/projects/'+project+'/source-analysis-authorization',dict(schema_version='1',authorized=True,revision=understanding['revision']))
            navigate(page,server.origin,'/application?view=source&project_id='+project)
            page.get_by_role('radio',name='由界鉴启动',exact=True).check()
            page.get_by_text('依赖与测试数据',exact=False).first.click()
            page.get_by_role('button',name='添加连接',exact=True).click()
            dialog=page.get_by_role('dialog',name='声明测试数据库',exact=True);expect(dialog).to_be_visible()
            for value in ('light','dark'):
                if page.locator('html').get_attribute('data-studio-theme')!=value:
                    page.keyboard.press('Escape');expect(dialog).not_to_be_visible();theme(value)
                    page.get_by_role('button',name='添加连接',exact=True).click();expect(dialog).to_be_visible()
                theme(value)
                for width in (1512,760,420):page.set_viewport_size({'width':width,'height':980});layout('数据库声明')
            page.set_viewport_size({'width':1512,'height':980});settled(page)
            page.keyboard.press('Escape');expect(dialog).not_to_be_visible()
            navigate(page,server.origin,'/permissions?project_id='+project)
            page.get_by_role('button',name='编写权限要求',exact=True).click()
            page.get_by_role('tab',name='操作与结果 0',exact=True).click()
            page.get_by_role('button',name='添加操作',exact=True).click()
            operations=page.get_by_role('region',name='业务操作',exact=True)
            operation_heading=operations.locator(':scope > header')
            expect(operation_heading.get_by_role('heading',name='业务操作',exact=True)).to_be_visible()
            expect(operation_heading.get_by_role('button',name='添加操作',exact=True)).to_be_visible()
            results=page.get_by_role('region',name='业务操作 1的业务结果',exact=True)
            expect(results.locator(':scope > header').get_by_role('button',name='添加结果',exact=True)).to_be_visible()
            page.get_by_label('操作名称',exact=True).fill('修改归属字段与较长的业务说明')
            page.get_by_label('操作的资源',exact=True).fill('项目资料')
            page.get_by_label('结果名称',exact=True).fill('归属字段被赋为指定值')
            choose('结果类型','状态改变')
            choose('状态证明范围','准确字段的写入')
            page.get_by_label('业务字段路径',exact=True).fill('profile.owner_id')
            choose('要观察的写入','字段被赋为指定值')
            choose('赋值类型','布尔值');choose('指定值','true')
            for value in ('light','dark'):
                theme(value)
                for width in (1512,760,420):page.set_viewport_size({'width':width,'height':980});layout('准确字段写入')
            page.set_viewport_size({'width':1512,'height':980});theme('light');settled(page)
            assert page.get_by_label('业务字段路径',exact=True).bounding_box()['width']>=300
            assert page.get_by_role('combobox',name='要观察的写入',exact=True).evaluate('node=>node.closest(".jj-choice").clientWidth')>=300
            snapshot('field-write-light.png')
            assert errors==[],errors
        finally:
            browser.close()
            (output/'review.json').write_text(json.dumps(dict(errors=errors,layouts=metrics),ensure_ascii=False,indent=2),encoding='utf-8')


def test_scenario_node_trial_uses_adopted_flow_and_keeps_history():
    import socket
    from threading import Thread
    import uvicorn
    from playwright.sync_api import sync_playwright,expect
    from product.backend.interfaces.http.app import create_app
    from product.protocols.checks.scenarios import BusinessScenarioRevision
    from tests.support.builders.preparation.external_application import external_application
    from tests.support.builders.runtime.runtime_environment import runtime_identity_environment
    from tests.support.secrets import MemorySecrets
    from tests.support.official import until
    from tests.support.browser_review import navigate,settled
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/audit/phase-b/build/runtime/source/receipt.json').read_text(encoding='utf-8'))
    output=root/'var/audit/phase-b/node-trial'/uuid4().hex
    instance=output/'instance'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    web=create_app(instance,control_origin=origin,control_session_token=uuid4().hex*2,
        frontend_dir=Path(receipt['frontend']['dist']),secret_store=MemorySecrets(),environ=runtime_identity_environment(instance))
    core=web.state.context
    server=uvicorn.Server(uvicorn.Config(web,host='127.0.0.1',port=port,log_level='error'))
    thread=Thread(target=server.run,daemon=True)
    try:
        with external_application(output/'ordinary',core=core) as app:
            core.operation_flows.adopt(app.project_id,app.flow.id,app.flow.revision)
            context=core.business_scenarios.context(app.project_id)
            action=context['actions'][0]
            case=next(item for item in action['cases'] if item['permission']['expectation']=='ALLOW')
            document=BusinessScenarioRevision.model_validate_json(json.dumps(dict(id='bsc_'+uuid4().hex,project_id=app.project_id,revision=1,label='订单流程试运行',experiments=[dict(id='normal',label='正常业务',kind='NORMAL',invocations=[dict(id='read',label='读取订单',items=[dict(id='order',resource_id=case['resource_id'],subject_identity_id=case['subject_test_identity_id'],permission={key:case['permission'][key] for key in ('intent_id','revision','intent_hash')})])]) ])))
            core.business_scenarios.save(app.project_id,document)
            thread.start();until(lambda:server.started,bool,seconds=30)
            with sync_playwright() as engine:
                browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
                try:
                    page=browser.new_page(viewport=dict(width=1512,height=980))
                    navigate(page,origin,'/testing?scenario='+document.id+'&project_id='+app.project_id)
                    page.get_by_role('button',name='单独试运行',exact=True).click()
                    dialog=page.get_by_role('dialog',name='单独试运行 · 读取订单',exact=True)
                    dialog.get_by_role('button',name='预览试运行',exact=True).click()
                    expect(dialog.get_by_role('heading',name='确认本次执行范围',exact=True)).to_be_visible()
                    dialog.get_by_role('button',name='确认执行一次',exact=True).click()
                    expect(dialog.get_by_text('主体核验：一致。本场景无需恢复',exact=True)).to_be_visible(timeout=60000)
                    for width in (1512,420):
                        page.set_viewport_size(dict(width=width,height=980));settled(page)
                        assert not dialog.evaluate('node=>node.scrollWidth>node.clientWidth+1')
                    dialog.get_by_role('button',name='关闭',exact=True).click();expect(dialog).not_to_be_visible()
                    page.set_viewport_size(dict(width=1512,height=980))
                    if page.locator('html').get_attribute('data-studio-theme')!='dark':
                        page.get_by_role('button',name='切换雾蓝深色',exact=True).click()
                    page.get_by_role('button',name='单独试运行',exact=True).click()
                    dialog.get_by_role('tab',name='试运行记录 1',exact=True).click()
                    expect(dialog.get_by_text('主体核验：一致。本场景无需恢复',exact=True)).to_be_visible()
                    for width in (1512,420):
                        page.set_viewport_size(dict(width=width,height=980));settled(page)
                        assert not dialog.evaluate('node=>node.scrollWidth>node.clientWidth+1')
                    dialog.get_by_role('button',name='关闭',exact=True).click();expect(dialog).not_to_be_visible()
                    assert core.business_scenarios.read(app.project_id,document.id,1)==document
                    assert app.state['target_calls']==1
                finally:browser.close()
    finally:
        server.should_exit=True
        if thread.ident is not None:thread.join(timeout=30)
        assert not thread.is_alive()
        core.close()


pytestmark=[pytest.mark.level4,pytest.mark.process,pytest.mark.slow]
