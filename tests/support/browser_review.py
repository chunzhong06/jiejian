# 只按用户可见内容等待页面就绪，截图与业务执行分别留证。
from playwright.sync_api import expect

def settled(page):
    page.wait_for_function("!document.documentElement.dataset.visualTransition && document.getAnimations().every(a=>a.effect.getComputedTiming().endTime===Infinity||a.playState==='finished')")

def report_ready(page,evidence_label='查看依据'):
    expect(page.get_by_text(evidence_label,exact=True).first).to_be_visible()
    expect(page.get_by_text('本次检查的适用范围',exact=True)).to_be_visible()
    settled(page)

def capture_workflow(page,origin,output,run_id,*,evidence_label='查看依据'):
    captures=[]
    def capture(name,path,kind):
        page.goto(origin+'/#'+path,wait_until='domcontentloaded')
        if kind=='permissions':expect(page.get_by_role('table')).to_be_visible()
        elif kind=='preparation':
            expect(page.get_by_text('所需材料',exact=True)).to_be_visible()
            expect(page.get_by_role('status',name='正在读取检查准备',exact=True)).not_to_be_visible()
        else:report_ready(page,evidence_label=evidence_label)
        settled(page)
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.mouse.move(1480,950)
        page.screenshot(path=str(output/(name+'.png')),full_page=True)
        captures.append(name+'.png')
    capture('permissions-light','/permissions','permissions')
    capture('preparation-light','/preparation','preparation')
    capture('report-light','/reports?run_id='+run_id,'report')
    page.get_by_role('button',name='切换雾蓝深色',exact=True).click()
    expect(page.locator('html')).to_have_attribute('data-studio-theme','dark')
    capture('preparation-dark','/preparation','preparation')
    capture('report-dark','/reports?run_id='+run_id,'report')
    navigation=page.get_by_role('navigation',name='应用工作区',exact=True)
    for title in ('权限规则','检查准备','检查记录','应用概览'):
        navigation.get_by_role('link',name=title,exact=True).click()
    expect(page.get_by_role('heading',name='数字展馆协作空间',exact=True)).to_be_visible()
    return captures
