import {afterEach,expect,test} from 'vitest'
import {cleanup,render,screen} from '@testing-library/react'
import type {OperationFlow} from '../api/operationFlows'
import {OperationFlowSummary} from './OperationFlowSummary'

afterEach(cleanup)
const flow:OperationFlow={id:'ofl_summary',revision:2,business_action_id:'approve',action_revision:1,subject_test_identity_id:'member',resource_owner_test_identity_id:'owner',provenance:'MANUAL',source_recording_id:null,source_fingerprint:null,actual_resource_id:'order-7',recovery:null,workflow:{target_step_id:'approve',steps:[{id:'approve',identity_id:'CASE_SUBJECT',purpose:'TARGET',request_template:{method:'POST',path:'/orders/{case_resource_id}/approve',body:{kind:'EMPTY'}},classifier:{accepted:[],denied:[]},depends_on_step_ids:[]}]}}
const accounts=[{identity_id:'member',label:'评审账号'},{identity_id:'owner',label:'项目负责人账号'}]

test('准确业务名称、操作人及数据归属先于技术配置阅读',()=>{
  render(<OperationFlowSummary flow={flow} accounts={accounts} actionLabel="批准借用申请" stateChanging/>)
  expect(screen.getAllByText('批准借用申请')).toHaveLength(2)
  expect(screen.getByText('评审账号')).toBeVisible()
  expect(screen.getByText('归属于 项目负责人账号')).toBeVisible()
  expect(screen.getByText('order-7')).toBeVisible()
  expect(screen.getByText('POST /orders/{case_resource_id}/approve').closest('details')).not.toHaveAttribute('open')
  expect(screen.getByText('尚未配置恢复请求。')).toBeVisible()
})

test('缺失动作上下文不会被解释为只读，无需恢复只来自明确的只读事实',()=>{
  const view=render(<OperationFlowSummary flow={flow} accounts={accounts} actionLabel="批准借用申请"/>)
  expect(screen.getByText('尚未配置恢复请求。')).toBeVisible()
  view.rerender(<OperationFlowSummary flow={flow} accounts={accounts} actionLabel="查看借用申请" stateChanging={false}/>)
  expect(screen.getByText('只读操作，无需恢复。')).toBeVisible()
})

test('恢复材料以原资源及所有者为对象，配置不提前声称业务已恢复',()=>{
  render(<OperationFlowSummary flow={{...flow,recovery:{method:'POST',relative_path:'/restore/{case_resource_id}',json_body:{}}}} accounts={accounts} actionLabel="批准借用申请" focus="recovery" stateChanging/>)
  expect(screen.getByText('恢复执行账号')).toBeVisible()
  expect(screen.getByText('项目负责人账号')).toBeVisible()
  expect(screen.queryByText('评审账号')).toBeNull()
  expect(screen.queryByRole('list',{name:'流程执行顺序'})).toBeNull()
  expect(screen.getByText('由数据所有者提交已配置的恢复请求。执行反馈在试运行或正式检查中查看。')).toBeVisible()
  expect(screen.getByText('POST /restore/{case_resource_id}')).toBeInTheDocument()
})
