/* AI 工具一级页面：集中呈现 MCP 连接、客户端指引、授权与连接管理。 */

import { Space, Typography } from 'antd'
import type { MCPAccessView } from '../../api/mcp'
import type { ProjectDto } from '../../api/projects'
import type { ApiError } from '../../api/http'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import MCPAccessCard from '../settings/MCPAccessCard'

export function ToolsPage({
  projects, onError, onStatusChange,
}: {
  projects: ProjectDto[]
  onError: (error: ApiError) => void
  onStatusChange?: (view: MCPAccessView) => void
}) {
  return <Space direction="vertical" size="large" className="full-width tools-page">
    <PageTaskHeader title="AI 工具" description="把 Codex、DSH 或其他 MCP 客户端连接到界鉴，并按应用授予本次会话权限。" status="MCP 连接与授权" />
    <Typography.Paragraph>连接分三步：准备长期凭据、显式配置一次客户端、等待客户端完成 initialize。界鉴不会自动修改客户端配置。</Typography.Paragraph>
    <MCPAccessCard open projects={projects} onError={onError} onStatusChange={onStatusChange} />
  </Space>
}
