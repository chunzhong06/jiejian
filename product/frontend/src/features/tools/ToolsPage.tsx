/* 开发工具连接工作面：复用同一连接内容和页头，不重复嵌套导航。 */

import { Button } from 'antd'
import type { MCPAccessView } from '../../api/system/mcp'
import type { ProjectDto } from '../../api/applications/projects'
import type { ApiError } from '../../api/http'
import { EditorialPage } from '../../shared/ui/Editorial'
import MCPAccessCard from './MCPAccessCard'

export function ToolsPage({
  projects, onError, onStatusChange, onReturn, sourceProjectId,
}: {
  projects: ProjectDto[]
  onError: (error: ApiError) => void
  onStatusChange?: (view: MCPAccessView) => void
  onReturn?: () => void
  sourceProjectId?: string
}) {
  return <EditorialPage label="开发工具连接与授权" width="summary">
    {onReturn && <Button type="link" onClick={onReturn}>返回刚才的任务</Button>}
    <MCPAccessCard open projects={projects} onError={onError} onStatusChange={onStatusChange} sourceProjectId={sourceProjectId} />
  </EditorialPage>
}
