// 验证产品壳装配工作台、业务边界及当前检查，旧结果深链不恢复旧状态机。

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { WorkspaceViewDto } from '../api/workspace'
import ControlShell from './ControlShell'
import { ProductThemeProvider } from './ThemeContext'

const mockApi = vi.hoisted(() => ({
  experienceStatus: vi.fn(), mcpStatus: vi.fn(), shutdown: vi.fn(), remove: vi.fn(),
}))

const currentWorkspace: WorkspaceViewDto = {
  project: { project_id: 'p1', name: '演示应用', status: 'READY', target_type: 'WEB' },
  connection: { endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED' },
  actors: [], actions: [],
  primary_task: {
    task_id: 'ptk_primary', task_kind: 'ESTABLISH_BUSINESS_BOUNDARY',
    business_action_id: null, business_actor_id: null,
    title: '建立当前业务边界', why_now: '当前还没有稳定业务边界。',
    user_responsibility: '确认业务主体、动作和权限。', system_will_do: '保存不可变提案并等待批准。',
    route: '/permissions', can_execute: true, stale_fingerprint: 'f'.repeat(64),
  },
  areas: [
    { key: 'overview', label: '工作台', description: '查看当前工作区', route: '/workspace', status: 'NEEDS_ATTENTION', status_label: '需要处理' },
    { key: 'permissions', label: '权限', description: '维护业务边界', route: '/permissions', status: 'NEEDS_ATTENTION', status_label: '需要建立' },
    { key: 'changes', label: '变化', description: '当前未接入', route: '/changes', status: 'BLOCKED', status_label: '当前不可用' },
    { key: 'tests', label: '测试', description: '当前未接入', route: '/tests', status: 'BLOCKED', status_label: '当前不可检查' },
  ],
}

const workspaceState = vi.hoisted(() => ({
  projects: [{ project_id: 'p1', name: '演示应用', status: 'READY' }],
  selected: { project_id: 'p1', name: '演示应用', status: 'READY' } as { project_id: string; name: string; status: string } | null,
  workspace: null as WorkspaceViewDto | null,
  selectProject: vi.fn(), refreshProjects: vi.fn(), refreshCurrentWorkspace: vi.fn(),
}))

vi.mock('./useProjectWorkspace', () => ({ useProjectWorkspace: () => workspaceState }))
vi.mock('./useSystemStatus', () => ({ useSystemStatus: () => ({
  profiles: [], setProfiles: vi.fn(), profilesFailed: false,
  aiSettings: { enabled: false, default_profile_name: null, updated_at_us: 0 },
  setAiSettings: vi.fn(), aiSettingsFailed: false,
  status: { api: 'available', worker: 'unavailable', browser: 'available' }, refresh: vi.fn(),
}) }))
vi.mock('../api/sourceChanges', () => ({ sourceChangesApi: { list: vi.fn().mockResolvedValue([]) } }))
vi.mock('../api/repairs', async () => ({ ...await vi.importActual<typeof import('../api/repairs')>('../api/repairs'), repairsApi: { project: vi.fn().mockResolvedValue({ project_id: 'p1', status: null, tasks: [], primary_task_reference: null }) } }))
vi.mock('../api/preparation', () => ({ preparationApi: { get: vi.fn().mockResolvedValue({ project_id: 'p1', actions: [], preparation_complete: false }) } }))
vi.mock('../api/currentChecks', () => ({ currentChecksApi: { preview: vi.fn().mockResolvedValue({ project_id: 'p1', can_execute: false, plan_fingerprint: 'f', action_count: 0, case_count: 0, actions: [], gaps: [] }), list: vi.fn().mockResolvedValue([]) } }))
vi.mock('../api/experience', () => ({ experienceApi: { status: mockApi.experienceStatus } }))
vi.mock('../api/mcp', () => ({ mcpAccessApi: { status: mockApi.mcpStatus } }))
vi.mock('../api/projects', () => ({ projectsApi: { remove: mockApi.remove } }))
vi.mock('../api/system', () => ({ systemApi: { shutdown: mockApi.shutdown } }))

describe('CURRENT 应用壳', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    window.location.hash = '#/workspace'
    vi.clearAllMocks()
    workspaceState.selected = { project_id: 'p1', name: '演示应用', status: 'READY' }
    workspaceState.workspace = currentWorkspace
    workspaceState.refreshProjects.mockResolvedValue(workspaceState.projects)
    workspaceState.refreshCurrentWorkspace.mockResolvedValue(currentWorkspace)
    mockApi.experienceStatus.mockResolvedValue({
      available: false, display_name: '协作空间', unavailable_reason: '当前不可用', active: false,
      experience_id: null, project_id: null, origin: null, scenario_prepared: false,
      scenario_version: null, vulnerable_change_id: null, repair_change_id: null,
    })
    mockApi.mcpStatus.mockResolvedValue({
      schema_version: '1', paired: false, accepting_connections: false,
      endpoint: 'http://127.0.0.1:8765/mcp', default_level: 'READ', project_grants: [],
      client_connected: false, client_name: null, client_version: null, last_seen_at_us: null,
      connection_state: 'DISABLED', last_authenticated_at_us: null, last_auth_failure_at_us: null,
    })
    mockApi.shutdown.mockResolvedValue({ status: 'stopping', message: 'stopping' })
  })

  it('在工作台展示服务端 Workspace 与唯一主任务', async () => {
    render(<ControlShell />)

    expect(await screen.findByRole('heading', { name: '当前还没有稳定业务边界。', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('当前还没有稳定业务边界。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '建立当前业务边界' })).toBeInTheDocument()
    expect(screen.getAllByText('变化与修复').length).toBeGreaterThan(0)
    expect(screen.getAllByText('验证').length).toBeGreaterThan(0)
  })

  it('变化与检查装配当前入口，准备缺失时不自动执行', async () => {
    window.location.hash = '#/changes'
    const view = render(<ControlShell />)
    expect(await screen.findByRole('heading', { name: '代码改过以后，继续检查原来的权限' })).toBeInTheDocument()
    expect(await screen.findByText('尚无代码变化记录')).toBeInTheDocument()

    view.unmount()
    window.location.hash = '#/tests'
    render(<ControlShell />)
    expect(await screen.findByRole('heading', { name: '请先补齐本次检查所需材料' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /开始检查|验证运行/ })).not.toBeInTheDocument()
  })

  it('历史 Run 与 Result 深链不会恢复旧状态机', async () => {
    window.location.hash = '#/results'
    render(<ControlShell />)

    expect(await screen.findByText('此历史入口当前不可用')).toBeInTheDocument()
    expect(screen.getByText(/请从工作台进入当前可用的业务边界或检查准备/)).toBeInTheDocument()
  })

  it('视口改变后关闭旧菜单，再次打开仍可退出', async () => {
    render(<ControlShell />)
    const more = await screen.findByRole('button', { name: /设置与更多/ })
    fireEvent.click(more)
    await waitFor(() => expect(screen.getByText('退出界鉴')).toBeVisible())
    fireEvent(window, new Event('resize'))
    await waitFor(() => expect(screen.queryByText('退出界鉴')).not.toBeInTheDocument())
    fireEvent.click(more)
    await waitFor(() => expect(screen.getByText('退出界鉴')).toBeVisible())
    expect(mockApi.shutdown).not.toHaveBeenCalled()
  })
  it('主题子菜单经明确点击展开，切换后关闭旧浮层', async () => {
    render(<ProductThemeProvider><ControlShell /></ProductThemeProvider>)
    fireEvent.click(await screen.findByRole('button', { name: /设置与更多/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /主题 ·/ }))
    fireEvent.click(await screen.findByText('暗色主题'))
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
    await waitFor(() => expect(screen.queryByText('退出界鉴')).not.toBeInTheDocument())
    expect(mockApi.shutdown).not.toHaveBeenCalled()
  })
  it('只通过明确确认请求安全退出', async () => {
    render(<ControlShell />)
    fireEvent.click(await screen.findByRole('button', { name: /设置与更多/ }))
    fireEvent.click(await screen.findByText('退出界鉴'))
    fireEvent.click(await screen.findByRole('button', { name: '安全退出' }))

    await waitFor(() => expect(mockApi.shutdown).toHaveBeenCalledOnce())
    expect(await screen.findByText('界鉴正在安全退出')).toBeInTheDocument()
  })
})
