// 验证工作台只消费后端 ProjectReadiness 投影，并据此展示普通用户下一步。

import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorkbenchPage } from './WorkbenchPage'

const mockAssistant = vi.hoisted(() => ({ guidance: vi.fn(), refresh: vi.fn() }))
vi.mock('../../api/assistant', () => ({ assistantApi: mockAssistant }))

const readiness = {
  schema_version: '1' as const,
  project_id: 'p1',
  project_status: 'READY',
  application_connected: true,
  endpoint_status: 'CONFIRMED' as const,
  source_analysis_status: 'COMPLETED' as const,
  discovered_role_count: 3,
  confirmed_role_count: 2,
  discovered_action_count: 4,
  confirmed_action_count: 3,
  execution_profile_available: true,
  completed_flow_available: true,
  active_contract_available: true,
  current_scope_runnable: true,
  remaining_gap_count: 0,
  active_tasks: [],
  latest_verified_run_id: 'run-current',
  next_required_action: 'OPEN_RESULT' as const,
}

describe('WorkbenchPage', () => {
  beforeEach(() => { vi.clearAllMocks(); mockAssistant.guidance.mockRejectedValue(new Error('assistant unavailable')) })

  it('展示后端投影的准备计数、下一步和最近检查结论', () => {
    render(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用', status: 'READY' }} readiness={readiness} runs={[{ lifecycle: 'COMPLETED', verdict: 'INCONCLUSIVE', result_integrity: 'VERIFIED' }]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} profiles={[]} llmLoadFailed={false} onNavigate={vi.fn()} />)
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('/ 3')).toBeInTheDocument()
    expect(screen.getByText('/ 4')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看检查结果' })).toBeInTheDocument()
    expect(screen.queryByText('INTERNAL_STATE')).not.toBeInTheDocument()
    expect(screen.getByText('证据不足，暂时不能下结论')).toBeInTheDocument()
    expect(screen.getByText('结果完整')).toBeInTheDocument()
  })

  it('没有应用时给出应用接入主操作', () => {
    const onNavigate = vi.fn()
    render(<WorkbenchPage selected={null} readiness={null} runs={[]} systemStatus={{ api: 'unknown', worker: 'unknown', browser: 'unknown' }} profiles={[]} llmLoadFailed={false} onNavigate={onNavigate} />)
    expect(screen.getByText('还没有选择要检查的应用。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '选择应用' })).toBeInTheDocument()
  })

  it('角色与动作确认完成后指向业务流程', () => {
    const onNavigate = vi.fn()
    render(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用', status: 'DRAFT' }} readiness={{ ...readiness, execution_profile_available: false, completed_flow_available: false, active_contract_available: false, latest_verified_run_id: null, next_required_action: 'RECORD_FLOW' }} runs={[]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} profiles={[]} llmLoadFailed={false} onNavigate={onNavigate} />)
    expect(screen.getByRole('button', { name: '准备测试账号并录制关键业务动作' })).toBeInTheDocument()
  })

  it('先按服务端确定性主动作展示，再显示 READY 的 AI 排序解释', async () => {
    const option = { option_id: 'opt_111111111111111111111111', kind: 'START_CURRENT_CHECK', title: '开始检查当前可运行范围', reason_codes: ['CURRENT_SCOPE_RUNNABLE'], priority_tier: 'PRIMARY' as const, route: '/checks/start' }
    mockAssistant.guidance.mockResolvedValue({ status: 'READY', template_id: 'jiejian.next_step', template_version: '1', guidance: { project_id: 'p1', state_fingerprint: 'a'.repeat(64), phase: 'CHECK_READY', current_scope_runnable: true, remaining_gap_count: 1, options: [option] }, recommendations: [{ option_id: option.option_id, explanation: '先开始当前可运行范围。' }], retry_after_us: null })
    render(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用', status: 'READY' }} readiness={readiness} runs={[]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} profiles={[]} llmLoadFailed={false} onNavigate={vi.fn()} />)
    expect(await screen.findByRole('button', { name: '开始检查当前可运行范围' })).toBeInTheDocument()
    expect(await screen.findByText('[AI辅助] 推荐优先')).toBeInTheDocument()
  })

  it('REFRESH_NEEDED 的同一指纹只自动刷新一次，失败时不改变确定性主流程', async () => {
    const guidance = { project_id: 'p1', state_fingerprint: 'b'.repeat(64), phase: 'CHECK_READY', current_scope_runnable: true, remaining_gap_count: 0, options: [] }
    mockAssistant.guidance.mockResolvedValue({ status: 'REFRESH_NEEDED', template_id: 'jiejian.next_step', template_version: '1', guidance, recommendations: [], retry_after_us: null })
    mockAssistant.refresh.mockRejectedValue(new Error('provider unavailable'))
    const view = render(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用', status: 'READY' }} readiness={readiness} runs={[]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} profiles={[]} llmLoadFailed={false} onNavigate={vi.fn()} />)
    await waitFor(() => expect(mockAssistant.refresh).toHaveBeenCalledOnce())
    view.rerender(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用', status: 'READY' }} readiness={{ ...readiness }} runs={[]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} profiles={[]} llmLoadFailed={false} onNavigate={vi.fn()} />)
    await waitFor(() => expect(mockAssistant.refresh).toHaveBeenCalledOnce())
    expect(screen.getByRole('button', { name: '查看检查结果' })).toBeInTheDocument()
  })
})
