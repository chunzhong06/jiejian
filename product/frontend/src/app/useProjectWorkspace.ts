/* 当前项目工作区状态：只恢复 Project 选择与服务端动作级 WorkspaceView。 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/http'
import { projectsApi, type ProjectDto } from '../api/projects'
import { workspaceApi, type WorkspaceViewDto } from '../api/workspace'
import { browserState } from './browserState'
import { useLiveRead } from './useLiveRead'

export function useProjectWorkspace(onError: (error: ApiError) => void) {
  const [projects, setProjects] = useState<ProjectDto[]>([])
  const [selected, setSelected] = useState<ProjectDto | null>(null)
  const [workspace, setWorkspace] = useState<WorkspaceViewDto | null>(null)
  const currentProject = useRef<string | null>(null)
  const requestEpoch = useRef(0)
  const pendingRead = useRef<{ projectId: string; epoch: number; promise: Promise<WorkspaceViewDto | undefined> } | undefined>(undefined)
  const acceptedRead = useRef<{ projectId: string; epoch: number; value: WorkspaceViewDto } | undefined>(undefined)
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

  const refreshCurrentWorkspace = useCallback(async (project: ProjectDto | null = selected, quiet = false) => {
    if (!project?.project_id) {
      if (!currentProject.current) setWorkspace(null)
      return undefined
    }
    const requestedProject = project.project_id
    // 背景回读加入已有请求；写后显式刷新仍发新请求，不能复用写入前的快照。
    if (quiet && pendingRead.current?.projectId === requestedProject) return pendingRead.current.promise
    const epoch = ++requestEpoch.current
    const read = (async (): Promise<WorkspaceViewDto | undefined> => {
    try {
      const current = await workspaceApi.current(requestedProject)
      // Agent 回读和用户切换可能交错；旧请求不能把另一项目或旧任务写回当前工作区。
      if (!alive.current || currentProject.current !== requestedProject) return undefined
      if (epoch !== requestEpoch.current) return pendingRead.current?.projectId === requestedProject ? pendingRead.current.promise : acceptedRead.current?.projectId === requestedProject && acceptedRead.current.epoch === requestEpoch.current ? acceptedRead.current.value : undefined
      if (current.project.project_id !== requestedProject) throw new ApiError('STATE_PRECONDITION', '工作区返回了另一项目的状态。')
      setWorkspace(current)
      acceptedRead.current = { projectId: requestedProject, epoch, value: current }
      return current
    } catch (error) {
      if (alive.current && currentProject.current === requestedProject && epoch !== requestEpoch.current) {
        return pendingRead.current?.projectId === requestedProject ? pendingRead.current.promise : acceptedRead.current?.projectId === requestedProject && acceptedRead.current.epoch === requestEpoch.current ? acceptedRead.current.value : undefined
      }
      if (alive.current && currentProject.current === requestedProject && epoch === requestEpoch.current && !quiet) onError(error as ApiError)
      return undefined
    } finally {
      if (pendingRead.current?.epoch === epoch) pendingRead.current = undefined
    }
    })()
    pendingRead.current = { projectId: requestedProject, epoch, promise: read }
    return read
  }, [onError, selected])

  useEffect(() => { void refreshProjects() }, [refreshProjects])
  const synchronization = useLiveRead(selected?.project_id, async () => {
    const next = await refreshCurrentWorkspace(selected, true)
    if (!next) throw new Error('Workspace read unavailable')
  }, 5000)


  return {
    projects,
    selected,
    workspace,
    selectProject,
    synchronization,
    refreshProjects,
    refreshCurrentWorkspace,
  }
}
