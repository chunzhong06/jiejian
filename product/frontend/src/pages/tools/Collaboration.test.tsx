import {fireEvent, render, screen, waitFor} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {Collaboration} from './Collaboration'
import {CollaborationArtifactReview} from './CollaborationArtifactReview'
import {CollaborationEntry} from '../../entities/runtime/ui/CollaborationEntry'
import {requestCollaboration,useHandoffContext} from '../../entities/runtime/model/handoff'

afterEach(()=>vi.unstubAllGlobals())

it('通过产品接口展示同一任务，区分请求回执和后台完成',async()=>{
  let accepted=false
  const task={task_id:'task',project_id:'app',goal:'核对工单权限',purpose:'CHECK',state:'WAITING_USER',revision:1,
    updated_at_us:1,references:{},reviews:[],questions:[],events:[],execution:null,
    operations:[{operation_id:'operation',capability:'checks.start',title:'执行已核对的检查',state:'WAITING_USER',arguments:{},result:null}]}
  const response=(data:unknown)=>new Response(JSON.stringify({schema_version:'1',data}),{headers:{'content-type':'application/json'}})
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const path=String(input)
    if(path==='/api/collaboration/executor?project_id=app')return response({available:false,provider:'codex-app-server'})
    if(path==='/api/projects/app/collaboration/task/context')return response({task,capabilities:[]})
    if(path==='/api/projects/app/collaboration/task/activity')return response(accepted?[{id:'job',label:'执行已核对的检查',phase:'SUCCEEDED',destination:'/reports?run_id=run'}]:[])
    if(path==='/api/projects/app/collaboration/task')return response(accepted?{...task,state:'WAITING_AGENT',revision:2,latest_check:{run_id:'run',lifecycle:'COMPLETED',verdict:'PASS',revalidation:false},operations:[{...task.operations[0],state:'SUCCEEDED',result:{run_id:'run'}}]}:task)
    if(path==='/api/projects/app/collaboration/task/actions/operation/decision'){
      expect(JSON.parse(String(init?.body))).toEqual({accept:true})
      accepted=true;return response({state:'SUCCEEDED'})
    }
    throw new Error('未预期的产品接口：'+path)
  }))
  render(<Collaboration projectId="app" taskId="task"/>)
  expect(await screen.findByText('核对工单权限')).toBeVisible()
  fireEvent.click(await screen.findByRole('button',{name:'确认并执行'}))
  expect(await screen.findByText('本次范围符合规则')).toBeVisible()
  expect(screen.getByRole('link',{name:'查看检查报告'})).toHaveAttribute('href',expect.stringContaining('run_id=run'))
  fireEvent.click(screen.getByRole('tab',{name:'操作记录'}))
  expect(await screen.findByText('执行已完成')).toBeVisible()
  expect(screen.getByRole('heading',{name:'操作记录'})).toBeVisible()
  expect(screen.getByText('已取得回执')).toBeVisible()
})

it('交代目标即可建立任务，结果未知时重试沿用原标识',async()=>{
  const identifiers:string[]=[]
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    if(init?.method==='POST'){
      expect(String(input)).toBe('/api/projects/app/collaboration')
      const body=JSON.parse(String(init.body));identifiers.push(body.operation_id)
      expect(body.goal).toBe('检查工单访问权限')
      return new Response(JSON.stringify({schema_version:'1',error:{code:'UNKNOWN',message:'回执暂不可达'}}),{status:503})
    }
    expect(String(input)).toBe('/api/projects/app/collaboration-active')
    return new Response(JSON.stringify({schema_version:'1',data:null}))
  }))
  const entry=render(<CollaborationEntry projectId="app" route="/workspace"/>)
  await waitFor(()=>expect(screen.getByRole('button',{name:'Agent 协作，开始任务'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'Agent 协作，开始任务'}))
  expect(await screen.findByRole('combobox',{name:'任务类型'})).toBeEnabled()
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'任务类型'}))
  fireEvent.click(await screen.findByText('整理权限要求',{selector:'.ant-select-item-option-content'}))
  expect(screen.getByLabelText('希望 Agent 完成什么')).toHaveValue('根据当前应用的接口资料，整理业务操作与权限要求，提交待我确认的候选。')
  expect(identifiers).toHaveLength(0)
  fireEvent.change(screen.getByLabelText('希望 Agent 完成什么'),{target:{value:'检查工单访问权限'}})
  fireEvent.click(screen.getByRole('button',{name:'建立协作任务'}))
  expect(await screen.findByText('回执暂不可达')).toBeVisible()
  entry.rerender(<CollaborationEntry projectId="app" route="/workspace" portalHost={document.createElement('nav')}/>)
  expect(screen.getByLabelText('希望 Agent 完成什么')).toHaveValue('检查工单访问权限')
  fireEvent.click(screen.getByRole('button',{name:'核对原交接请求'}))
  await waitFor(()=>expect(identifiers).toHaveLength(2))
  expect(identifiers[0]).toBe(identifiers[1])
})

it.each([['WAITING_AGENT','待继续'],['WAITING_USER','待你确认']])('固定协作入口呈现%s，接续原任务并保留所属应用',async(state,status)=>{
  location.hash='/workspace?project_id=other';
  const fetch=vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    expect(String(input)).toBe('/api/projects/app/collaboration-active');
    expect(init?.method??'GET').toBe('GET');
    return new Response(JSON.stringify({schema_version:'1',data:{task_id:'current',goal:'核对工单权限',state,revision:1,updated_at_us:1}}));
  });
  vi.stubGlobal('fetch',fetch);
  render(<CollaborationEntry projectId="app" route="/permissions?project_id=app"/>);
  expect(await screen.findByText(status)).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'Agent 协作，继续任务'}));
  const query=new URLSearchParams(location.hash.split('?')[1]);
  expect(query.get('task_id')).toBe('current');
  expect(query.get('project_id')).toBe('app');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});


it('等待继续时突出实际启动入口，打开确认前不调用本地模型',async()=>{
  let executionCalls=0;
  const task={task_id:'task',project_id:'app',goal:'继续核对原工单问题',purpose:'UNDERSTAND',state:'WAITING_AGENT',revision:1,updated_at_us:1,references:{},reviews:[],questions:[],events:[],execution:null,operations:[]};
  const response=(data:unknown)=>new Response(JSON.stringify({schema_version:'1',data}));
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{
    const path=String(input);
    if(path.endsWith('/execute')){executionCalls++;return response({})}
    if(path==='/api/collaboration/executor?project_id=app')return response({available:true,ready:true,provider:'codex-app-server',read_only:false});
    if(path.endsWith('/activity'))return response([]);
    if(path==='/api/projects/app/collaboration/task')return response(task);
    throw new Error(path);
  }));
  render(<Collaboration projectId="app" taskId="task"/>);
  fireEvent.click(await screen.findByRole('button',{name:'继续本地 Agent'}));
  expect(await screen.findByRole('dialog',{name:'启动本地 Agent'})).toBeVisible();
  expect(executionCalls).toBe(0);
  expect(screen.getByRole('checkbox',{name:'允许修改当前应用的源码'})).not.toBeChecked();
  expect(screen.getByText(/可能产生费用/)).toBeVisible();
  fireEvent.click(screen.getByText('执行方式与权限边界'));
  expect(screen.getByRole('checkbox',{name:'持续推进当前任务'})).toBeChecked();
  fireEvent.click(screen.getByRole('checkbox',{name:'持续推进当前任务'}));
  expect(screen.getByText('执行 1 个模型回合')).toBeVisible();
  fireEvent.click(screen.getByRole('checkbox',{name:'持续推进当前任务'}));
  expect(screen.getByText(/最多 8 个模型回合/)).toBeVisible();
  expect(screen.queryByRole('heading',{name:'操作记录'})).not.toBeInTheDocument();
});

it.each([['整理权限要求','RULES'],['补齐检查准备','SETUP'],['调查权限问题','CHECK']])('目标示例%s采用自己的完成判据',async(label,purpose)=>{
  const response=(data:unknown)=>new Response(JSON.stringify({schema_version:'1',data}))
  let submitted=false
  vi.stubGlobal('fetch',vi.fn(async(_input:RequestInfo|URL,init?:RequestInit)=>{
    if(init?.method==='POST'){
      const body=JSON.parse(String(init.body));expect(body.purpose).toBe(purpose);submitted=true
      return response({task_id:'created'})
    }
    return response(null)
  }))
  render(<CollaborationEntry projectId="app" route="/permissions?candidate_id=chosen"/>)
  fireEvent.click(await screen.findByRole('button',{name:'Agent 协作，开始任务'}))
  fireEvent.mouseDown(await screen.findByRole('combobox',{name:'任务类型'}))
  fireEvent.click(await screen.findByText(label,{selector:'.ant-select-item-option-content'}))
  fireEvent.change(screen.getByLabelText('希望 Agent 完成什么'),{target:{value:'核对当前业务的权限要求'}})
  fireEvent.click(screen.getByRole('button',{name:'建立协作任务'}))
  await waitFor(()=>expect(submitted).toBe(true))
})

it('当前对象显式补充到原任务，创建和交接都不启动模型',async()=>{
  const response=(data:unknown)=>new Response(JSON.stringify({schema_version:'1',data}))
  let sent:Record<string,unknown>|undefined
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    if(init?.method==='POST'){
      expect(String(input)).toBe('/api/projects/app/collaboration-followup')
      sent=JSON.parse(String(init.body));return response({task_id:'current'})
    }
    return response({task_id:'current',goal:'准备工单',state:'WAITING_AGENT',revision:1,updated_at_us:1})
  }))
  function Current(){useHandoffContext({projectId:'app',label:'当前订单',references:{action_id:'order',return_to:'/testing?action_id=order'}});return <button onClick={()=>requestCollaboration('app','SETUP','补全当前流程')}>请求协作</button>}
  render(<><CollaborationEntry projectId="app" route="/testing?action_id=order"/><Current/></>)
  await screen.findByText('待继续')
  fireEvent.click(screen.getByText('请求协作'))
  expect(await screen.findByText('当前订单')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'补充到原任务'}))
  await waitFor(()=>expect(sent).toMatchObject({task_id:'current',purpose:'SETUP',references:{action_id:'order',return_to:'/testing?action_id=order'}}))
})

it('有建议选项时仍能补充自由回答，选择本身不提交',async()=>{
  const response=(data:unknown)=>new Response(JSON.stringify({schema_version:'1',data}))
  const task={task_id:'task',goal:'整理权限',purpose:'RULES',state:'WAITING_USER',references:{},operations:[],events:[],questions:[{question_id:'question',question:'成员可以修改谁的工单？',options:['仅自己','同团队'],answer:null}],execution:null}
  let answer:string|undefined
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const path=String(input)
    if(init?.method==='POST'){answer=JSON.parse(String(init.body)).answer;return response({})}
    if(path.includes('executor'))return response({available:false})
    if(path.endsWith('/activity'))return response([])
    return response(task)
  }))
  render(<Collaboration projectId="app" taskId="task"/>)
  fireEvent.click(await screen.findByRole('radio',{name:'同团队'}))
  expect(answer).toBeUndefined()
  fireEvent.change(screen.getByLabelText('你的回答或补充说明'),{target:{value:'同团队，但归档后只能负责人修改'}})
  fireEvent.click(screen.getByRole('button',{name:'提交回答并继续'}))
  await waitFor(()=>expect(answer).toBe('同团队，但归档后只能负责人修改'))
})

it('多项待办一次只展开一项，跨事项和页签保留回答，提交后转到剩余待办',async()=>{
  const response=(data:unknown)=>new Response(JSON.stringify({schema_version:'1',data}))
  let answered=false
  const writes:string[]=[]
  const question={question_id:'question',question:'归档后谁可以修改？',options:['仅负责人'],answer:null}
  const review={id:'review',title:'审阅流程候选',destination:'/testing?action_id=action&revision=2&review=1',action_label:'比较并审阅流程'}
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const path=String(input)
    if(init?.method==='POST'){writes.push(path);answered=true;return response({})}
    if(path.includes('executor'))return response({available:false})
    if(path.endsWith('/activity'))return response([])
    return response({task_id:'task',goal:'整理文档权限',purpose:'SETUP',state:'WAITING_USER',revision:answered?2:1,references:{},operations:[],events:[{id:'event',actor:'AGENT',title:'已经读取应用',at_us:1}],questions:answered?[]:[question],reviews:[review],execution:null})
  }))
  render(<Collaboration projectId="app" taskId="task"/>)
  const answer=await screen.findByLabelText('你的回答或补充说明')
  expect(screen.queryByRole('link',{name:'比较并审阅流程'})).not.toBeInTheDocument()
  expect(screen.queryByText('已经读取应用')).not.toBeInTheDocument()
  fireEvent.change(answer,{target:{value:'仅负责人，成员只读'}})
  fireEvent.click(screen.getByRole('button',{name:/审阅产物 审阅流程候选/}))
  expect(screen.getByRole('link',{name:'比较并审阅流程'})).toHaveAttribute('href',expect.stringContaining('revision=2'))
  expect(screen.queryByLabelText('你的回答或补充说明')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab',{name:'操作记录'}))
  expect(screen.getByText('已经读取应用')).toBeVisible()
  fireEvent.click(screen.getByRole('tab',{name:'当前工作'}))
  fireEvent.click(screen.getByRole('button',{name:/补充说明 归档后谁可以修改/}))
  expect(screen.getByLabelText('你的回答或补充说明')).toHaveValue('仅负责人，成员只读')
  expect(writes).toHaveLength(0)
  fireEvent.click(screen.getByRole('button',{name:'提交回答并继续'}))
  expect(await screen.findByRole('link',{name:'比较并审阅流程'})).toBeVisible()
  expect(writes).toEqual(['/api/projects/app/collaboration/task/questions/question'])
})

it('协作事项就地比较准确流程修订，只读查看不保存或采用',async()=>{
  const base={id:'flow_review',revision:1,business_action_id:'review_action',action_revision:1,subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',provenance:'MANUAL',source_recording_id:null,source_fingerprint:null,actual_resource_id:'campus',recovery:null,workflow:{target_step_id:'read',steps:[{id:'read',identity_id:'CASE_SUBJECT',purpose:'TARGET',request_template:{method:'GET',path:'/before',body:{kind:'JSON',value:{private_value:'literal-not-for-review'}}},classifier:{accepted:[],denied:[]},depends_on_step_ids:[]}]}}
  const candidate={...base,revision:2,workflow:{...base.workflow,steps:base.workflow.steps.map(step=>({...step,request_template:{...step.request_template,path:'/after'}}))}}
  const review={id:'flow_review@2',title:'核对执行与恢复步骤',destination:'/testing?action_id=review_action&flow_id=flow_review&revision=2&review=1',action_label:'比较并审阅流程'}
  const task={task_id:'review_task',goal:'补全读取流程',editor:{kind:'FLOW',flow_id:'flow_review',revision:1,action_id:'review_action'},operations:[{capability:'flows.save',state:'SUCCEEDED',result:{id:'flow_review',revision:2}}]}
  const response=(data:unknown)=>new Response(JSON.stringify({schema_version:'1',data}),{headers:{'content-type':'application/json'}})
  const requests:string[]=[]
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    expect(init?.method??'GET').toBe('GET');const path=String(input);requests.push(path)
    if(path.endsWith('/operation-flows/flow_review/2'))return response(candidate)
    if(path.endsWith('/operation-flows/flow_review/1'))return response(base)
    if(path.endsWith('/test-identities'))return response([{identity_id:'owner',label:'负责人'}])
    throw new Error('unexpected '+path)
  }))
  render(<CollaborationArtifactReview projectId="review-app" task={task as never} review={review}/>)
  expect(await screen.findByText('GET /after')).toBeVisible()
  expect(screen.getByText('GET /before')).toBeVisible()
  expect(screen.queryByText('literal-not-for-review')).not.toBeInTheDocument()
  expect(screen.getByText(/与交接时保存的流程比较/)).toBeVisible()
  expect(screen.getByRole('link',{name:'进入流程继续核对'})).toHaveAttribute('href',expect.stringContaining('revision=2'))
  expect(screen.getByRole('link',{name:'进入流程继续核对'})).toHaveAttribute('href',expect.stringContaining('return_to='))
  expect(requests).toHaveLength(3)
  expect(screen.queryByRole('rowheader',{name:'恢复请求'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'完整流程'}))
  expect(screen.getByRole('rowheader',{name:'恢复请求'})).toBeVisible()
})

it('产物链接与成功回执不相符时不读取任意流程',()=>{
  const fetch=vi.fn();vi.stubGlobal('fetch',fetch)
  render(<CollaborationArtifactReview projectId="app" task={{goal:'核对产物',task_id:'task',operations:[]} as never} review={{id:'other@2',title:'产物',destination:'/testing?flow_id=other&revision=2&action_id=action',action_label:'审阅产物'}}/>)
  expect(screen.getByRole('link',{name:'审阅产物'})).toBeVisible()
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.queryByRole('region',{name:'流程结构对照'})).not.toBeInTheDocument()
})

it('不预选建议，暂不确定留在原任务查证，来源链接保留准确修订',async()=>{
 const response=(data:unknown)=>new Response(JSON.stringify({schema_version:'1',data}))
 const task={task_id:'task',project_id:'app',goal:'准备结果证明',purpose:'SETUP',state:'WAITING_USER',revision:1,references:{return_to:'/preparation?proof_sources=1&configure=new'},editor:{kind:'PROOF',basis_id:'basis',action_id:'read',effect_id:'note',resource_binding_id:null,table:'orders',collection:null,protected_column:'note',tenant_column:null,state_column:null},operations:[],events:[],questions:[{question_id:'question',question:'订单备注使用哪个字段？',options:['note','remark'],answer:null}],execution:null}
 const writes:Array<{path:string;answer:string}>=[]
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const path=String(input)
  if(init?.method==='POST'){writes.push({path,answer:JSON.parse(String(init.body)).answer});return response({})}
  if(path.includes('executor'))return response({available:false})
  if(path.endsWith('/activity'))return response([])
  if(path.includes('proof-preparation'))return response({project_id:'app',basis_id:'basis',actions:[{action_id:'read',revision:1,label:'查看订单备注',effects:[{effect_id:'note',label:'订单备注可读',kind:'DATA_DISCLOSURE'}]}],sources:[{source_id:'source',revision:4,adopted:false,config:{action_id:'read',action_revision:1,effect_id:'note',resource_binding_id:null,table:'orders',protected_column:'note'}}]})
  return response(task)
 }))
 render(<Collaboration projectId="app" taskId="task"/>)
 const choice=await screen.findByRole('radio',{name:'note'})
 expect(choice).not.toBeChecked();expect(writes).toHaveLength(0)
 const source=await screen.findByRole('link',{name:/核对这份来源/});expect(source).toHaveAttribute('href',expect.stringContaining('revision=4'))
 fireEvent.click(screen.getByRole('radio',{name:/暂不确定/}))
 expect(screen.getByRole('heading',{level:1,name:task.questions[0].question})).toBeVisible()
 expect(screen.getByText(/条件不足时，Agent 会说明需要补充的信息并等待处理/)).toBeVisible()
 fireEvent.click(screen.getByRole('button',{name:'提交回答并继续'}))
 await waitFor(()=>expect(writes).toHaveLength(1))
 expect(writes[0].path).toContain('/task/questions/question');expect(writes[0].answer).toContain('当前任务已有授权范围内继续查证')
})
