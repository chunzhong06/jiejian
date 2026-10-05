/* 开发工具连接工作面：复用同一连接内容和页头，不重复嵌套导航。 */

import type { MCPAccessView } from '../../api/system/mcp'
import type { ProjectDto } from '../../api/applications/projects'
import type { ApiError } from '../../api/http'
import { EditorialPage } from '../../shared/ui/Editorial'
import MCPAccessCard from './MCPAccessCard'

export function ToolsPage({
  projects, onError, onStatusChange,
}: {
  projects: ProjectDto[]
  onError: (error: ApiError) => void
  onStatusChange?: (view: MCPAccessView) => void
}) {
  return <EditorialPage label="开发工具连接与授权">
    <MCPAccessCard open projects={projects} onError={onError} onStatusChange={onStatusChange} />
  </EditorialPage>
}
