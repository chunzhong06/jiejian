/* 协作模块连接子页：复用模块页头，再完成连接和逐应用授权。 */

import type { MCPAccessView } from '../../api/system/mcp'
import type { ProjectDto } from '../../api/applications/projects'
import type { ApiError } from '../../api/http'
import { EditorialPage } from '../../shared/ui/Editorial'
import MCPAccessCard from './MCPAccessCard'
import { AgentPageHeader } from './AgentPageHeader'

export function ToolsPage({
  projects, onError, onStatusChange, onNavigate,
}: {
  projects: ProjectDto[]
  onError: (error: ApiError) => void
  onStatusChange?: (view: MCPAccessView) => void
  onNavigate: (path: string) => void
}) {
  return <EditorialPage label="Agent 连接与授权">
    <AgentPageHeader onNavigate={onNavigate}/>
    <MCPAccessCard open projects={projects} onError={onError} onStatusChange={onStatusChange} />
  </EditorialPage>
}
