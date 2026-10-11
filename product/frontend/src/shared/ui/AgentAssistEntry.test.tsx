// 验证协作入口只复制当前授权范围的请求，拒绝陈旧或跨项目内容并保留失败恢复。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { AgentAssistEntry, type AgentAssistContext } from './AgentAssistEntry'
import type { MCPAccessView } from '../../api/system/mcp'
import { WorkPageVisible } from '../runtime/visibility'

const api = vi.hoisted(() => ({ status: vi.fn(), connection: vi.fn() }))
vi.mock('../../api/system/mcp', async () => ({ ...await vi.importActual('../../api/system/mcp'), mcpAccessApi: api, agentConnectionsApi: { status: api.connection } }))
const access: MCPAccessView = { schema_version:'1',paired:true,accepting_connections:true,endpoint:'http://127.0.0.1:5000/mcp',default_level:'READ',project_grants:[{project_id:'app-a',level:'PREPARE'},{project_id:'app-b',level:'PREPARE'}],client_connected:true,client_name:'开发客户端',client_version:null,last_seen_at_us:1,connection_state:'CONNECTED',last_authenticated_at_us:1,last_auth_failure_at_us:null }
const context: AgentAssistContext = {projectId:'app-a',revisionKey:'basis-1',requestText:'请读取当前规则，再保存候选。'}
const clipboard = vi.fn()
beforeEach(() => {
  vi.clearAllMocks(); api.status.mockResolvedValue(access); clipboard.mockResolvedValue(undefined)
  api.connection.mockResolvedValue({client:'codex',state:'NOT_CONFIGURED',code:'NONE'})
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:clipboard}})
})
const props = () => ({projectId:'app-a',contextKey:'rules',title:'整理权限要求',description:'候选需要人批准。',returnTo:'/permissions?candidate=one',loadContext:vi.fn().mockResolvedValue(context),onNavigate:vi.fn(),onRefresh:vi.fn().mockResolvedValue(undefined)})
const open = () => fireEvent.click(screen.getByRole('button',{name:'Agent 协助'}))

it('重启后配置已核验且授权足够时可交接，不冒充客户端在线',async()=>{
  api.status.mockResolvedValue({...access,connection_state:'CREDENTIAL_READY',client_connected:false})
  api.connection.mockImplementation(async(client:string)=>({client,state:client==='codex'?'AWAITING_CLIENT':'NOT_CONFIGURED',code:'NONE'}))
  render(<AgentAssistEntry {...props()}/>);open()
  await screen.findByText(/连接配置已核验/)
  fireEvent.click(screen.getByRole('button',{name:'复制协助请求'}))
  await waitFor(()=>expect(clipboard).toHaveBeenCalledWith(context.requestText))
})

it.each(['PAUSED','CREDENTIAL_REJECTED'])('状态 %s 仍阻止交接',async(connection_state)=>{
  api.status.mockResolvedValue({...access,connection_state})
  render(<AgentAssistEntry {...props()}/>);open();await screen.findByText('查看协助请求')
  expect(screen.getByRole('button',{name:'复制协助请求'})).toBeDisabled()
  expect(api.connection).not.toHaveBeenCalled()
})

it('配置可复用但重启后项目授权清空时仍需确认原范围',async()=>{
  api.status.mockResolvedValue({...access,connection_state:'CREDENTIAL_READY',project_grants:[]})
  api.connection.mockImplementation(async(client:string)=>({client,state:client==='codex'?'AWAITING_CLIENT':'NOT_CONFIGURED',code:'NONE'}))
  const p=props();render(<AgentAssistEntry {...p}/>);open();await screen.findByText(/当前应用授权不足/)
  expect(screen.getByRole('button',{name:'复制协助请求'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'调整允许范围'}))
  expect(p.onNavigate).toHaveBeenCalledWith('/tools?return_to=%2Fpermissions%3Fcandidate%3Done&source_project_id=app-a')
})

it('复制前配置已被改动时拒绝交接',async()=>{
  api.status.mockResolvedValue({...access,connection_state:'CREDENTIAL_READY'})
  api.connection.mockImplementation(async(client:string)=>({client,state:'AWAITING_CLIENT',code:'NONE'}))
  render(<AgentAssistEntry {...props()}/>);open();await screen.findByText(/连接配置已核验/)
  api.connection.mockImplementation(async(client:string)=>({client,state:'FAILED',code:'CONFIG_CHANGED'}))
  fireEvent.click(screen.getByRole('button',{name:'复制协助请求'}))
  await screen.findByText(/尚未确认可用的客户端配置/)
  expect(clipboard).not.toHaveBeenCalled()
})

it('入口展开后读取内容，复制前再次核对，只报告复制完成',async()=>{
  const p=props();render(<AgentAssistEntry {...p}/>);expect(api.status).not.toHaveBeenCalled()
  open();await screen.findByText('查看协助请求')
  fireEvent.click(screen.getByRole('button',{name:'复制协助请求'}))
  await waitFor(()=>expect(clipboard).toHaveBeenCalledWith(context.requestText))
  expect(p.loadContext).toHaveBeenCalledTimes(2)
  expect(await screen.findByText('协助请求已复制。请粘贴到原来的 Agent 对话中。')).toBeInTheDocument()
  expect(screen.queryByText(/Agent 正在工作|已派单/)).not.toBeInTheDocument()
})

it('没有核验配置时禁止复制，并打开客户端选择',async()=>{
  api.status.mockResolvedValue({...access,connection_state:'CREDENTIAL_READY',client_connected:false})
  const p=props();render(<AgentAssistEntry {...p}/>);open();await screen.findByText('查看协助请求')
  expect(screen.getByRole('button',{name:'复制协助请求'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'连接 Agent'}))
  expect(await screen.findByText('你正在使用哪个客户端？')).toBeInTheDocument()
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
