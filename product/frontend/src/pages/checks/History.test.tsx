import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {beforeEach,afterEach,expect,it,vi} from 'vitest'
import {History} from './History'
import {readRoute} from '../../shared/lib/navigation'

beforeEach(()=>{sessionStorage.clear();location.hash='/reports?project_id=app';vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({schema_version:'1',data:{project_id:'app',items:[],next_cursor:null}}))))})
afterEach(()=>vi.unstubAllGlobals())
const props=()=>({projectId:'app',name:'测试应用',official:false,route:readRoute(),refresh:vi.fn(),onError:vi.fn()})

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

it('归档无记录保留归档上下文，不提供新检查动作',async()=>{
  render(<History {...props()} archive/>)
  expect(await screen.findByText('这份示例没有检查记录')).toBeVisible()
  expect(screen.getByRole('link',{name:'返回官方示例'})).toBeVisible()
  expect(screen.queryByRole('link',{name:'发起检查'})).not.toBeInTheDocument()
})
