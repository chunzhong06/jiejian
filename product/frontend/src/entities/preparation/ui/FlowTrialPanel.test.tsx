import {afterEach,expect,test,vi} from 'vitest'
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {FlowTrialPanel} from './FlowTrialPanel'
import {flowTrialsApi as api,type FlowTrial,type TrialPlan,type TrialReport} from '../api/flowTrials'
import {operationFlowsApi,type OperationFlow} from '../api/operationFlows'
import {testIdentitiesApi} from '../api/testIdentities'
import {OperationFlowEditor} from './OperationFlowEditor'

vi.mock('../api/flowTrials',()=>({flowTrialsApi:{history:vi.fn(),preview:vi.fn(),start:vi.fn(),cancel:vi.fn()}}))
afterEach(()=>{cleanup();vi.resetAllMocks();sessionStorage.clear()})
const flow:OperationFlow={id:'ofl_example',revision:2,business_action_id:'action',action_revision:1,subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',provenance:'MANUAL',source_recording_id:null,source_fingerprint:null,actual_resource_id:'order-1',recovery:null,workflow:{target_step_id:'read',steps:[{id:'read',identity_id:'CASE_SUBJECT',purpose:'TARGET',request_template:{method:'GET',path:'/orders/{id}',body:{kind:'EMPTY'}},classifier:{accepted:[],denied:[]},depends_on_step_ids:[]}]}}
const plan:TrialPlan={flow,case:{subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',resource_id:'order-1'},state_changing:false,mode:'TRIAL',runtime:{target:{base_url:'http://127.0.0.1:18081'},budget:{max_requests:4,max_duration_us:20000000}}}
const props={projectId:'app',flow,accounts:[{identity_id:'owner',label:'负责人'}],onResume:vi.fn()}
const receipt=(operation:string):FlowTrial=>({request:{operation_id:operation,trial_id:'ftr_original',created_at_us:1000000,plan},job_id:'job_original',state:'RUNNING',report:null,operation_may_have_run:true,recovery_pending:false})

test('业务场景传入的账号和资源用于预览，未确认前不执行',async()=>{
  vi.mocked(api.history).mockResolvedValue([])
  vi.mocked(api.preview).mockResolvedValue({plan,plan_hash:'b'.repeat(64)})
  const selection={flow_id:flow.id,revision:flow.revision,subject_identity_id:'member',resource_owner_identity_id:'owner',resource_id:'order-2'}
  render(<FlowTrialPanel {...props} onResume={undefined} accounts={[...props.accounts,{identity_id:'member',label:'成员'}]} initialSelection={selection}/>)
  fireEvent.click(screen.getByRole('button',{name:'预览试运行'}))
  await screen.findByRole('button',{name:'确认执行一次'})
  expect(api.preview).toHaveBeenCalledWith('app',selection)
  expect(api.start).not.toHaveBeenCalled()
})

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
  expect(screen.queryByRole('combobox',{name:'选择试运行记录'})).not.toBeInTheDocument()
  expect(screen.queryByText('权限通过')).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:'准备新的试运行'}))
  expect(screen.getByRole('button',{name:'预览试运行'})).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:/查看试运行记录/}))
  expect(screen.getByText('请求被拒绝')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'从此修订继续编辑'}))
  expect(props.onResume).toHaveBeenLastCalledWith(old.request.plan.flow)
  expect(api.start).not.toHaveBeenCalled()
})

test('记录选择沿用准确试运行与旧修订，不在外层任务中重复建立目录',async()=>{
  const newest=receipt('newest'),older=receipt('older')
  newest.state='SUCCEEDED';older.state='SUCCEEDED'
  older.request={...older.request,trial_id:'trial-old',plan:{...plan,case:{...plan.case,resource_id:'order-old'},flow:{...flow,revision:1}}}
  vi.mocked(api.history).mockResolvedValue([newest,older])
  render(<FlowTrialPanel {...props} initialTrialId="trial-old"/>)
  const picker=await screen.findByRole('combobox',{name:'选择试运行记录'})
  expect(screen.getByRole('heading',{name:'负责人 · order-old'})).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'从此修订继续编辑'}))
  expect(props.onResume).toHaveBeenLastCalledWith(older.request.plan.flow)
  fireEvent.mouseDown(picker)
  fireEvent.click(await screen.findByRole('option',{name:/第\s*2\s*修订/}))
  expect(screen.getByRole('heading',{name:'负责人 · order-1'})).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'从此修订继续编辑'}))
  expect(props.onResume).toHaveBeenLastCalledWith(newest.request.plan.flow)
  expect(api.start).not.toHaveBeenCalled()
})

function editorContext(){
  vi.mocked(api.history).mockResolvedValue([])
  vi.spyOn(operationFlowsApi,'context').mockResolvedValue({project_id:'app',source_fingerprint:null,endpoint:null,recordings:[],actions:[{action_id:'action',revision:1,label:'读取订单',state_changing:false,effects:[]}],flows:[{document:flow,adopted:true,in_use:true,configuration_current:true}]})
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([{identity_id:'owner',label:'负责人',auth_method:'COOKIE'}] as never)
}

test('指定记录失效时保留缺失反馈，不回退其他试运行',async()=>{
  const other=receipt('other');other.state='SUCCEEDED';vi.mocked(api.history).mockResolvedValue([other]);
  render(<FlowTrialPanel {...props} initialTrialId="missing-record"/>);
  expect(await screen.findByText('未找到指定的试运行记录，当前没有改为显示其他记录。')).toBeVisible();
  expect(screen.queryByRole('heading',{name:'负责人 · order-1'})).not.toBeInTheDocument();
  expect(api.start).not.toHaveBeenCalled();
})

test('返回编辑器仍保留后台试运行门禁，不把离开当作执行结束',async()=>{
  editorContext();vi.mocked(api.history).mockResolvedValue([receipt('active')]);
  render(<OperationFlowEditor projectId="gate-app" actionId="action" initialFlow={flow} onBack={vi.fn()}/>);
  fireEvent.click(await screen.findByRole('button',{name:'试运行记录'}));
  expect(await screen.findByRole('button',{name:'取消原任务'})).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'返回流程编辑'}));
  expect(screen.getByRole('button',{name:'用于后续检查'})).toBeDisabled();
  expect(screen.getByRole('tab',{name:'执行请求'})).toBeDisabled();
  expect(api.cancel).not.toHaveBeenCalled();expect(api.start).not.toHaveBeenCalled();
})

test.each([
  ['MISMATCH','UNCONFIRMED','不一致','结果不明'],
  ['UNKNOWN','NOT_ATTEMPTED','尚未确认','尚未执行'],
  ['MATCH','REQUEST_ACCEPTED','一致','请求被接受'],
] as const)('执行结束仍保留主体与恢复的独立事实：%s / %s',async(identity,recovery,identityLabel,recoveryLabel)=>{
  const item=receipt('completed-request')
  item.state='SUCCEEDED'
  item.report={identity_status:identity,recovery,steps:[],target_attempted:true,flow_attempted:true,error_code:null} satisfies TrialReport
  vi.mocked(api.history).mockResolvedValue([item])
  render(<FlowTrialPanel {...props}/>)
  const account=await screen.findByText('实际账号与计划')
  expect(account.closest('.jj-result-summary')).toHaveTextContent(identityLabel)
  expect(screen.getByText('恢复请求').closest('.jj-result-summary')).toHaveTextContent(recoveryLabel)
  if(recovery==='REQUEST_ACCEPTED')expect(screen.getByText('请求被接受只表示接口反馈，业务状态仍由正式检查核对。')).toBeVisible()
  expect(screen.queryByText(/符合规则|已验证修复|权限通过/)).not.toBeInTheDocument()
  expect(api.start).not.toHaveBeenCalled()
})

test('已有流程直接切换到请求编辑，未保存草稿不能试运行或采用',async()=>{
  editorContext()
  render(<OperationFlowEditor projectId="app" actionId="action" initialFlow={flow} onBack={vi.fn()}/>)
  await screen.findByRole('tab',{name:'执行请求'})
  fireEvent.click(screen.getByRole('tab',{name:'执行请求'}))
  const path=await screen.findByRole('textbox',{name:'接口路径'})
  fireEvent.change(path,{target:{value:'/orders/changed'}})
  expect(screen.getByRole('button',{name:'保存修改'})).toBeEnabled()
  fireEvent.click(screen.getByRole('tab',{name:'保存与使用'}))
  expect(screen.queryByRole('button',{name:'预览试运行'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'确认用于检查'})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'保存操作设置'})).toBeVisible()
  fireEvent.click(screen.getByRole('tab',{name:'执行请求'}))
  expect(screen.getByRole('textbox',{name:'接口路径'})).toHaveValue('/orders/changed')
})

test('新建流程继续使用引导，不混入已有流程的维护分类',async()=>{
  editorContext()
  render(<OperationFlowEditor projectId="new-app" actionId="action" onBack={vi.fn()}/>)
  expect(await screen.findByRole('heading',{name:'从已有操作开始'})).toBeVisible()
  expect(screen.queryByRole('tablist',{name:'流程维护'})).not.toBeInTheDocument()
})


test('离开已有流程后恢复未保存请求及维护分类，不重新进入首次引导',async()=>{
  editorContext()
  const first=render(<OperationFlowEditor projectId="app" actionId="action" initialFlow={flow} onBack={vi.fn()}/>)
  fireEvent.click(await screen.findByRole('tab',{name:'执行请求'}))
  fireEvent.change(screen.getByRole('textbox',{name:'接口路径'}),{target:{value:'/orders/unsaved-return'}})
  expect(screen.getByRole('button',{name:'保存修改'})).toBeEnabled()
  first.unmount()
  render(<OperationFlowEditor projectId="app" actionId="action" onBack={vi.fn()}/>)
  expect(await screen.findByRole('tablist',{name:'流程维护'})).toBeVisible()
  expect(screen.getByRole('textbox',{name:'接口路径'})).toHaveValue('/orders/unsaved-return')
  expect(screen.queryByRole('heading',{name:'从已有操作开始'})).not.toBeInTheDocument()
  expect(api.start).not.toHaveBeenCalled()
})
