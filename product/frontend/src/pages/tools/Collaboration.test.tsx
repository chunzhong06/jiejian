import {fireEvent, render, screen, waitFor} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {Collaboration} from './Collaboration'
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
  fireEvent.click(screen.getByRole('tab',{name:'处理记录'}))
  expect(await screen.findByText('执行已完成')).toBeVisible()
  expect(screen.getByRole('heading',{name:'处理记录'})).toBeVisible()
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
  fireEvent.click(screen.getByRole('button',{name:'整理权限要求'}))
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

it.each([['WAITING_AGENT','待接续'],['WAITING_USER','待你确认']])('固定协作入口呈现%s，接续原任务并保留所属应用',async(state,status)=>{
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


it('等待接续时突出实际启动入口，打开确认前不调用本地模型',async()=>{
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
  expect(screen.queryByRole('heading',{name:'处理记录'})).not.toBeInTheDocument();
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
  fireEvent.click(await screen.findByRole('button',{name:label}))
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
  await screen.findByText('待接续')
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
  fireEvent.click(await screen.findByRole('button',{name:'同团队'}))
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
  fireEvent.click(screen.getByRole('tab',{name:'处理记录'}))
  expect(screen.getByText('已经读取应用')).toBeVisible()
  fireEvent.click(screen.getByRole('tab',{name:'当前工作'}))
  fireEvent.click(screen.getByRole('button',{name:/补充说明 归档后谁可以修改/}))
  expect(screen.getByLabelText('你的回答或补充说明')).toHaveValue('仅负责人，成员只读')
  expect(writes).toHaveLength(0)
  fireEvent.click(screen.getByRole('button',{name:'提交回答并继续'}))
  expect(await screen.findByRole('link',{name:'比较并审阅流程'})).toBeVisible()
  expect(writes).toEqual(['/api/projects/app/collaboration/task/questions/question'])
})
