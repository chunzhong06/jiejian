/* 项目工作区状态
 * 以后端 Project、Readiness 和 Run 为权威事实恢复当前应用与活动任务。
 * browserState 只提供上次查看提示，后端不存在的项目不会被本地状态复活。
 */

import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/http'
import { projectsApi, type ProjectDto, type ProjectReadinessDto } from '../api/projects'
import { runsApi, type RunDto } from '../api/runs'
import { browserState } from './browserState'

export function useProjectWorkspace(onError: (error: ApiError) => void) {
  const [projects, setProjects] = useState<ProjectDto[]>([])
  const [selected, setSelected] = useState<ProjectDto | null>(null)
  const [readiness, setReadiness] = useState<ProjectReadinessDto | null>(null)
  const [runs, setRuns] = useState<RunDto[]>([])

  const selectProject = useCallback((project: ProjectDto | null) => {
    setSelected(project)
    setReadiness(null)
    setRuns([])
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

  const refreshCurrent = useCallback(async () => {
    if (!selected?.project_id) {
      setReadiness(null)
      setRuns([])
      return
    }
    try {
      const [nextReadiness, nextRuns] = await Promise.all([
        projectsApi.readiness(selected.project_id),
        runsApi.runs(selected.project_id),
      ])
      setReadiness(nextReadiness)
      setRuns(nextRuns)
    } catch (error) {
      onError(error as ApiError)
    }
  }, [onError, selected?.project_id])

  useEffect(() => { void refreshProjects() }, [refreshProjects])
  useEffect(() => { void refreshCurrent() }, [refreshCurrent])

  return {
    projects,
    selected,
    readiness,
    runs,
    selectProject,
    refreshProjects,
    refreshCurrent,
  }
}
