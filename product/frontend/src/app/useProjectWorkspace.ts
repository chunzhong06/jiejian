/* 当前项目工作区状态：只恢复 Project 选择与服务端动作级 WorkspaceView。 */

import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/http'
import { projectsApi, type ProjectDto } from '../api/projects'
import { workspaceApi, type WorkspaceViewDto } from '../api/workspace'
import { browserState } from './browserState'

export function useProjectWorkspace(onError: (error: ApiError) => void) {
  const [projects, setProjects] = useState<ProjectDto[]>([])
  const [selected, setSelected] = useState<ProjectDto | null>(null)
  const [workspace, setWorkspace] = useState<WorkspaceViewDto | null>(null)

  const selectProject = useCallback((project: ProjectDto | null) => {
    setSelected(project)
    setWorkspace(null)
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
      setWorkspace(null)
      return undefined
    }
    try {
      const current = await workspaceApi.current(project.project_id)
      setWorkspace(current)
      return current
    } catch (error) {
      onError(error as ApiError)
      return undefined
    }
  }, [onError, selected])

  useEffect(() => { void refreshProjects() }, [refreshProjects])
  useEffect(() => { void refreshCurrentWorkspace() }, [refreshCurrentWorkspace])

  return {
    projects,
    selected,
    workspace,
    selectProject,
    refreshProjects,
    refreshCurrentWorkspace,
  }
}
