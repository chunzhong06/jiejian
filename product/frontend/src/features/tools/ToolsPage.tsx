/* 开发工具连接工作面：复用同一连接内容和页头，不重复嵌套导航。 */

import { Button } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { MCPAccessView } from '../../api/system/mcp'
import { projectsApi, type ProjectDto } from '../../api/applications/projects'
import type { ApiError } from '../../api/http'
import { EditorialPage } from '../../shared/ui/Editorial'
import MCPAccessCard from './MCPAccessCard'
import { useLiveRead } from '../../shared/runtime/useLiveRead'

export function ToolsPage({
  projects, onError, onStatusChange, onReturn, sourceProjectId,
}: {
  projects: ProjectDto[]
  onError: (error: ApiError) => void
  onStatusChange?: (view: MCPAccessView) => void
  onReturn?: () => void
  sourceProjectId?: string
}) {
  const [currentProjects, setCurrentProjects] = useState<ProjectDto[] | null>(null)
  const [projectListState, setProjectListState] = useState<'loading' | 'ready' | 'failed'>('loading')
  const request = useRef(0), alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false; request.current++ } }, [])
  // 原 Agent 或另一标签页接入应用后，壳层初始列表可能已过期；授权面独立回读，
  // 不切换当前项目、不关闭正在编辑的授权弹窗，也不把连接成功当作项目授权。
  const refreshProjects = useCallback(async () => {
    const stamp = ++request.current
    try {
      const next = await projectsApi.projects()
      if (alive.current && stamp === request.current) { setCurrentProjects(next); setProjectListState('ready') }
    } catch (error) {
      if (alive.current && stamp === request.current) setProjectListState('failed')
      throw error
    }
  }, [])
  useLiveRead('agent-projects', refreshProjects, 10000)
  return <EditorialPage label="开发工具连接与授权" width="summary">
    {onReturn && <Button type="link" onClick={onReturn}>返回刚才的任务</Button>}
    <MCPAccessCard open projects={currentProjects ?? projects} projectListState={projectListState} onRefreshProjects={() => { void refreshProjects().catch(() => {}) }} onError={onError} onStatusChange={onStatusChange} sourceProjectId={sourceProjectId} />
  </EditorialPage>
}
