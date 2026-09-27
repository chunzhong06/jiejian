/* AI 工具一级页面：以新手步骤完成客户端连接，再管理逐应用的本次允许范围。 */

import { Space } from 'antd'
import type { MCPAccessView } from '../../api/mcp'
import type { ProjectDto } from '../../api/projects'
import type { ApiError } from '../../api/http'
import { PageTaskHeader } from '../../shared/ui/PageTaskHeader'
import MCPAccessCard from './MCPAccessCard'
import { AgentNavigation } from '../../app/navigation/AgentNavigation'

export function ToolsPage({
  projects, onError, onStatusChange, onNavigate,
}: {
  projects: ProjectDto[]
  onError: (error: ApiError) => void
  onStatusChange?: (view: MCPAccessView) => void
  onNavigate: (path: string) => void
}) {
  return <Space direction="vertical" size="large" className="full-width tools-page">
    <PageTaskHeader title="Agent 连接与授权" description="连接 Coding Agent，并明确它可以读取、登记修改或执行检查的范围。连接不表示任务已经发送。" status="连接与使用范围" />
    <AgentNavigation active="connection" onNavigate={onNavigate}/>
    <MCPAccessCard open projects={projects} onError={onError} onStatusChange={onStatusChange} />
  </Space>
}
