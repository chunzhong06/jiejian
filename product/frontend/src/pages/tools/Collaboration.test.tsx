import {fireEvent, render, screen, waitFor} from '@testing-library/react'
import {afterEach, expect, it, vi} from 'vitest'
import {Collaboration} from './Collaboration'
import {CollaborationEntry} from '../../entities/runtime/ui/CollaborationEntry'

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
  expect(await screen.findByText('执行已完成')).not.toBeVisible()
  fireEvent.click(screen.getByText('后台执行记录'))
  expect(screen.getByText('执行已完成')).toBeVisible()
  expect(screen.getByText('已取得回执')).toBeVisible()
  expect(screen.getByRole('link',{name:'查看检查报告'})).toHaveAttribute('href',expect.stringContaining('run_id=run'))
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
  render(<CollaborationEntry projectId="app" route="/workspace"/>)
  await waitFor(()=>expect(screen.getByRole('button',{name:'开始协作'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'开始协作'}))
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('目标'),{target:{value:'检查工单访问权限'}})
  fireEvent.click(screen.getByRole('button',{name:'建立任务'}))
  expect(await screen.findByText('回执暂不可达')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'建立任务'}))
  await waitFor(()=>expect(identifiers).toHaveLength(2))
  expect(identifiers[0]).toBe(identifiers[1])
})

it('固定协作入口接续原任务，并保留所属应用而不创建新任务',async()=>{
  location.hash='/workspace?project_id=other';
  const fetch=vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    expect(String(input)).toBe('/api/projects/app/collaboration-active');
    expect(init?.method??'GET').toBe('GET');
    return new Response(JSON.stringify({schema_version:'1',data:{task_id:'current',goal:'核对工单权限',state:'WAITING_AGENT',revision:1,updated_at_us:1}}));
  });
  vi.stubGlobal('fetch',fetch);
  render(<CollaborationEntry projectId="app" route="/permissions?project_id=app"/>);
  fireEvent.click(await screen.findByRole('button',{name:'继续协作'}));
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
    if(path==='/api/collaboration/executor?project_id=app')return response({available:true,ready:true,provider:'codex-app-server',read_only:true});
    if(path.endsWith('/activity'))return response([]);
    if(path==='/api/projects/app/collaboration/task')return response(task);
    throw new Error(path);
  }));
  render(<Collaboration projectId="app" taskId="task"/>);
  fireEvent.click(await screen.findByRole('button',{name:'继续本地 Agent'}));
  expect(await screen.findByRole('dialog',{name:'在界鉴中继续这项任务'})).toBeVisible();
  expect(executionCalls).toBe(0);
  expect(screen.queryByRole('heading',{name:'处理记录'})).not.toBeInTheDocument();
});
