import {normalizedPath} from './Navigation'
import {scopedPath,returnDestination,returnDestinationLabel,checkPlanDestination,withReturnDestination} from '../shared/lib/navigation'
import {routes,routeAliases} from '../shared/lib/routes'
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {Breadcrumbs,pageTransitionKey,NavigationLinks} from './Navigation'
import {AppShell} from './shell/AppShell'
import {SettingsWorkspace} from './shell/SettingsWorkspace'
import {settingsSection} from '../shared/lib/settings'
import {historyLocation,type Route} from '../shared/lib/navigation'
import {subscribePageRefresh} from '../shared/lib/pageRefresh'

const route=(path:string,query=''):Route=>({path,query:new URLSearchParams(query)})

it('报告面包屑回到当前应用和对应历史列表',()=>{
  render(<Breadcrumbs route={route('/reports','run_id=run_a')} projectName="数字展馆" projectId="project-a"/>)
  expect(screen.getByRole('link',{name:'数字展馆'})).toHaveAttribute('href','#/workspace?project_id=project-a')
  expect(screen.getByRole('link',{name:'检查记录'})).toHaveAttribute('href','#/reports?project_id=project-a')
  expect(screen.getByText('报告详情')).toHaveAttribute('aria-current','page')
})

it('页面身份区分业务对象，证据页签不重新播放整页过渡',()=>{
  expect(pageTransitionKey(route('/reports','run_id=a&tab=trace'),'app')).toBe(pageTransitionKey(route('/reports','run_id=a&tab=records'),'app'))
  expect(pageTransitionKey(route('/reports','run_id=a'),'app')).not.toBe(pageTransitionKey(route('/reports','run_id=b'),'app'))
  expect(pageTransitionKey(route('/preparation'),'app')).not.toBe(pageTransitionKey(route('/preparation','identities=1'),'app'))
  expect(pageTransitionKey(route('/application','view=sources'),'app')).toBe(pageTransitionKey(route('/application','view=business'),'app'))
  expect(pageTransitionKey(route('/application','view=create'),'app')).not.toBe(pageTransitionKey(route('/application','view=environment'),'app'))
})

it('历史返回不接受报告详情或其他页面作为列表地址',()=>{
  sessionStorage.setItem('jiejian.studio.history-location:app','/reports?run_id=old')
  expect(historyLocation('app')).toBe('/reports')
  sessionStorage.setItem('jiejian.studio.history-location:app','/application')
  expect(historyLocation('app')).toBe('/reports')
})

it('面包屑链接可由键盘聚焦',()=>{
  render(<Breadcrumbs route={route('/preparation','identities=1')} projectName="展馆" projectId="app"/>)
  const link=screen.getByRole('link',{name:'检查准备'})
  fireEvent.focus(link)
  expect(link).toHaveAttribute('href','#/preparation?project_id=app')
})

vi.mock('../entities/runtime/api/collaboration',async importOriginal=>{const actual=await importOriginal<typeof import('../entities/runtime/api/collaboration')>();return {...actual,collaborationApi:{...actual.collaborationApi,current:vi.fn(async()=>null)}}})
vi.mock('./shell/Activity',()=>({Activity:()=>null}))

it('Agent入口位于应用资料后，设置为侧栏底部图文入口，链接保留应用归属',async()=>{
  render(<AppShell route={route('/workspace','project_id=app-a&view=collaboration&task_id=old')} current="/workspace" project={{project_id:'app-a',name:'工单'}} choose={vi.fn()} appearance="light" toggleAppearance={vi.fn()}><h1>协作任务</h1></AppShell>)
  const tools=within(screen.getByRole('navigation',{name:'全局工具'}))
  const settings=within(screen.getByRole('navigation',{name:'设置入口'})).getByRole('button',{name:'设置'})
  expect(settings).toHaveTextContent('设置')
  expect(tools.queryByRole('button',{name:'设置'})).not.toBeInTheDocument()
  expect(screen.queryByRole('navigation',{name:'本地维护'})).not.toBeInTheDocument()
  expect(tools.getAllByRole('button').at(-1)).toHaveAccessibleName('退出界鉴')
  expect(tools.queryByRole('button',{name:'Agent 协作，开始任务'})).not.toBeInTheDocument()
  expect(within(screen.getByRole('navigation',{name:'Agent协作'})).getByRole('button',{name:'Agent 协作，开始任务'})).toHaveTextContent('Agent 协作')
  expect(within(screen.getByRole('navigation',{name:'Agent协作'})).getByRole('button')).toHaveAttribute('aria-current','page')
  expect(screen.getByRole('link',{name:'工作台'})).not.toHaveAttribute('aria-current')
  expect(within(screen.getByRole('navigation',{name:'当前位置'})).getByText('Agent 协作')).toHaveAttribute('aria-current','page')
  expect(tools.getAllByRole('button')).toHaveLength(3)
  expect(tools.getAllByRole('button')[0]).toHaveAccessibleName('刷新当前界面')
  fireEvent.click(settings)
  expect(location.hash).toBe('#/settings?project_id=app-a')
  expect(screen.queryByRole('dialog',{name:'设置'})).not.toBeInTheDocument()
  expect(within(screen.getByRole('navigation',{name:'应用工作区'})).getByRole('link',{name:'工作台'})).toHaveAttribute('href','#/workspace?project_id=app-a')
  expect(within(screen.getByRole('navigation',{name:'应用工作区'})).getAllByRole('link')).toHaveLength(4)
  expect(screen.queryByRole('navigation',{name:'应用与示例'})).not.toBeInTheDocument()
  expect(within(screen.getByRole('navigation',{name:'应用资料'})).getByRole('link',{name:'应用与来源'})).toHaveAttribute('href','#/application?project_id=app-a')
})

it('顶栏刷新等待当前读取，持续点击不重复启动且不重新挂载正文',async()=>{
  let finish!:()=>void
  const read=vi.fn(()=>new Promise<void>(resolve=>{finish=resolve})),unsubscribe=subscribePageRefresh(read)
  try{
    render(<AppShell route={route('/workspace')} current="/workspace" choose={vi.fn()} appearance="light" toggleAppearance={vi.fn()}><input aria-label="草稿" defaultValue="未提交"/></AppShell>)
    const draft=screen.getByLabelText('草稿'),refresh=screen.getByRole('button',{name:'刷新当前界面'})
    fireEvent.click(refresh)
    expect(screen.getByRole('button',{name:'刷新当前界面'})).toBeDisabled()
    fireEvent.click(screen.getByRole('button',{name:'刷新当前界面'}))
    expect(read).toHaveBeenCalledOnce()
    finish()
    await waitFor(()=>expect(screen.getByRole('button',{name:'刷新当前界面'})).toBeEnabled())
    expect(screen.getByLabelText('草稿')).toBe(draft)
    expect(draft).toHaveValue('未提交')
  }finally{unsubscribe()}
})

it('应用菜单分开切换与新建命令，示例不占业务导航',async()=>{
  const choose=vi.fn()
  render(<AppShell route={route('/workspace')} current="/workspace" project={{project_id:'app-a',name:'工单'}} projects={[{project_id:'app-a',name:'工单'},{project_id:'app-b',name:'结算'}]} choose={choose} appearance="light" toggleAppearance={vi.fn()}><h1>工单</h1></AppShell>)
  fireEvent.click(screen.getByRole('button',{name:'切换应用，当前：工单'}))
  expect(await screen.findByRole('link',{name:'新建应用工作区'})).toHaveAttribute('href','#/application?view=create&project_id=app-a')
  expect(screen.getByRole('link',{name:'官方示例'})).toHaveAttribute('href','#/environment')
  fireEvent.click(screen.getByRole('menuitem',{name:'结算'}))
  expect(choose).toHaveBeenCalledWith('app-b')
})

it('设置分类保留应用归属，导航不重复展示服务状态',()=>{
  const preload=vi.fn()
  render(<SettingsWorkspace onPreload={preload} route={route('/settings','section=storage')} projectId="app-a"><h2>存储内容</h2></SettingsWorkspace>)
  const categories=within(screen.getByRole('navigation',{name:'设置分类'}))
  expect(categories.getByRole('link',{name:'本地存储'})).toHaveAttribute('href','#/settings?section=storage&project_id=app-a')
  expect(categories.getByRole('link',{name:'本地存储'})).toHaveAttribute('aria-current','page')
  fireEvent.pointerEnter(categories.getByRole('link',{name:'运行与维护'}))
  expect(preload).toHaveBeenCalledWith('/settings?section=system')
  expect(categories.getByRole('link',{name:'运行与维护'})).toHaveAttribute('href','#/settings?section=system&project_id=app-a')
  expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1)
})

it('旧设置链接和新分类共享页面归属，分类切换保留外层页面',()=>{
  for(const [path,section] of [['/tools','tools'],['/settings/models','tools'],['/storage','storage'],['/system','system']])expect(settingsSection(route(path))).toBe(section)
  expect(settingsSection(route('/settings','section=unknown'))).toBe('tools')
  expect(pageTransitionKey(route('/settings','section=tools'),'app')).toBe(pageTransitionKey(route('/settings','section=storage'),'app'))
  render(<Breadcrumbs route={route('/storage')} projectId="app-a"/>)
  expect(screen.getByRole('link',{name:'设置'})).toHaveAttribute('href','#/settings?project_id=app-a')
  expect(screen.getByText('本地存储')).toHaveAttribute('aria-current','page')
})


it('路由登记保持唯一，旧链接沿用归属和分类',()=>{
  expect(new Set(routes.map(item=>item.path)).size).toBe(routes.length)
  for(const [old,path] of Object.entries(routeAliases))expect(normalizedPath(route(old))).toBe(path)
  for(const item of routes.filter(item=>item.scoped))expect(scopedPath(item.path,'project-a')).toContain('project_id=project-a')
  expect(normalizedPath(route('/tests','materials=1'))).toBe('/preparation')
  expect(normalizedPath(route('/tests','run_id=old'))).toBe('/reports')
})


it('返回入口按实际任务命名，拒绝外部位置',()=>{
  expect(returnDestination('https://example.com')).toBeNull()
  expect(returnDestinationLabel('/permissions?rule_id=deny')).toBe('返回权限规则')
  expect(returnDestinationLabel('/reports?view=plan')).toBe('返回检查范围')
  expect(returnDestinationLabel('/testing?action_id=read')).toBe('返回接口流程')
})

it('重新核对保留原规则、实验和发起位置，不带入运行详情参数',()=>{
  const source=new URLSearchParams({run_id:'old',case_id:'case',rule_id:'deny',scope_id:'specific',scenario_id:'scenario',scenario_revision:'2',return_to:'/testing?scenario=scenario'})
  const target=new URLSearchParams(checkPlanDestination(source).split('?')[1])
  expect(target.get('view')).toBe('plan')
  expect(target.get('scope_id')).toBe('specific')
  expect(target.get('rule_id')).toBe('deny')
  expect(target.get('scenario_revision')).toBe('2')
  expect(target.get('return_to')).toBe('/testing?scenario=scenario')
  expect(target.has('run_id')).toBe(false)
  expect(target.has('case_id')).toBe(false)
})


it('协作只接受准确任务回程，保留原对象并替换旧的返回参数',()=>{
  const origin='/workspace?view=collaboration&task_id=task&project_id=app'
  expect(returnDestination(origin)).toBe(origin)
  expect(returnDestination('/workspace?project_id=app')).toBe('/workspace?project_id=app')
  expect(returnDestinationLabel('/workspace')).toBe('返回工作台')
  for(const path of ['/workspace?view=collaboration','/workspace?view=other&task_id=task','//example.com','/testing\\evil'])expect(returnDestination(path)).toBeNull()
  expect(returnDestinationLabel(origin)).toBe('返回协作任务')
  const result=new URLSearchParams(withReturnDestination('/testing?action_id=read&revision=2&return_to=old',origin).split('?')[1])
  expect(result.get('action_id')).toBe('read')
  expect(result.get('revision')).toBe('2')
  expect(result.getAll('return_to')).toEqual([origin])
})

it('源码修改沿用权限导航，测试子工作面在面包屑中有清楚归属',()=>{
  const {unmount}=render(<NavigationLinks current="/changes" hasProject projectId="app" onNavigate={()=>{}}/>)
  expect(screen.getByRole('link',{name:'权限与覆盖'})).toHaveAttribute('aria-current','page')
  unmount()
  render(<Breadcrumbs route={route('/testing','action_id=read')} projectName="订单系统" projectId="app"/>)
  expect(screen.getByRole('link',{name:'测试'})).toHaveAttribute('href','#/testing?project_id=app')
  expect(screen.getByText('接口流程')).toHaveAttribute('aria-current','page')
})
