// 预设开发与真实 Agent 交付明确区分；状态回读不能触发代码变更或检查。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { OfficialDevelopmentJourney } from './OfficialDevelopmentJourney'
import type { OfficialExperienceDto } from '../../api/experience'

const api = vi.hoisted(() => ({ development: vi.fn(), project: vi.fn(), switchVersion: vi.fn(), status: vi.fn() }))
vi.mock('../../api/experience', () => ({ experienceApi: api }))
vi.mock('../../api/repairs', async () => ({ ...await vi.importActual<typeof import('../../api/repairs')>('../../api/repairs'), repairsApi: { project: api.project } }))
const value = { project_id: 'p', active: true, scenario_version: 'BASELINE' } as OfficialExperienceDto
const facts = { project_id: 'p', implementation: 'BASELINE', delivery_source: 'PRESET_DEMONSTRATION', can_optimize: false, repair_verified: false, verdict: null, run_id: null, evidence_limited: false, reason: '先检查起始实现' }
const props = () => ({ value, onChanged: vi.fn().mockResolvedValue(undefined), onNavigate: vi.fn(), onError: vi.fn() })
beforeEach(() => { vi.clearAllMocks(); api.development.mockResolvedValue(facts); api.project.mockResolvedValue({ project_id: 'p', tasks: [] }); api.switchVersion.mockResolvedValue({ ...value, scenario_version: 'VULNERABLE', vulnerable_change_id: 'change' }) })
it('没有起始检查时引导准备，不提前开放优化或伪造通过', async () => {
  const p = props(); render(<OfficialDevelopmentJourney {...p}/>)
  fireEvent.click(await screen.findByRole('button', { name: '继续准备与验证' }))
  expect(p.onNavigate).toHaveBeenCalledWith('/workspace')
  expect(screen.queryByRole('button', { name: '应用预设异步优化' })).not.toBeInTheDocument()
  expect(api.switchVersion).not.toHaveBeenCalled()
})
it('服务端允许后仍要明确确认，变更来源如实标注为预设', async () => {
  api.development.mockResolvedValue({ ...facts, can_optimize: true, verdict: 'PASS', run_id: 'baseline' })
  render(<OfficialDevelopmentJourney {...props()}/>)
  fireEvent.click(await screen.findByRole('button', { name: '应用预设异步优化' }))
  expect(api.switchVersion).not.toHaveBeenCalled()
  expect(screen.getByText(/不表示 Codex 已编写代码/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '应用代码变更' }))
  await waitFor(() => expect(api.switchVersion).toHaveBeenCalledExactlyOnceWith('VULNERABLE', undefined))
})
it('证据不足不凭版本名声称权限问题或修复通过', async () => {
  api.development.mockResolvedValue({ ...facts, implementation: 'VULNERABLE', verdict: 'INCONCLUSIVE', run_id: 'limited', evidence_limited: true })
  const p = props(); render(<OfficialDevelopmentJourney {...p}/>)
  fireEvent.click(await screen.findByRole('button', { name: '查看本次检查' }))
  expect(p.onNavigate).toHaveBeenCalledWith('/history?run_id=limited')
  expect(screen.queryByRole('button', { name: '应用预设修复' })).not.toBeInTheDocument()
  expect(screen.queryByText('本次修复已通过原题复验')).not.toBeInTheDocument()
})
it('修复通过后继续当前任务，不跳转连接设置或创建另一轮检查', async () => {
  api.development.mockResolvedValue({ ...facts, implementation: 'FIXED', repair_verified: true, verdict: 'PASS', run_id: 'verified' })
  const p = props(); render(<OfficialDevelopmentJourney {...p}/>)
  fireEvent.click(await screen.findByRole('button', { name: '返回修改记录' }))
  expect(p.onNavigate).toHaveBeenCalledWith('/changes?view=handoff')
  expect(api.switchVersion).not.toHaveBeenCalled()
})
it('用户自行改码后进入普通协作，不继续显示预设阶段或覆盖按钮', async () => {
  api.development.mockResolvedValue({ ...facts, implementation: 'CUSTOM', delivery_source: 'EXTERNAL_CODE' })
  render(<OfficialDevelopmentJourney {...props()}/>)
  expect(await screen.findByRole('heading', { name: '已进入真实代码开发' })).toBeInTheDocument()
  expect(screen.queryByRole('list', { name: '开发演练流程' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '应用预设异步优化' })).not.toBeInTheDocument()
  expect(api.switchVersion).not.toHaveBeenCalled()
})

it('修复版顶部入口直接携带这次修复批次，不能退回普通检查', async () => {
  api.development.mockResolvedValue({ ...facts, implementation: 'FIXED' })
  const p = props(); render(<OfficialDevelopmentJourney {...p} value={{...value, scenario_version: 'FIXED', repair_change_id: 'repair-exact'}}/>)
  fireEvent.click(await screen.findByRole('button', { name: '继续准备与验证' }))
  expect(p.onNavigate).toHaveBeenCalledWith('/tests?change_id=repair-exact')
  expect(api.switchVersion).not.toHaveBeenCalled()
})

it('代码已切换但交付登记未完成时，先回读再显式恢复同一批登记', async () => {
  api.development.mockResolvedValue({ ...facts, can_optimize: true })
  api.switchVersion.mockRejectedValueOnce(new Error('lost response'))
  api.status.mockResolvedValue({ ...value, scenario_version: 'VULNERABLE', vulnerable_change_id: null })
  render(<OfficialDevelopmentJourney {...props()}/>)
  fireEvent.click(await screen.findByRole('button', { name: '应用预设异步优化' }))
  fireEvent.click(screen.getByRole('button', { name: '应用代码变更' }))
  fireEvent.click(await screen.findByRole('button', { name: '核对当前状态' }))
  const recover = await screen.findByRole('button', { name: '恢复本批交付登记' })
  expect(api.switchVersion).toHaveBeenCalledTimes(1)
  fireEvent.click(recover)
  await waitFor(() => expect(api.switchVersion).toHaveBeenCalledTimes(2))
  expect(api.switchVersion.mock.calls[1]).toEqual(['VULNERABLE', undefined])
})
