/* AI 工具一级页面：以新手步骤完成客户端连接，再管理逐应用的本次允许范围。 */

import { Space } from 'antd'
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
    <PageTaskHeader title="AI 工具连接" description="选择你使用的工具，按页面上的 5 个步骤完成首次连接；连接成功后，再决定它这次可以为每个应用做到哪一步。" status="连接与使用范围" />
    <MCPAccessCard open projects={projects} onError={onError} onStatusChange={onStatusChange} />
  </Space>
}
