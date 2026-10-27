import {fireEvent,render,screen} from '@testing-library/react'
import {expect,it} from 'vitest'
import {Breadcrumbs,pageTransitionKey} from './Navigation'
import {historyLocation,type Route} from '../shared/lib/navigation'

const route=(path:string,query=''):Route=>({path,query:new URLSearchParams(query)})

it('报告面包屑回到当前应用和对应历史列表',()=>{
  render(<Breadcrumbs route={route('/reports','run_id=run_a')} projectName="数字展馆" projectId="project-a"/>)
  expect(screen.getByRole('link',{name:'数字展馆'})).toHaveAttribute('href','#/workspace')
  expect(screen.getByRole('link',{name:'检查记录'})).toHaveAttribute('href','#/reports')
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
  expect(link).toHaveAttribute('href','#/preparation')
})
