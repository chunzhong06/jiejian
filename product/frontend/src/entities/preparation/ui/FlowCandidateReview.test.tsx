import {cleanup,fireEvent,render,screen,within} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import type {OperationFlow} from '../api/operationFlows'
import {FlowCandidateReview,FlowComparison,flowComparisonBaseline} from './FlowCandidateReview'

afterEach(cleanup)
const flow:OperationFlow={id:'flow',revision:2,business_action_id:'download',action_revision:1,subject_test_identity_id:'judge',resource_owner_test_identity_id:'owner',actual_resource_id:'campus',provenance:'MANUAL',source_recording_id:null,source_fingerprint:null,workflow:{target_step_id:'target',steps:[{id:'target',purpose:'TARGET',identity_id:'judge',request_template:{method:'GET',path:'/files/{case_resource_id}',query:[{name:'format',literal:'private-local-value'}],headers:[],body:{kind:'EMPTY'}},classifier:{accepted:[],denied:[]},depends_on_step_ids:[]}]},recovery:null}
const accounts=[{identity_id:'judge',label:'评审'},{identity_id:'owner',label:'负责人'}]

it('变化视图按实际字段归组，完整视图保留未变化内容且不展示本机固定值',()=>{
  const previous={...flowComparisonBaseline(flow),subject:'owner',recovery:'/restore/{case_resource_id}',restoreMethod:'POST'}
  render(<FlowComparison candidate={flow} previous={previous} accounts={accounts}/>)
  const table=screen.getByRole('table')
  expect(screen.getByRole('rowheader',{name:'操作账号'})).toBeVisible()
  expect(screen.queryByRole('rowheader',{name:'测试数据'})).not.toBeInTheDocument()
  expect(within(table).getByText('账号与测试数据')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'完整流程'}))
  expect(screen.getByRole('rowheader',{name:'测试数据'})).toBeVisible()
  expect(screen.getAllByText(/查询 · format ← 固定值/)).toHaveLength(2)
  expect(screen.queryByText('private-local-value')).not.toBeInTheDocument()
})

it('取消保留当前内容，带入只回交草稿选择，不自动保存或采用',()=>{
  const apply=vi.fn(),keep=vi.fn()
  render(<FlowCandidateReview candidate={flow} accounts={accounts} onApply={apply} onKeep={keep}/>)
  fireEvent.click(screen.getByRole('button',{name:'保留当前草稿'}))
  expect(keep).toHaveBeenCalledOnce()
  expect(apply).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'带入候选继续核对'}))
  expect(apply).toHaveBeenCalledWith(true)
})
