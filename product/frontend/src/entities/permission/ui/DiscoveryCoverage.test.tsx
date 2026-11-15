import {fireEvent,render,screen} from '@testing-library/react'
import {expect,it} from 'vitest'
import {DiscoveryCoveragePanel} from './DiscoveryCoverage'
import type {DiscoveryCoverage} from '../api/discovery'

const coverage:DiscoveryCoverage={fingerprint:'a'.repeat(64),pending_count:1,related_count:1,excluded_count:0,recheck_count:0,omitted_count:0,unexecuted_request_count:1,items:[
  {key:'new',kind:'ACTION',label:'批量导出',status:'PENDING',fingerprint:'b'.repeat(64),candidate_id:'candidate',action_id:null,source_id:null,request_id:null},
  {key:'api',kind:'REQUEST',label:'读取订单',status:'RELATED',fingerprint:'c'.repeat(64),candidate_id:null,action_id:'action',source_id:'source',request_id:'request',in_execution:false}
]}

it('已有规则可继续，未登记业务与尚未执行的接口仍明确保留',()=>{
  location.hash='#/workspace?project_id=app'
  render(<DiscoveryCoveragePanel coverage={coverage}/>)
  expect(screen.getByText(/1 项线索尚待核对/)).toBeVisible()
  expect(screen.getByText(/1 个已关联接口未作为本次受检步骤执行/)).toBeVisible()
  expect(screen.getByRole('link',{name:'核对新增业务与权限要求'})).toBeVisible()
  fireEvent.click(screen.getByText('查看待核对线索与已确认范围'))
  expect(screen.getByText('批量导出')).toBeInTheDocument()
  expect(screen.getByRole('link',{name:'核对新增业务与权限要求'})).toHaveAttribute('href',expect.stringContaining('view=business'))
})

it('历史快照只描述当时状态，归档阅读不提供修改入口',()=>{
  render(<DiscoveryCoveragePanel coverage={coverage} historical readOnly/>)
  expect(screen.getByText(/当时尚未完成核对/)).toBeInTheDocument()
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
  expect(screen.getByText(/后来的处理不会改写/)).toBeInTheDocument()
})
