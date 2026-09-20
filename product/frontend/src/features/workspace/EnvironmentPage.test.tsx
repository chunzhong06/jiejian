// 区分普通应用与托管环境；未知状态不能触发重启，历史选择保持精确项目。
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { EnvironmentPage } from './EnvironmentPage'
const api = vi.hoisted(() => ({ status: vi.fn(), history: vi.fn(), start: vi.fn(), project: vi.fn() }))
vi.mock('../../api/experience', () => ({ experienceApi: api }))
vi.mock('../../api/repairs', () => ({ repairsApi: { project: api.project }, repairReference: vi.fn() }))
vi.mock('./EnvironmentHistory', () => ({ EnvironmentHistory: ({ projectId }: {projectId:string}) => <div>历史项目 {projectId}</div> }))
const system = { api: 'available' as const, worker: 'running' as const, browser: 'available' as const }
const stopped = { available: true, active: false, display_name: '协作空间', project_id: 'old', history_project_id: 'old', lifecycle: 'STOPPED', scenario_prepared: false, scenario_version: null }
const props = { project: { project_id: 'old', name: '协作空间' }, workspace: null, systemStatus: system, onNavigate: vi.fn(), onChanged: vi.fn(), onError: vi.fn() }
beforeEach(() => { vi.clearAllMocks(); api.status.mockResolvedValue(stopped); api.history.mockResolvedValue({ items: [], has_more: false }); api.project.mockResolvedValue({project_id:'old',tasks:[]}) })
it('停止环境与服务可访问分开表达，打开页面不会启动环境', async () => {
  render(<EnvironmentPage {...props}/>)
  await screen.findByRole('heading', { name: '示例已停止，原项目记录仍可查看' })
  expect(screen.getByText('当前可访问')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '重新启动示例' })).toBeInTheDocument()
  expect(api.start).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '查看原项目历史' }))
  expect(screen.getByText('历史项目 old')).toBeInTheDocument()
})
it('状态未知不允许反复启动', async () => {
  api.status.mockResolvedValue({ ...stopped, lifecycle: 'UNKNOWN', operation_state: 'UNKNOWN' })
  render(<EnvironmentPage {...props}/>)
  expect(await screen.findByRole('button', { name: '启动官方示例' })).toBeDisabled()
  expect(api.start).not.toHaveBeenCalled()
})
it('普通应用只给连接核对，不冒充托管进程', async () => {
  render(<EnvironmentPage {...props} project={{ project_id: 'ordinary', name: '文档中心' }}/>)
  await screen.findByRole('heading', { name: '应用由你启动，界鉴保留已有记录' })
  expect(screen.getByRole('button', { name: '核对应用连接' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '重新启动示例' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '停止官方示例' })).not.toBeInTheDocument()
})
