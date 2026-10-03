// 项目切换与后台刷新交错时，只接受当前项目的最新响应。
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import type { WorkspaceViewDto } from '../../api/workspace'
import { useProjectWorkspace } from './useProjectWorkspace'
import { browserState } from '../../shared/runtime/browserState'

const api = vi.hoisted(() => ({ projects: vi.fn(), current: vi.fn(), experience: vi.fn() }))
vi.mock('../../api/applications/experience', () => ({ experienceApi: { status: api.experience } }))
vi.mock('../../api/applications/projects', () => ({ projectsApi: { projects: api.projects } }))
vi.mock('../../api/workspace', () => ({ workspaceApi: { current: api.current } }))
vi.mock('../../shared/runtime/browserState', () => ({ browserState: { readProject: () => ({ project_id: 'p1' }), writeProject: vi.fn(), clearProject: vi.fn() } }))
const workspace = (id: string) => ({ project: { project_id: id }, actors: [], actions: [], areas: [], primary_task: null } as unknown as WorkspaceViewDto)
beforeEach(() => { vi.clearAllMocks(); api.experience.mockResolvedValue({ active: false, project_id: null }); api.projects.mockResolvedValue([{ project_id: 'p1' }, { project_id: 'p2' }]); api.current.mockResolvedValue(workspace('p1')) })

it.each(['STOPPED', 'UNKNOWN', 'STARTING'])('不自动恢复%s的旧示例，也不读取旧待办', async lifecycle => {
  api.projects.mockResolvedValue([{ project_id: 'p1', official_sample: true }])
  api.experience.mockResolvedValue({ active: false, project_id: 'p1', lifecycle })
  const onError = vi.fn(); const { result } = renderHook(() => useProjectWorkspace(onError))
  await waitFor(() => expect(result.current.projects).toHaveLength(1))
  expect(result.current.selected).toBeNull()
  expect(browserState.clearProject).toHaveBeenCalled()
  expect(api.current).not.toHaveBeenCalled()
})

it('状态读取失败仍恢复普通应用，但不恢复已知示例', async () => {
  api.projects.mockResolvedValue([{ project_id: 'p1', official_sample: true }])
  api.experience.mockRejectedValue(new Error('offline'))
  const onError = vi.fn(); const { result } = renderHook(() => useProjectWorkspace(onError))
  await waitFor(() => expect(onError).toHaveBeenCalledTimes(1))
  expect(result.current.selected).toBeNull()
  api.projects.mockResolvedValue([{ project_id: 'p1', official_sample: false }])
  await act(async () => { await result.current.refreshProjects() })
  expect(result.current.selected?.project_id).toBe('p1')
})

it('等待实时状态后才恢复当前仍在运行的示例', async () => {
  let resolve!: (value: unknown) => void
  api.projects.mockResolvedValue([{ project_id: 'p1', official_sample: true }])
  api.experience.mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const onError = vi.fn(); const { result } = renderHook(() => useProjectWorkspace(onError))
  expect(result.current.selected).toBeNull(); expect(api.current).not.toHaveBeenCalled()
  await act(async () => resolve({ active: true, project_id: 'p1', lifecycle: 'RUNNING' }))
  await waitFor(() => expect(result.current.workspace?.project.project_id).toBe('p1'))
})

it('最新实例属于另一项目时不会恢复更早的示例', async () => {
  api.projects.mockResolvedValue([{ project_id: 'p1', official_sample: true }])
  api.experience.mockResolvedValue({ active: true, project_id: 'p2', lifecycle: 'RUNNING' })
  const onError = vi.fn(); const { result } = renderHook(() => useProjectWorkspace(onError))
  await waitFor(() => expect(result.current.projects).toHaveLength(1))
  expect(result.current.selected).toBeNull(); expect(api.current).not.toHaveBeenCalled()
})

it('初始回读不能覆盖用户期间主动选择的应用', async () => {
  let resolve!: (value: unknown) => void
  api.experience.mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const onError = vi.fn(); const { result } = renderHook(() => useProjectWorkspace(onError))
  act(() => result.current.selectProject({ project_id: 'p2' }))
  await act(async () => resolve({ active: false, project_id: 'p1', lifecycle: 'STOPPED' }))
  expect(result.current.selected?.project_id).toBe('p2')
})

it('切换项目以后，延迟的旧响应不会覆盖新项目', async () => {
  let old!: (value: WorkspaceViewDto) => void
  api.current.mockImplementationOnce(() => new Promise(resolve => { old = resolve })).mockResolvedValueOnce(workspace('p2'))
  const onError = vi.fn(); const { result } = renderHook(() => useProjectWorkspace(onError))
  await waitFor(() => expect(api.current).toHaveBeenCalledWith('p1'))
  act(() => result.current.selectProject({ project_id: 'p2' }))
  await waitFor(() => expect(result.current.workspace?.project.project_id).toBe('p2'))
  await act(async () => old(workspace('p1')))
  expect(result.current.workspace?.project.project_id).toBe('p2'); expect(onError).not.toHaveBeenCalled()
})

it('拒绝响应内项目不一致，保留已有权威工作区', async () => {
  const onError = vi.fn(); const { result } = renderHook(() => useProjectWorkspace(onError))
  await waitFor(() => expect(result.current.workspace?.project.project_id).toBe('p1'))
  api.current.mockResolvedValueOnce(workspace('p2'))
  await act(async () => { await result.current.refreshCurrentWorkspace() })
  expect(result.current.workspace?.project.project_id).toBe('p1'); expect(onError).toHaveBeenCalledTimes(1)
})

it('后台轮询加入显式刷新，不使材料保存后的读取失效', async () => {
  const onError = vi.fn(); const { result } = renderHook(() => useProjectWorkspace(onError))
  await waitFor(() => expect(result.current.workspace?.project.project_id).toBe('p1'))
  let resolve!: (value: WorkspaceViewDto) => void
  api.current.mockImplementationOnce(() => new Promise(done => { resolve = done }))
  let explicit!: Promise<WorkspaceViewDto | undefined>, background!: Promise<WorkspaceViewDto | undefined>
  act(() => { explicit = result.current.refreshCurrentWorkspace(); background = result.current.refreshCurrentWorkspace(undefined, true) })
  expect(api.current).toHaveBeenCalledTimes(2)
  const next = { ...workspace('p1'), primary_task: { task_id: 'new-task' } } as WorkspaceViewDto
  await act(async () => { resolve(next); expect(await explicit).toEqual(next); expect(await background).toEqual(next) })
  expect(result.current.workspace).toEqual(next)
})

it.each([false, true])('旧显式读取延迟或失败时采用最新已接受结果（失败=%s）', async failed => {
  const onError = vi.fn(); const { result } = renderHook(() => useProjectWorkspace(onError))
  await waitFor(() => expect(result.current.workspace?.project.project_id).toBe('p1'))
  let resolveOld!: (value: WorkspaceViewDto) => void
  let rejectOld!: (error: Error) => void
  api.current.mockImplementationOnce(() => new Promise((done, reject) => { resolveOld = done; rejectOld = reject }))
  let older!: Promise<WorkspaceViewDto | undefined>
  act(() => { older = result.current.refreshCurrentWorkspace() })
  const next = { ...workspace('p1'), primary_task: { task_id: 'new-task' } } as WorkspaceViewDto
  api.current.mockResolvedValueOnce(next)
  await act(async () => { expect(await result.current.refreshCurrentWorkspace()).toEqual(next) })
  await act(async () => { if (failed) rejectOld(new Error('older request failed')); else resolveOld(workspace('p1')); expect(await older).toEqual(next) })
  expect(result.current.workspace).toEqual(next)
})
