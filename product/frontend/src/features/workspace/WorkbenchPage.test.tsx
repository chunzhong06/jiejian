// 验证工作台直接消费后端统一产品状态中的 Readiness 与唯一下一步。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WorkbenchPage } from './WorkbenchPage'

const mockAssistant = vi.hoisted(() => ({ project: vi.fn(), generateProject: vi.fn(), result: vi.fn(), generateResult: vi.fn(), generateError: vi.fn() }))
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

const resultAction = { action: 'OPEN_RESULT' as const, label: '查看检查结果', description: '查看真实副作用、可信证据和已经发布的安全结论。', route: '/results' as const, cli_command: 'jiejian result show --help' }
const accountAction = { action: 'RECORD_FLOW' as const, label: '准备测试账号', description: '先为已确认权限组准备安全登录状态。', route: '/identities' as const, cli_command: 'jiejian account --help' }
const officialExperience = { available: true, display_name: '协作空间', unavailable_reason: null, active: false, experience_id: null, experience_mode: null, project_id: null, origin: null, identities_ready: false, authorization_order: null, blob_observation: null }

describe('WorkbenchPage', () => {
  beforeEach(() => { vi.clearAllMocks(); mockAssistant.project.mockRejectedValue(new Error('assistant unavailable')) })

  it('只展示唯一下一步主卡与三个固定辅助卡', () => {
    render(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用', status: 'READY' }} readiness={readiness} nextAction={resultAction} runs={[{ lifecycle: 'COMPLETED', verdict: 'INCONCLUSIVE', result_integrity: 'VERIFIED' }]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} experience={officialExperience} experienceBusy={false} onStartExperience={vi.fn().mockResolvedValue(true)} onNavigate={vi.fn()} />)
    expect(screen.queryByText('六步检查进度')).not.toBeInTheDocument()
    expect(screen.getByText('当前应用')).toBeInTheDocument()
    expect(screen.getByText('现在继续')).toBeInTheDocument()
    expect(screen.getByText('最近检查')).toBeInTheDocument()
    expect(screen.getByText('[AI辅助]')).toBeInTheDocument()
    expect(screen.queryByText('系统状态')).not.toBeInTheDocument()
    expect(screen.getByText('官方示例')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看检查结果' })).toBeInTheDocument()
    expect(screen.queryByText('INTERNAL_STATE')).not.toBeInTheDocument()
    expect(screen.getByText('证据不足，暂时不能下结论')).toBeInTheDocument()
    expect(screen.getByText('结果完整')).toBeInTheDocument()
  })

  it('没有应用时给出应用接入主操作', () => {
    const onNavigate = vi.fn()
    render(<WorkbenchPage selected={null} readiness={null} nextAction={null} runs={[]} systemStatus={{ api: 'unknown', worker: 'unknown', browser: 'unknown' }} experience={officialExperience} experienceBusy={false} onStartExperience={vi.fn().mockResolvedValue(true)} onNavigate={onNavigate} />)
    expect(screen.getByText('开始一次安全检查')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '接入自己的应用' })).toBeInTheDocument()
    expect(screen.getByText('或者先体验界鉴')).toBeInTheDocument()
  })

  it('角色与动作确认完成后指向业务流程', () => {
    const onNavigate = vi.fn()
    render(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用', status: 'DRAFT' }} readiness={{ ...readiness, execution_profile_available: false, completed_flow_available: false, active_contract_available: false, latest_verified_run_id: null, next_required_action: 'RECORD_FLOW' }} nextAction={accountAction} runs={[]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} experience={officialExperience} experienceBusy={false} onStartExperience={vi.fn().mockResolvedValue(true)} onNavigate={onNavigate} />)
    expect(screen.getByRole('button', { name: '准备测试账号' })).toBeInTheDocument()
  })

  it('先按服务端确定性主动作展示，再显示 READY 的 AI 排序解释', async () => {
    mockAssistant.project.mockResolvedValue({ status: 'READY', template_id: 'jiejian.next_step', template_version: '1', subject_id: 'p1', state_fingerprint: 'a'.repeat(64), entities: [{ entity_id: 'task:check', entity_type: 'TASK', display_name: '开始检查当前可运行范围', facts: [] }], suggestions: [{ kind: 'PRIORITIZE', entity_ids: ['task:check'], explanation: '先开始当前可运行范围。' }], retry_after_us: null })
    render(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用', status: 'READY' }} readiness={readiness} nextAction={resultAction} runs={[]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} experience={officialExperience} experienceBusy={false} onStartExperience={vi.fn().mockResolvedValue(true)} onNavigate={vi.fn()} />)
    expect(await screen.findByText('开始检查当前可运行范围')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看检查结果' })).toBeInTheDocument()
    expect(await screen.findByText('先开始当前可运行范围。')).toBeInTheDocument()
  })

  it('REFRESH_NEEDED 只冷读取，用户点击后才请求模型且失败不改变确定性主流程', async () => {
    mockAssistant.project.mockResolvedValue({ status: 'REFRESH_NEEDED', template_id: 'jiejian.next_step', template_version: '1', subject_id: 'p1', state_fingerprint: 'b'.repeat(64), entities: [], suggestions: [], retry_after_us: null })
    mockAssistant.generateProject.mockRejectedValue(new Error('provider unavailable'))
    render(<WorkbenchPage selected={{ project_id: 'p1', name: '演示应用', status: 'READY' }} readiness={readiness} nextAction={resultAction} runs={[]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} experience={officialExperience} experienceBusy={false} onStartExperience={vi.fn().mockResolvedValue(true)} onNavigate={vi.fn()} />)
    expect(await screen.findByText('尚未生成建议，点击按钮后才会连接模型服务。')).toBeInTheDocument()
    expect(mockAssistant.generateProject).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '生成 AI 建议' }))
    await waitFor(() => expect(mockAssistant.generateProject).toHaveBeenCalledOnce())
    expect(screen.getByRole('button', { name: '查看检查结果' })).toBeInTheDocument()
  })

  it('开始评委导览前明确说明本机运行、源码分析和不会预制结论', async () => {
    const onStart = vi.fn().mockResolvedValue(true)
    render(<WorkbenchPage selected={null} readiness={null} nextAction={null} runs={[]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} experience={officialExperience} experienceBusy={false} onStartExperience={onStart} onNavigate={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '评委导览' }))
    expect(await screen.findByText('评委导览还会授权界鉴只读分析随产品附带的示例源码。')).toBeInTheDocument()
    expect(screen.getByText('不会开始真实安全检查，也不会预先生成检查结论。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '同意并开始' }))
    await waitFor(() => expect(onStart).toHaveBeenCalledWith('GUIDED'))
  })

  it('官方体验进行中时只提供明确的结束体验动作', () => {
    const onStop = vi.fn().mockResolvedValue(undefined)
    render(<WorkbenchPage selected={{ project_id: 'p1', name: '协作空间', status: 'READY' }} readiness={readiness} nextAction={resultAction} runs={[]} systemStatus={{ api: 'available', worker: 'running', browser: 'available' }} experience={{ ...officialExperience, active: true, experience_id: 'exp-1', experience_mode: 'GUIDED', project_id: 'p1' }} experienceBusy={false} onStartExperience={vi.fn().mockResolvedValue(true)} onStopExperience={onStop} onNavigate={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: '结束体验' }))
    expect(onStop).toHaveBeenCalledOnce()
    expect(screen.queryByRole('button', { name: '评委导览' })).not.toBeInTheDocument()
  })
})
