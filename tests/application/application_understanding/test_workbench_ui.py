"""构建后真实浏览器验证持续工作入口、来源导入及双主题窄窗；不替代后端整链。"""
import json
from pathlib import Path
from uuid import uuid4
import pytest

pytestmark=[pytest.mark.level4,pytest.mark.browser,pytest.mark.process]


def test_shared_file_picker_in_native_browser():
    """系统选择、拖放和错误替换不自动预览；窄窗沿用同一文件行。"""
    from playwright.sync_api import sync_playwright, expect
    from tests.support.runtime_server import launch
    from tests.support.browser_review import settled
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text(encoding='utf-8'))
    output=root/'var/maintenance/file-controls-startup-20261106/browser'/uuid4().hex
    document=json.dumps({'openapi':'3.0.3','info':{'title':'Orders','version':'1'},'paths':{'/orders':{'get':{'responses':{'200':{'description':'OK'}}}}}}).encode()
    filename='订单与结算接口-用于持续权限核验的测试资料.json'
    previews=[]
    with launch(output,Path(receipt['frontend']['dist'])) as server,sync_playwright() as engine:
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980})
            page.on('request',lambda request:previews.append(request.url) if request.method=='POST' and '/preview' in request.url else None)
            page.goto(server.origin+'/#/application')
            page.get_by_label('应用名称',exact=True).fill('文件导入审阅')
            page.get_by_role('button',name='建立工作区',exact=True).click()
            page.get_by_role('tab',name='接口来源',exact=True).click()
            page.get_by_role('button',name='导入接口资料或请求',exact=True).click()
            dialog=page.get_by_role('dialog',name='导入接口资料',exact=True)
            group=dialog.get_by_role('group',name='JSON 文件',exact=True)
            zone=group.locator('.jj-file-picker')
            with page.expect_file_chooser() as chooser:
                group.get_by_role('button',name='选择JSON 文件',exact=True).click()
            chooser.value.set_files({'name':filename,'mimeType':'application/json','buffer':document})
            expect(group.get_by_text(filename,exact=True)).to_be_visible()
            expect(group.get_by_role('button',name='更换JSON 文件',exact=True)).to_be_enabled()
            assert not previews
            group.locator('input[type=file]').set_input_files({'name':'不支持.txt','mimeType':'text/plain','buffer':b'wrong'})
            expect(group.get_by_role('alert')).to_be_visible()
            expect(group.get_by_text(filename,exact=True)).to_be_visible()
            assert not previews
            # 外部拖放与系统窗口走相同路径，只有明确点击预览才请求解析。
            zone.evaluate('''(node,document)=>{const data=new DataTransfer();data.items.add(new File([document],'orders.json',{type:'application/json'}));node.dispatchEvent(new DragEvent('dragenter',{bubbles:true,dataTransfer:data}));node.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:data}))}''',document.decode())
            expect(group.get_by_text('orders.json',exact=True)).to_be_visible()
            expect(group.get_by_role('alert')).to_have_count(0)
            assert not previews
            for theme,width in [('dark',1512),('light',375)]:
                page.evaluate('(theme)=>{document.documentElement.dataset.studioTheme=theme}',theme)
                page.set_viewport_size({'width':width,'height':980})
                settled(page)
                assert dialog.evaluate('node=>node.scrollWidth<=node.clientWidth+1')
                geometry=zone.evaluate('''node=>{const r=node.getBoundingClientRect(),text=node.querySelector('.jj-file-information').getBoundingClientRect(),actions=node.querySelector('.jj-file-actions').getBoundingClientRect();return {left:text.left-r.left,right:r.right-actions.right,overlap:!(text.bottom<=actions.top||text.right<=actions.left)}}''')
                assert geometry['left']>=16 and geometry['right']>=15 and not geometry['overlap'],geometry
                page.screenshot(path=str(output/f'file-picker-{theme}.png'),full_page=True)
            dialog.get_by_role('button',name='预览并净化',exact=True).click()
            expect(dialog.get_by_role('heading',name='本次变化',exact=True)).to_be_visible()
            assert len(previews)==1
            dialog.get_by_role('button',name='取消',exact=True).click()
            expect(dialog).not_to_be_visible()
            # 菜单取消只关闭当前浮层；移动导航中的第二次 Escape 才关闭导航本身。
            page.set_viewport_size({'width':1512,'height':980})
            switcher=page.locator('.jj-application-switcher')
            switcher.focus();page.keyboard.press('ArrowDown');page.keyboard.press('Escape')
            expect(page.get_by_role('menu')).not_to_be_visible()
            expect(switcher).to_be_focused()
            switcher.focus();page.keyboard.press('ArrowDown')
            expect(page.get_by_role('menu')).to_be_visible()
            expect(page.get_by_role('menuitem',name='文件导入审阅',exact=True)).to_be_focused()
            page.keyboard.press('Escape')
            expect(page.get_by_role('menu')).not_to_be_visible()
            expect(switcher).to_be_focused()
            page.set_viewport_size({'width':375,'height':980})
            page.get_by_role('button',name='打开导航',exact=True).click()
            switcher.focus();page.keyboard.press('ArrowDown')
            expect(page.get_by_role('menu')).to_be_visible()
            page.keyboard.press('Escape')
            expect(page.get_by_role('menu')).not_to_be_visible()
            expect(page.get_by_role('dialog')).to_be_visible()
            expect(switcher).to_be_focused()
            page.keyboard.press('Escape')
            expect(page.get_by_role('dialog')).not_to_be_visible()
            timings=[json.loads(line) for line in (output/'instance/logs/app/jiejian.log').read_text(encoding='utf-8').splitlines()]
            stages={item['stage']:item['elapsed_ms'] for item in timings if item.get('event_code')=='STARTUP_STAGE_COMPLETED'}
            assert {'http_import','application_assembly','worker_start'} <= stages.keys(),stages
            assert all(value>=0 for value in stages.values())
        finally:
            browser.close()


def test_shared_corner_profile_and_fallback_in_browser(readonly_official_review):
    """实际控件与 Portal 同步曲线；禁用增强规则后尺寸和原半径不变。"""
    from playwright.sync_api import sync_playwright, expect
    from tests.support.browser_review import navigate, settled
    server, scenario, receipt = readonly_official_review
    with sync_playwright() as engine:
        browser = engine.chromium.launch(executable_path=receipt['playwright']['executable'], headless=True)
        try:
            page = browser.new_page(viewport={'width': 1512, 'height': 980})
            for theme in ('light', 'dark'):
                navigate(page, server.origin, '/application?view=sources&project_id='+scenario.project_id)
                if page.locator('html').get_attribute('data-studio-theme') != theme:
                    page.get_by_role('button', name='切换雾蓝深色' if theme == 'dark' else '切换浅色', exact=True).click()
                page.get_by_role('button', name='导入接口资料或请求', exact=True).click()
                dialog = page.get_by_role('dialog', name='导入接口资料', exact=True)
                settled(page)
                expect(dialog).to_have_css('border-radius', '20px')
                assert page.evaluate("CSS.supports('corner-shape','superellipse(1.5)')")
                for selector in ('.jj-dialog', '.jj-dialog input', '.jj-dialog .jj-button', '.jj-dialog .ant-select-selector'):
                    assert '1.5' in page.locator(selector).first.evaluate("node=>getComputedStyle(node).getPropertyValue('corner-shape')"), selector
                button = dialog.get_by_role('button', name='取消', exact=True)
                assert button.evaluate("node=>getComputedStyle(node,'::before').getPropertyValue('corner-shape')") == button.evaluate("node=>getComputedStyle(node).getPropertyValue('corner-shape')")
                dialog.locator('.ant-select-selector').first.click()
                menu = page.locator('.jj-choice-menu:visible')
                expect(menu).to_be_visible()
                assert '1.5' in menu.evaluate("node=>getComputedStyle(node).getPropertyValue('corner-shape')")
                page.keyboard.press('Escape')
                if theme == 'dark':
                    before = dialog.bounding_box()
                    # 移除渐进增强，直接检查浏览器仍保有原轮廓与可操作的布局。
                    removed = page.evaluate('''()=>{let count=0;for(const sheet of document.styleSheets){for(let i=sheet.cssRules.length-1;i>=0;i--){const rule=sheet.cssRules[i];if(rule instanceof CSSSupportsRule&&rule.conditionText.includes('corner-shape')){sheet.deleteRule(i);count++}}}return count}''')
                    assert removed > 0
                    expect(dialog).to_have_css('border-radius', '20px')
                    assert dialog.evaluate("node=>getComputedStyle(node).getPropertyValue('corner-shape')") == 'round'
                    assert dialog.bounding_box() == before
                button.click()
                expect(dialog).not_to_be_visible()
        finally:
            browser.close()


def test_shared_selection_keeps_motion_and_reduced_motion_in_browser(readonly_official_review):
    """以浏览器动画的实际插值验证反向接续，覆盖横向页签、分段与纵向索引。"""
    from playwright.sync_api import sync_playwright, expect
    from tests.support.browser_review import navigate, settled
    server, scenario, receipt = readonly_official_review
    action = scenario.request('GET', f'/api/projects/{scenario.project_id}/operation-flows')['actions'][0]
    paths = [('/application', '.jj-tabs'), ('/permissions', '.jj-toggle-group'),
             ('/preparation?action_id='+action['action_id'], '.jj-index-selection')]
    with sync_playwright() as engine:
        browser = engine.chromium.launch(executable_path=receipt['playwright']['executable'], headless=True)
        try:
            page = browser.new_page(viewport={'width': 1512, 'height': 980})
            # 浏览器创建动画时暂停采样，避免自动等待选择状态时短动画已播放完。
            page.add_init_script('''(()=>{const animate=Element.prototype.animate;Element.prototype.animate=function(...args){const animation=animate.apply(this,args);if(window.pauseSelection&&this.hasAttribute('data-selection-indicator')){animation.pause();animation.currentTime=75}return animation}})()''')
            for path, selector in paths:
                page.evaluate('window.pauseSelection=false')
                navigate(page, server.origin, path+('&' if '?' in path else '?')+'project_id='+scenario.project_id)
                control = page.locator(selector).first
                items = control.locator('button:not(:disabled)')
                assert items.count() >= 2, selector
                items.nth(0).click(); settled(page)
                page.evaluate('window.pauseSelection=true')
                items.nth(1).click()
                # 路由页签由 hashchange 提交，点击返回不代表 React 已更新选择；只等实际目标。
                attribute = 'aria-selected' if selector == '.jj-tabs' else 'aria-pressed'
                expect(items.nth(1)).to_have_attribute(attribute, 'true')
                marker = control.locator('[data-selection-indicator]')
                before = marker.evaluate('''(node,selector)=>{const animation=node.getAnimations()[0];if(!animation)throw Error('missing selection animation '+selector+' '+node.outerHTML);animation.pause();animation.currentTime=75;const style=getComputedStyle(node),matrix=new DOMMatrix(style.transform);return {x:matrix.e,y:matrix.f,width:parseFloat(style.width),height:parseFloat(style.height)}}''',selector)
                items.nth(0).click()
                expect(items.nth(0)).to_have_attribute(attribute, 'true')
                after = marker.evaluate('''node=>{const animations=node.getAnimations();if(animations.length!==1)throw Error('stale animation');const frame=animations[0].effect.getKeyframes()[0],matrix=new DOMMatrix(frame.transform);return {x:matrix.e,y:matrix.f,width:parseFloat(frame.width),height:parseFloat(frame.height)}}''')
                assert all(abs(before[key]-after[key]) < .1 for key in before), (selector, before, after)
                page.emulate_media(reduced_motion='reduce')
                page.wait_for_function("[...document.querySelectorAll('[data-selection-indicator]')].every(node=>node.getAnimations().length===0)")
                items.nth(1).focus(); page.keyboard.press('Enter')
                expect(items.nth(1)).to_be_focused()
                assert marker.evaluate('node=>node.getAnimations().length') == 0
                page.emulate_media(reduced_motion='no-preference')
        finally:
            browser.close()


def test_loading_costs_with_isolated_browser_contexts():
    """本机可比采样，不以耗时阈值代替行为验收；可显式提供旧构建对照。"""
    import hashlib
    import os
    import time
    from urllib.parse import urlsplit
    from playwright.sync_api import sync_playwright,expect
    from tests.support.runtime_server import launch
    from tests.support.official import OfficialScenario
    from tests.support.browser_review import settled
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text('utf-8'))
    output=root/'var/audit/loading-costs'/uuid4().hex
    modes=[]
    if os.environ.get('JIEJIAN_REVIEW_BASELINE_DIST'):
        modes.append(('baseline',Path(os.environ['JIEJIAN_REVIEW_BASELINE_DIST'])))
    modes.append(('current',Path(receipt['frontend']['dist'])))
    samples=[]
    for mode,dist in modes:
        started=time.perf_counter()
        with launch(output/mode,dist) as server,sync_playwright() as engine:
            startup_seconds=time.perf_counter()-started
            scenario=OfficialScenario(server.client);scenario.start()
            raw=json.dumps({'openapi':'3.1.0','paths':{f'/orders/{i}':{'get':{'summary':f'读取订单 {i}'}} for i in range(64)}})
            prefix=f'/api/projects/{scenario.project_id}/api-sources'
            preview=scenario.request('POST',prefix+'/preview',dict(raw=raw,kind='OPENAPI'))
            scenario.request('POST',prefix+'/accept',dict(candidate_id=preview['candidate_id'],source_id='src_'+uuid4().hex,name='加载采样',expected_revision=0,expected_fingerprint=preview['fingerprint']))
            action=scenario.request('GET',f'/api/projects/{scenario.project_id}/operation-flows')['actions'][0]
            browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
            try:
                for sample in range(3):
                    context=browser.new_context(viewport={'width':1512,'height':980})
                    page=context.new_page();requests=[];errors=[]
                    page.on('request',lambda request:requests.append(dict(kind=request.resource_type,path=urlsplit(request.url).path)))
                    page.on('pageerror',lambda error:errors.append(type(error).__name__))
                    for stage,path,selector in [
                        ('cold-environment','/application','.jj-environment-form'),
                        ('warm-directory','/testing','.jj-testing-directory'),
                        ('warm-editor','/testing?action_id='+action['action_id'],'.jj-flow-workspace')]:
                        begin=len(requests);clock=time.perf_counter()
                        target=path+('&' if '?' in path else '?')+'project_id='+scenario.project_id
                        if stage=='cold-environment':page.goto(server.origin+'/#'+target)
                        else:page.evaluate('(path)=>{location.hash=path}',target)
                        expect(page.locator(selector)).to_be_visible()
                        expect(page.locator('main .jj-loading')).to_have_count(0)
                        ready_ms=(time.perf_counter()-clock)*1000
                        settled(page)
                        resources=page.evaluate("()=>performance.getEntriesByType('resource').filter(r=>new URL(r.name).pathname.startsWith('/assets/')).map(r=>({path:new URL(r.name).pathname,transferred:r.transferSize,encoded:r.encodedBodySize,decoded:r.decodedBodySize}))")
                        samples.append(dict(mode=mode,sample=sample,stage=stage,ready_ms=round(ready_ms,2),settled_ms=round((time.perf_counter()-clock)*1000,2),requests=requests[begin:],resources=resources if stage=='cold-environment' else [],font=page.locator('html').get_attribute('data-ui-font'),startup_seconds=round(startup_seconds,3),manifest_sha256=hashlib.sha256((dist/'frontend-manifest.json').read_bytes()).hexdigest()))
                    assert errors==[],errors
                    context.close()
            finally:browser.close()
    (output/'samples.json').write_text(json.dumps(dict(schema_version='1',conditions='loopback; three fresh browser contexts per build; same current backend and 64-request fixture; no OS-cache reset',samples=samples),ensure_ascii=False,indent=2),encoding='utf-8')


def test_application_sources_and_continuous_navigation_in_browser():
    from playwright.sync_api import sync_playwright,expect
    from tests.support.runtime_server import launch
    from tests.support.browser_review import settled
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text(encoding='utf-8'))
    output=root/'var/audit/stage-a-ui'/uuid4().hex
    errors=[]
    fonts=[]
    settings_geometry=[]
    navigation_geometry=[]
    label_geometry="""node=>[...node.querySelectorAll('.jj-nav-label')].filter(item=>item.getBoundingClientRect().width>0).map(item=>{const r=item.getBoundingClientRect(),icon=item.closest('.jj-nav-item').querySelector('.anticon').getBoundingClientRect();return {label:item.textContent,center:r.x+r.width/2,iconCenter:icon.x+icon.width/2,spacing:getComputedStyle(item).letterSpacing}})"""
    with launch(output,Path(receipt['frontend']['dist'])) as server,sync_playwright() as engine:
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980},device_scale_factor=1)
            page.on('pageerror',lambda error:errors.append(type(error).__name__))
            page.goto(server.origin+'/#/application')
            expect(page.get_by_role('heading',name='建立应用工作区',exact=True)).to_be_visible()
            fonts.append(_rendered_font(page,'cold-document'))
            assert fonts[-1]['choice']=='misans'
            assert any(font['isCustomFont'] and font['familyName'].startswith('MiSans') for font in fonts[-1]['rendered'])
            page.get_by_label('应用名称',exact=True).fill('订单与结算协作系统')
            page.get_by_role('button',name='建立工作区',exact=True).click()
            expect(page.get_by_role('heading',name='应用与来源',exact=True)).to_be_visible()
            expect(page.locator('main h1')).to_have_count(1)
            expect(page.locator('.jj-environment-form')).to_be_visible()
            expect(page.locator('.jj-environment-catalog')).to_have_count(0)
            settled(page);page.screenshot(path=str(output/'environment-empty-light.png'),full_page=True)
            page.get_by_label('环境名称',exact=True).fill('日常验证环境')
            page.get_by_label('应用地址',exact=True).fill('http://127.0.0.1:18081')
            page.get_by_role('button',name='保存环境',exact=True).click()
            expect(page.get_by_text('日常验证环境',exact=True)).to_be_visible()
            page.get_by_role('button',name='切换到此环境',exact=True).click()
            expect(page.get_by_role('heading',name='日常验证环境',exact=True)).to_be_visible()
            settled(page);page.screenshot(path=str(output/'environment-light.png'),full_page=True)
            page.get_by_role('button',name='编辑',exact=True).click()
            page.get_by_label('应用地址',exact=True).fill('http://127.0.0.1:18081/not-an-origin')
            page.get_by_role('button',name='保存环境',exact=True).click()
            alert=page.get_by_role('alert');expect(alert).to_be_visible()
            expect(page.get_by_label('应用地址',exact=True)).to_have_value('http://127.0.0.1:18081/not-an-origin')
            gap=page.locator('.jj-application-browser').evaluate('(node)=>{const alert=node.querySelector("[role=alert]").getBoundingClientRect(),panel=node.querySelector("[role=tabpanel]").getBoundingClientRect();return panel.top-alert.bottom}')
            assert gap>=16,gap
            settled(page);page.screenshot(path=str(output/'environment-error-light.png'),full_page=True)
            page.get_by_role('tab',name='接口来源',exact=True).click()
            expect(page.get_by_role('button',name='导入资料',exact=True)).to_have_count(0)
            page.get_by_role('button',name='导入接口资料或请求',exact=True).click()
            page.get_by_label('来源名称',exact=True).fill('订单 API')
            document={'openapi':'3.1.0','paths':{'/orders/{id}':{'get':{'summary':'读取订单与客户可见字段'}},
                **{f'/orders/queue-{index}':{'get':{'summary':f'读取订单队列 {index} 的结算与协作权限说明，以及需要单独核对的业务状态'}} for index in range(63)}}}
            page.get_by_label('JSON 文件',exact=True).set_input_files(dict(name='orders.json',mimeType='application/json',buffer=json.dumps(document,ensure_ascii=False).encode()))
            page.get_by_role('button',name='预览并净化',exact=True).click()
            expect(page.get_by_role('heading',name='本次变化',exact=True)).to_be_visible()
            page.get_by_role('button',name='接受本次修订',exact=True).click()
            expect(page.get_by_role('heading',name='读取订单与客户可见字段',exact=True)).to_be_visible()
            assert page.locator('.jj-request-item').count()==64
            assert page.locator('.jj-source-requests').evaluate('element=>element.scrollHeight>element.clientHeight')
            settled(page);page.screenshot(path=str(output/'sources-light.png'),full_page=True)
            page.get_by_role('button',name='切换雾蓝深色',exact=True).click()
            expect(page.locator('html')).to_have_attribute('data-studio-theme','dark')
            settled(page);page.screenshot(path=str(output/'sources-dark.png'),full_page=True)
            page.set_viewport_size({'width':800,'height':960})
            settled(page)
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.screenshot(path=str(output/'sources-narrow-dark.png'),full_page=True)
            page.get_by_role('button',name='查看请求：读取订单与客户可见字段',exact=True).click()
            expect(page.get_by_role('heading',name='读取订单与客户可见字段',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='返回请求列表',exact=True)).to_be_visible()
            page.screenshot(path=str(output/'request-narrow-dark.png'),full_page=True)
            page.get_by_role('button',name='返回请求列表',exact=True).click()
            expect(page.get_by_role('button',name='查看请求：读取订单与客户可见字段',exact=True)).to_be_visible()
            page.set_viewport_size({'width':1512,'height':980})
            navigation=page.get_by_role('navigation',name='应用工作区',exact=True)
            for title in ('权限与覆盖','测试','问题','工作台'):
                navigation.get_by_role('link',name=title,exact=True).click()
                expect(page.get_by_role('heading',level=1)).to_be_visible()
                settled(page)
                if title=='权限与覆盖':
                    buttons=page.locator('.jj-empty-actions > .jj-button').all()
                    assert len(buttons)==2
                    first,second=(button.bounding_box() for button in buttons)
                    assert first['x']+first['width']<=second['x'] or first['y']+first['height']<=second['y']
            # 先加载材料页，再经应用导航回来，检查两类索引的样式不会串用。
            project=page.evaluate('localStorage.getItem("jiejian.studio.project")')
            page.goto(server.origin+'/?font_review='+uuid4().hex+'#/preparation?project_id='+project)
            expect(page.get_by_role('heading',name='先确认要检查的权限',exact=True)).to_be_visible()
            fonts.append(_rendered_font(page,'cached-document'))
            assert fonts[-1]['choice']=='misans'
            assert any(font['isCustomFont'] and font['familyName'].startswith('MiSans') for font in fonts[-1]['rendered'])
            page.get_by_role('navigation',name='应用资料',exact=True).get_by_role('link',name='应用与来源',exact=True).click()
            page.get_by_role('tab',name='接口来源',exact=True).click()
            expect(page.get_by_role('heading',name='读取订单与客户可见字段',exact=True)).to_be_visible()
            for selector in ('.jj-request-purpose-heading','.jj-request-section-heading'):
                alignment=page.locator(selector).evaluate('''node=>[...node.children].map(child=>{
                    const rect=child.getBoundingClientRect();return rect.y+rect.height/2;
                })''')
                assert max(alignment)-min(alignment)<1
            expect(page.locator('.jj-request-index')).to_have_css('display','block')
            page.screenshot(path=str(output/'source-after-preparation-dark.png'),full_page=True)
            navigation.get_by_role('link',name='工作台',exact=True).click()
            expect(page.get_by_role('heading',name='订单与结算协作系统',exact=True)).to_be_visible()
            expect(page.locator('[data-page-pending=true]')).to_have_count(0)
            entry=page.get_by_role('button',name='Agent 协作，开始任务',exact=True)
            expect(entry).to_contain_text('Agent 协作')
            source_link=page.get_by_role('navigation',name='应用资料',exact=True).get_by_role('link',name='应用与来源',exact=True)
            assert entry.bounding_box()['y']>=source_link.bounding_box()['y']+source_link.bounding_box()['height']
            entry.click()
            collaboration=page.get_by_role('dialog',name='与 Agent 协作',exact=True)
            collaboration.get_by_role('button',name='补齐检查准备',exact=True).click()
            expect(collaboration.get_by_label('希望 Agent 完成什么',exact=True)).to_have_value('根据已确认的权限要求，整理测试账号、资源与执行场景，指出需要我提供的材料。')
            for width in (1512,800,375):
                page.set_viewport_size({'width':width,'height':980});settled(page)
                expect(collaboration).to_be_visible()
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                page.screenshot(path=str(output/f'agent-entry-{width}.png'),full_page=True)
            page.set_viewport_size({'width':1512,'height':980})
            page.keyboard.press('Escape')
            expect(collaboration).not_to_be_visible()
            page.set_viewport_size({'width':375,'height':980})
            page.get_by_role('button',name='打开导航',exact=True).click()
            mobile_navigation=page.get_by_role('dialog',name='界鉴导航',exact=True)
            mobile_navigation.get_by_role('button',name='Agent 协作，开始任务',exact=True).click()
            expect(collaboration.get_by_label('希望 Agent 完成什么',exact=True)).to_have_value('根据已确认的权限要求，整理测试账号、资源与执行场景，指出需要我提供的材料。')
            page.keyboard.press('Escape');expect(collaboration).not_to_be_visible()
            expect(mobile_navigation).to_be_visible()
            page.screenshot(path=str(output/'agent-sidebar-mobile.png'),full_page=True)
            page.keyboard.press('Escape');expect(mobile_navigation).not_to_be_visible()
            page.set_viewport_size({'width':1512,'height':980})
            settled(page)
            # 当前动作、对象目录和历史分层；摘要不再复制成三个可点击的统计入口。
            expect(page.locator('.jj-home-metrics > div')).to_have_count(3)
            expect(page.locator('.jj-home-metrics button')).to_have_count(0)
            focus=page.locator('.jj-home-current-task').bounding_box()
            action=page.get_by_role('link',name='设置权限规则',exact=True).bounding_box()
            assert action['x']>focus['x']+focus['width']/2
            assert action['y']>focus['y']+focus['height']/2
            assert focus['x']+focus['width']-action['x']-action['width']>=20
            assert focus['y']+focus['height']-action['y']-action['height']>=20
            expect(page.locator('.jj-heading').get_by_role('button')).to_have_count(0)
            expect(page.get_by_role('link',name='核对应用连接',exact=True)).to_be_visible()
            expect(page.locator('.jj-home-context')).to_contain_text('http://127.0.0.1:18081')
            expect(page.locator('.jj-home-context')).to_contain_text('64 个请求')
            expect(page.locator('.jj-home-task-description')).to_contain_text('后续验证')
            expect(page.get_by_text('当前业务动作',exact=True)).to_have_count(0)
            context=page.locator('.jj-home-context').bounding_box()
            assert abs(focus['y']-context['y'])<1
            expect(page.locator('.jj-home-context')).to_contain_text('待核验')
            expect(page.locator('.jj-home-context').get_by_text('未关联源码',exact=True)).to_have_count(0)
            expect(page.get_by_role('heading',name='接口与请求资料',exact=True)).to_have_count(0)
            page.screenshot(path=str(output/'workspace-dark.png'),full_page=True)
            page.set_viewport_size({'width':375,'height':980})
            settled(page)
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.screenshot(path=str(output/'workspace-narrow-dark.png'),full_page=True)
            page.get_by_role('button',name='切换浅色',exact=True).click()
            settled(page)
            page.screenshot(path=str(output/'workspace-narrow-light.png'),full_page=True)
            page.set_viewport_size({'width':1512,'height':980})
            source_link=page.get_by_role('navigation',name='应用资料快捷入口',exact=True).get_by_role('link').filter(has_text='接口资料')
            source_link.focus();page.keyboard.press('Enter')
            expect(page.get_by_role('heading',name='读取订单与客户可见字段',exact=True)).to_be_visible()
            navigation.get_by_role('link',name='工作台',exact=True).click()
            expect(page.get_by_role('heading',name='订单与结算协作系统',exact=True)).to_be_visible()
            page.get_by_role('navigation',name='应用资料',exact=True).get_by_role('link',name='应用与来源',exact=True).focus()
            page.keyboard.press('Enter')
            expect(page.get_by_role('heading',name='应用与来源',exact=True)).to_be_visible()
            page.get_by_role('tab',name='接口来源',exact=True).click()
            expect(page.get_by_role('heading',name='读取订单与客户可见字段',exact=True)).to_be_visible()
            expect(page.get_by_role('navigation',name='应用与示例',exact=True)).to_have_count(0)
            switcher=page.get_by_role('button',name='切换应用，当前：订单与结算协作系统',exact=True)
            switcher.focus();page.keyboard.press('Enter')
            expect(page.get_by_role('link',name='官方示例',exact=True)).to_be_visible()
            page.keyboard.press('Escape');switcher.click()
            settled(page);page.screenshot(path=str(output/'application-menu-light.png'),full_page=True)
            menu_style=page.locator('.jj-application-menu .ant-dropdown-menu').evaluate('node=>({radius:getComputedStyle(node).borderRadius,font:getComputedStyle(node).fontFamily})')
            assert menu_style['radius']=='10px'
            assert 'MiSansUI' in menu_style['font'] or 'Microsoft YaHei' in menu_style['font']
            page.get_by_role('link',name='新建应用工作区',exact=True).focus();page.keyboard.press('Enter')
            expect(page.get_by_role('heading',name='建立应用工作区',exact=True)).to_be_visible()
            switcher.click()
            page.get_by_role('menuitem',name='订单与结算协作系统',exact=True).click()
            expect(page.get_by_role('heading',name='订单与结算协作系统',exact=True)).to_be_visible()
            nav_labels=page.locator('.jj-sidebar').evaluate(label_geometry)
            assert len(nav_labels)==6
            assert max(item['center'] for item in nav_labels)-min(item['center'] for item in nav_labels)<1,nav_labels
            assert max(item['iconCenter'] for item in nav_labels)-min(item['iconCenter'] for item in nav_labels)<1,nav_labels
            assert all(float(item['spacing'].removesuffix('px'))>2 for item in nav_labels if item['label'] in ('测试','问题'))
            navigation_geometry.append(dict(surface='sidebar',labels=nav_labels))
            tools=page.locator('.jj-toolbar .jj-settings-entry')
            tools.focus();page.keyboard.press('Enter')
            expect(page.get_by_role('heading',name='设置',exact=True)).to_be_visible()
            expect(page.get_by_role('dialog',name='设置',exact=True)).to_have_count(0)
            expect(page.get_by_role('navigation',name='全局工具').get_by_role('button')).to_have_count(3)
            categories=page.get_by_role('navigation',name='设置分类',exact=True)
            sections=[('开发工具','tools'),('本地存储','storage'),('运行与维护','system')]
            project_query=page.url.split('project_id=')[1].split('&')[0]
            for label,section in sections:
                link=categories.get_by_role('link',name=label,exact=section!='system')
                assert link.get_attribute('href')==f'#/settings?section={section}&project_id={project_query}'
            expect(page.get_by_role('heading',name='工具连接',exact=True)).to_be_visible()
            expect(page.get_by_role('heading',name='开发工具',exact=True)).to_have_count(0)
            chooser=page.locator('.jj-tool-selector .jj-choice')
            chooser.click();page.get_by_role('option',name='DSH',exact=True).click()
            expect(page.locator('.jj-tool-selector .jj-choice')).to_have_attribute('data-value','dsh')
            expect(page.get_by_text('正在读取工具连接',exact=True)).to_have_count(0)
            chooser.click();page.get_by_role('option',name='Codex',exact=True).click()
            expect(page.locator('.jj-tool-selector .jj-choice')).to_have_attribute('data-value','codex')
            expect(page.locator('.jj-tool-state').get_by_text('尚未配置',exact=True)).to_be_visible()
            expect(page.get_by_text('尚未为此客户端准备连接。',exact=True)).to_have_count(0)
            expect(page.locator('.jj-tools-connection details')).to_have_count(1)
            management=page.locator('.jj-tool-management')
            management.locator('summary').click();settled(page)
            expect(management.locator('dd')).to_be_visible()
            page.screenshot(path=str(output/'tool-connection-management.png'),full_page=True)
            management.locator('summary').click();settled(page)
            for theme in ('light','dark'):
                if page.locator('html').get_attribute('data-studio-theme')!=theme:
                    page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                for width in (1512,800,375,320):
                    page.set_viewport_size({'width':width,'height':980});settled(page)
                    for label,section in sections:
                        categories.get_by_role('link',name=label,exact=section!='system').click()
                        expect(page.get_by_role('heading',name={'tools':'工具连接','storage':'清理闲置文件','system':'运行诊断'}[section],exact=True)).to_be_visible()
                        if section=='system':expect(page.get_by_role('heading',name='运行诊断',exact=True)).to_be_visible()
                        elif section=='storage':
                            expect(page.get_by_text('正在扫描已登记的运行文件',exact=True)).to_have_count(0)
                            expect(page.get_by_role('link',name='应用概览',exact=True)).to_have_count(0)
                        settled(page)
                        expect(page.locator('main h1')).to_have_count(1)
                        geometry=page.locator('.jj-settings-page').evaluate("""node=>{const selected=node.querySelector('[aria-current=page]').getBoundingClientRect(),indicator=node.querySelector('.jj-settings-navigation .jj-tab-indicator').getBoundingClientRect(),r=node.getBoundingClientRect();return {left:r.left,right:r.right,viewport:Math.min(document.documentElement.clientWidth,document.body.getBoundingClientRect().right),overflow:document.documentElement.scrollWidth>innerWidth,indicatorError:Math.max(Math.abs(selected.x-indicator.x),Math.abs(selected.bottom-indicator.bottom),Math.abs(selected.width-indicator.width))}}""")
                        assert not geometry['overflow'],geometry
                        assert geometry['left']>=0 and geometry['right']<=geometry['viewport']+1,geometry
                        assert geometry['indicatorError']<1,geometry
                        if section=='tools':
                            pairs=page.locator('.jj-tools-layout').evaluate("""node=>[['.jj-tool-object .jj-choice','.jj-tool-state .jj-badge'],['.jj-current-grant h3','.jj-current-grant .jj-badge'],['.jj-tools-service-state strong','.jj-tools-service-state .jj-badge']].map(([left,right])=>{const a=node.querySelector(left).getBoundingClientRect(),b=node.querySelector(right).getBoundingClientRect();return Math.abs(a.y+a.height/2-b.y-b.height/2)})""")
                            assert max(pairs)<1,pairs
                            geometry['object_state_center_errors']=pairs
                        settings_geometry.append(dict(theme=theme,width=width,section=section,**geometry))
                        page.screenshot(path=str(output/f'settings-{theme}-{width}-{section}.png'),full_page=True)
            page.set_viewport_size({'width':1512,'height':980})
            page.get_by_role('button',name='切换浅色',exact=True).click()
            categories.get_by_role('link',name='开发工具',exact=True).click();settled(page)
            # 采样真实帧，确认局部切换在持续页面中插值，而非只检查CSS声明。
            page.locator('.jj-settings-page').evaluate("node=>node.dataset.continuity='retained'")
            page.evaluate("""()=>{window.settingsMotion=[];window.settingsMotionDone=false;const start=performance.now();function frame(){const node=document.querySelector('.jj-settings-navigation .jj-tab-indicator');window.settingsMotion.push({at:performance.now()-start,transform:getComputedStyle(node).transform});if(performance.now()-start<500)requestAnimationFrame(frame);else window.settingsMotionDone=true}requestAnimationFrame(frame)}""")
            categories.get_by_role('link',name='本地存储',exact=True).click()
            page.wait_for_function('window.settingsMotionDone');settled(page)
            assert page.locator('.jj-settings-page').get_attribute('data-continuity')=='retained'
            motion=page.evaluate('window.settingsMotion')
            assert len({item['transform'] for item in motion})>=3,motion
            (output/'settings-motion.json').write_text(json.dumps(motion),encoding='utf-8')
            page.evaluate("""async()=>{window.settingsInterrupted=[];window.settingsInterruptedDone=false;const start=performance.now();function frame(){window.settingsInterrupted.push({at:performance.now()-start,transform:getComputedStyle(document.querySelector('.jj-settings-navigation .jj-tab-indicator')).transform});if(performance.now()-start<450)requestAnimationFrame(frame);else window.settingsInterruptedDone=true}requestAnimationFrame(frame);const links=[...document.querySelectorAll('.jj-settings-navigation a')];for(const index of [2,0,1]){links[index].click();await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))}}""")
            page.wait_for_function('window.settingsInterruptedDone');settled(page)
            expect(categories.locator('a[aria-current=page]')).to_have_text('本地存储')
            assert page.locator('.jj-settings-page').get_attribute('data-continuity')=='retained'
            alignment=categories.evaluate("""node=>{const a=node.querySelector('a[aria-current=page]').getBoundingClientRect(),b=node.querySelector('.jj-settings-navigation .jj-tab-indicator').getBoundingClientRect();return Math.max(Math.abs(a.x-b.x),Math.abs(a.bottom-b.bottom))}""")
            assert alignment<1
            (output/'settings-motion-interrupt.json').write_text(json.dumps(page.evaluate('window.settingsInterrupted')),encoding='utf-8')
            # 浏览器历史与旧地址仍恢复对应分类；不会额外弹出菜单。
            page.go_back();expect(page.get_by_role('heading',name='工具连接',exact=True)).to_be_visible()
            page.go_forward();expect(page.get_by_role('heading',name='清理闲置文件',exact=True)).to_be_visible()
            page.emulate_media(reduced_motion='reduce')
            categories.get_by_role('link',name='开发工具',exact=True).click();settled(page)
            assert page.locator('.jj-settings-navigation .jj-tab-indicator').evaluate("node=>getComputedStyle(node).transitionDuration")=='0s'
            assert page.locator('.jj-settings-content').evaluate("node=>getComputedStyle(node).animationName")=='none'
            page.emulate_media(reduced_motion='no-preference')
            for path,label in [('/tools','开发工具'),('/settings/models','开发工具'),('/storage','本地存储'),('/system?view=update','运行与维护')]:
                page.goto(server.origin+'/#'+path+('&' if '?' in path else '?')+'project_id='+project_query)
                expect(page.get_by_role('heading',name='设置',exact=True)).to_be_visible()
                if path.startswith('/system'):expect(page.get_by_role('heading',name='版本与更新',exact=True)).to_be_visible()
                else:expect(page.get_by_role('heading',name='清理闲置文件' if path=='/storage' else '工具连接',exact=True)).to_be_visible()
                expect(categories.locator('a[aria-current=page]')).to_contain_text(label)
            settled(page);page.screenshot(path=str(output/'settings-light.png'),full_page=True)
            navigation.get_by_role('link',name='工作台',exact=True).click()
            expect(page.get_by_role('heading',name='订单与结算协作系统',exact=True)).to_be_visible()
            page.set_viewport_size({'width':375,'height':980})
            page.get_by_role('button',name='打开导航',exact=True).click()
            dialog=page.get_by_role('dialog',name='界鉴导航',exact=True)
            nav_labels=dialog.evaluate(label_geometry)
            assert max(item['center'] for item in nav_labels)-min(item['center'] for item in nav_labels)<1,nav_labels
            navigation_geometry.append(dict(surface='mobile-navigation',labels=nav_labels))
            dialog.get_by_role('button',name='切换应用，当前：订单与结算协作系统',exact=True).click()
            expect(dialog.get_by_role('link',name='官方示例',exact=True)).to_be_visible()
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            settled(page);page.screenshot(path=str(output/'application-menu-narrow-light.png'),full_page=True)
            page.evaluate('''()=>{
                window.navigationEvents=[];
                for(const kind of ['cancel','close','click'])document.addEventListener(kind,event=>{
                    if(kind==='click'&&!event.target.closest('[aria-label="打开导航"]'))return;
                    window.navigationEvents.push({kind,at:performance.now(),dialogs:[...document.querySelectorAll('dialog')].map(node=>({open:node.open,inert:node.inert,closing:node.dataset.closing}))});
                },true);
            }''')
            page.keyboard.press('Escape');page.keyboard.press('Escape')
            expect(dialog).to_have_count(0)
            # 退出动效期间原生模态层仍在；等它关闭后再测试重新打开。
            expect(page.locator('dialog[open]')).to_have_count(0)
            page.locator('.jj-toolbar .jj-settings-entry').click(timeout=3000)
            expect(page.get_by_role('heading',name='设置',exact=True)).to_be_visible()
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            settled(page);page.screenshot(path=str(output/'settings-narrow-light.png'),full_page=True)
            categories.get_by_role('link',name='本地存储',exact=True).click()
            expect(page.get_by_role('heading',name='清理闲置文件',exact=True)).to_be_visible()
            expect(dialog).to_have_count(0)
            assert errors==[]
        except Exception:
            page.screenshot(path=str(output/'failure.png'),full_page=True)
            (output/'navigation-events.json').write_text(json.dumps(page.evaluate('window.navigationEvents??[]'),ensure_ascii=False,indent=2),encoding='utf-8')
            raise
        finally:
            browser.close()
            (output/'browser.json').write_text(json.dumps(dict(schema_version='1',page_errors=errors,settings_geometry=settings_geometry,navigation_geometry=navigation_geometry)),encoding='utf-8')
            (output/'fonts.json').write_text(json.dumps(dict(schema_version='1',observations=fonts),ensure_ascii=False,indent=2),encoding='utf-8')


def _rendered_font(page,label):
    client=page.context.new_cdp_session(page)
    try:
        client.send('DOM.enable')
        client.send('CSS.enable')
        root=client.send('DOM.getDocument')['root']['nodeId']
        node=client.send('DOM.querySelector',dict(nodeId=root,selector='main h1'))['nodeId']
        fonts=client.send('CSS.getPlatformFontsForNode',dict(nodeId=node))['fonts']
        choice=page.evaluate('''()=>({choice:document.documentElement.dataset.uiFont,css:getComputedStyle(document.querySelector('main h1')).fontFamily,faces:[...document.fonts].map(face=>({family:face.family,status:face.status})),requests:performance.getEntriesByType('resource').filter(item=>item.name.includes('.ttf')).map(item=>({duration:item.duration,bytes:item.transferSize}))})''')
        return dict(label=label,rendered=fonts,**choice)
    finally:
        client.detach()


def test_delayed_misans_keeps_fallback_glyphs_stable():
    """主动延迟字体传输；字体迟到后，已显示的后备字形和行宽保持稳定。"""
    import asyncio
    from playwright.async_api import async_playwright,expect
    from tests.support.runtime_server import launch
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text(encoding='utf-8'))
    output=root/'var/audit/font-loading'/uuid4().hex
    with launch(output,Path(receipt['frontend']['dist'])) as server:
        async def review():
            async with async_playwright() as engine:
                browser=await engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
                try:
                    page=await browser.new_page(viewport={'width':1512,'height':980})
                    async def delayed_font(route):
                        await asyncio.sleep(2)
                        await route.continue_()
                    await page.route('**/*MiSansVF*.ttf',delayed_font)
                    await page.goto(server.origin+'/#/application',wait_until='domcontentloaded')
                    await expect(page.get_by_role('heading',name='建立应用工作区',exact=True)).to_be_visible()
                    client=await page.context.new_cdp_session(page)
                    await client.send('DOM.enable');await client.send('CSS.enable')
                    async def snapshot():
                        document=(await client.send('DOM.getDocument'))['root']['nodeId']
                        node=(await client.send('DOM.querySelector',dict(nodeId=document,selector='main h1')))['nodeId']
                        rendered=(await client.send('CSS.getPlatformFontsForNode',dict(nodeId=node)))['fonts']
                        layout=await page.evaluate('''()=>{
                            const node=document.querySelector('main h1'),range=document.createRange();range.selectNodeContents(node);
                            return {choice:document.documentElement.dataset.uiFont,width:range.getBoundingClientRect().width,faces:[...document.fonts].map(face=>face.status)};
                        }''')
                        return dict(rendered=rendered,**layout)
                    before=await snapshot()
                    await page.evaluate('document.fonts.ready.then(()=>true)')
                    after=await snapshot()
                    (output/'fonts.json').write_text(json.dumps(dict(schema_version='1',before=before,after=after),ensure_ascii=False,indent=2),encoding='utf-8')
                    assert before['choice']==after['choice']=='system'
                    assert before['width']==after['width']
                    assert not any(font['isCustomFont'] for font in before['rendered']+after['rendered'])
                    assert 'loaded' in after['faces']
                    await client.detach()
                finally:
                    await browser.close()
        asyncio.run(review())


def test_registered_repair_heading_and_timestamp_in_browser():
    """使用真实原问题与登记修改，核对修改和问题详情的标题状态对齐。"""
    from playwright.sync_api import sync_playwright,expect
    from tests.support.runtime_server import launch
    from tests.support.official import OfficialScenario
    from tests.support.browser_review import settled
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text(encoding='utf-8'))
    output=root/'var/audit/heading-status'/uuid4().hex
    observations=[]
    with launch(output,Path(receipt['frontend']['dist'])) as server,sync_playwright() as engine:
        scenario=OfficialScenario(server.client)
        scenario.start()
        baseline=scenario.check('baseline')
        assert baseline.status['run']['verdict']=='PASS'
        scenario.load('VULNERABLE')
        checked=scenario.check('vulnerable')
        assert checked.status['run']['verdict']=='BLOCK'
        change=scenario.load('FIXED',repair=checked)
        contract=scenario.request('GET',f'/api/runs/{checked.run_id}/repair-contracts')[0]
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980},device_scale_factor=1)
            page.goto(server.origin+'/#/permissions?view=repair&project_id='+scenario.project_id+'&change_id='+change+'&repair_reference='+contract['repair_fingerprint'])
            heading=page.get_by_role('heading',name='已登记的修改',exact=True)
            expect(heading).to_be_visible()
            for theme in ('light','dark'):
                if page.locator('html').get_attribute('data-studio-theme')!=theme:
                    page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                for width in (1512,800,375):
                    page.set_viewport_size({'width':width,'height':980})
                    settled(page)
                    geometry=heading.evaluate('''node=>{
                        const title=node.getBoundingClientRect(),status=node.nextElementSibling.getBoundingClientRect();
                        return {title:title.y+title.height/2,status:status.y+status.height/2,sameRow:status.x>=title.right};
                    }''')
                    observations.append(dict(theme=theme,width=width,**geometry))
                    # 窄窗口可换行；处于同一行时必须共享中心轴。
                    assert not geometry['sameRow'] or abs(geometry['title']-geometry['status'])<1
                    page.screenshot(path=str(output/f'registered-repair-{theme}-{width}.png'),full_page=True)
            page.goto(server.origin+'/#/issues?project_id='+scenario.project_id)
            expect(page.locator('.jj-issue-reading')).to_be_visible()
            for theme in ('light','dark'):
                if page.locator('html').get_attribute('data-studio-theme')!=theme:
                    page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                for width in (1512,800,375):
                    page.set_viewport_size({'width':width,'height':980});settled(page)
                    geometry=page.locator('.jj-issue-reading .jj-collection-title').evaluate('''node=>{
                        const title=node.children[0].getBoundingClientRect(),status=node.children[1].getBoundingClientRect();
                        return {title:title.y+title.height/2,status:status.y+status.height/2,sameRow:status.x>=title.right};
                    }''')
                    assert not geometry['sameRow'] or abs(geometry['title']-geometry['status'])<1,geometry
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(theme,width,'issues')
        finally:
            browser.close()
            (output/'alignment.json').write_text(json.dumps(dict(schema_version='1',observations=observations),ensure_ascii=False,indent=2),encoding='utf-8')


def test_populated_routes_and_shared_control_layout_in_browser(readonly_official_review):
    """遍历双主题与三种窗口；只保存重点改动截图，不调用模型或更新部署。"""
    from playwright.sync_api import sync_playwright,expect
    from tests.support.runtime_server import launch
    from tests.support.official import OfficialScenario
    from tests.support.browser_review import settled,navigate
    import os
    root=Path(__file__).resolve().parents[3]
    receipt=json.loads((root/'var/runtime/source/receipt.json').read_text(encoding='utf-8'))
    output=root/'var/audit/stage-a-layout'/uuid4().hex
    errors=[]
    observations=[]
    # 产品构建未变化时，可从失败坐标续查；默认仍遍历完整矩阵，回执明确记录续查范围。
    resume=os.environ.get('JIEJIAN_LAYOUT_REVIEW_RESUME')
    resume_seen=resume is None
    server,scenario,receipt=readonly_official_review
    output.mkdir(parents=True,exist_ok=False)
    with sync_playwright() as engine:
        checked=scenario.check('baseline')
        paths=[
            ('workspace','/workspace'),('environment','/application'),('source','/application?view=source'),
            ('sources','/application?view=sources'),('business','/application?view=business'),
            ('permissions','/permissions'),('testing','/testing'),('preparation','/preparation'),
            ('identities','/preparation?identities=1'),('proof','/preparation?proof_sources=1'),
            ('plan','/reports?view=plan'),('history','/reports'),('report','/reports?run_id='+checked.run_id),
            ('issues','/issues'),('changes','/changes'),('tools','/tools'),('storage','/storage'),
            ('runtime','/system'),('updates','/system?view=update'),('sample','/environment'),
        ]
        paths.extend([('agent','/workspace?view=collaboration'),('changes-register','/changes?view=register')])
        rule=scenario.request('GET',f'/api/projects/{scenario.project_id}/rule-workspace')['rules'][0]
        paths.append(('rule-detail','/permissions?rule_id='+rule['permission']['intent_id']))
        action=scenario.request('GET',f'/api/projects/{scenario.project_id}/operation-flows')['actions'][0]
        paths.append(('flow','/testing?action_id='+action['action_id']))
        browser=engine.chromium.launch(executable_path=receipt['playwright']['executable'],headless=True)
        try:
            page=browser.new_page(viewport={'width':1512,'height':980},device_scale_factor=1)
            page.on('pageerror',lambda error:errors.append(type(error).__name__))
            page.goto(server.origin)
            for theme in ('light','dark'):
                page.evaluate('(theme)=>localStorage.setItem("jiejian.studio.theme",theme)',theme)
                # 使用真实主题按钮，保证样式与应用状态一致。
                if page.locator('html').get_attribute('data-studio-theme')!=theme:
                    page.get_by_role('button',name='切换'+('雾蓝深色' if theme=='dark' else '浅色'),exact=True).click()
                for width in (1512,800,375):
                    page.set_viewport_size({'width':width,'height':980})
                    for name,path in paths:
                        if not resume_seen:
                            if resume!=f'{theme}:{width}:{name}':continue
                            resume_seen=True
                        separator='&' if '?' in path else '?'
                        navigate(page,server.origin,path+separator+'project_id='+scenario.project_id)
                        expect(page.locator('main h1').first).to_be_visible()
                        expect(page.locator('main h1')).to_have_count(1)
                        expect(page.locator('main h1')).to_have_css('font-size','28px')
                        expect(page.locator('main h1')).to_have_css('line-height','36px')
                        # 页内操作不能自行缩小为辅助文字；选中也不改变字号或字重。
                        invalid=page.locator('main .jj-button:not(.jj-index-item)').evaluate_all('''nodes=>nodes.filter(node=>node.getClientRects().length).flatMap(node=>{const s=getComputedStyle(node),r=node.getBoundingClientRect();return r.height<35.5||s.fontSize!=='14px'?[{name:node.textContent?.trim().slice(0,40),height:r.height,size:s.fontSize}]:[]})''')
                        assert not invalid,(theme,width,name,invalid)
                        expect(page.locator('[data-page-pending=true]')).to_have_count(0)
                        expect(page.locator('main .jj-loading')).to_have_count(0)
                        if name=='flow':
                            # 页内导航按产品约定保留草稿；首次准备一次，其后缩放与换主题复用。
                            if page.get_by_role('tab',name='手动填写接口',exact=True).count():
                                page.get_by_role('tab',name='手动填写接口',exact=True).click()
                                page.get_by_role('button',name='开始填写',exact=True).click()
                                page.get_by_label('用于测试的数据编号',exact=True).fill('layout-review-resource')
                                page.get_by_role('button',name='下一步：设置执行步骤',exact=True).click()
                                expect(page.get_by_role('heading',name='设置执行请求',exact=True)).to_be_visible()
                                page.get_by_label('接口路径',exact=True).fill('/orders/{case_resource_id}')
                                page.get_by_role('button',name='添加查询参数',exact=True).click()
                                page.get_by_label('参数名称',exact=True).fill('view')
                                page.get_by_label('发送的值',exact=True).fill('detail')
                                page.get_by_role('tab',name='请求头 0',exact=True).click()
                                page.get_by_role('button',name='添加请求头',exact=True).click()
                                page.get_by_label('参数名称',exact=True).fill('Accept')
                                page.get_by_label('发送的值',exact=True).fill('application/json')
                                page.get_by_role('button',name='准备动态防伪参数',exact=True).click()
                                dialog=page.get_by_role('dialog',name='准备动态防伪参数',exact=True)
                                dialog.get_by_role('button',name='加入准备步骤',exact=True).click()
                                expect(dialog).not_to_be_visible()
                                expect(page.get_by_role('tab',name='请求头 2',exact=True)).to_be_visible()
                            expect(page.get_by_role('heading',name='设置执行请求',exact=True)).to_be_visible()
                            expect(page.get_by_label('接口路径',exact=True)).to_have_value('/orders/{case_resource_id}')
                            expect(page.get_by_role('tab',name='请求头 2',exact=True)).to_be_visible()

                        if name=='sample' and width==1512:
                            page.get_by_role('button',name='管理示例',exact=True).click()
                            expect(page.get_by_role('menu')).to_have_css('border-radius','16px')
                            settled(page)
                            page.keyboard.press('Escape')
                        if name in {'permissions','testing'}:
                            directory=page.get_by_role('region',name='权限规则目录' if name=='permissions' else '可维护场景',exact=True)
                            selected=directory.locator('.jj-object-select[aria-pressed=true]')
                            expect(directory.locator('.jj-inspector')).to_be_visible()
                            expect(directory.locator('.jj-object-summary').first).not_to_be_visible()
                            directory.get_by_role('button',name='收起详情',exact=True).click()
                            expect(selected).to_be_focused()
                            expect(directory.locator('.jj-inspector')).to_have_count(0)
                            expect(directory.locator('.jj-object-summary').first).to_be_visible()
                            assert directory.locator('.jj-collection-layout').evaluate("node=>getComputedStyle(node).gridTemplateColumns.split(' ').length") == 1
                            selected.click()
                            expect(directory.locator('.jj-inspector')).to_be_visible()
                            # 清除只改变本目录筛选，宽度、焦点与项目范围保持稳定。
                            search=page.get_by_role('searchbox',name='查找规则' if name=='permissions' else '查找场景',exact=True)
                            before=search.locator('..').bounding_box()
                            search.fill(selected.locator('strong').inner_text())
                            page.get_by_role('button',name='清除查找规则' if name=='permissions' else '清除查找场景',exact=True).click()
                            expect(search).to_be_focused();expect(search).to_have_value('')
                            assert search.locator('..').bounding_box()['width'] == before['width']
                        settled(page)
                        measurements=page.evaluate('''()=>{
                            const issues=[],headingRows=[];let buttons=0,icons=0;
                            for(const heading of document.querySelectorAll('main :is(h1,h2,h3,h4)')){
                                const row=heading.parentElement,style=getComputedStyle(row),box=heading.getBoundingClientRect();
                                if(!box.width||!box.height||!style.display.includes('flex')||style.flexDirection!=='row')continue;
                                for(const status of row.children){
                                    if(status===heading||!status.matches('span,small,time,.jj-badge'))continue;
                                    const rect=status.getBoundingClientRect();
                                    if(!rect.width||!rect.height||rect.bottom<=box.top||rect.top>=box.bottom)continue;
                                    const delta=Math.abs(box.y+box.height/2-rect.y-rect.height/2);
                                    headingRows.push({heading:heading.textContent.trim(),status:status.textContent.trim(),alignment:style.alignItems,delta});
                                    if(style.alignItems==='center'&&delta>1.5)issues.push({kind:'heading-status',text:heading.textContent.trim(),delta});
                                }
                            }
                            for(const button of document.querySelectorAll('.jj-button')){
                                const box=button.getBoundingClientRect();if(!box.width||!box.height)continue;buttons++;
                                if(button.scrollWidth>button.clientWidth+2)issues.push({kind:'button-overflow',text:button.textContent.trim()});
                                const icon=button.querySelector(':scope>.anticon'),style=getComputedStyle(button);
                                if(!icon||!style.display.includes('flex')||style.alignItems!=='center')continue;
                                const walker=document.createTreeWalker(button,NodeFilter.SHOW_TEXT);let node,texts=[];
                                while(node=walker.nextNode())if(node.textContent.trim()&&!node.parentElement.closest('.anticon')){
                                    const range=document.createRange();range.selectNodeContents(node);texts.push(...range.getClientRects());
                                }
                                if(!texts.length)continue;icons++;
                                const first=texts[0],last=texts.at(-1),symbol=icon.getBoundingClientRect();
                                if(Math.abs(symbol.y+symbol.height/2-(first.y+last.bottom)/2)>3)issues.push({kind:'icon-text',text:button.textContent.trim()});
                            }
                            for(const control of document.querySelectorAll('main button,main input,main textarea,main [role=combobox]')){
                                const box=control.getBoundingClientRect();
                                if(box.width<=2||box.height<=2||getComputedStyle(control).opacity==='0')continue;
                                for(let parent=control.parentElement;parent;parent=parent.parentElement){
                                    const overflow=getComputedStyle(parent).overflowX;
                                    if(['auto','scroll'].includes(overflow))break;
                                    const bounds=parent.getBoundingClientRect();
                                    if(['hidden','clip'].includes(overflow)&&(box.x<bounds.x-1||box.right>bounds.right+1)){
                                        issues.push({kind:'control-clipped',text:control.getAttribute('aria-label')||control.textContent.trim()});break;
                                    }
                                }
                            }
                            const entries=[...document.querySelectorAll('main button,main a')].filter(node=>node.getBoundingClientRect().width>0).map(node=>({label:node.getAttribute('aria-label')||node.textContent.trim(),href:node.getAttribute('href')}));
                            return {pageOverflow:document.documentElement.scrollWidth>innerWidth+1,buttons,icons,headingRows,issues,entries};
                        }''')
                        observations.append(dict(theme=theme,width=width,page=name,**measurements))
                        if width==1512 and theme=='dark' and name in {'permissions','testing'}:
                            page.screenshot(path=str(output/f'{name}-{theme}-{width}.png'),full_page=True)
                        if width==1512 and theme=='light' and name=='sources':
                            page.get_by_role('button',name='导入接口资料或请求',exact=True).click()
                            dialog=page.get_by_role('dialog',name='导入接口资料',exact=True)
                            settled(page);page.screenshot(path=str(output/'source-import-light.png'),full_page=True)
                            dialog.get_by_role('button',name='取消',exact=True).click()
                            expect(dialog).not_to_be_visible()
            assert resume_seen, '续查坐标不在当前视图矩阵中'
            assert errors==[]
            assert not [item for item in observations if item['pageOverflow'] or item['issues']],observations
        except Exception:
            page.screenshot(path=str(output/'failure.png'),full_page=True)
            readiness=page.evaluate('''()=>({
                pending:[...document.querySelectorAll('[data-page-pending=true]')].map(node=>({tag:node.tagName,className:node.className})),
                requests:performance.getEntriesByType('resource').filter(item=>item.name.includes('/api/')).map(item=>({path:new URL(item.name).pathname,duration:item.duration}))
            })''')
            (output/'failure.json').write_text(json.dumps(dict(page=name,theme=theme,width=width,**readiness),ensure_ascii=False,indent=2),encoding='utf-8')
            raise
        finally:
            browser.close()
            (output/'layout.json').write_text(json.dumps(dict(schema_version='1',resume=resume,page_errors=errors,observations=observations),ensure_ascii=False,indent=2),encoding='utf-8')
