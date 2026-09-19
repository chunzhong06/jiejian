/* 当前项目工作区状态：只恢复 Project 选择与服务端动作级 WorkspaceView。 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/http'
import { projectsApi, type ProjectDto } from '../api/projects'
import { workspaceApi, type WorkspaceViewDto } from '../api/workspace'
import { browserState } from './browserState'

export function useProjectWorkspace(onError: (error: ApiError) => void) {
  const [projects, setProjects] = useState<ProjectDto[]>([])
  const [selected, setSelected] = useState<ProjectDto | null>(null)
  const [workspace, setWorkspace] = useState<WorkspaceViewDto | null>(null)
  const currentProject = useRef<string | null>(null)
  const requestEpoch = useRef(0)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false; requestEpoch.current += 1 } }, [])

  const selectProject = useCallback((project: ProjectDto | null) => {
    if (currentProject.current !== (project?.project_id ?? null)) { requestEpoch.current += 1; setWorkspace(null) }
    currentProject.current = project?.project_id ?? null
    setSelected(project)
    if (project) browserState.writeProject(project)
    else browserState.clearProject()
  }, [])

  const refreshProjects = useCallback(async () => {
    try {
      const current = await projectsApi.projects()
      setProjects(current)
      const recalled = browserState.readProject()
      const authoritative = current.find((item) => item.project_id === recalled?.project_id) ?? null
      selectProject(authoritative)
      return current
    } catch (error) {
      onError(error as ApiError)
      return []
    }
  }, [onError, selectProject])

  const refreshCurrentWorkspace = useCallback(async (project: ProjectDto | null = selected) => {
    if (!project?.project_id) {
      if (!currentProject.current) setWorkspace(null)
      return undefined
    }
    const requestedProject = project.project_id
    const epoch = ++requestEpoch.current
    try {
      const current = await workspaceApi.current(requestedProject)
      // Agent 回读和用户切换可能交错；旧请求不能把另一项目或旧任务写回当前工作区。
      if (!alive.current || currentProject.current !== requestedProject || epoch !== requestEpoch.current) return undefined
      if (current.project.project_id !== requestedProject) throw new ApiError('STATE_PRECONDITION', '工作区返回了另一项目的状态。')
      setWorkspace(current)
      return current
    } catch (error) {
      if (alive.current && currentProject.current === requestedProject && epoch === requestEpoch.current) onError(error as ApiError)
      return undefined
    }
  }, [onError, selected])

  useEffect(() => { void refreshProjects() }, [refreshProjects])
  useEffect(() => { void refreshCurrentWorkspace() }, [refreshCurrentWorkspace])
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') void refreshCurrentWorkspace() }
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => { window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh) }
  }, [refreshCurrentWorkspace])

  return {
    projects,
    selected,
    workspace,
    selectProject,
    refreshProjects,
    refreshCurrentWorkspace,
  }
}
