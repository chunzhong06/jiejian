import {afterEach,expect,test,vi} from 'vitest'
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {FlowTrialPanel} from './FlowTrialPanel'
import {flowTrialsApi as api,type FlowTrial,type TrialPlan} from '../api/flowTrials'
import type {OperationFlow} from '../api/operationFlows'

vi.mock('../api/flowTrials',()=>({flowTrialsApi:{history:vi.fn(),preview:vi.fn(),start:vi.fn(),cancel:vi.fn()}}))
afterEach(()=>{cleanup();vi.resetAllMocks();sessionStorage.clear()})
const flow:OperationFlow={id:'ofl_example',revision:2,business_action_id:'action',action_revision:1,subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',provenance:'MANUAL',source_recording_id:null,source_fingerprint:null,actual_resource_id:'order-1',recovery:null,workflow:{target_step_id:'read',steps:[{id:'read',identity_id:'CASE_SUBJECT',purpose:'TARGET',request_template:{method:'GET',path:'/orders/{id}',body:{kind:'EMPTY'}},classifier:{accepted:[],denied:[]},depends_on_step_ids:[]}]}}
const plan:TrialPlan={flow,case:{subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',resource_id:'order-1'},state_changing:false,mode:'TRIAL',runtime:{target:{base_url:'http://127.0.0.1:18081'},budget:{max_requests:4,max_duration_us:20000000}}}
const props={projectId:'app',flow,accounts:[{identity_id:'owner',label:'负责人'}],onResume:vi.fn()}
const receipt=(operation:string):FlowTrial=>({request:{operation_id:operation,trial_id:'ftr_original',created_at_us:1000000,plan},job_id:'job_original',state:'RUNNING',report:null,operation_may_have_run:true,recovery_pending:false})

test('未知提交回执和重新打开只查询原操作，不重新发送场景',async()=>{
  let original:FlowTrial|undefined
  vi.mocked(api.history).mockImplementation(async()=>original?[original]:[])
  vi.mocked(api.preview).mockResolvedValue({plan,plan_hash:'a'.repeat(64)})
  vi.mocked(api.start).mockImplementation(async(_project,_selection,_preview,operation)=>{original=receipt(operation);throw new TypeError('连接中断')})
  const first=render(<FlowTrialPanel {...props}/>)
  expect(screen.queryByRole('alert')).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:'预览试运行'}))
  fireEvent.click(await screen.findByRole('button',{name:'确认执行一次'}))
  await waitFor(()=>expect(api.start).toHaveBeenCalledTimes(1))
  await screen.findByRole('button',{name:'取消原任务'})
  expect(screen.queryByRole('button',{name:'确认执行一次'})).toBeNull()
  first.unmount();render(<FlowTrialPanel {...props}/>)
  await screen.findByRole('button',{name:'取消原任务'})
  expect(api.start).toHaveBeenCalledTimes(1)
})

test('历史沿用准确旧修订，有限步骤反馈不冒充权限通过',async()=>{
  const old=receipt('original')
  old.state='SUCCEEDED';old.request.plan={...plan,flow:{...flow,revision:1}}
  old.report={steps:[{step_id:'read',purpose:'TARGET',status_code:403,response_bytes:100,classification:'DENIED',error_code:null}],identity_status:'MATCH',target_attempted:true,flow_attempted:true,recovery:'NOT_REQUIRED',error_code:null}
  vi.mocked(api.history).mockResolvedValue([old])
  render(<FlowTrialPanel {...props}/>)
  expect(await screen.findByText('请求被拒绝')).toBeTruthy()
  expect(screen.queryByText('权限通过')).toBeNull()
  fireEvent.keyDown(screen.getByRole('tab',{name:'试运行记录 1'}),{key:'ArrowLeft'})
  expect(screen.getByRole('button',{name:'预览试运行'})).toBeTruthy()
  fireEvent.keyDown(screen.getByRole('tab',{name:'本次试运行'}),{key:'ArrowRight'})
  expect(screen.getByText('请求被拒绝')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'从此修订继续编辑'}))
  expect(props.onResume).toHaveBeenLastCalledWith(old.request.plan.flow)
  expect(api.start).not.toHaveBeenCalled()
})
