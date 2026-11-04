"""使用真实本地示例核对导航选择、局部交接和操作上下文，不调用模型。"""
import json
from pathlib import Path
from uuid import uuid4
import pytest

pytestmark=[pytest.mark.level4,pytest.mark.browser,pytest.mark.process]


def _record_switch(page,root_selector,button):
    page.evaluate("""selector=>{window.localMotion=[];window.localMotionDone=false;const start=performance.now();function frame(){const root=document.querySelector(selector),marker=root?.querySelector('.jj-segment-indicator,.jj-material-indicator');window.localMotion.push({at:performance.now()-start,marker:marker?getComputedStyle(marker).transform:'absent',animations:document.getAnimations().filter(item=>item.effect.getComputedTiming().endTime!==Infinity).map(item=>({name:item.animationName??item.transitionProperty??'content',target:item.effect.target?.className,duration:item.effect.getComputedTiming().duration}))});if(performance.now()-start<500)requestAnimationFrame(frame);else window.localMotionDone=true}requestAnimationFrame(frame)}""",root_selector)
    button.click()
    page.wait_for_function('window.localMotionDone')
    return page.evaluate('window.localMotion')


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
            assert page.locator('.jj-material-indicator').evaluate('(node)=>getComputedStyle(node).backgroundColor')==expected
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
                        measured=message.evaluate('(node)=>{const r=node.getBoundingClientRect(),p=node.previousElementSibling.getBoundingClientRect(),parent=node.parentElement.getBoundingClientRect();return {gap:r.top-p.bottom,left:r.left-parent.left,right:parent.right-r.right}}')
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
                    page.locator('.jj-application-switcher').click()
                    selected=page.locator('.jj-application-menu .ant-dropdown-menu-item-selected')
                    expect(selected).to_be_visible()
                    page.get_by_role('menuitem',name='新建应用工作区',exact=True).hover();settled(page)
                    colors=selected.evaluate('node=>{const base=getComputedStyle(node),over=getComputedStyle(node,"::before"),n=document.createElement("span");n.style.backgroundColor=getComputedStyle(document.documentElement).getPropertyValue("--selected");document.body.append(n);const expected=getComputedStyle(n).backgroundColor;n.remove();const r=node.getBoundingClientRect();return {color:Number(over.opacity)>.99?over.backgroundColor:base.backgroundColor,expected,left:r.left,right:r.right}}')
                    assert colors['color']==colors['expected'],colors
                    assert colors['left']>=0 and colors['right']<=width,colors
                    page.screenshot(path=str(output/f'application-menu-{theme}-{width}.png'),full_page=True)
                    observations.append(dict(theme=theme,width=width,**colors))
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


def test_shared_tabs_keep_the_same_presentation_across_workspaces():
    """跨页比较真实计算样式，防止公共控件仍依赖某个页面的附加类。"""
    from playwright.sync_api import sync_playwright,expect
    from tests.support.runtime_server import launch
    from tests.support.browser_review import navigate,settled
    from tests.support.builders.preparation.action_preparation import build_preparation_harness
    from tests.support.builders.checks import assurance
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text('utf-8'))
    output=root/'var/audit/shared-tabs'/uuid4().hex
    seed=output/'seed';seed.mkdir(parents=True)
    harness=build_preparation_harness(seed)
    project,action,workspace=harness.project_id,harness.action,harness.var_dir
    with harness.core.uow_factory() as work:
        current=work.projects.get(project)
        work.projects.replace(current.model_copy(update={'name':'文档协作系统'}))
        work.commit()
    harness.close()
    samples=[];errors=[];writes=[]
    # 只比较组件自己的呈现；各工作面外围位置和内容不要求相同。
    signature="""root=>{const item=root.querySelector('[aria-selected=true],[aria-current=page]'),style=getComputedStyle(item),box=item.getBoundingClientRect(),marker=root.querySelector('.jj-tab-indicator').getBoundingClientRect();return {display:getComputedStyle(root).display,gap:getComputedStyle(root).columnGap,padding:style.padding,font:style.fontSize,lineHeight:style.lineHeight,radius:style.borderRadius,fill:style.backgroundColor,color:style.color,weight:style.fontWeight,height:box.height,boundary:getComputedStyle(root).borderBottomWidth,markerError:Math.max(Math.abs(box.x-marker.x),Math.abs(box.bottom-marker.bottom),Math.abs(box.width-marker.width))}}"""
    with launch(output/'runtime',Path(receipt['frontend']['dist']),workspace=workspace) as server,sync_playwright() as engine:
        response=server.client.post(f'/api/projects/{project}/collaboration',json=dict(operation_id=uuid4().hex,goal='补齐更新文档的接口流程，整理执行步骤、结果核对与恢复安排。',purpose='SETUP',references={}))
        assert response.status_code==200,response.text
        task=response.json()['data']['task_id']
        response=server.client.post(f'/api/projects/{project}/collaboration/{task}/questions',json=dict(question_id=uuid4().hex,question='文档归档后还允许成员修改吗？',options=['仅负责人可以','所有成员可以']))
        assert response.status_code==200,response.text
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
            assert compact['boundary']=='0px' and compact['font']=='12px' and compact['height']>=44,compact
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


def test_semantic_colors_keep_selection_and_task_state_separate():
    """真实导航和菜单验证状态归属，组合样本核对语义文字及选中底上的对比度。"""
    import re
    from playwright.sync_api import sync_playwright,expect
    from tests.support.runtime_server import launch
    from tests.support.browser_review import navigate,settled
    from tests.support.builders.preparation.action_preparation import build_preparation_harness
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text('utf-8'))
    output=root/'var/audit/semantic-colors'/uuid4().hex
    seed=output/'seed';seed.mkdir(parents=True)
    harness=build_preparation_harness(seed)
    project,workspace=harness.project_id,harness.var_dir
    with harness.core.uow_factory() as work:
        record=work.projects.get(project)
        work.projects.replace(record.model_copy(update={'name':'文档协作系统'}))
        work.commit()
    harness.close()
    records=[];errors=[];writes=[]
    def contrast(foreground,background):
        def luminance(color):
            components=[int(value)/255 for value in re.findall(r'\d+',color)[:3]]
            assert len(components)==3,color
            return sum(weight*(value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4) for value,weight in zip(components,(.2126,.7152,.0722)))
        low,high=sorted((luminance(foreground),luminance(background)))
        return (high+.05)/(low+.05)
    pair="node=>({foreground:getComputedStyle(node).color,background:getComputedStyle(node).backgroundColor})"
    with launch(output/'runtime',Path(receipt['frontend']['dist']),workspace=workspace) as server,sync_playwright() as engine:
        response=server.client.post(f'/api/projects/{project}/collaboration',json=dict(operation_id=uuid4().hex,goal='补齐更新文档的接口流程，核对执行步骤和业务要求。',purpose='SETUP',references={}))
        assert response.status_code==200,response.text
        task=response.json()['data']['task_id']
        response=server.client.post(f'/api/projects/{project}/collaboration/{task}/questions',json=dict(question_id=uuid4().hex,question='文档归档后还允许成员修改吗？',options=['仅负责人可以','所有成员可以']))
        assert response.status_code==200,response.text
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
                expect(page.locator('.jj-collaboration-state')).to_have_attribute('data-tone','accent')
                if theme=='dark':
                    page.mouse.move(1500,965);settled(page)
                    page.screenshot(path=str(output/'collaboration-state-dark.png'),full_page=True)
                page.get_by_role('button',name='任务操作',exact=True).click()
                danger=page.get_by_role('menuitem',name='停止任务',exact=True)
                expect(danger).to_be_visible();danger.hover();settled(page)
                record('danger-menu-hover',danger.evaluate(pair),theme)
                page.keyboard.press('Escape')
                visit('/workspace?view=collaboration')
                badge=page.locator('.jj-collaboration-task-list .jj-badge')
                expect(badge).to_have_class('jj-badge is-accent')
                record('waiting-task-badge',badge.evaluate(pair),theme)
                visit('/preparation')
                # CSS 组合样本不伪装成业务数据；共用控件的真实语义由组件测试及上述入口核对。
                page.evaluate("""()=>{const host=document.createElement('section');host.id='semantic-color-fixture';for(const tone of ['neutral','accent','positive','caution','negative']){for(const kind of ['badge','notice']){const item=document.createElement('div');item.className='jj-'+kind+' is-'+tone;item.dataset.sample=kind+'-'+tone;item.textContent=tone;host.append(item)}}const selected=document.createElement('div');selected.className='jj-index-selection';selected.innerHTML='<button class="jj-index-item" aria-current="page"><span class="jj-account-index-status" data-tone="positive" data-sample="selected-ready">已准备</span><span class="jj-material-select-status" data-tone="caution" data-sample="selected-missing">待准备</span></button>';host.append(selected);document.querySelector('main').append(host)}""")
                settled(page)
                for item in page.locator('#semantic-color-fixture [data-sample]').all():
                    value=item.evaluate(pair)
                    if item.get_attribute('data-sample').startswith('selected-'):
                        value['background']=item.evaluate("node=>{const sample=document.createElement('div');sample.style.backgroundColor=getComputedStyle(node).getPropertyValue('--selected');document.body.append(sample);const color=getComputedStyle(sample).backgroundColor;sample.remove();return color}")
                        selected_color=item.evaluate("node=>getComputedStyle(node.closest('.jj-index-item')).color")
                        assert value['foreground']==selected_color,value
                    record(item.get_attribute('data-sample'),value,theme)
                page.locator('#semantic-color-fixture').evaluate('node=>node.remove()')
            assert not writes and not errors,(writes,errors)
        finally:browser.close()
    (output/'result.json').write_text(json.dumps(dict(records=records,errors=errors,writes=writes,model_calls=0),ensure_ascii=False,indent=2),encoding='utf-8')
    print('semantic_color_review='+str(output))
