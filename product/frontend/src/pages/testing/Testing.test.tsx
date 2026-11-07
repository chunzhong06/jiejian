import {fireEvent,render,screen,within,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {Testing} from './Testing'
import {operationFlowsApi,type OperationContext} from '../../entities/preparation/api/operationFlows'
import {testIdentitiesApi,type TestIdentityDto} from '../../entities/preparation/api/testIdentities'
import {workbenchApi} from '../../entities/application/api/workbench'
import {flowTrialsApi} from '../../entities/preparation/api/flowTrials'
import {preparationApi} from '../../entities/preparation/api/preparation'
import {rememberEditorDraft,editorDraft,discardProjectEditorDrafts,useCurrentHandoff} from '../../entities/runtime/model/handoff'
import {flowDraftKey} from '../../entities/preparation/ui/FlowCandidateReview'
import type {OperationFlow} from '../../entities/preparation/api/operationFlows'
import {BusinessScenarios} from './BusinessScenarios'
import {ScenarioResources} from './ScenarioResources'
import {businessScenariosApi,type BusinessScenario,type ScenarioContext} from '../../entities/preparation/api/businessScenarios'
import type {PageProps} from '../../shared/model/page'

afterEach(()=>rememberEditorDraft(flowDraftKey('app','action'),undefined))

const context:OperationContext={project_id:'app',source_fingerprint:null,endpoint:'http://127.0.0.1:8080',recordings:[],flows:[],actions:[{action_id:'action',revision:1,label:'读取订单',state_changing:false,effects:[]}]}
const props=(query=''):PageProps=>({projectId:'app',name:'订单',official:false,refresh:vi.fn(),onError:vi.fn(),route:{path:'/testing',query:new URLSearchParams(query)}})
const account:TestIdentityDto={identity_id:'owner',project_id:'app',actor_id:'actor',actor_revision:1,actor_display_name:'所有者',label:'所有者账号',auth_method:'BEARER',status:'PREPARED',review_reasons:[],cookie_count:0,prepared_at_us:1,refreshed_at_us:1,created_at_us:1,updated_at_us:1,authentication:null,verification:null}

const scenarioDocument:BusinessScenario={document_type:'jiejian.business-scenario',schema_version:'1',id:'bsc_'+'1'.repeat(32),project_id:'app',revision:1,label:'订单审批',description:'',experiments:[{id:'normal',label:'正常业务',kind:'NORMAL',control_experiment_id:null,invocations:[{id:'read',label:'读取订单',depends_on:[],batch:null,items:[{id:'order',permission:{intent_id:'rule',revision:1,intent_hash:'a'.repeat(64)},subject_identity_id:'owner',resource_id:'order-1'}]}]}]}
const scenarioSummary={id:scenarioDocument.id,revision:1,label:scenarioDocument.label,description:'',experiment_count:1}
const scenarioContext:ScenarioContext={project_id:'app',documents:[scenarioSummary],gaps:[],identities:[{identity_id:'owner',label:'订单所有者'}],actions:[{action_id:'action',action_revision:1,label:'读取订单',cases:[{case_id:'case',permission:{intent_id:'rule',revision:1,intent_hash:'a'.repeat(64),expectation:'ALLOW'},subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',resource_id:'order-1'}]}]}
afterEach(()=>rememberEditorDraft('scenario-editor:app:'+scenarioDocument.id+':1',undefined))

it('空实验只有一处创建入口，加入首个动作后才展示执行目录及追加操作',async()=>{
  vi.spyOn(businessScenariosApi,'list').mockResolvedValue({project_id:'app',documents:[]})
  vi.spyOn(businessScenariosApi,'context').mockResolvedValue(scenarioContext)
  render(<BusinessScenarios {...props('scenario=new')}/>)
  const create=await screen.findByRole('button',{name:'添加已有动作'})
  expect(screen.queryByRole('button',{name:'添加动作'})).not.toBeInTheDocument()
  fireEvent.click(create)
  expect(screen.getByRole('heading',{name:'执行动作'})).toBeVisible()
  expect(screen.getByRole('button',{name:'添加动作'})).toBeVisible()
  expect(screen.queryByRole('button',{name:'添加已有动作'})).not.toBeInTheDocument()
})

it('业务场景目录只读取摘要，不准备编辑上下文或加载正文',async()=>{
  vi.spyOn(businessScenariosApi,'list').mockResolvedValue({project_id:'app',documents:[scenarioSummary]})
  const contextRead=vi.spyOn(businessScenariosApi,'context'),read=vi.spyOn(businessScenariosApi,'read')
  render(<BusinessScenarios {...props('scenario=list')}/>)
  expect(await screen.findByText('订单审批')).toBeVisible()
  expect(contextRead).not.toHaveBeenCalled();expect(read).not.toHaveBeenCalled()
})

it('混合批量逐项显示归属和效果义务，选择资源后只编辑这一项',()=>{
  const allow=scenarioContext.actions[0].cases[0]
  const denied={...allow,case_id:'denied',resource_id:'order-2',resource_owner_test_identity_id:'other',permission:{...allow.permission,intent_id:'deny',expectation:'DENY' as const}}
  const action={...scenarioContext.actions[0],cases:[allow,denied]}
  const current={...scenarioDocument.experiments[0].invocations[0],batch:{strategy:'ATOMIC' as const,array_path:['ids'],response_items_path:null,response_resource_field:null},items:[scenarioDocument.experiments[0].invocations[0].items[0],{id:'second',resource_id:'order-2',subject_identity_id:'owner',permission:denied.permission}]}
  const changed=vi.fn(),added=vi.fn()
  const view=render(<ScenarioResources current={current} context={{...scenarioContext,identities:[...scenarioContext.identities,{identity_id:'other',label:'其他所有者'}]}} options={action.cases.map(value=>({action,value}))} producers={[]} disabled={false} onChange={changed} onAdd={added}/>)
  const resources=within(screen.getByRole('region',{name:'批量资源比较'}))
  expect(resources.getByRole('heading',{name:'批量资源',level:3})).toBeVisible()
  fireEvent.click(resources.getByRole('button',{name:'添加资源'}))
  expect(added).toHaveBeenCalledOnce()
  expect(changed).not.toHaveBeenCalled()
  expect(screen.getAllByText('不应产生效果')).toHaveLength(2)
  expect(screen.getByText('其他所有者')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'编辑第 2 项资源'}))
  fireEvent.click(screen.getByRole('button',{name:'移除此项'}))
  expect(changed).toHaveBeenCalledWith([current.items[0]])
  view.rerender(<ScenarioResources current={{...current,batch:{...current.batch,strategy:'PER_ITEM'}}} context={scenarioContext} options={action.cases.map(value=>({action,value}))} producers={[]} disabled={false} onChange={changed} onAdd={added}/>)
  expect(screen.getByText('应产生完整效果')).toBeVisible()
  expect(screen.getByText('不应产生效果')).toBeVisible()
})

it('业务场景保存响应未知时保留草稿并核对原修订，不重复保存',async()=>{
  vi.spyOn(businessScenariosApi,'list').mockResolvedValue({project_id:'app',documents:[scenarioSummary]})
  vi.spyOn(businessScenariosApi,'context').mockResolvedValue(scenarioContext)
  const save=vi.spyOn(businessScenariosApi,'save').mockRejectedValue(new Error('connection interrupted'))
  const read=vi.spyOn(businessScenariosApi,'read').mockImplementation(async()=>save.mock.calls[0]?.[1]??scenarioDocument)
  render(<BusinessScenarios {...props('scenario='+scenarioDocument.id)}/>)
  fireEvent.change(await screen.findByLabelText('场景名称'),{target:{value:'已调整的订单审批'}})
  fireEvent.click(screen.getByRole('button',{name:'保存并预览检查'}))
  expect(await screen.findByRole('button',{name:'核对原保存结果'})).toBeVisible()
  expect(save).toHaveBeenCalledTimes(1)
  expect(save.mock.calls[0][1]).toMatchObject({revision:2,label:'已调整的订单审批'})
  fireEvent.click(screen.getByRole('button',{name:'核对原保存结果'}))
  await waitFor(()=>expect(screen.getByRole('button',{name:'保存并预览检查'})).toBeVisible())
  expect(read).toHaveBeenCalledWith('app',scenarioDocument.id,2)
  expect(save).toHaveBeenCalledTimes(1)
  expect(screen.getByLabelText('场景名称')).toHaveValue('已调整的订单审批')
})

it('业务场景历史修订保持只读，不能覆盖后来保存的实验',async()=>{
  vi.spyOn(businessScenariosApi,'list').mockResolvedValue({project_id:'app',documents:[{...scenarioSummary,revision:2,label:'后续修订'}]})
  vi.spyOn(businessScenariosApi,'context').mockResolvedValue({...scenarioContext,documents:[{...scenarioSummary,revision:2,label:'后续修订'}]})
  vi.spyOn(businessScenariosApi,'read').mockResolvedValue(scenarioDocument)
  const save=vi.spyOn(businessScenariosApi,'save')
  render(<BusinessScenarios {...props('scenario='+scenarioDocument.id+'&revision=1')}/>)
  expect(await screen.findByRole('button',{name:'打开当前修订'})).toBeVisible()
  expect(screen.getByLabelText('场景名称')).toBeDisabled()
  expect(screen.queryByRole('button',{name:'保存并预览检查'})).not.toBeInTheDocument()
  expect(save).not.toHaveBeenCalled()
})

it('目录不因无关来源失败而阻塞，打开编辑器只读取一份场景上下文',async()=>{
  const read=vi.spyOn(operationFlowsApi,'context').mockResolvedValue(context)
  const summary=vi.spyOn(operationFlowsApi,'summary').mockResolvedValue({project_id:'app',actions:context.actions,flows:[]})
  vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'app',actions:[],preparation_complete:false,recommended_action_id:null,basis_fingerprint:null,policy_epoch:1,source_fingerprint:null,impacts:[]})
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([])
  const sources=vi.spyOn(workbenchApi,'sources').mockRejectedValue(new Error('来源暂不可读'))
  const trials=vi.spyOn(flowTrialsApi,'read')
  const view=render(<Testing {...props()}/>)
  expect(await screen.findByRole('heading',{name:'读取订单'})).toBeVisible()
  expect(summary).toHaveBeenCalledTimes(1)
  expect(read).not.toHaveBeenCalled()
  const directory=screen.getByRole('region',{name:'可维护场景'})
  const selected=within(directory).getByRole('button',{name:/读取订单/})
  fireEvent.click(screen.getByRole('button',{name:'收起详情'}))
  expect(directory).toHaveAttribute('data-detail-open','false')
  expect(selected).toHaveFocus()
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  fireEvent.click(selected)
  expect(screen.getByRole('complementary',{name:'读取订单'})).toBeVisible()
  fireEvent.keyDown(screen.getByRole('button',{name:'收起详情'}),{key:'Escape'})
  expect(selected).toHaveFocus()
  expect(summary).toHaveBeenCalledTimes(1)
  view.rerender(<Testing {...props('action_id=action')}/>)
  expect(await screen.findByRole('heading',{name:'接口流程'})).toBeVisible()
  expect(read).toHaveBeenCalledTimes(1)
  expect(sources).not.toHaveBeenCalled();expect(trials).not.toHaveBeenCalled()
})

it('从请求进入只请求指定来源，仍由编辑器读取当前场景',async()=>{
  const read=vi.spyOn(operationFlowsApi,'context').mockResolvedValue(context)
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([])
  const sources=vi.spyOn(workbenchApi,'sources').mockResolvedValue({project_id:'app',sources:[{source_id:'src',revision:1,kind:'OPENAPI',name:'订单',requests:[{item_id:'request',label:'订单',method:'GET',path:'/orders',pointer:'/orders/get',parameters:[]}],warnings:[],created_at_us:1}],annotations:[],request_references:[]})
  render(<Testing {...props('action_id=action&source_id=src&request_id=request')}/>)
  expect(await screen.findByRole('heading',{name:'接口流程'})).toBeVisible()
  expect(sources).toHaveBeenCalledWith('app',expect.any(AbortSignal),'src')
  expect(read).toHaveBeenCalledTimes(1)
})

it('接口文档选择只产生可选接口，切换起点保留文件且不保存或采用流程',async()=>{
  vi.spyOn(operationFlowsApi,'context').mockResolvedValue(context)
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([])
  const parse=vi.spyOn(operationFlowsApi,'openapi').mockResolvedValue([{label:'读取订单',method:'GET',path:'/orders',fields:[]}])
  const save=vi.spyOn(operationFlowsApi,'save'),candidate=vi.spyOn(operationFlowsApi,'candidate')
  render(<Testing {...props('action_id=action')}/>)
  fireEvent.click(await screen.findByRole('tab',{name:'导入接口文档'}))
  const picker=screen.getByRole('group',{name:'接口文档'}),file=new File(['{}'],'orders.json',{type:'application/json'})
  Object.defineProperty(file,'text',{value:async()=>'openapi-content'})
  fireEvent.change(picker.querySelector('input[type=file]')!,{target:{files:[file]}})
  await screen.findByRole('combobox',{name:'文档中的接口'})
  expect(parse).toHaveBeenCalledExactlyOnceWith('app','openapi-content')
  fireEvent.click(screen.getByRole('tab',{name:'手动填写接口'}))
  fireEvent.click(screen.getByRole('tab',{name:'导入接口文档'}))
  expect(screen.getByText('orders.json')).toBeVisible()
  expect(parse).toHaveBeenCalledTimes(1)
  expect(save).not.toHaveBeenCalled();expect(candidate).not.toHaveBeenCalled()
})

it('起点方式以同级页签切换，返回起点保留本地数据且不保存场景',async()=>{
  vi.spyOn(operationFlowsApi,'context').mockResolvedValue(context)
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([])
  const save=vi.spyOn(operationFlowsApi,'save'),candidate=vi.spyOn(operationFlowsApi,'candidate')
  render(<Testing {...props('action_id=action')}/>)
  const manual=await screen.findByRole('tab',{name:'手动填写接口'})
  fireEvent.click(manual)
  expect(screen.getByRole('tabpanel',{name:'手动填写接口'})).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'开始填写'}))
  fireEvent.change(screen.getByLabelText('用于测试的数据编号'),{target:{value:'order-draft'}})
  fireEvent.click(screen.getByRole('button',{name:/选择起点/}))
  fireEvent.click(screen.getByRole('tab',{name:'使用操作录制'}))
  expect(screen.getByRole('tabpanel',{name:'使用操作录制'})).toBeVisible()
  fireEvent.click(screen.getByRole('tab',{name:'手动填写接口'}))
  fireEvent.click(screen.getByRole('button',{name:'开始填写'}))
  expect(screen.getByLabelText('用于测试的数据编号')).toHaveValue('order-draft')
  expect(candidate).not.toHaveBeenCalled()
  expect(save).not.toHaveBeenCalled()
})

it('普通只读请求直接核对，返回编辑保留请求和数据，阶段切换不保存',async()=>{
  vi.spyOn(operationFlowsApi,'context').mockResolvedValue(context)
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([account])
  const save=vi.spyOn(operationFlowsApi,'save'),candidate=vi.spyOn(operationFlowsApi,'candidate')
  render(<Testing {...props('action_id=action')}/>)
  fireEvent.click(await screen.findByRole('tab',{name:'手动填写接口'}))
  fireEvent.click(screen.getByRole('button',{name:'开始填写'}))
  fireEvent.change(screen.getByLabelText('用于测试的数据编号'),{target:{value:'order-1'}})
  fireEvent.click(screen.getByRole('button',{name:'下一步：设置执行步骤'}))
  fireEvent.change(screen.getByLabelText('接口路径'),{target:{value:'/orders/{case_resource_id}'}})
  expect(screen.queryByRole('button',{name:/结果与恢复/})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'下一步：核对操作'}))
  expect(screen.getByRole('heading',{name:'场景核对'})).toBeVisible()
  expect(screen.getByText('order-1')).toBeVisible()
  fireEvent.click(within(screen.getByRole('list',{name:'操作设置进度'})).getByRole('button',{name:/执行请求/}))
  expect(screen.getByLabelText('接口路径')).toHaveValue('/orders/{case_resource_id}')
  expect(screen.getByRole('tab',{name:'路径取值 1'})).toHaveAttribute('aria-selected','true')
  expect(candidate).not.toHaveBeenCalled();expect(save).not.toHaveBeenCalled()
})

it('结果与恢复独立配置，返回请求保留查询和恢复草稿，恢复缺失仍阻止推进',async()=>{
  vi.spyOn(operationFlowsApi,'context').mockResolvedValue({...context,actions:[{...context.actions[0],state_changing:true,effects:[{effect_id:'visible',label:'订单内容可见',kind:'DATA_DISCLOSURE',protected_projection:['title']}]}]})
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([account])
  const candidate=vi.spyOn(operationFlowsApi,'candidate'),save=vi.spyOn(operationFlowsApi,'save')
  render(<Testing {...props('action_id=action')}/>)
  fireEvent.click(await screen.findByRole('tab',{name:'手动填写接口'}))
  fireEvent.click(screen.getByRole('button',{name:'开始填写'}))
  fireEvent.change(screen.getByLabelText('用于测试的数据编号'),{target:{value:'order-1'}})
  fireEvent.click(screen.getByRole('button',{name:'下一步：设置执行步骤'}))
  fireEvent.change(screen.getByLabelText('接口路径'),{target:{value:'/orders/{case_resource_id}'}})
  expect(screen.queryByLabelText('恢复接口路径')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'准备动态防伪参数'}))
  expect(screen.getByRole('dialog',{name:'准备动态防伪参数'})).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'加入准备步骤'}))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(within(screen.getByRole('navigation',{name:'操作步骤'})).getAllByRole('button')).toHaveLength(2)
  fireEvent.click(screen.getByRole('button',{name:'下一步：结果与恢复'}))
  expect(screen.queryByLabelText('接口路径')).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'下一步：核对操作'})).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox',{name:'订单内容可见'}))
  fireEvent.change(screen.getByLabelText('所有者查询路径'),{target:{value:'/owner/orders/{case_resource_id}'}})
  fireEvent.change(screen.getByLabelText('恢复接口路径'),{target:{value:'/orders/{case_resource_id}/restore'}})
  fireEvent.click(screen.getByRole('button',{name:'上一步'}))
  expect(screen.getByLabelText('接口路径')).toHaveValue('/orders/{case_resource_id}')
  fireEvent.click(screen.getByRole('button',{name:'下一步：结果与恢复'}))
  expect(screen.getByLabelText('所有者查询路径')).toHaveValue('/owner/orders/{case_resource_id}')
  expect(screen.getByLabelText('恢复接口路径')).toHaveValue('/orders/{case_resource_id}/restore')
  expect(screen.getByRole('button',{name:'下一步：核对操作'})).toBeEnabled()
  expect(candidate).not.toHaveBeenCalled();expect(save).not.toHaveBeenCalled()
})

it('协作交接只带请求结构，返回编辑器仍保留原始草稿',async()=>{
  vi.spyOn(operationFlowsApi,'context').mockResolvedValue(context)
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([account])
  function ContextReader(){const handoff=useCurrentHandoff('app');return <output aria-label="交接结构">{JSON.stringify(handoff?.editor)}</output>}
  let view=render(<><Testing {...props('action_id=action')}/><ContextReader/></>)
  fireEvent.click(await screen.findByRole('tab',{name:'手动填写接口'}))
  fireEvent.click(screen.getByRole('button',{name:'开始填写'}))
  fireEvent.change(screen.getByLabelText('用于测试的数据编号'),{target:{value:'order-local'}})
  fireEvent.click(screen.getByRole('button',{name:'下一步：设置执行步骤'}))
  fireEvent.change(screen.getByLabelText('接口路径'),{target:{value:'/orders/{case_resource_id}?token=local-canary'}})
  expect(screen.getByLabelText('交接结构')).not.toHaveTextContent('local-canary')
  expect(screen.getByLabelText('交接结构')).toHaveTextContent('/orders/{case_resource_id}')
  view.unmount()
  view=render(<Testing {...props('action_id=action&resume_draft=1')}/>)
  expect(await screen.findByLabelText('接口路径')).toHaveValue('/orders/{case_resource_id}?token=local-canary')
  expect(sessionStorage.length).toBe(0)
})

it('准确修订先展示候选比较，显式带入前不保存也不采用',async()=>{
  vi.spyOn(operationFlowsApi,'context').mockResolvedValue(context)
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([account])
  const candidate:OperationFlow={id:'flow',revision:3,business_action_id:'action',action_revision:1,subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',provenance:'MANUAL',source_recording_id:null,source_fingerprint:null,actual_resource_id:'order-1',recovery:null,workflow:{target_step_id:'read',steps:[{id:'read',purpose:'TARGET',identity_id:'CASE_SUBJECT',depends_on_step_ids:[],request_template:{method:'GET',path:'/orders/{case_resource_id}',body:{kind:'EMPTY'},input_slots:[{slot_id:'case_resource_id',source:'CASE_RESOURCE_ID',consumer:'PATH'}]},classifier:{accepted:[],denied:[]}}]}}
  const read=vi.spyOn(operationFlowsApi,'read').mockResolvedValue(candidate)
  const save=vi.spyOn(operationFlowsApi,'save'),adopt=vi.spyOn(operationFlowsApi,'adopt')
  render(<Testing {...props('action_id=action&flow_id=flow&revision=3&review=1')}/>)
  expect(await screen.findByRole('dialog',{name:'审阅流程候选 · 第 3 修订'})).toBeVisible()
  expect(read).toHaveBeenCalledWith('app','flow',3,expect.any(AbortSignal))
  expect(save).not.toHaveBeenCalled();expect(adopt).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'带入候选继续核对'}))
  expect(screen.getByRole('button',{name:'确认用于检查'})).toBeVisible()
  expect(adopt).not.toHaveBeenCalled()
})

it("已结束的草稿移除，项目归档只清理所属项目的内存输入",()=>{
  rememberEditorDraft("one",{value:"a"},"app")
  rememberEditorDraft("two",{value:"b"},"other")
  expect(editorDraft("one","other")).toBeUndefined()
  rememberEditorDraft("one",undefined)
  expect(editorDraft("one","app")).toBeUndefined()
  rememberEditorDraft("one",{value:"new"},"app")
  discardProjectEditorDrafts("app")
  expect(editorDraft("one","app")).toBeUndefined()
  expect(editorDraft("two","other")).toEqual({value:"b"})
  rememberEditorDraft("two",undefined)
})
