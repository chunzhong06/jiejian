// 区分普通应用与托管环境；未知状态不能触发重启，每次重新开始不提供旧示例历史入口。
import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { EnvironmentPage } from './EnvironmentPage'
const api = vi.hoisted(() => ({ status: vi.fn(), history: vi.fn(), start: vi.fn(), project: vi.fn() }))
vi.mock('../../api/applications/experience', () => ({ experienceApi: api }))
vi.mock('../../api/checks/repairs', () => ({ repairsApi: { project: api.project }, repairReference: vi.fn() }))
const stopped = { available: true, active: false, display_name: '协作空间', project_id: 'old', history_project_id: 'old', lifecycle: 'STOPPED', scenario_prepared: false, scenario_version: null }
const props = { project: { project_id: 'old', name: '协作空间' }, workspace: null, onNavigate: vi.fn(), onChanged: vi.fn(), onError: vi.fn() }
beforeEach(() => { vi.clearAllMocks(); api.status.mockResolvedValue(stopped); api.history.mockResolvedValue({ items: [], has_more: false }); api.project.mockResolvedValue({project_id:'old',tasks:[]}) })
it('停止环境与服务可访问分开表达，打开页面不会启动环境', async () => {
  render(<EnvironmentPage {...props}/>)
  await screen.findByRole('heading', { name: '应用与环境' })
  expect(screen.getByText(/示例已停止，可重新开始/)).toBeInTheDocument()
  expect(screen.getByText('已停止')).toBeInTheDocument()
  expect(screen.queryByText('界鉴服务')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '启动示例' })).toBeInTheDocument()
  expect(api.start).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: '查看原项目历史' })).not.toBeInTheDocument()
  expect(api.history).not.toHaveBeenCalled()
})
it('状态未知不允许反复启动', async () => {
  api.status.mockResolvedValue({ ...stopped, lifecycle: 'UNKNOWN', operation_state: 'UNKNOWN' })
  render(<EnvironmentPage {...props}/>)
  expect(await screen.findByRole('button', { name: '启动示例' })).toBeDisabled()
  expect(api.start).not.toHaveBeenCalled()
})
it('普通应用只给连接核对，不冒充托管进程', async () => {
  render(<EnvironmentPage {...props} project={{ project_id: 'ordinary', name: '文档中心' }}/>)
  await screen.findByRole('heading', { name: '应用与环境' })
  expect(screen.getByText(/核对当前应用的运行方式/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '核对应用连接' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '启动示例' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '停止官方示例' })).not.toBeInTheDocument()
})
