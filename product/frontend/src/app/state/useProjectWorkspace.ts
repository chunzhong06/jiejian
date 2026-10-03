/* 当前项目工作区状态：只恢复 Project 选择与服务端动作级 WorkspaceView。 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/http'
import { experienceApi, type OfficialExperienceDto } from '../../api/applications/experience'
import { projectsApi, type ProjectDto } from '../../api/applications/projects'
import { workspaceApi, type WorkspaceViewDto } from '../../api/workspace'
import { browserState } from '../../shared/runtime/browserState'
import { useLiveRead } from '../../shared/runtime/useLiveRead'

export function useProjectWorkspace(onError: (error: ApiError) => void) {
  const [projects, setProjects] = useState<ProjectDto[]>([])
  const [selected, setSelected] = useState<ProjectDto | null>(null)
  const [workspace, setWorkspace] = useState<WorkspaceViewDto | null>(null)
  const [experience, updateExperience] = useState<OfficialExperienceDto | null>(null)
  const currentProject = useRef<string | null>(null)
  const selectionEpoch = useRef(0)
  const projectsEpoch = useRef(0)
  const requestEpoch = useRef(0)
  const pendingRead = useRef<{ projectId: string; epoch: number; promise: Promise<WorkspaceViewDto | undefined> } | undefined>(undefined)
  const acceptedRead = useRef<{ projectId: string; epoch: number; value: WorkspaceViewDto } | undefined>(undefined)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false; requestEpoch.current += 1 } }, [])

  const selectProject = useCallback((project: ProjectDto | null) => {
    selectionEpoch.current += 1
    if (currentProject.current !== (project?.project_id ?? null)) { requestEpoch.current += 1; setWorkspace(null) }
    currentProject.current = project?.project_id ?? null
    setSelected(project)
    if (project) browserState.writeProject(project)
    else browserState.clearProject()
  }, [])

  const setExperience = useCallback((value: OfficialExperienceDto | null) => {
    // 启停回执优先于操作前已发出的状态读取。
    projectsEpoch.current += 1
    updateExperience(value)
  }, [])

  const refreshProjects = useCallback(async () => {
    const epoch = ++projectsEpoch.current
    const selection = selectionEpoch.current
    try {
      // 等来源和运行状态一起返回后才恢复，避免旧任务先闪现并触发工作区回读。
      const [projectRead, environmentRead] = await Promise.allSettled([projectsApi.projects(), experienceApi.status()])
      if (!alive.current || epoch !== projectsEpoch.current) return []
      if (projectRead.status === 'rejected') throw projectRead.reason
      const current = projectRead.value
      const environment = environmentRead.status === 'fulfilled' ? environmentRead.value : null
      updateExperience(environment)
      setProjects(current)
      if (selection === selectionEpoch.current) {
        const recalled = browserState.readProject()
        const authoritative = current.find((item) => item.project_id === recalled?.project_id) ?? null
        const official = authoritative?.official_sample || (authoritative && [environment?.project_id, environment?.history_project_id].includes(authoritative.project_id))
        const running = environment?.active && environment.project_id === authoritative?.project_id && environment.lifecycle === 'RUNNING'
        selectProject(official && !running ? null : authoritative)
      }
      if (environmentRead.status === 'rejected') onError(environmentRead.reason as ApiError)
      return current
    } catch (error) {
      if (alive.current && epoch === projectsEpoch.current) onError(error as ApiError)
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
    experience,
    setExperience,
    selected,
    workspace,
    selectProject,
    synchronization,
    refreshProjects,
    refreshCurrentWorkspace,
  }
}
