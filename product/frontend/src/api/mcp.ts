// MCP 设置 API：只在当前页面会话中接收进程内令牌，不写入浏览器持久化存储。

import { request } from './http'

export type MCPAccessLevel = 'READ' | 'PREPARE' | 'EXECUTE'

export type MCPProjectGrant = {
  project_id: string
  level: MCPAccessLevel
}

export type MCPAccessView = {
  schema_version: '1'
  enabled: boolean
  endpoint: string
  access_token: string | null
  default_level: 'READ'
  project_grants: MCPProjectGrant[]
}

export const mcpAccessApi = {
  status: () => request<MCPAccessView>('/api/mcp/access'),
  enable: () => request<MCPAccessView>('/api/mcp/access/enable', { method: 'POST' }),
  regenerate: () => request<MCPAccessView>('/api/mcp/access/regenerate', { method: 'POST' }),
  disable: () => request<MCPAccessView>('/api/mcp/access/disable', { method: 'POST' }),
  setProjectAccess: (projectId: string, level: MCPAccessLevel) =>
    request<MCPAccessView>(`/api/mcp/access/projects/${encodeURIComponent(projectId)}`, {
      method: 'PUT',
      body: JSON.stringify({ schema_version: '1', level }),
    }),
}
