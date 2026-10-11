// 一键连接必须先选客户端，写入配置不冒充连接；项目授权仍由本机用户决定。
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { MCPAccessCard } from './MCPAccessCard'
const api=vi.hoisted(()=>({status:vi.fn(),connect:vi.fn(),connection:vi.fn(),grant:vi.fn(),pause:vi.fn(),forget:vi.fn()}))
vi.mock('../../api/system/mcp',async()=>({...await vi.importActual<typeof import('../../api/system/mcp')>('../../api/system/mcp'),mcpAccessApi:{status:api.status,setProjectAccess:api.grant,pause:api.pause,forget:api.forget},agentConnectionsApi:{connect:api.connect,status:api.connection}}))
const access={schema_version:'1',paired:true,accepting_connections:true,connection_state:'CREDENTIAL_READY',project_grants:[],client_name:null}
const waiting={client:'dsh',label:'DSH',state:'AWAITING_CLIENT',message:'配置已准备好，等待客户端。',code:'NONE',tool_count:0,profiles:[],open_url:null}
const props=()=>({open:true,projects:[{project_id:'p1',name:'测试应用'}],onError:vi.fn(),onStatusChange:vi.fn()})
beforeEach(()=>{vi.resetAllMocks();api.status.mockResolvedValue(access);api.connect.mockResolvedValue(waiting);api.connection.mockResolvedValue(waiting).mockResolvedValueOnce({...waiting,state:'NOT_CONFIGURED'});api.grant.mockResolvedValue(access);api.pause.mockResolvedValue({...access,connection_state:'PAUSED'});api.forget.mockResolvedValue({...access,paired:false})})
it('点击连接后才展示六客户端，不展示复制凭据或配置教程',async()=>{
 render(<MCPAccessCard {...props()}/>);const start=await screen.findByRole('button',{name:'连接 Agent'});await waitFor(()=>expect(start).toBeEnabled());expect(screen.queryByRole('button',{name:/DeepSeek Harness/})).not.toBeInTheDocument();fireEvent.click(start)
 for(const name of [/DSH/,/Codex/,/ZCode/,/TRAE/,/CodeBuddy Code/,/Qoder CLI/])expect(screen.getByRole('button',{name})).toBeInTheDocument()
 fireEvent.click(screen.getByRole('button',{name:/DSH/}));await screen.findByText(waiting.message);expect(api.connect).toHaveBeenCalledWith('dsh',undefined);expect(screen.queryByText('客户端已读取工具')).not.toBeInTheDocument();expect(screen.queryByRole('button',{name:'复制凭据'})).not.toBeInTheDocument()
})
it('真实工具读取回执才显示已读取工具',async()=>{
 const p=props();render(<MCPAccessCard {...p}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'连接 Agent'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'连接 Agent'}));fireEvent.click(screen.getByRole('button',{name:/DSH/}));await screen.findByText(waiting.message)
 api.connection.mockResolvedValue({...waiting,state:'TOOLS_READ',tool_count:44,message:'已读取 44 个工具'});fireEvent.click(screen.getByRole('button',{name:'重新检测'}));await screen.findByText('客户端已读取工具');expect(screen.getByRole('button',{name:'返回当前工作'})).toBeInTheDocument()
})
it('握手确认即可反馈连接，无需业务调用或重新安装',async()=>{
 api.connection.mockReset().mockResolvedValue({...waiting,state:'CONNECTED',message:'协议通道已确认'})
 render(<MCPAccessCard {...props()}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'连接 Agent'})).toBeEnabled())
 fireEvent.click(screen.getByRole('button',{name:'连接 Agent'}));fireEvent.click(screen.getByRole('button',{name:/DSH/}))
 await screen.findByText('MCP 连接已确认')
 expect(screen.getByRole('button',{name:'返回当前工作'})).toBeEnabled()
 expect(screen.queryByText('客户端已读取工具')).not.toBeInTheDocument()
 expect(api.connect).not.toHaveBeenCalled();expect(api.grant).not.toHaveBeenCalled()
})
it('未知写回执只检测，不重放安装',async()=>{
 api.connect.mockRejectedValue(new Error('lost'));render(<MCPAccessCard {...props()}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'连接 Agent'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'连接 Agent'}));fireEvent.click(screen.getByRole('button',{name:/DSH/}));await screen.findByText(/配置操作的回执尚未确认/);expect(screen.queryByRole('button',{name:'重新连接'})).not.toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'重新检测'}));await screen.findByText(waiting.message);expect(api.connect).toHaveBeenCalledTimes(1)
})
it('失败原因显示为错误且可重新连接',async()=>{
 api.connect.mockResolvedValue({...waiting,state:'FAILED',code:'CLIENT_NOT_FOUND',message:'没有找到 DSH 配置档。'});render(<MCPAccessCard {...props()}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'连接 Agent'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'连接 Agent'}));fireEvent.click(screen.getByRole('button',{name:/DSH/}));await screen.findByText('没有找到 DSH 配置档。');expect(screen.getByRole('button',{name:'重新连接'})).toBeInTheDocument()
})
it('连接不会自动提高项目授权',async()=>{
 render(<MCPAccessCard {...props()}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'调整这次允许范围'})).toBeEnabled());expect(api.grant).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'调整这次允许范围'}));fireEvent.click(screen.getByRole('radio',{name:'协助整理'}));fireEvent.click(screen.getByRole('button',{name:'保存这次允许范围'}));await waitFor(()=>expect(api.grant).toHaveBeenCalledWith('p1','PREPARE'))
})
it('关闭后安装的迟到回执不污染再次打开',async()=>{
 let resolve:(value:unknown)=>void=()=>{};api.connect.mockImplementation(()=>new Promise(done=>{resolve=done}));const p=props();const view=render(<MCPAccessCard {...p}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'连接 Agent'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'连接 Agent'}));fireEvent.click(screen.getByRole('button',{name:/DSH/}));await waitFor(()=>expect(api.connect).toHaveBeenCalledTimes(1));view.rerender(<MCPAccessCard {...p} open={false}/>);await act(async()=>resolve({...waiting,state:'TOOLS_READ'}));view.rerender(<MCPAccessCard {...p}/>);expect(screen.queryByText('客户端已读取工具')).not.toBeInTheDocument()
})

it('已有连接再次选择只读取状态，不重装或作废回执',async()=>{
 api.connection.mockReset().mockResolvedValue({...waiting,client:'codex',state:'TOOLS_READ',tool_count:44,message:'Codex 已读取工具'});render(<MCPAccessCard {...props()}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'连接 Agent'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'连接 Agent'}));fireEvent.click(screen.getByRole('button',{name:/Codex/}));await screen.findByText('客户端已读取工具');expect(api.connect).not.toHaveBeenCalled()
})
it('服务重启后成功调用原连接也显示可用',async()=>{
 api.connection.mockReset().mockResolvedValue({...waiting,state:'REQUEST_ACCEPTED',message:'客户端已通过原连接调用界鉴工具。'});render(<MCPAccessCard {...props()}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'连接 Agent'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'连接 Agent'}));fireEvent.click(screen.getByRole('button',{name:/DSH/}));await screen.findByText('客户端已调用工具');expect(api.connect).not.toHaveBeenCalled()
})

it('已保存但尚无新请求时可以返回工作，不重新配置',async()=>{
 api.connection.mockReset().mockResolvedValue({...waiting,client:'codex'});render(<MCPAccessCard {...props()}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'连接 Agent'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'连接 Agent'}));fireEvent.click(screen.getByRole('button',{name:/Codex/}));await screen.findByText('配置已保存，可复用');expect(screen.getByRole('button',{name:'返回当前工作'})).toBeInTheDocument();expect(screen.queryByText('客户端已读取工具')).not.toBeInTheDocument();expect(api.connect).not.toHaveBeenCalled()
})

it.each(['SERVICE_UNAVAILABLE','SESSION_EXPIRED','CONNECT_TIMEOUT','RESPONSE_TIMEOUT'])('通信错误 %s 检测可恢复，且不显示重装操作',async(code)=>{
 api.connection.mockReset().mockResolvedValue({...waiting,state:'FAILED',code,message:'原请求未重放'});render(<MCPAccessCard {...props()}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'连接 Agent'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'连接 Agent'}));fireEvent.click(screen.getByRole('button',{name:/DSH/}));await screen.findByText('原请求未重放');expect(screen.queryByRole('button',{name:'重新连接'})).not.toBeInTheDocument()
 let finish!:(value:unknown)=>void;api.connection.mockImplementation(()=>new Promise(resolve=>{finish=resolve}));const button=screen.getByRole('button',{name:'重新检测'});fireEvent.click(button);expect(button).toHaveClass('ant-btn-loading');await act(async()=>finish({...waiting,state:'REQUEST_ACCEPTED'}));await screen.findByText('客户端已调用工具');expect(api.connect).not.toHaveBeenCalled()
})

it('旧 DSH 配置明确提示更新，查看状态不自动写入',async()=>{
 api.connection.mockReset().mockResolvedValue({...waiting,state:'FAILED',code:'CONFIG_UPDATE_REQUIRED',message:'旧配置需要更新启动策略'});render(<MCPAccessCard {...props()}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'连接 Agent'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'连接 Agent'}));fireEvent.click(screen.getByRole('button',{name:/DSH/}));await screen.findByText('旧配置需要更新启动策略');expect(api.connect).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'更新连接配置'}));await waitFor(()=>expect(api.connect).toHaveBeenCalledTimes(1));expect(api.grant).not.toHaveBeenCalled()
})
