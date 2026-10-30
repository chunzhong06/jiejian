import {fireEvent,render,screen,within} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {Breadcrumbs,pageTransitionKey} from './Navigation'
import {AppShell} from './shell/AppShell'
import {historyLocation,type Route} from '../shared/lib/navigation'

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

vi.mock('./shell/RuntimeStatus',()=>({RuntimeStatus:()=>null}))
vi.mock('./shell/Activity',()=>({Activity:()=>null}))

it('全局工具入口保留当前应用归属，返回工作区时仍指向原应用',()=>{
  render(<AppShell route={route('/tools','project_id=app-a')} current="/tools" project={{project_id:'app-a',name:'工单'}} choose={vi.fn()} appearance="light" toggleAppearance={vi.fn()}><h1>开发工具</h1></AppShell>)
  const tools=within(screen.getByRole('navigation',{name:'全局工具'}))
  expect(tools.getByRole('link',{name:'开发工具'})).toHaveAttribute('href','#/tools?project_id=app-a')
  expect(tools.getByRole('link',{name:'本地存储'})).toHaveAttribute('href','#/storage?project_id=app-a')
  expect(within(screen.getByRole('navigation',{name:'应用工作区'})).getByRole('link',{name:'应用概览'})).toHaveAttribute('href','#/workspace?project_id=app-a')
})
