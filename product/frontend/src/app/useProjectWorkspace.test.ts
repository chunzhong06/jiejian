// 项目切换与后台刷新交错时，只接受当前项目的最新响应。
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import type { WorkspaceViewDto } from '../api/workspace'
import { useProjectWorkspace } from './useProjectWorkspace'

const api = vi.hoisted(() => ({ projects: vi.fn(), current: vi.fn() }))
vi.mock('../api/projects', () => ({ projectsApi: { projects: api.projects } }))
vi.mock('../api/workspace', () => ({ workspaceApi: { current: api.current } }))
vi.mock('./browserState', () => ({ browserState: { readProject: () => ({ project_id: 'p1' }), writeProject: vi.fn(), clearProject: vi.fn() } }))
const workspace = (id: string) => ({ project: { project_id: id }, actors: [], actions: [], areas: [], primary_task: null } as unknown as WorkspaceViewDto)
beforeEach(() => { vi.clearAllMocks(); api.projects.mockResolvedValue([{ project_id: 'p1' }, { project_id: 'p2' }]); api.current.mockResolvedValue(workspace('p1')) })

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
