// 示例动作必须明确确认，普通审批与准备分开，失败后只回读状态。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { OfficialSamplePanel } from './OfficialSamplePanel'
import type { OfficialExperienceDto } from '../../api/experience'

const api = vi.hoisted(() => ({ start: vi.fn(), prepare: vi.fn(), status: vi.fn(), boundaryProposal: vi.fn(), switchVersion: vi.fn(), project: vi.fn() }))
vi.mock('../../api/experience', () => ({ experienceApi: api }))
vi.mock('../../api/repairs', async () => ({ ...await vi.importActual<typeof import('../../api/repairs')>('../../api/repairs'), repairsApi: { project: api.project } }))
const idle: OfficialExperienceDto = { available: true, display_name: '协作空间', unavailable_reason: null, active: false, experience_id: null, project_id: null, origin: null, scenario_prepared: false, scenario_version: null, vulnerable_change_id: null, repair_change_id: null }
const active: OfficialExperienceDto = { ...idle, active: true, project_id: 'p1', experience_id: 'experience', scenario_version: 'VULNERABLE', pending_tasks: ['HUMAN_BOUNDARY_APPROVAL_REQUIRED'] }
const props = () => ({ value: idle, onChanged: vi.fn().mockResolvedValue(undefined), onError: vi.fn(), onNavigate: vi.fn() })
beforeEach(() => { vi.clearAllMocks(); api.start.mockResolvedValue(active); api.status.mockResolvedValue(active); api.prepare.mockResolvedValue(active); api.project.mockResolvedValue({ project_id: 'p1', status: null, tasks: [] }); api.boundaryProposal.mockResolvedValue({}) })
it('打开确认框不会启动或批准；确认后只启动一次', async () => {
  render(<OfficialSamplePanel {...props()} />)
  fireEvent.click(screen.getByRole('button', { name: '启动官方示例' }))
  expect(api.start).not.toHaveBeenCalled()
  fireEvent.click(await screen.findByRole('button', { name: '启动问题版' }))
  await waitFor(() => expect(api.start).toHaveBeenCalledTimes(1))
  expect(api.boundaryProposal).not.toHaveBeenCalled()
  expect(api.prepare).not.toHaveBeenCalled()
})
it('未批准时只请求准备检查并展示待办，不偷偷批准权限', async () => {
  render(<OfficialSamplePanel {...props()} value={active} />)
  expect(screen.getByText('请先审阅并批准示例权限。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '进入示例检查' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '准备示例材料' }))
  await waitFor(() => expect(api.prepare).toHaveBeenCalledTimes(1))
  expect(api.boundaryProposal).not.toHaveBeenCalled()
})
it('提案生成后前往普通业务边界审阅，未创建检查', async () => {
  const p = props(); render(<OfficialSamplePanel {...p} value={active} />)
  fireEvent.click(screen.getByRole('button', { name: '审阅示例权限' }))
  await waitFor(() => expect(p.onNavigate).toHaveBeenCalledWith('/permissions'))
  expect(api.prepare).not.toHaveBeenCalled()
})
it('启动回执不明时回读实际状态，不自动重试', async () => {
  api.start.mockRejectedValue(new Error('lost response'))
  const p = props(); render(<OfficialSamplePanel {...p} />)
  fireEvent.click(screen.getByRole('button', { name: '启动官方示例' }))
  fireEvent.click(await screen.findByRole('button', { name: '启动问题版' }))
  await waitFor(() => expect(api.status).toHaveBeenCalledTimes(1))
  expect(api.start).toHaveBeenCalledTimes(1)
  expect(p.onChanged).toHaveBeenCalledWith(active)
})
