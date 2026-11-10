import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import {Agent} from './Agent'
import {agentConnectionsApi,mcpAccessApi,type AgentConnection,type MCPAccessLevel} from '../../entities/runtime/api/mcp'

vi.mock('../../entities/runtime/api/mcp',async original=>{
  const actual=await original<typeof import('../../entities/runtime/api/mcp')>()
  return {...actual,agentConnectionsApi:{...actual.agentConnectionsApi,status:vi.fn(),connect:vi.fn()},mcpAccessApi:{...actual.mcpAccessApi,status:vi.fn(),setProjectAccess:vi.fn(),pause:vi.fn(),resume:vi.fn()}}
})

function prepare(state:AgentConnection['state']='NOT_CONFIGURED',grant?:MCPAccessLevel){
  vi.mocked(agentConnectionsApi.status).mockImplementation(async client=>({client,label:client,state,message:state==='FAILED'?'配置后来有过改动，请重新连接。':'尚未为此客户端准备连接。',code:'TEST',tool_count:0,profiles:[],open_url:null}))
  vi.mocked(mcpAccessApi.status).mockResolvedValue({schema_version:'1',paired:true,accepting_connections:true,endpoint:'http://127.0.0.1:18081/mcp',default_level:'READ',project_grants:grant?[{project_id:'app',level:grant}]:[],client_connected:false,client_name:null,client_version:null,last_seen_at_us:null,connection_state:'CREDENTIAL_READY',last_authenticated_at_us:null,last_auth_failure_at_us:null})
}
beforeEach(()=>{vi.clearAllMocks();prepare()})

it('即时接入开关失败时保留服务器确认值，不连带修改应用授权',async()=>{
  const error=new Error('连接状态未修改'),onError=vi.fn()
  vi.mocked(mcpAccessApi.pause).mockRejectedValue(error)
  render(<Agent projectId="app" name="订单系统" onError={onError} embedded/>)
  const control=await screen.findByRole('switch',{name:'允许开发工具接入'})
  expect(control).toBeChecked()
  fireEvent.click(control)
  await waitFor(()=>expect(onError).toHaveBeenCalledWith(error))
  expect(control).toBeChecked();expect(control).not.toBeDisabled()
  expect(mcpAccessApi.pause).toHaveBeenCalledOnce()
  expect(mcpAccessApi.resume).not.toHaveBeenCalled();expect(mcpAccessApi.setProjectAccess).not.toHaveBeenCalled()
})

it('正常未配置不重复解释，选择工具不写配置，确认前保留所选工具身份',async()=>{
  render(<Agent projectId="app" name="订单系统" onError={vi.fn()} embedded/>)
  await screen.findByText('尚未配置')
  expect(screen.queryByText('尚未为此客户端准备连接。')).not.toBeInTheDocument()
  expect(screen.getAllByText('连接管理')).toHaveLength(1)
  expect(screen.getByText('未授权')).toBeInTheDocument()
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'开发工具'}))
  fireEvent.click(await screen.findByRole('option',{name:'DSH'}))
  await waitFor(()=>expect(agentConnectionsApi.status).toHaveBeenCalledWith('dsh'))
  fireEvent.click(screen.getByRole('button',{name:'配置连接'}))
  expect(await screen.findByRole('dialog',{name:'配置开发工具连接'})).toHaveTextContent('DSH')
  expect(agentConnectionsApi.connect).not.toHaveBeenCalled()
})

it('连接失败保留可执行原因，管理区只提供有配置对象的恢复操作',async()=>{
  prepare('FAILED')
  render(<Agent projectId="app" name="订单系统" onError={vi.fn()} embedded/>)
  expect(await screen.findByText('配置后来有过改动，请重新连接。')).toBeVisible()
  expect(screen.getByText('连接未完成')).toBeInTheDocument()
  fireEvent.click(screen.getByText('连接管理'))
  expect(screen.getByRole('button',{name:'恢复此工具原配置'})).toBeInTheDocument()
})

it('授权草稿保留实际范围，选择高权限不自动保存，确认后才提交',async()=>{
  prepare('NOT_CONFIGURED','READ')
  render(<Agent projectId="app" name="订单系统" onError={vi.fn()} embedded/>)
  await screen.findByText('已授权')
  expect(screen.getByRole('button',{name:'保存权限'})).toBeDisabled()
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'访问范围'}))
  fireEvent.click(await screen.findByRole('option',{name:'准备材料并提交检查'}))
  expect(screen.getByText('当前权限：只读资料与报告，新范围尚未保存。')).toBeInTheDocument()
  expect(screen.getByText('执行前会核对账号、资源和权限范围；权限规则由你确认后生效。')).toBeInTheDocument()
  expect(mcpAccessApi.setProjectAccess).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'保存权限'}))
  const dialog=await screen.findByRole('dialog',{name:'更新工具权限'})
  expect(mcpAccessApi.setProjectAccess).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button',{name:'更新权限'}))
  await waitFor(()=>expect(mcpAccessApi.setProjectAccess).toHaveBeenCalledWith('app','EXECUTE'))
})
