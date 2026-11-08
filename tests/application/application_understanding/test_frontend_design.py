"""使用真实本地示例核对导航选择、局部交接和操作上下文，不调用模型。"""
import json
from pathlib import Path
from uuid import uuid4
import pytest

pytestmark=[pytest.mark.level4,pytest.mark.browser,pytest.mark.process]


def _record_switch(page,root_selector,button):
    page.evaluate("""selector=>{window.localMotion=[];window.localMotionDone=false;const start=performance.now();function frame(){const root=document.querySelector(selector),marker=root?.querySelector('.jj-segment-indicator,.jj-index-surface');window.localMotion.push({at:performance.now()-start,marker:marker?getComputedStyle(marker).transform:'absent',animations:document.getAnimations().filter(item=>item.effect.getComputedTiming().endTime!==Infinity).map(item=>({name:item.animationName??item.transitionProperty??'content',target:item.effect.target?.className,duration:item.effect.getComputedTiming().duration}))});if(performance.now()-start<500)requestAnimationFrame(frame);else window.localMotionDone=true}requestAnimationFrame(frame)}""",root_selector)
    button.click()
    page.wait_for_function('window.localMotionDone')
    return page.evaluate('window.localMotion')


def test_collection_titles_keep_typography_across_semantic_levels():
    """用实际构建核对同类标题、表单分组与窄窗阅读顺序，不提交规则。"""
    import re
    from playwright.sync_api import sync_playwright, expect
    from tests.support.runtime_server import launch
    from tests.support.browser_review import settled

    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text('utf-8'))
    output=root/'var/maintenance/consolidation-20261106/title-review'/uuid4().hex
    source=output/'source';source.mkdir(parents=True)
    signatures=[]
    with launch(output/'runtime',Path(receipt['frontend']['dist'])) as server,sync_playwright() as engine:
        response=server.client.post('/api/applications/connect',json={'schema_version':'1','source_root':str(source),'project_name':'权限协作工作区'})
        assert response.status_code==201,response.text
        project=response.json()['data']['project']['project_id']
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980})
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(server.origin+'/#/permissions?project_id='+project)
            page.get_by_role('button',name=re.compile(r'^(编写|编辑)权限要求$')).click()
            expect(page.get_by_role('heading',name='编写权限要求',exact=True)).to_be_visible()
            page.get_by_role('tab',name='操作与结果 0',exact=True).click()
            page.get_by_role('button',name='添加操作',exact=True).click()
            page.get_by_label('操作名称',exact=True).fill('修改项目归属与授权范围')
            for theme in ('light','dark'):
                if page.locator('html').get_attribute('data-studio-theme')!=theme:
                    page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                for width in (1512,800,375):
                    page.set_viewport_size({'width':width,'height':980})
                    settled(page)
                    values=[]
                    for title,level in [('业务操作',2),('业务结果',3)]:
                        heading=page.get_by_role('heading',name=title,level=level,exact=True)
                        expect(heading).to_be_visible()
                        values.append(heading.evaluate("node=>{const s=getComputedStyle(node);return {size:s.fontSize,line:s.lineHeight,weight:s.fontWeight,family:s.fontFamily}}"))
                    assert values[0]==values[1],values
                    assert values[0]['size']=='20px' and values[0]['line']=='28px' and values[0]['weight']=='600',values
                    columns=page.locator('.jj-initial-action .jj-form-columns-layout').first
                    operation,result=columns.locator(':scope > section').all()
                    left,right=operation.bounding_box(),result.bounding_box()
                    assert left and right
                    if width==1512:
                        assert abs(left['y']-right['y'])<1,(left,right)
                        assert right['x']-(left['x']+left['width'])>=31,(left,right)
                    else:
                        assert right['y']>=left['y']+left['height']+27,(left,right)
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    signatures.append(dict(theme=theme,width=width,typography=values[0]))
                    if width==1512:
                        page.mouse.move(1500,970)
                        page.screenshot(path=str(output/f'titles-{theme}.png'),full_page=False)
            assert not errors,errors
        finally:
            browser.close()
    (output/'observations.json').write_text(json.dumps(signatures,ensure_ascii=False,indent=2),encoding='utf-8')


def test_database_forms_group_fields_with_spacing_in_browser():
    """只编辑数据库声明，核对两类配置的组间距；不保存凭据或启动应用。"""
    from playwright.sync_api import sync_playwright, expect
    from tests.support.runtime_server import launch
    from tests.support.browser_review import settled

    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text('utf-8'))
    output=root/'var/maintenance/consolidation-20261106/database-review'/uuid4().hex
    source=output/'source';source.mkdir(parents=True)
    (source/'app.mjs').write_text('export const fixture = true\n',encoding='utf-8')
    observations=[]
    with launch(output/'runtime',Path(receipt['frontend']['dist'])) as server,sync_playwright() as engine:
        response=server.client.post('/api/applications/connect',json={'schema_version':'1','source_root':str(source),'project_name':'数据库配置审阅'})
        assert response.status_code==201,response.text
        project=response.json()['data']['project']['project_id']
        understanding=server.client.get(f'/api/projects/{project}/application-understanding').json()['data']
        authorized=server.client.put(f'/api/projects/{project}/source-analysis-authorization',json={'schema_version':'1','authorized':True,'revision':understanding['revision']})
        assert authorized.status_code==200,authorized.text
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(server.origin+'/#/application?view=source&project_id='+project)
            page.get_by_role('radio',name='由界鉴启动',exact=True).check()
            page.locator('.jj-runtime-options > summary').click()
            page.get_by_role('button',name='手动添加',exact=True).click()
            card=page.locator('.jj-runtime-database').first
            for width in (1512,800,375):
                page.set_viewport_size({'width':width,'height':980});settled(page)
                bounds=card.evaluate('node=>[...node.children].map(item=>{const r=item.getBoundingClientRect();return {top:r.top,bottom:r.bottom}})')
                assert all(bounds[i]['top']-bounds[i-1]['bottom']>=19 for i in range(1,len(bounds))),bounds
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                observations.append(dict(view='sqlite',width=width,children=bounds))
            page.set_viewport_size({'width':1512,'height':980})
            page.get_by_role('button',name='添加连接',exact=True).click()
            dialog=page.get_by_role('dialog',name='声明测试数据库')
            expect(dialog).to_be_visible()
            # 临时显示不改变输入，也不保存凭据；键盘离开组后立即恢复遮蔽。
            password=dialog.get_by_label('数据库密码',exact=True)
            password.fill('temporary-ui-fixture')
            dialog.get_by_role('button',name='显示密码',exact=True).click()
            expect(password).to_have_attribute('type','text')
            dialog.get_by_role('button',name='隐藏密码',exact=True).focus()
            page.keyboard.press('Tab')
            expect(password).to_have_attribute('type','password')
            expect(password).to_have_value('temporary-ui-fixture')
            password.fill('')
            for selector in ('input:not([type=checkbox]):not(.ant-select-selection-search-input)','.jj-choice'):
                for node in dialog.locator(selector).all():
                    if node.is_visible(): assert abs(node.bounding_box()['height']-44)<1
            for width in (1512,800,375):
                page.set_viewport_size({'width':width,'height':980});settled(page)
                bounds=dialog.locator('.jj-form-columns-layout').evaluate('node=>[...node.children].map(item=>{const r=item.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}})')
                if width==1512:
                    assert abs(bounds[0]['top']-bounds[1]['top'])<1,bounds
                    assert bounds[1]['left']-bounds[0]['right']>=31,bounds
                else:
                    assert bounds[1]['top']-bounds[0]['bottom']>=27,bounds
                assert not dialog.evaluate('node=>node.scrollWidth>node.clientWidth')
                observations.append(dict(view='service',width=width,sections=bounds))
            assert not errors,errors
        finally:
            browser.close()
    (output/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf-8')


def test_navigation_selection_motion_in_browser():
    from playwright.sync_api import sync_playwright,expect
    from tests.support.runtime_server import launch
    from tests.support.official import OfficialScenario
    from tests.support.browser_review import settled
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text(encoding='utf-8'))
    output=root/'var/audit/ui-design-review'/uuid4().hex
    motions={}
    with launch(output,Path(receipt['frontend']['dist'])) as server,sync_playwright() as engine:
        scenario=OfficialScenario(server.client)
        scenario.start()
        checked=scenario.check('baseline')
        assert checked.status['run']['verdict']=='PASS'
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980},device_scale_factor=1)
            page.goto(server.origin+'/#/permissions?project_id='+scenario.project_id)
            expect(page.get_by_role('table')).to_be_visible();settled(page)
            if page.locator('html').get_attribute('data-studio-theme')!='dark':page.get_by_role('button',name='切换雾蓝深色',exact=True).click();settled(page)
            page.screenshot(path=str(output/'permissions-before.png'),full_page=True)
            all_button=page.get_by_role('button',name='全部',exact=True)
            page.get_by_role('button',name='允许',exact=True).hover();settled(page)
            colors=page.locator('.jj-segment-indicator').evaluate('(node)=>({selected:getComputedStyle(node).backgroundColor,expected:getComputedStyle(document.documentElement).getPropertyValue("--selected").trim(),container:getComputedStyle(node.parentElement).backgroundColor})')
            expected=page.evaluate('color=>{const n=document.createElement("span");n.style.backgroundColor=color;document.body.append(n);const colorValue=getComputedStyle(n).backgroundColor;n.remove();return colorValue}',colors['expected'])
            assert colors['selected']==expected and colors['selected']!=colors['container'],colors
            expect(all_button).to_have_attribute('aria-pressed','true')
            page.screenshot(path=str(output/'selection-hover-dark.png'),full_page=True)
            motions['filter']=_record_switch(page,'.jj-toggle-group',page.get_by_role('button',name='允许',exact=True))
            expect(page.get_by_role('button',name='允许',exact=True)).to_have_attribute('aria-pressed','true')
            assert len({frame['marker'] for frame in motions['filter'] if frame['marker']!='absent'})>2
            page.get_by_role('button',name='禁止',exact=True).click();page.wait_for_timeout(60)
            page.get_by_role('button',name='全部',exact=True).click();settled(page)
            marker=page.locator('.jj-segment-indicator').bounding_box()
            chosen=page.get_by_role('button',name='全部',exact=True).bounding_box()
            assert abs(marker['x']-chosen['x'])<1
            page.screenshot(path=str(output/'permissions-filtered.png'),full_page=True)
            page.goto(server.origin+'/#/preparation?project_id='+scenario.project_id)
            resources=page.get_by_role('button',name='查看测试资源',exact=True)
            expect(resources).to_be_visible();settled(page)
            motions['material']=_record_switch(page,'.jj-material-index',resources)
            expect(resources).to_have_attribute('aria-pressed','true')
            assert len({frame['marker'] for frame in motions['material'] if frame['marker']!='absent'})>2
            assert resources.evaluate('(node)=>getComputedStyle(node).borderRadius')=='0px'
            assert page.locator('.jj-material-index .jj-index-surface').evaluate('(node)=>getComputedStyle(node).backgroundColor')==expected
            page.emulate_media(reduced_motion='reduce')
            motions['reduced']=_record_switch(page,'.jj-material-index',page.get_by_role('button',name='查看测试账号',exact=True))
            assert all(not frame['animations'] for frame in motions['reduced'])
            quit_button=page.get_by_role('navigation',name='全局工具').get_by_role('button').last
            expect(quit_button).to_have_accessible_name('退出界鉴')
            quit_button.click();expect(page.get_by_role('dialog')).to_be_visible()
            page.get_by_role('dialog').get_by_role('button',name='继续使用',exact=True).click()
            expect(page.get_by_role('dialog')).to_have_count(0);expect(quit_button).to_be_focused()
            page.emulate_media(reduced_motion='no-preference')
            page.get_by_role('button',name='查看测试资源',exact=True).click();settled(page)
            page.screenshot(path=str(output/'material-selected.png'),full_page=True)
            review=[]
            paths=[('testing','/testing'),('business','/application?view=business'),('plan','/reports?view=plan'),('tools','/settings?section=tools')]
            for theme in ('light','dark'):
                if page.locator('html').get_attribute('data-studio-theme')!=theme:page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                for width in (1512,800,375):
                    page.set_viewport_size({'width':width,'height':980})
                    for name,path in paths:
                        page.goto(server.origin+'/?review='+uuid4().hex+'#'+path+('&' if '?' in path else '?')+'project_id='+scenario.project_id)
                        expect(page.locator('main h1')).to_have_count(1)
                        expect(page.locator('[data-page-pending=true]')).to_have_count(0)
                        expect(page.locator('main .jj-loading')).to_have_count(0);settled(page)
                        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(name,theme,width)
                        if name=='testing':
                            directory=page.locator('.jj-testing-directory')
                            rows=directory.locator('tbody > tr')
                            expect(rows).to_have_count(3)
                            expect(rows.first.get_by_role('button')).to_have_attribute('aria-pressed','true')
                            rows.nth(1).get_by_role('button').click()
                            expect(rows.nth(1).get_by_role('button')).to_have_attribute('aria-pressed','true')
                            expect(directory.locator('.jj-inspector h2')).to_have_text(rows.nth(1).get_by_role('button').locator('strong').inner_text())
                            if width==1512:
                                table=directory.locator('.jj-collection-main').bounding_box()
                                inspector=directory.locator('.jj-inspector').bounding_box()
                                assert table['x']+table['width']<=inspector['x']+1
                                assert abs(table['y']-inspector['y'])<1
                            page.get_by_role('button',name='准备与资料',exact=True).click()
                            expect(page.get_by_role('menuitem',name='身份与会话',exact=True)).to_be_visible()
                            page.keyboard.press('Escape')
                        if name=='plan':
                            page.get_by_role('button',name='选定规则',exact=True).click()
                            denied=page.locator('.jj-scope-rule-option').filter(has_text='不得').first.get_by_role('checkbox')
                            denied.check()
                            expect(page.locator('.jj-scope-controls')).to_be_visible()
                            expect(page.locator('main [aria-busy=true]')).to_have_count(0);settled(page)
                            chosen_colors=page.locator('.jj-scope-rule-option[data-selected=true]').evaluate_all('(nodes)=>nodes.map(node=>({color:getComputedStyle(node).backgroundColor,expected:getComputedStyle(document.documentElement).getPropertyValue("--selected").trim(),disabled:node.querySelector("input").disabled}))')
                            canonical=page.evaluate('color=>{const node=document.createElement("span");node.style.backgroundColor=color;document.body.append(node);const value=getComputedStyle(node).backgroundColor;node.remove();return value}',chosen_colors[0]['expected'])
                            assert all(item['color']==canonical for item in chosen_colors),chosen_colors
                            assert any(item['disabled'] for item in chosen_colors),chosen_colors
                        if name=='tools' and width==1512:
                            panels=page.locator('.jj-tools-layout > section').evaluate_all('(nodes)=>nodes.map(n=>{const r=n.getBoundingClientRect(),h=n.querySelector("h2").getBoundingClientRect();return {top:r.top,bottom:r.bottom,title:h.top}})')
                            assert abs(panels[0]['bottom']-panels[1]['bottom'])<1,panels
                            assert abs(panels[0]['title']-panels[1]['title'])<1,panels
                            page.get_by_text('连接管理',exact=True).click();settled(page)
                            page.get_by_role('combobox',name='开发工具',exact=True).focus();page.keyboard.press('ArrowDown')
                            option=page.get_by_role('option',name='Codex',exact=True)
                            expect(option).to_be_visible()
                            if theme=='dark':assert option.evaluate('(node)=>getComputedStyle(node).backgroundColor')==expected
                            page.keyboard.press('Escape')
                        page.mouse.move(0,0)
                        settled(page)
                        page.screenshot(path=str(output/f'{name}-{theme}-{width}.png'),full_page=True)
                        review.append(dict(page=name,theme=theme,width=width))
            page.set_viewport_size({'width':1512,'height':980})
            page.goto(server.origin+'/#/application?view=business&project_id='+scenario.project_id)
            field=page.get_by_role('textbox',name='业务角色名称').first
            expect(field).to_be_visible();field.fill('owner-review')
            page.route('**/candidate-decisions',lambda route:route.fulfill(status=503,content_type='application/json',body=json.dumps({'error':{'message':'布局复核：保存暂未完成'}})))
            page.get_by_role('button',name='保存业务确认',exact=True).click()
            alert=page.get_by_role('alert');expect(alert).to_be_visible()
            expect(field).to_have_value('owner-review')
            assert alert.bounding_box()['y']+alert.bounding_box()['height']<page.locator('.jj-understanding-groups').bounding_box()['y']
            page.screenshot(path=str(output/'business-error.png'),full_page=True)
            page.get_by_role('tab',name='环境',exact=True).click();expect(alert).to_have_count(0)
            # 在已知读取边界注入失败，验证此前正常截图无法覆盖的反馈布局。
            page.route('**/api/projects/'+scenario.project_id+'/check-routines',lambda route:route.fulfill(status=503,content_type='application/json',body='{}'))
            page.route('**/api/projects/'+scenario.project_id+'/check-history?*',lambda route:route.fulfill(status=503,content_type='application/json',body='{}'))
            page.route('**/api/mcp/access',lambda route:route.fulfill(status=503,content_type='application/json',body='{}'))
            feedback=[]
            for theme in ('light','dark'):
                if page.locator('html').get_attribute('data-studio-theme')!=theme:page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                for width in (1512,375):
                    page.set_viewport_size({'width':width,'height':980})
                    for name,path,selector in [('history','/reports','.jj-history-workspace > .jj-notice'),('saved','/reports?view=plan','.jj-saved-checks > .jj-notice'),('access','/settings?section=tools','.jj-tools-access > .jj-notice')]:
                        page.goto(server.origin+'/?failure_review='+uuid4().hex+'#'+path+('&' if '?' in path else '?')+'project_id='+scenario.project_id)
                        if name=='saved':page.get_by_text('保存与沿用检查范围',exact=True).click()
                        message=page.locator(selector);expect(message).to_be_visible();settled(page)
                        # 失败时目录可能只有通知；此时核对容器内边距，而非不存在的上一行。
                        measured=message.evaluate('(node)=>{const r=node.getBoundingClientRect(),p=node.previousElementSibling?.getBoundingClientRect(),parent=node.parentElement.getBoundingClientRect();return {gap:r.top-(p?.bottom??parent.top),left:r.left-parent.left,right:parent.right-r.right}}')
                        assert measured['gap']>=16,dict(page=name,**measured)
                        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                        page.mouse.move(0,0);page.screenshot(path=str(output/f'{name}-failure-{theme}-{width}.png'),full_page=True)
                        feedback.append(dict(page=name,theme=theme,width=width,**measured))
                    page.goto(server.origin+'/?proof_review='+uuid4().hex+'#/preparation?proof_sources=1&project_id='+scenario.project_id)
                    expect(page.locator('main h1')).to_have_count(1)
                    expect(page.locator('[data-page-pending=true]')).to_have_count(0);settled(page)
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    page.screenshot(path=str(output/f'proof-{theme}-{width}.png'),full_page=True)
            (output/'feedback.json').write_text(json.dumps(feedback,ensure_ascii=False,indent=2),encoding='utf-8')
            page.set_viewport_size({'width':1512,'height':980})
            page.goto(server.origin+'/#/application?view=create&project_id='+scenario.project_id)
            page.get_by_label('应用名称',exact=True).fill('空来源布局核对')
            page.get_by_role('button',name='建立工作区',exact=True).click()
            page.get_by_role('tab',name='接口来源',exact=True).click()
            expect(page.get_by_role('heading',name='从已有资料继续调查',exact=True)).to_be_visible();settled(page)
            geometry=page.locator('.jj-source-library .jj-empty p').evaluate('(node)=>({height:node.getBoundingClientRect().height,line:parseFloat(getComputedStyle(node).lineHeight)})')
            assert geometry['height']<=geometry['line']+1,geometry
            page.mouse.move(0,0);page.screenshot(path=str(output/'sources-empty.png'),full_page=True)
            (output/'layouts.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception:
            page.screenshot(path=str(output/'failure.png'),full_page=True)
            raise
        finally:
            (output/'motion.json').write_text(json.dumps(motions,ensure_ascii=False,indent=2),encoding='utf-8')
            browser.close()


def test_application_menu_selection_in_browser(readonly_official_review):
    """验证组件库菜单的当前项与悬停叠加色，覆盖桌面及移动导航。"""
    from playwright.sync_api import sync_playwright,expect
    from tests.support.runtime_server import launch
    from tests.support.official import OfficialScenario
    from tests.support.browser_review import settled
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text(encoding='utf-8'))
    output=root/'var/audit/ui-selection-review'/uuid4().hex
    observations=[]
    server,scenario,receipt=readonly_official_review
    output.mkdir(parents=True,exist_ok=False)
    with sync_playwright() as engine:
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980},device_scale_factor=1)
            page.goto(server.origin+'/#/workspace?project_id='+scenario.project_id)
            expect(page.locator('main h1')).to_be_visible()
            for theme in ('light','dark'):
                if page.locator('html').get_attribute('data-studio-theme')!=theme:page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                for width in (1512,800,375,320):
                    page.set_viewport_size({'width':width,'height':980})
                    if width<=800:page.get_by_role('button',name='打开导航',exact=True).click()
                    if theme=='light' and width==1512:
                        page.evaluate('''()=>{window.menuMotions=[];document.addEventListener('transitionrun',event=>{if(event.target.classList.contains('jj-menu-surface'))window.menuMotions.push(event.propertyName)})}''')
                    page.locator('.jj-application-switcher').click()
                    if theme=='light' and width==1512:
                        page.wait_for_function('window.menuMotions.includes("transform")')
                    selected=page.locator('.jj-application-menu .ant-dropdown-menu-item-selected')
                    expect(selected).to_be_visible()
                    page.get_by_role('menuitem',name='新建应用工作区',exact=True).hover();settled(page)
                    # 未生成的伪元素也能返回 opacity=1；只采样实际绘制的悬停层。
                    colors=selected.evaluate('node=>{const base=getComputedStyle(node),over=getComputedStyle(node,"::before"),n=document.createElement("span");n.style.backgroundColor=getComputedStyle(document.documentElement).getPropertyValue("--selected");document.body.append(n);const expected=getComputedStyle(n).backgroundColor;n.remove();const r=node.getBoundingClientRect();return {color:over.content!=="none"&&over.content!=="normal"&&Number(over.opacity)>.99?over.backgroundColor:base.backgroundColor,expected,left:r.left,right:r.right}}')
                    assert colors['color']==colors['expected'],colors
                    assert colors['left']>=0 and colors['right']<=width,colors
                    alignment=page.locator('.jj-application-menu [role=menuitem]').evaluate_all('''nodes=>nodes.map(node=>{const icon=node.querySelector('.ant-dropdown-menu-item-icon'),label=node.querySelector('.ant-dropdown-menu-title-content'),tail=node.querySelector('.jj-command-label > .anticon'),center=n=>{const r=n.getBoundingClientRect();return r.top+r.height/2};return {icon:center(icon),label:center(label),tail:tail?center(tail):null,lineHeight:parseFloat(getComputedStyle(label).lineHeight),labelHeight:label.getBoundingClientRect().height}})''')
                    assert all(abs(item['icon']-item['label'])<1 for item in alignment),alignment
                    assert all(item['tail'] is None or abs(item['tail']-item['label'])<1 for item in alignment),alignment
                    # 此处均为单行菜单；不能仅对齐一个比实际文字更高的空链接盒。
                    assert all(abs(item['labelHeight']-item['lineHeight'])<1 for item in alignment),alignment
                    page.screenshot(path=str(output/f'application-menu-{theme}-{width}.png'),full_page=True)
                    observations.append(dict(theme=theme,width=width,alignment=alignment,**colors))
                    page.keyboard.press('Escape')
                    expect(page.get_by_role('menu')).to_have_count(0)
                    if width<=800:page.keyboard.press('Escape');expect(page.get_by_role('dialog')).to_have_count(0)
        except Exception:
            page.screenshot(path=str(output/'failure.png'),full_page=True);raise
        finally:
            (output/'selection.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf-8')
            browser.close()


def test_environment_form_and_navigation_reference_in_browser():
    from playwright.sync_api import sync_playwright,expect
    from tests.support.runtime_server import launch
    from tests.support.official import OfficialScenario
    from tests.support.browser_review import settled
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text(encoding='utf-8'))
    output=root/'var/audit/environment-navigation'/uuid4().hex
    observations=[]
    with launch(output,Path(receipt['frontend']['dist'])) as server,sync_playwright() as engine:
        scenario=OfficialScenario(server.client);scenario.start()
        original=scenario.request('GET',f'/api/projects/{scenario.project_id}/environments')
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980})
            application=server.origin+'/#/application?project_id='+scenario.project_id
            settings=server.origin+'/#/settings?section=tools&project_id='+scenario.project_id
            for theme in ('light','dark'):
                for width in (1512,800,375,320):
                    page.set_viewport_size({'width':width,'height':980})
                    page.goto(application)
                    expect(page.locator('.jj-environment-form')).to_be_visible()
                    if page.locator('html').get_attribute('data-studio-theme')!=theme:
                        page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                    settled(page)
                    form=page.locator('.jj-environment-form')
                    geometry=form.evaluate('node=>{const r=node.getBoundingClientRect(),inputs=[...node.querySelectorAll("input")].map(n=>{const b=n.getBoundingClientRect();return {left:b.left,right:b.right,width:b.width}});return {width:r.width,left:r.left,right:r.right,inputs,overflow:document.documentElement.scrollWidth>innerWidth}}')
                    assert geometry['width']<=880 and not geometry['overflow'],geometry
                    assert geometry['left']>=0 and geometry['right']<=width,geometry
                    assert max(x['left'] for x in geometry['inputs'])-min(x['left'] for x in geometry['inputs'])<1,geometry
                    if width>650:assert geometry['inputs'][0]['width']<=360,geometry
                    tabs=page.get_by_role('tablist',name='应用资料')
                    selected=tabs.get_by_role('tab',name='环境',exact=True)
                    marker=page.locator('.jj-application-tabs .jj-tab-indicator')
                    before=marker.bounding_box()
                    tabs.get_by_role('tab',name='接口来源',exact=True).hover();settled(page)
                    expect(selected).to_have_attribute('aria-selected','true')
                    assert abs(marker.bounding_box()['x']-before['x'])<1
                    states=selected.evaluate('node=>({selected:getComputedStyle(node).backgroundColor,hover:getComputedStyle(node.nextElementSibling,"::before").backgroundColor,hoverOpacity:getComputedStyle(node.nextElementSibling,"::before").opacity,overlay:getComputedStyle(node,"::before").backgroundColor})')
                    assert states['selected']!='rgba(0, 0, 0, 0)' and states['selected']!=states['hover'],states
                    assert float(states['hoverOpacity'])>.99,states
                    page.screenshot(path=str(output/f'environment-hover-{theme}-{width}.png'),full_page=True)
                    observations.append(dict(page='environment',theme=theme,width=width,geometry=geometry,states=states))
                    page.goto(settings)
                    expect(page.locator('.jj-tools-layout')).to_be_visible();settled(page)
                    navigation=page.get_by_role('navigation',name='设置分类')
                    current=navigation.locator('a[aria-current=page]')
                    before=page.locator('.jj-settings-navigation .jj-tab-indicator').bounding_box()
                    navigation.get_by_role('link',name='本地存储',exact=True).hover();settled(page)
                    expect(current).to_have_text('开发工具')
                    assert abs(page.locator('.jj-settings-navigation .jj-tab-indicator').bounding_box()['x']-before['x'])<1
                    assert current.evaluate('node=>getComputedStyle(node).backgroundColor')!='rgba(0, 0, 0, 0)'
                    tones=current.evaluate('node=>{const canvas=document.createElement("canvas"),ctx=canvas.getContext("2d");canvas.width=canvas.height=1;const bg=getComputedStyle(document.documentElement).getPropertyValue("--bg");function pixel(item){ctx.clearRect(0,0,1,1);ctx.fillStyle=bg;ctx.fillRect(0,0,1,1);if(item){ctx.fillStyle=getComputedStyle(item).backgroundColor;ctx.fillRect(0,0,1,1);const over=getComputedStyle(item,"::before");if(Number(over.opacity)>0){ctx.globalAlpha=Number(over.opacity);ctx.fillStyle=over.backgroundColor;ctx.fillRect(0,0,1,1);ctx.globalAlpha=1}}return [...ctx.getImageData(0,0,1,1).data].slice(0,3)}const base=pixel(),difference=item=>Math.hypot(...pixel(item).map((v,i)=>v-base[i]));return {selected:difference(node),hover:difference(node.nextElementSibling)}}')
                    assert 0<tones['hover']<tones['selected'],tones
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    page.screenshot(path=str(output/f'settings-hover-{theme}-{width}.png'),full_page=True)
                    observations.append(dict(page='settings',theme=theme,width=width,tones=tones))
            page.set_viewport_size({'width':1512,'height':980});page.goto(application)
            expect(page.locator('.jj-environment-form')).to_be_visible();settled(page)
            page.get_by_label('环境名称',exact=True).fill('日常验证环境')
            page.get_by_label('应用地址',exact=True).fill('http://127.0.0.1:18081/path')
            page.get_by_role('button',name='保存环境',exact=True).click()
            expect(page.get_by_role('alert')).to_contain_text('不含路径')
            page.mouse.move(0,0);settled(page)
            page.screenshot(path=str(output/'environment-error-dark.png'),full_page=True)
            page.get_by_role('tab',name='接口来源',exact=True).click()
            expect(page.get_by_role('tab',name='接口来源',exact=True)).to_have_attribute('aria-selected','true')
            page.get_by_role('tab',name='接口来源',exact=True).press('Home')
            expect(page.get_by_label('应用地址',exact=True)).to_have_value('http://127.0.0.1:18081/path')
            # 采样真实标记位置，避免把两张静态选中截图当成连续运动。
            page.evaluate('window.tabFrames=[];window.tabDone=false;const start=performance.now();function frame(){window.tabFrames.push(getComputedStyle(document.querySelector(".jj-tab-indicator")).transform);if(performance.now()-start<450)requestAnimationFrame(frame);else window.tabDone=true}requestAnimationFrame(frame)')
            page.get_by_role('tab',name='接口来源',exact=True).click()
            page.wait_for_function('window.tabDone')
            frames=page.evaluate('window.tabFrames');assert len(set(frames))>2,frames
            page.get_by_role('tab',name='接口来源',exact=True).press('Home')
            page.get_by_label('应用地址',exact=True).fill('http://127.0.0.1:18081')
            page.get_by_role('button',name='保存环境',exact=True).click()
            expect(page.get_by_label('已保存的环境')).to_be_visible()
            context=scenario.request('GET',f'/api/projects/{scenario.project_id}/environments')
            assert context['active_environment'] is None
            assert context['confirmed_endpoint']==original['confirmed_endpoint']
            page.get_by_role('button',name='编辑',exact=True).click()
            expect(page.get_by_label('已保存的环境')).to_have_count(0)
            expect(page.get_by_label('环境名称',exact=True)).to_have_value('日常验证环境')
            settled(page);page.screenshot(path=str(output/'environment-edit-dark.png'),full_page=True)
            page.get_by_role('button',name='取消编辑',exact=True).click()
            expect(page.get_by_label('已保存的环境')).to_be_visible()
            page.emulate_media(reduced_motion='reduce')
            page.get_by_role('tab',name='环境',exact=True).press('ArrowRight');settled(page)
            assert page.locator('.jj-tab-indicator').evaluate('node=>getComputedStyle(node).transitionDuration')=='0s'
            (output/'motion.json').write_text(json.dumps(dict(frames=frames,reduced=True),ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception:
            page.screenshot(path=str(output/'failure.png'),full_page=True);raise
        finally:
            (output/'layouts.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf-8')
            browser.close()


def test_shared_tabs_keep_the_same_presentation_across_workspaces(readonly_collaboration_review):
    """跨页比较真实计算样式，防止公共控件仍依赖某个页面的附加类。"""
    from playwright.sync_api import sync_playwright,expect
    from tests.support.browser_review import navigate,settled
    from tests.support.builders.checks import assurance
    root=Path(__file__).resolve().parents[3]
    server,project,action,task,receipt=readonly_collaboration_review
    output=root/'var/audit/shared-tabs'/uuid4().hex
    output.mkdir(parents=True)
    samples=[];errors=[];writes=[]
    # 只比较组件自己的呈现；各工作面外围位置和内容不要求相同。
    signature="""root=>{const item=root.querySelector('[aria-selected=true],[aria-current=page]'),style=getComputedStyle(item),box=item.getBoundingClientRect(),marker=root.querySelector('.jj-tab-indicator').getBoundingClientRect();return {display:getComputedStyle(root).display,gap:getComputedStyle(root).columnGap,padding:style.padding,font:style.fontSize,lineHeight:style.lineHeight,radius:style.borderRadius,fill:style.backgroundColor,color:style.color,weight:style.fontWeight,height:box.height,boundary:getComputedStyle(root).borderBottomWidth,markerError:Math.max(Math.abs(box.x-marker.x),Math.abs(box.bottom-marker.bottom),Math.abs(box.width-marker.width))}}"""
    with sync_playwright() as engine:
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980},device_scale_factor=1)
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:writes.append(request.url) if request.method not in ('GET','HEAD','OPTIONS') else None)
            def visit(path):navigate(page,server.origin,path+('&' if '?' in path else '?')+'project_id='+project)
            paths=[('collaboration','/workspace?view=collaboration&task_id='+task,'tablist','协作内容'),('application','/application','tablist','应用资料'),('settings','/settings?section=tools','navigation','设置分类'),('tasks','/workspace?view=collaboration','tablist','协作任务范围'),('rule','/permissions?rule_id='+assurance.permission().intent_id,'tablist','规则详情')]
            for theme in ('dark','light'):
                visit(paths[0][1])
                if page.locator('html').get_attribute('data-studio-theme')!=theme:
                    page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                comparable=[];hover_samples=[]
                for name,path,role,label in paths:
                    visit(path)
                    tabs=page.get_by_role(role,name=label,exact=True)
                    expect(tabs).to_be_visible();settled(page)
                    sample=tabs.evaluate(signature)
                    assert sample['markerError']<1,(name,sample)
                    assert sample['display']=='flex' and sample['boundary']=='1px',(name,sample)
                    comparable.append({key:value for key,value in sample.items() if key!='markerError'})
                    samples.append(dict(theme=theme,name=name,values=sample))
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    tabs.locator('button,a').nth(1).hover();settled(page)
                    hovered=tabs.locator('button,a').nth(1).evaluate("node=>({color:getComputedStyle(node).color,fill:getComputedStyle(node,'::before').backgroundColor,opacity:getComputedStyle(node,'::before').opacity})")
                    assert hovered['opacity']=='1' and tabs.evaluate(signature)==sample,(name,hovered)
                    hover_samples.append(hovered)
                    samples[-1]['hover']=hovered
                    if name=='collaboration' and theme=='dark':
                        page.mouse.move(1500,965);settled(page)
                        page.screenshot(path=str(output/'collaboration-tabs-dark.png'),full_page=True)
                assert all(value==comparable[0] for value in comparable[1:]),samples
                assert all(value==hover_samples[0] for value in hover_samples[1:]),samples
            # 正常密度的新调用不需要专属样式；局部输入明确选择紧凑密度。
            visit('/testing?action_id='+action.action_id)
            origins=page.get_by_role('tablist',name='流程的来源',exact=True)
            expect(origins).to_be_visible();settled(page)
            origin_signature=origins.evaluate(signature)
            assert origin_signature['padding']==comparable[0]['padding'] and origin_signature['height']==comparable[0]['height']
            page.get_by_role('tab',name='手动填写接口',exact=True).click()
            page.get_by_role('button',name='开始填写',exact=True).click()
            page.get_by_label('用于测试的数据编号',exact=True).fill('document-1')
            page.get_by_role('button',name='下一步：设置执行步骤',exact=True).click()
            inputs=page.get_by_role('tablist',name='输入位置',exact=True)
            expect(inputs).to_be_visible();settled(page)
            compact=inputs.evaluate(signature)
            assert compact['boundary']=='0px' and compact['font']=='14px' and compact['height']>=36,compact
            assert inputs.locator('..').evaluate('node=>getComputedStyle(node).borderBottomWidth')=='1px'
            samples.append(dict(name='request-inputs',values=compact))
            visit(paths[0][1])
            tabs=page.get_by_role('tablist',name='协作内容',exact=True)
            first=tabs.get_by_role('tab',name='当前工作',exact=True)
            first.focus();page.keyboard.press('ArrowRight')
            expect(tabs.get_by_role('tab',name='产物与上下文',exact=True)).to_be_focused()
            expect(tabs.get_by_role('tab',name='产物与上下文',exact=True)).to_have_attribute('aria-selected','true')
            page.keyboard.press('End')
            expect(tabs.get_by_role('tab',name='处理记录',exact=True)).to_be_focused()
            for width in (820,375):
                page.set_viewport_size({'width':width,'height':900});settled(page)
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                final=tabs.get_by_role('tab',name='处理记录',exact=True)
                final.scroll_into_view_if_needed();final.click();settled(page)
                assert final.bounding_box()['width']>60
            page.emulate_media(reduced_motion='reduce')
            page.keyboard.press('Home');settled(page)
            assert tabs.locator('.jj-tab-indicator').evaluate('node=>getComputedStyle(node).transitionDuration')=='0s'
            assert not writes and not errors,(writes,errors)
        finally:browser.close()
    (output/'result.json').write_text(json.dumps(dict(samples=samples,errors=errors,writes=writes,model_calls=0),ensure_ascii=False,indent=2),encoding='utf-8')
    print('shared_tabs_review='+str(output))


def test_semantic_colors_keep_selection_and_task_state_separate(readonly_collaboration_review):
    """真实导航和菜单验证状态归属，组合样本核对语义文字及选中底上的对比度。"""
    import re
    from playwright.sync_api import sync_playwright,expect
    from tests.support.browser_review import navigate,settled
    root=Path(__file__).resolve().parents[3]
    server,project,action,task,receipt=readonly_collaboration_review
    output=root/'var/maintenance/color-system-20261107/semantic-colors'/uuid4().hex
    output.mkdir(parents=True)
    records=[];errors=[];writes=[]
    def contrast(foreground,background):
        def luminance(color):
            if color.startswith('color(srgb '):
                components=[float(value) for value in color.removeprefix('color(srgb ').rstrip(')').split()[:3]]
            else:
                components=[int(value)/255 for value in re.findall(r'\d+',color)[:3]]
            assert len(components)==3,color
            return sum(weight*(value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4) for value,weight in zip(components,(.2126,.7152,.0722)))
        low,high=sorted((luminance(foreground),luminance(background)))
        return (high+.05)/(low+.05)
    pair="node=>({foreground:getComputedStyle(node).color,background:getComputedStyle(node).backgroundColor})"
    with sync_playwright() as engine:
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980},device_scale_factor=1)
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda request:writes.append(request.url) if request.method not in ('GET','HEAD','OPTIONS') else None)
            def visit(path):navigate(page,server.origin,path+('&' if '?' in path else '?')+'project_id='+project)
            def record(name,value,theme):
                ratio=contrast(value['foreground'],value['background'])
                assert ratio>=4.5,(name,theme,value,ratio)
                records.append(dict(name=name,theme=theme,ratio=round(ratio,3),**value))
            for theme in ('dark','light'):
                visit('/workspace?view=collaboration&task_id='+task)
                if page.locator('html').get_attribute('data-studio-theme')!=theme:
                    page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                settled(page)
                entry=page.locator('.jj-collaboration-entry')
                expect(entry).to_have_attribute('aria-current','page')
                expect(entry.locator('.jj-collaboration-entry-status')).to_have_text('待你确认',timeout=7000)
                value=entry.evaluate("node=>({foreground:getComputedStyle(node.querySelector('.jj-collaboration-entry-status')).color,background:getComputedStyle(node).backgroundColor,entry:getComputedStyle(node).color})")
                assert value['foreground']==value.pop('entry'),value
                record('selected-sidebar',value,theme)
                entry.hover();settled(page)
                hovered=entry.evaluate("node=>({foreground:getComputedStyle(node.querySelector('.jj-collaboration-entry-status')).color,background:getComputedStyle(node,'::before').backgroundColor})")
                assert hovered['background']!=value['background'],hovered
                record('selected-sidebar-hover',hovered,theme)
                page.locator('.jj-application-switcher').click()
                selected=page.locator('.jj-application-menu .ant-dropdown-menu-item-selected')
                expect(selected).to_be_visible();selected.hover();settled(page)
                selected_pair=selected.evaluate(pair)
                assert selected_pair['background']==value['background'],selected_pair
                record('selected-menu-hover',selected_pair,theme)
                record('selected-menu-hover-overlay',selected.evaluate("node=>({foreground:getComputedStyle(node).color,background:getComputedStyle(node,'::before').backgroundColor})"),theme)
                page.keyboard.press('Escape')
                expect(page.locator('.jj-collaboration-state')).to_have_attribute('data-tone','accent')
                page.get_by_role('button',name='任务操作',exact=True).click()
                danger=page.get_by_role('menuitem',name='停止任务',exact=True)
                expect(danger).to_be_visible();danger.hover();settled(page)
                record('danger-menu-hover',danger.evaluate(pair),theme)
                menu=page.locator('.jj-command-menu .ant-dropdown-menu')
                elevated=menu.evaluate("node=>{const sample=document.createElement('div');sample.style.backgroundColor='var(--surface-elevated)';document.body.append(sample);const color=getComputedStyle(sample).backgroundColor;sample.remove();return color}")
                assert menu.evaluate('node=>getComputedStyle(node).backgroundColor')==elevated
                records.append(dict(name='actual-menu-elevation',theme=theme,background=elevated))
                page.keyboard.press('Escape')
                visit('/workspace?view=collaboration')
                badge=page.locator('.jj-collaboration-task-list .jj-badge')
                expect(badge).to_have_class('jj-badge is-accent')
                record('waiting-task-badge',badge.evaluate(pair),theme)
                visit('/preparation')
                # CSS 组合样本不伪装成业务数据；共用控件的真实语义由组件测试及上述入口核对。
                page.evaluate("""()=>{const host=document.createElement('section');host.id='semantic-color-fixture';for(const tone of ['neutral','accent','positive','caution','negative']){for(const kind of ['badge','notice']){const item=document.createElement('div');item.className='jj-'+kind+' is-'+tone;item.dataset.sample=kind+'-'+tone;item.textContent=tone;host.append(item)}}const selected=document.createElement('div');selected.className='jj-index-selection';selected.innerHTML='<button class="jj-index-item" aria-current="page"><span class="jj-account-index-status" data-tone="positive" data-sample="selected-ready">已准备</span><span class="jj-material-select-status" data-tone="caution" data-sample="selected-missing">待准备</span></button>';host.append(selected);document.querySelector('main').append(host)}""")
                page.locator('#semantic-color-fixture').evaluate("""host=>host.insertAdjacentHTML('beforeend','<button class="jj-button is-primary" data-sample="primary-action">继续</button><button class="jj-button is-danger" data-sample="danger-action">移除</button><input data-sample="input-text" value="当前名称"><div class="jj-panel jj-muted" data-sample="surface-secondary">补充说明</div><button class="jj-button is-primary" disabled data-disabled-sample="button">暂不可用</button><input disabled value="暂不可编辑" data-disabled-sample="input">')""")
                settled(page)
                for item in page.locator('#semantic-color-fixture [data-sample]').all():
                    value=item.evaluate(pair)
                    if item.get_attribute('data-sample').startswith('selected-'):
                        value['background']=item.evaluate("node=>{const sample=document.createElement('div');sample.style.backgroundColor=getComputedStyle(node).getPropertyValue('--selected');document.body.append(sample);const color=getComputedStyle(sample).backgroundColor;sample.remove();return color}")
                        selected_color=item.evaluate("node=>getComputedStyle(node.closest('.jj-index-item')).color")
                        assert value['foreground']==selected_color,value
                    record(item.get_attribute('data-sample'),value,theme)
                danger_action=page.locator('#semantic-color-fixture [data-sample="danger-action"]')
                danger_action.hover();settled(page)
                record('danger-action-hover',danger_action.evaluate("node=>({foreground:getComputedStyle(node).color,background:getComputedStyle(node,'::before').backgroundColor})"),theme)
                for item in page.locator('#semantic-color-fixture [data-disabled-sample]').all():
                    value=item.evaluate("node=>{const css=getComputedStyle(node);return {foreground:css.color,background:css.backgroundColor,opacity:css.opacity}}")
                    assert value['opacity']=='1',value
                    record('disabled-'+item.get_attribute('data-disabled-sample'),value,theme)
                page.locator('#semantic-color-fixture').evaluate('node=>node.remove()')
            assert not writes and not errors,(writes,errors)
        finally:browser.close()
    (output/'result.json').write_text(json.dumps(dict(records=records,errors=errors,writes=writes,model_calls=0),ensure_ascii=False,indent=2),encoding='utf-8')
    print('semantic_color_review='+str(output))



def test_collection_hit_areas_feedback_and_review_reading_stay_consistent():
    """真实示例核对整行选择、入口留白、稳定框架及概览与详情的切换。"""
    from playwright.sync_api import sync_playwright,expect
    from tests.support.runtime_server import launch
    from tests.support.official import OfficialScenario
    from tests.support.browser_review import navigate,settled
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text('utf-8'))
    output=root/'var/maintenance/color-system-20261107/browser'/uuid4().hex
    metrics=[];errors=[]
    with launch(output/'runtime',Path(receipt['frontend']['dist'])) as server,sync_playwright() as engine:
        scenario=OfficialScenario(server.client);scenario.start()
        proposal=next(item['path'].split('/')[-2] for item in scenario.operations if item['path'].endswith('/approve'))
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980})
            page.on('pageerror',lambda error:errors.append(str(error)))
            for theme in ('light','dark'):
                navigate(page,server.origin,'/testing?project_id='+scenario.project_id)
                if page.locator('html').get_attribute('data-studio-theme')!=theme:
                    page.get_by_role('button',name='切换雾蓝深色' if theme=='dark' else '切换浅色',exact=True).click()
                for width in (1512,800,375):
                    page.set_viewport_size({'width':width,'height':980})
                    for path in ('/testing','/permissions'):
                        navigate(page,server.origin,path+'?project_id='+scenario.project_id)
                        rows=page.locator('.jj-object-table tbody tr')
                        count=rows.count();assert count>=3
                        # 不等待详情动画结束，快速改向也应立即接受当前选择。
                        for ordinal in (1,2,0,2,1,0):
                            row=rows.nth(ordinal);cell=row.locator('td:visible').last
                            cell.scroll_into_view_if_needed();box=cell.bounding_box();assert box
                            page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
                            expect(row.locator('.jj-object-select')).to_have_attribute('aria-pressed','true')
                        button=rows.nth(1).locator('.jj-object-select')
                        button.focus();page.keyboard.press('Enter')
                        expect(button).to_have_attribute('aria-pressed','true')
                        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                        metrics.append(dict(theme=theme,width=width,path=path,changes=7))
                    if theme=='light' and width==1512:
                        navigate(page,server.origin,'/testing?project_id='+scenario.project_id)
                        page.locator('.jj-object-select').first.click()
                        # 固定背景按实际视口审阅，避免整页截图把视口外区域拼成背景断层。
                        page.mouse.move(1500,970);settled(page);page.screenshot(path=str(output/'testing-light.png'),full_page=False)
                page.set_viewport_size({'width':1512,'height':980})
                navigate(page,server.origin,'/workspace?project_id='+scenario.project_id)
                for link in page.locator('.jj-home-text-link').all():
                    if not link.is_visible():continue
                    link.hover()
                    assert 'underline' in link.evaluate('node=>getComputedStyle(node).textDecorationLine')
                    metrics.append(dict(theme=theme,feedback=link.inner_text()))
                for width in (1512,800,375):
                    page.set_viewport_size({'width':width,'height':980})
                    for metric in page.locator('.jj-home-object-link').all():
                        metric.hover()
                        assert 'underline' in metric.locator('strong').evaluate('node=>getComputedStyle(node).textDecorationLine')
                        inset=metric.evaluate("node=>{const box=node.getBoundingClientRect(),children=[...node.children].map(child=>child.getBoundingClientRect());return {top:Math.min(...children.map(child=>child.top))-box.top,bottom:box.bottom-Math.max(...children.map(child=>child.bottom)),left:Math.min(...children.map(child=>child.left))-box.left,right:box.right-Math.max(...children.map(child=>child.right))}}")
                        assert min(inset.values())>=11,inset
                        metrics.append(dict(theme=theme,width=width,metric=metric.inner_text(),inset=inset))
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                for width in (1512,800,375):
                    page.set_viewport_size({'width':width,'height':980})
                    navigate(page,server.origin,'/permissions?project_id='+scenario.project_id+'&proposal_id='+proposal)
                    workspace=page.get_by_role('region',name='访问规则概览',exact=True)
                    choices=workspace.locator('.jj-object-select')
                    expect(choices).to_have_count(5)
                    detail=workspace.locator('.jj-inspector')
                    expect(detail).to_have_count(0)
                    if theme=='dark' and width==1512:
                        page.mouse.move(1500,970);settled(page)
                        page.screenshot(path=str(output/'review-overview-dark.png'),full_page=False)
                    for ordinal in range(5):
                        choice=choices.nth(ordinal);choice.click()
                        expect(choice).to_have_attribute('aria-pressed','true')
                        expect(detail.locator('.jj-rule-meaning')).to_have_count(1)
                        definition=detail.locator('.jj-rule-definition').bounding_box()
                        effects=detail.locator('.jj-rule-effects').bounding_box()
                        assert definition and effects and 16<=effects['y']-definition['y']-definition['height']<=24
                        if width<=800:
                            expect(workspace.locator('.jj-collection-main')).to_be_hidden()
                            expect(detail.get_by_role('button',name='收起详情',exact=True)).to_be_focused()
                        else:
                            expect(workspace.locator('.jj-proposal-summary-column').first).to_be_hidden()
                        detail.get_by_role('button',name='收起详情',exact=True).click()
                        expect(detail).to_have_count(0);expect(choice).to_be_focused()
                    choices.nth(1).click()
                    selected=detail.locator('.jj-rule-title h3').inner_text()
                    page.get_by_role('tab',name='提案来源',exact=True).click()
                    expect(page.get_by_role('heading',name='提案来源',exact=True)).to_be_visible()
                    page.get_by_role('tab',name='业务定义 5',exact=True).click()
                    expect(page.get_by_role('heading',name='提案来源',exact=True)).to_have_count(0)
                    page.get_by_role('tab',name='访问规则 5',exact=True).click()
                    expect(detail.locator('.jj-rule-meaning')).to_have_count(1)
                    expect(detail.locator('.jj-rule-title h3')).to_have_text(selected)
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                    if theme=='dark' and width==1512:
                        page.mouse.move(1500,970);settled(page)
                        page.screenshot(path=str(output/'review-detail-dark.png'),full_page=False)
                    detail.get_by_role('button',name='收起详情',exact=True).click()
                # 固定栏必须遮挡滚动内容；共用视口坐标可避免各自铺色产生接缝。
                page.set_viewport_size({'width':1512,'height':500})
                page.evaluate('window.scrollTo(0,120)')
                expect(page.locator('.jj-topbar button').last).to_be_in_viewport()
                page.screenshot(path=str(output/'review-scrolled-dark.png'),full_page=False)
                assert page.locator('.jj-topbar').evaluate("node=>getComputedStyle(node).borderBottomWidth")=='0px'
                page.evaluate('window.scrollTo(0,0)')
                page.set_viewport_size({'width':1512,'height':980})
                navigate(page,server.origin,'/reports?project_id='+scenario.project_id)
                expect(page.get_by_role('button',name='发起检查',exact=True)).to_be_visible()
                expect(page.locator('.jj-history-toolbar')).to_have_count(0)
                canvas=page.locator('.jj-content').evaluate("node=>{const style=getComputedStyle(node);return {left:parseFloat(style.marginLeft),radius:parseFloat(style.borderTopLeftRadius),gradient:style.backgroundImage}}")
                assert canvas['left']==0 and canvas['radius']==0 and canvas['gradient']=='none',canvas
                assert page.locator('.jj-main').evaluate("node=>getComputedStyle(node).backgroundImage")=='none'
                layers=page.locator('.jj-app,.jj-sidebar,.jj-topbar').evaluate_all("nodes=>nodes.map(node=>{const css=getComputedStyle(node);return {gradient:css.backgroundImage,attachment:css.backgroundAttachment,size:css.backgroundSize}})")
                assert len(layers)==3 and all(layer==layers[0] for layer in layers),layers
                assert 'linear-gradient' in layers[0]['gradient'] and layers[0]['attachment']=='fixed',layers
                separator=page.locator('.jj-sidebar').evaluate("node=>{const css=getComputedStyle(node,'::after');return {top:parseFloat(css.top),bottom:parseFloat(css.bottom)}}")
                assert separator['top']>0 and separator['bottom']>0,separator
                canvas['layers']=layers
                metrics.append(dict(theme=theme,canvas=canvas))
                page.goto(server.origin+'/#/reports?project_id='+scenario.project_id+'&query=no-such-report')
                # 同文档 hash 导航保留本地筛选；冷入口独立验证 URL 的初始查询。
                page.reload()
                expect(page.get_by_role('heading',name='检查记录',exact=True)).to_be_visible()
                expect(page.get_by_label('查找检查记录',exact=True)).to_be_visible()
                expect(page.get_by_role('button',name='清除筛选',exact=True)).to_be_visible()
                assert page.locator('.jj-history-toolbar').evaluate("node=>getComputedStyle(node).borderBottomWidth")=='0px'
                # 筛选是用户状态，跨页面返回应保留；显式清除后再检验下一主题的初始空态。
                page.get_by_role('button',name='清除筛选',exact=True).click()
                expect(page.locator('.jj-history-toolbar')).to_have_count(0)
            # 使用真实检查形成历史入口，避免仅凭空列表推断行内留白。
            scenario.check('BASELINE')
            navigate(page,server.origin,'/workspace?project_id='+scenario.project_id)
            for button in page.locator('.jj-home-check-row').all():
                inset=button.evaluate("node=>{const s=getComputedStyle(node);return [s.paddingTop,s.paddingRight,s.paddingBottom,s.paddingLeft].map(parseFloat)}")
                assert min(inset)>=8,inset
            page.emulate_media(reduced_motion='reduce')
            navigate(page,server.origin,'/testing?project_id='+scenario.project_id)
            rows=page.locator('.jj-object-table tbody tr');rows.nth(2).locator('button').click()
            expect(rows.nth(2)).to_have_attribute('data-selected','true')
            navigate(page,server.origin,'/permissions?project_id='+scenario.project_id+'&proposal_id='+proposal)
            page.locator('.jj-proposal-workspace .jj-object-select').last.click()
            expect(page.locator('.jj-proposal-workspace .jj-inspector .jj-rule-meaning')).to_have_count(1)
            assert not errors,errors
        finally:
            (output/'result.json').write_text(json.dumps(dict(metrics=metrics,errors=errors),ensure_ascii=False,indent=2),encoding='utf-8')
            browser.close()


def test_focused_settings_business_editor_and_rule_navigation(readonly_official_review):
    """真实页面核对分类编辑、名称状态对齐、连续行选择及检查范围往返。"""
    from playwright.sync_api import sync_playwright, expect
    from tests.support.browser_review import settled
    server, scenario, receipt = readonly_official_review
    output=Path(__file__).resolve().parents[3]/'var/maintenance/workface-review-20261107'
    output.mkdir(parents=True,exist_ok=True)
    review=[]
    with sync_playwright() as engine:
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980})
            for theme in ('dark','light'):
                if theme=='light':
                    page.close();page=browser.new_page(viewport={'width':1512,'height':980})
                page.goto(server.origin+'/#/settings?section=tools&project_id='+scenario.project_id)
                expect(page.get_by_role('heading',name='工具连接',exact=True)).to_be_visible()
                if page.locator('html').get_attribute('data-studio-theme')!=theme:
                    page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                for width in (2100,1512,800,375,320):
                    page.set_viewport_size({'width':width,'height':980});settled(page)
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(theme,width)
                    geometry=page.locator('.jj-tools-layout > section').evaluate_all('(nodes)=>nodes.map(node=>{const r=node.getBoundingClientRect();return {width:r.width,top:r.top,bottom:r.bottom}})')
                    if width>=1512:
                        assert max(item['width'] for item in geometry)<610,geometry
                        assert abs(geometry[0]['bottom']-geometry[1]['bottom'])<1,geometry
                    review.append(dict(view='tools',theme=theme,width=width,panels=geometry))
                    if theme=='dark' and width==1512:page.screenshot(path=str(output/'settings-dark.png'),full_page=True)
                page.set_viewport_size({'width':1512,'height':980})
                page.goto(server.origin+'/#/application?view=business&project_id='+scenario.project_id)
                index=page.get_by_role('navigation',name='业务线索',exact=True)
                expect(index).to_be_visible()
                for width in (2100,1512,800,375,320):
                    page.set_viewport_size({'width':width,'height':980});settled(page)
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(theme,width,'business')
                    editor=page.locator('.jj-understanding-editor')
                    field=editor.get_by_role('textbox')
                    assert field.bounding_box()['width']<=321
                    assert editor.locator('.jj-choice').bounding_box()['width']<=241
                    toolbar=page.locator('.jj-understanding-catalog > header').evaluate("""node=>[...node.children].map(child=>{const r=child.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right}})""")
                    assert toolbar[0]['right']<=toolbar[1]['left'] or toolbar[0]['bottom']<=toolbar[1]['top'],(theme,width,toolbar)
                    title=editor.locator('header .jj-collection-title').evaluate("""node=>[...node.children].map(child=>{const r=child.getBoundingClientRect();return r.top+r.height/2})""")
                    assert abs(title[0]-title[1])<1,(theme,width,title)
                    if width>=1512:
                        fields=editor.locator('.jj-understanding-fields > .jj-field').evaluate_all('nodes=>nodes.map(node=>node.getBoundingClientRect().top)')
                        assert abs(fields[0]-fields[1])<1,fields
                    review.append(dict(view='business',theme=theme,width=width))
                page.set_viewport_size({'width':1512,'height':980})
                page.get_by_role('button',name='添加角色',exact=True).click()
                expect(page.get_by_role('textbox',name='业务角色名称',exact=True)).to_be_focused()
                page.get_by_role('button',name='取消添加',exact=True).click()
                expect(index.locator('.jj-index-item')).to_have_count(2)
                page.mouse.move(0,0);page.evaluate('window.scrollTo(0,0)');settled(page)
                page.screenshot(path=str(output/('business-'+theme+'.png')),full_page=True)
                categories=page.get_by_role('group',name='线索类别',exact=True).get_by_role('button')
                categories.last.click()
                items=index.locator('.jj-index-item')
                assert items.count()>2
                items.last.click()
                name=page.get_by_role('textbox',name='业务操作名称',exact=True)
                original=name.input_value()
                assert name.bounding_box()['width']<=401
                name.fill(original+' · 审阅草稿')
                items.first.click();items.last.click()
                expect(name).to_have_value(original+' · 审阅草稿')
                categories.last.focus();categories.last.press('ArrowLeft')
                expect(page.get_by_role('textbox',name='业务角色名称',exact=True)).to_be_visible()
                categories.first.press('ArrowRight')
                expect(items.last).to_have_attribute('aria-current','true')
                expect(name).to_have_value(original+' · 审阅草稿')
                page.route('**/candidate-decisions',lambda route:route.fulfill(status=503,content_type='application/json',body=json.dumps({'error':{'message':'保存暂未完成'}})))
                page.get_by_role('button',name='保存业务确认',exact=True).click()
                expect(page.get_by_role('alert')).to_be_visible()
                expect(name).to_have_value(original+' · 审阅草稿')
                page.unroute('**/candidate-decisions')
            page.goto(server.origin+'/#/permissions?project_id='+scenario.project_id)
            table=page.locator('.jj-table-selection')
            expect(table).to_be_visible();settled(page)
            rows=table.locator('.jj-object-select')
            rows.first.click();settled(page)
            motion=_record_switch(page,'.jj-table-selection',rows.nth(1))
            assert len({frame['marker'] for frame in motion if frame['marker']!='absent'})>2
            settled(page)
            table_geometry=table.evaluate("""root=>{const a=root.querySelector('tr[data-selected=true]').getBoundingClientRect(),b=root.querySelector('[data-selection-indicator]').getBoundingClientRect();return {delta:Math.max(Math.abs(a.top-b.top),Math.abs(a.height-b.height),Math.abs(a.left-b.left))}}""")
            assert table_geometry['delta']<1,table_geometry
            page.emulate_media(reduced_motion='reduce')
            reduced=_record_switch(page,'.jj-table-selection',rows.first)
            assert all(not frame['animations'] for frame in reduced)
            page.get_by_role('link',name='规则、结果与修改',exact=True).click()
            expect(page.get_by_role('button',name='检查这条规则',exact=True)).to_be_visible()
            bar=page.locator('.jj-rule-section-bar')
            assert bar.evaluate('(node)=>getComputedStyle(node).backgroundImage')==page.locator('.jj-app').evaluate('(node)=>getComputedStyle(node).backgroundImage')
            page.get_by_role('button',name='检查这条规则',exact=True).click()
            expect(page.get_by_role('heading',name='核对本次检查范围',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='选定规则',exact=True)).to_have_attribute('aria-pressed','true')
            expect(page.locator('.jj-scope-rule-option input:checked:not(:disabled)')).to_have_count(1)
            page.get_by_role('button',name='返回权限规则',exact=True).click()
            expect(page.get_by_role('button',name='检查这条规则',exact=True)).to_be_visible()
            (output/'browser-review.json').write_text(json.dumps(dict(layouts=review,motion=motion,reduced=reduced,table_geometry=table_geometry),ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            browser.close()
