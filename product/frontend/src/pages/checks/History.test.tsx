import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {beforeEach,afterEach,expect,it,vi} from 'vitest'
import {History} from './History'
import {Reports} from './Reports'
import {readRoute} from '../../shared/lib/navigation'

beforeEach(()=>{sessionStorage.clear();location.hash='/reports?project_id=app';vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({schema_version:'1',data:{project_id:'app',items:[],next_cursor:null}}))))})
afterEach(()=>vi.unstubAllGlobals())
const props=()=>({projectId:'app',name:'测试应用',official:false,route:readRoute(),refresh:vi.fn(),onError:vi.fn()})

it('归档链接残留比较参数时仍进入只读记录，不进入当前检查任务',async()=>{
 populatedHistory();location.hash='/archive?project_id=app&view=compare'
 render(<Reports {...props()} archive/>);
 expect(await screen.findByRole('heading',{name:'测试应用的检查记录'})).toBeInTheDocument()
 expect(await screen.findAllByRole('button',{name:'阅读报告'})).toHaveLength(3)
 expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
 expect(screen.queryByRole('link',{name:'发起新检查'})).not.toBeInTheDocument()
})

function populatedHistory(){
 const ids=['c','b','a'].map(letter=>'run_'+letter.repeat(32))
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({schema_version:'1',data:{project_id:'app',items:ids.map((run_id,index)=>({status:{run:{run_id,project_id:'app',created_at_us:(3-index)*1000000,policy_epoch:1,verdict:'PASS',lifecycle:'COMPLETED'}},action_labels:['读取订单'],source_run_id:null,change_id:null})),next_cursor:null}}))))
 return ids
}

it('比较操作栏按实际选择启用，保留时间顺序与返回位置',async()=>{
 const ids=populatedHistory()
 render(<History {...props()}/>);
 fireEvent.click(await screen.findByRole('checkbox',{name:'选择比较记录 cccccccc'}))
 expect(screen.getByRole('button',{name:'查看本轮变化'})).toBeDisabled()
 expect(screen.getByRole('status')).toHaveTextContent('已选 1 条记录，再选 1 条可比较')
 fireEvent.click(screen.getByRole('checkbox',{name:'选择比较记录 bbbbbbbb'}))
 expect(screen.getByRole('status')).toHaveTextContent('已选 2 条记录')
 expect(screen.getByRole('checkbox',{name:'选择比较记录 aaaaaaaa'})).toBeDisabled()
 fireEvent.click(screen.getByRole('button',{name:'查看本轮变化'}))
 const query=readRoute().query
 expect(query.get('baseline')).toBe(ids[1]);expect(query.get('current')).toBe(ids[0])
 expect(query.get('return_to')).toBe('/reports?project_id=app')
})

it('清除比较选择只恢复列表选择，不发起检查或更改记录',async()=>{
 populatedHistory();render(<History {...props()}/>);
 fireEvent.click(await screen.findByRole('checkbox',{name:'选择比较记录 cccccccc'}))
 fireEvent.click(screen.getByRole('button',{name:'清除选择'}))
 expect(screen.queryByRole('button',{name:'查看本轮变化'})).not.toBeInTheDocument()
 expect(screen.getByRole('checkbox',{name:'选择比较记录 cccccccc'})).not.toBeChecked()
 expect(readRoute().path).toBe('/reports')
 expect(screen.getAllByRole('button',{name:'阅读报告'})).toHaveLength(3)
})

it('首次无记录只呈现报告说明和开始动作，不筛选尚不存在的资料',async()=>{
  render(<History {...props()}/>)
  expect(await screen.findByText('这里将保存你的检查报告')).toBeVisible()
  expect(screen.getByRole('link',{name:'发起检查'})).toBeVisible()
  expect(screen.queryByLabelText('查找检查记录')).not.toBeInTheDocument()
})

it('筛选无结果保留条件与清除动作，清除后回到初始空态',async()=>{
  location.hash='/reports?project_id=app&query=订单'
  render(<History {...props()}/>)
  expect(await screen.findByText('没有符合筛选条件的检查')).toBeVisible()
  expect(screen.getByLabelText('查找检查记录')).toHaveValue('订单')
  fireEvent.click(screen.getByRole('button',{name:'清除筛选'}))
  await waitFor(()=>expect(screen.getByText('这里将保存你的检查报告')).toBeVisible())
  expect(screen.queryByLabelText('查找检查记录')).not.toBeInTheDocument()
})

it('读取失败保留错误原因，不伪装成没有历史记录',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({schema_version:'1',error:{code:'STORAGE_STATE',message:'历史记录暂不可读'}}),{status:500})))
  render(<History {...props()}/>)
  expect(await screen.findByRole('alert')).toHaveTextContent('历史记录暂不可读')
  expect(screen.queryByText('这里将保存你的检查报告')).not.toBeInTheDocument()
  expect(screen.queryByRole('link',{name:'发起检查'})).not.toBeInTheDocument()
})

it('失败后就近重读原筛选，不提交检查或清空用户条件',async()=>{
  location.hash='/reports?project_id=app&query=订单'
  let failed=true
  const fetcher=vi.fn(async(_path:string,_init?:RequestInit)=>new Response(JSON.stringify(failed?{schema_version:'1',error:{code:'STORAGE_STATE',message:'历史记录暂不可读'}}:{schema_version:'1',data:{project_id:'app',items:[],next_cursor:null}}),{status:failed?500:200}))
  vi.stubGlobal('fetch',fetcher)
  render(<History {...props()}/>)
  const retry=await screen.findByRole('button',{name:'重新读取检查记录'})
  failed=false
  fireEvent.click(retry)
  expect(await screen.findByText('没有符合筛选条件的检查')).toBeVisible()
  expect(screen.getByLabelText('查找检查记录')).toHaveValue('订单')
  expect(fetcher.mock.calls.every(([path])=>String(path).includes('query=%E8%AE%A2%E5%8D%95'))).toBe(true)
  expect(fetcher.mock.calls.every(([,init])=>!init?.method||init.method==='GET')).toBe(true)
})

it('归档无记录保留归档上下文，不提供新检查动作',async()=>{
  render(<History {...props()} archive/>)
  expect(await screen.findByText('这份示例没有检查记录')).toBeVisible()
  expect(screen.getByRole('link',{name:'返回官方示例'})).toBeVisible()
  expect(screen.queryByRole('link',{name:'发起检查'})).not.toBeInTheDocument()
})

it('归档历史独立保存筛选，进入报告携带准确归档回程',async()=>{
 populatedHistory()
 sessionStorage.setItem('jiejian.studio.history:app:all',JSON.stringify({query:'当前应用筛选',search:'当前应用筛选',filter:'BLOCK',stack:[],scroll:0}))
 location.hash='/archive?project_id=app&query=归档资料'
 render(<History {...props()} archive/>)
 expect(await screen.findByRole('heading',{name:'测试应用的检查记录'})).toBeVisible()
 expect(screen.getByLabelText('查找检查记录')).toHaveValue('归档资料')
 fireEvent.click(screen.getAllByRole('button',{name:'阅读报告'})[0])
 expect(readRoute().path).toBe('/archive')
 const origin=readRoute().query.get('return_to')!
 expect(origin.split('?')[0]).toBe('/archive')
 expect(new URLSearchParams(origin.split('?')[1]).get('query')).toBe('归档资料')
 expect(JSON.parse(sessionStorage.getItem('jiejian.studio.history:app:all')!).query).toBe('当前应用筛选')
 expect(screen.queryByRole('link',{name:'发起新检查'})).not.toBeInTheDocument()
})

it('同名操作按准确修改说明区分，缺失说明保留原操作名，归档同样可读',async()=>{
 const labels=['移除内部包下载限制','允许后撤回内部包访问',null]
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({schema_version:'1',data:{project_id:'app',items:labels.map((change_label,index)=>({status:{run:{run_id:'run_'+String(index).repeat(32),project_id:'app',created_at_us:1000000,policy_epoch:1,verdict:'BLOCK',lifecycle:'COMPLETED'}},action_labels:['取得内部完整包'],change_id:'change-'+index,change_label,change_reason:index===0?'预设演示：VULNERABLE':null,source_run_id:null})),next_cursor:null}}))))
 render(<History {...props()} archive/>)
 expect(await screen.findByText(labels[0]!)).toBeVisible()
 expect(screen.getByText(labels[1]!)).toBeVisible()
 expect(screen.getByText('修改登记说明未保留')).toBeVisible()
 expect(screen.queryByText('预设演示：VULNERABLE')).not.toBeInTheDocument()
 expect(screen.getAllByText('取得内部完整包')).toHaveLength(3)
 expect(screen.getAllByRole('button',{name:'阅读报告'})).toHaveLength(3)
})
