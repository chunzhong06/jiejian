// 验证协作入口只复制当前授权范围的请求，拒绝陈旧或跨项目内容并保留失败恢复。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { AgentAssistEntry, type AgentAssistContext } from './AgentAssistEntry'
import type { MCPAccessView } from '../../api/system/mcp'
import { WorkPageVisible } from '../runtime/visibility'

const api = vi.hoisted(() => ({ status: vi.fn() }))
vi.mock('../../api/system/mcp', () => ({ mcpAccessApi: api }))
const access: MCPAccessView = { schema_version:'1',paired:true,accepting_connections:true,endpoint:'http://127.0.0.1:5000/mcp',default_level:'READ',project_grants:[{project_id:'app-a',level:'PREPARE'},{project_id:'app-b',level:'PREPARE'}],client_connected:true,client_name:'开发客户端',client_version:null,last_seen_at_us:1,connection_state:'CONNECTED',last_authenticated_at_us:1,last_auth_failure_at_us:null }
const context: AgentAssistContext = {projectId:'app-a',revisionKey:'basis-1',requestText:'请读取当前规则，再保存候选。'}
const clipboard = vi.fn()
beforeEach(() => {
  vi.clearAllMocks(); api.status.mockResolvedValue(access); clipboard.mockResolvedValue(undefined)
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:clipboard}})
})
const props = () => ({projectId:'app-a',contextKey:'rules',title:'整理权限要求',description:'候选需要人批准。',returnTo:'/permissions?candidate=one',loadContext:vi.fn().mockResolvedValue(context),onNavigate:vi.fn(),onRefresh:vi.fn().mockResolvedValue(undefined)})
const open = () => fireEvent.click(screen.getByRole('button',{name:'Agent 协助'}))

it('入口展开后读取内容，复制前再次核对，只报告复制完成',async()=>{
  const p=props();render(<AgentAssistEntry {...p}/>);expect(api.status).not.toHaveBeenCalled()
  open();await screen.findByText('查看协助请求')
  fireEvent.click(screen.getByRole('button',{name:'复制协助请求'}))
  await waitFor(()=>expect(clipboard).toHaveBeenCalledWith(context.requestText))
  expect(p.loadContext).toHaveBeenCalledTimes(2)
  expect(await screen.findByText('协助请求已复制。请粘贴到原来的 Agent 对话中。')).toBeInTheDocument()
  expect(screen.queryByText(/Agent 正在工作|已派单/)).not.toBeInTheDocument()
})

it('未连接时指向开发工具，并保留当前对象返回位置',async()=>{
  api.status.mockResolvedValue({...access,connection_state:'CREDENTIAL_READY',client_connected:false})
  const p=props();render(<AgentAssistEntry {...p}/>);open();await screen.findByText('查看协助请求')
  expect(screen.getByRole('button',{name:'复制协助请求'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'打开开发工具'}))
  expect(p.onNavigate).toHaveBeenCalledWith('/tools?return_to=%2Fpermissions%3Fcandidate%3Done&source_project_id=app-a')
  expect(clipboard).not.toHaveBeenCalled()
})

it('复制前授权已降为只读时阻止交接写入任务',async()=>{
  api.status.mockResolvedValueOnce(access).mockResolvedValue({...access,project_grants:[]})
  render(<AgentAssistEntry {...props()}/>);open();await screen.findByText('查看协助请求')
  fireEvent.click(screen.getByRole('button',{name:'复制协助请求'}))
  await waitFor(()=>expect(screen.getByRole('button',{name:'复制协助请求'})).toBeDisabled())
  expect(clipboard).not.toHaveBeenCalled()
})

it('依据改变先展示新请求，再允许明确复制',async()=>{
  const p=props();p.loadContext.mockResolvedValueOnce(context).mockResolvedValue({...context,revisionKey:'basis-2',requestText:'请按更新后的规则整理。'})
  render(<AgentAssistEntry {...p}/>);open();await screen.findByText('查看协助请求')
  fireEvent.click(screen.getByRole('button',{name:'复制协助请求'}))
  expect(await screen.findByText('当前内容已经变化，请核对更新后的请求，再复制。')).toBeInTheDocument()
  expect(clipboard).not.toHaveBeenCalled()
  fireEvent.click(await screen.findByRole('button',{name:'复制协助请求'}))
  await waitFor(()=>expect(clipboard).toHaveBeenCalledWith('请按更新后的规则整理。'))
})

it('旧项目的迟到响应不能替换新项目请求',async()=>{
  let release!: (value:AgentAssistContext)=>void
  const p=props();p.loadContext.mockReturnValue(new Promise<AgentAssistContext>(resolve=>{release=resolve}))
  const view=render(<AgentAssistEntry {...p}/>);open();await waitFor(()=>expect(p.loadContext).toHaveBeenCalled())
  view.rerender(<AgentAssistEntry {...p} projectId="app-b" loadContext={async()=>({projectId:'app-b',revisionKey:'b-1',requestText:'项目 B 的请求'})}/>);open()
  await screen.findByText('项目 B 的请求');release(context)
  await waitFor(()=>expect(screen.queryByText(context.requestText)).not.toBeInTheDocument())
  fireEvent.click(screen.getByRole('button',{name:'复制协助请求'}))
  await waitFor(()=>expect(clipboard).toHaveBeenCalledWith('项目 B 的请求'))
})

it('复制失败保留可手工选择的请求，不显示成功',async()=>{
  clipboard.mockRejectedValue(new Error('denied'))
  render(<AgentAssistEntry {...props()}/>);open();await screen.findByText('查看协助请求')
  fireEvent.click(screen.getByRole('button',{name:'复制协助请求'}))
  expect(await screen.findByText('复制失败，可以展开请求后手工复制。')).toBeInTheDocument()
  expect(screen.getByText(context.requestText)).toBeInTheDocument()
  expect(screen.queryByText(/协助请求已复制/)).not.toBeInTheDocument()
})

it('隐藏页面不读取连接或业务上下文',async()=>{
  const p=props();render(<WorkPageVisible.Provider value={false}><AgentAssistEntry {...p}/></WorkPageVisible.Provider>);open()
  expect(api.status).not.toHaveBeenCalled();expect(p.loadContext).not.toHaveBeenCalled()
})
