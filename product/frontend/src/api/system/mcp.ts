// MCP 设置 API：读取当前连接状态，并让 GUI 显式管理长期配对与本次会话。

import { request } from '../http'

export type MCPAccessLevel = 'READ' | 'PREPARE' | 'EXECUTE'
export type MCPConnectionState = 'DISABLED' | 'CREDENTIAL_READY' | 'AUTHENTICATED' | 'CONNECTED' | 'CREDENTIAL_REJECTED' | 'PAUSED'

export type MCPProjectGrant = {
  project_id: string
  level: MCPAccessLevel
}

export type MCPAccessView = {
  schema_version: '1'
  paired: boolean
  accepting_connections: boolean
  endpoint: string
  default_level: 'READ'
  project_grants: MCPProjectGrant[]
  client_connected: boolean
  client_name: string | null
  client_version: string | null
  last_seen_at_us: number | null
  connection_state: MCPConnectionState
  last_authenticated_at_us: number | null
  last_auth_failure_at_us: number | null
}

export type MCPAccessCredentialView = MCPAccessView & { access_token: string }

export const agentClients = [
  {key:'dsh',name:'DSH',description:'DeepSeek Harness'}, {key:'codex',name:'Codex',description:'OpenAI'},
  {key:'zcode',name:'ZCode',description:'智谱'}, {key:'trae',name:'TRAE',description:'字节跳动'},
  {key:'codebuddy',name:'CodeBuddy Code',description:'腾讯'}, {key:'qoder',name:'Qoder CLI',description:'Qoder'},
] as const
export type AgentClient = typeof agentClients[number]['key']
export type AgentConnection = {
  client: AgentClient; label: string
  state: 'NOT_CONFIGURED'|'AWAITING_CLIENT'|'STARTED'|'TOOLS_READ'|'REQUEST_ACCEPTED'|'DISCONNECTED'|'FAILED'
  message: string; code: string; tool_count: number; profiles: string[]; open_url: string|null; config_path?: string
}
export const agentConnectionsApi = {
  connect: (client:AgentClient,profile?:string)=>request<AgentConnection>(`/api/mcp/clients/${client}/connect`,{method:'POST',body:JSON.stringify({profile:profile??null})}),
  status: (client:AgentClient)=>request<AgentConnection>(`/api/mcp/clients/${client}`),
  restore: (client:AgentClient)=>request<AgentConnection>(`/api/mcp/clients/${client}/restore`,{method:'POST'}),
}

export const mcpAccessApi = {
  status: () => request<MCPAccessView>('/api/mcp/access'),
  pair: () => request<MCPAccessCredentialView>('/api/mcp/access/pair', { method: 'POST' }),
  reveal: () => request<MCPAccessCredentialView>('/api/mcp/access/reveal', { method: 'POST' }),
  rotate: () => request<MCPAccessCredentialView>('/api/mcp/access/rotate', { method: 'POST' }),
  resume: () => request<MCPAccessView>('/api/mcp/access/resume', { method: 'POST' }),
  pause: () => request<MCPAccessView>('/api/mcp/access/pause', { method: 'POST' }),
  forget: () => request<MCPAccessView>('/api/mcp/access/forget', { method: 'POST' }),
  setProjectAccess: (projectId: string, level: MCPAccessLevel) =>
    request<MCPAccessView>(`/api/mcp/access/projects/${encodeURIComponent(projectId)}`, {
      method: 'PUT',
      body: JSON.stringify({ schema_version: '1', level }),
    }),
}
