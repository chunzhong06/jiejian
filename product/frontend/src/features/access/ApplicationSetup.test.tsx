/* 验证普通接入只要求目录、endpoint、源码授权和候选人工确认。 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApplicationSetup } from './ApplicationSetup'

const mockProjects = vi.hoisted(() => ({
  understanding: vi.fn(),
  connectApplication: vi.fn(),
  discoverEndpoints: vi.fn(),
  confirmEndpoint: vi.fn(),
  authorizeSourceAnalysis: vi.fn(),
  analyzeSource: vi.fn(),
  decideRole: vi.fn(),
  decideAction: vi.fn(),
  addRole: vi.fn(),
  addAction: vi.fn(),
}))
const mockOnboarding = vi.hoisted(() => ({ selectFolder: vi.fn() }))

vi.mock('../../api/projects', () => ({ projectsApi: mockProjects }))
vi.mock('../../api/onboarding', () => ({ onboardingApi: mockOnboarding }))

const baseUnderstanding = {
  project_id: 'app-demo',
  source_root: 'D:\\apps\\demo',
  confirmed_endpoint: null,
  endpoint_source_fingerprint: null,
  endpoint_confirmed_at_us: null,
  endpoint_last_checked_at_us: null,
  endpoint_reachable: null,
  source_analysis_authorized: false,
  source_analysis_authorized_at_us: null,
  source_fingerprint: null,
  analysis_completed_at_us: null,
  role_candidates: [],
  action_candidates: [],
  revision: 0,
  created_at_us: 1,
  updated_at_us: 1,
}

const role = {
  candidate_id: 'role_11111111111111111111111111111111',
  canonical_key: 'owner',
  display_name: 'owner',
  confidence: 'HIGH' as const,
  decision: 'PROPOSED' as const,
  origin: 'DETECTED' as const,
  stale: false,
  evidence: [{ relative_path: 'app.py', line_start: 3, line_end: 4, symbol: 'AccountRole', detector: 'python-role-enum', content_sha256: 'a'.repeat(64) }],
}

const action = {
  candidate_id: 'action_22222222222222222222222222222222',
  canonical_key: 'PATCH /documents/{id}',
  display_name: '修改文档',
  confidence: 'MEDIUM' as const,
  risk_hint: 'WRITE' as const,
  decision: 'PROPOSED' as const,
  origin: 'DETECTED' as const,
  stale: false,
  evidence: [{ relative_path: 'openapi.json', line_start: 1, line_end: 1, symbol: 'updateDocument', detector: 'openapi-operation', content_sha256: 'b'.repeat(64) }],
}

describe('ApplicationSetup', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockOnboarding.selectFolder.mockResolvedValue({ status: 'selected', path: 'D:\\apps\\demo' })
    mockProjects.connectApplication.mockResolvedValue({
      project: { project_id: 'app-demo', name: 'demo', status: 'DRAFT' },
      understanding: baseUnderstanding,
      discovery: {
        detected_types: ['Vite'],
        start_candidates: [{ label: 'Vite 开发服务候选', command: 'pnpm run dev', source: 'package.json', confirmation_required: true, executed: false, safety_note: '只展示不执行' }],
        config_hints: [], interface_hints: [], auth_hints: [], missing_items: [], warnings: [],
      },
    })
    mockProjects.discoverEndpoints.mockResolvedValue({ source_fingerprint: 'c'.repeat(64), candidates: [{ endpoint: 'http://127.0.0.1:5173', source_type: 'CONFIG', source: 'vite.config.ts', rank: 0, reachable: true, status_code: 200, probe_detail: '已响应', confirmation_required: true }], request_count: 1, default_endpoint: 'http://127.0.0.1:5173', manual_entry_required: false })
    mockProjects.confirmEndpoint.mockResolvedValue({ ...baseUnderstanding, confirmed_endpoint: 'http://127.0.0.1:5173', endpoint_source_fingerprint: 'c'.repeat(64), endpoint_confirmed_at_us: 2, endpoint_last_checked_at_us: 2, endpoint_reachable: true, revision: 1 })
    mockProjects.authorizeSourceAnalysis.mockResolvedValue({ ...baseUnderstanding, confirmed_endpoint: 'http://127.0.0.1:5173', endpoint_source_fingerprint: 'c'.repeat(64), endpoint_confirmed_at_us: 2, endpoint_last_checked_at_us: 2, endpoint_reachable: true, source_analysis_authorized: true, source_analysis_authorized_at_us: 3, revision: 2 })
    mockProjects.analyzeSource.mockResolvedValue({ ...baseUnderstanding, confirmed_endpoint: 'http://127.0.0.1:5173', endpoint_source_fingerprint: 'c'.repeat(64), endpoint_confirmed_at_us: 2, endpoint_last_checked_at_us: 2, endpoint_reachable: true, source_analysis_authorized: true, source_analysis_authorized_at_us: 3, source_fingerprint: 'd'.repeat(64), analysis_completed_at_us: 4, role_candidates: [role], action_candidates: [action], revision: 3 })
  })

  it('完成目录、自动地址、显式源码授权和候选展示的普通路径', async () => {
    const onConnected = vi.fn()
    render(<ApplicationSetup selected={null} onConnected={onConnected} onChanged={vi.fn()} onBack={vi.fn()} onContinue={vi.fn()} />)

    expect(screen.queryByText(/Profile path|resource id|read path|recovery path/i)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '选择应用文件夹' }))
    expect(await screen.findByText('确认本地访问地址', { selector: '.ant-card-head-title' })).toBeInTheDocument()
    expect(screen.getByText(/只探测 127\.0\.0\.1/)).toBeInTheDocument()
    expect(screen.queryByText(/::1/)).not.toBeInTheDocument()
    expect(await screen.findByText('Vite')).toBeInTheDocument()
    expect(screen.getByText(/可能启动方式：Vite 开发服务候选/)).toBeInTheDocument()
    expect(screen.getByText(/vite.config.ts/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /应用已经由我启动/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /确认这是我的本地应用/ }))
    fireEvent.click(screen.getByRole('button', { name: '确认本地地址' }))
    expect(await screen.findByText('分析权限组与关键业务动作', { selector: '.ant-card-head-title' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: /只读分析当前应用源码/ }))
    fireEvent.click(screen.getByRole('button', { name: '授权并开始分析' }))
    expect(await screen.findByText('界鉴已经理解', { selector: '.ant-card-head-title' })).toBeInTheDocument()
    expect(screen.getByText('还有 2 项应用理解需要你确认')).toBeInTheDocument()
    expect(screen.getByText(/这里只确认应用中存在哪些用户类别和操作/)).toBeInTheDocument()
    expect(screen.getByDisplayValue('owner')).toBeInTheDocument()
    expect(screen.getByDisplayValue('修改文档')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确认权限组和业务动作后继续' })).toBeDisabled()
    expect(onConnected).toHaveBeenCalledWith(expect.objectContaining({ project_id: 'app-demo' }))
  })

  it('重新打开页面时从后端事实恢复候选并保存人工决定', async () => {
    const restored = { ...baseUnderstanding, confirmed_endpoint: 'http://127.0.0.1:5173', endpoint_source_fingerprint: 'c'.repeat(64), endpoint_confirmed_at_us: 2, endpoint_last_checked_at_us: 2, endpoint_reachable: true, source_analysis_authorized: true, source_analysis_authorized_at_us: 3, source_fingerprint: 'd'.repeat(64), analysis_completed_at_us: 4, role_candidates: [role], action_candidates: [action], revision: 3 }
    mockProjects.understanding.mockResolvedValue(restored)
    const confirmed = { ...restored, role_candidates: [{ ...role, decision: 'CONFIRMED', display_name: '所有者' }], revision: 4 }
    mockProjects.decideRole
      .mockResolvedValueOnce(confirmed)
      .mockResolvedValueOnce({ ...confirmed, role_candidates: [{ ...role, decision: 'REJECTED', display_name: '所有者' }], revision: 5 })
    render(<ApplicationSetup selected={{ project_id: 'app-demo', name: 'demo', status: 'DRAFT' }} onConnected={vi.fn()} onChanged={vi.fn()} onBack={vi.fn()} onContinue={vi.fn()} />)

    expect(await screen.findByDisplayValue('owner')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('权限组显示名称'), { target: { value: '所有者' } })
    fireEvent.click(screen.getByRole('button', { name: '确认这个权限组' }))
    await waitFor(() => expect(mockProjects.decideRole).toHaveBeenCalledWith('app-demo', role.candidate_id, 'CONFIRMED', '所有者', 3))
    expect((await screen.findAllByText('所有者')).length).toBeGreaterThan(0)
    expect(screen.queryByLabelText('权限组显示名称')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '排除这个权限组' }))
    await waitFor(() => expect(mockProjects.decideRole).toHaveBeenCalledWith('app-demo', role.candidate_id, 'REJECTED', '所有者', 4))
    expect(await screen.findByText('已排除的候选（1）')).toBeInTheDocument()
  })

  it('保留只读授权并允许按当前源码重新发现候选', async () => {
    const restored = { ...baseUnderstanding, confirmed_endpoint: 'http://127.0.0.1:5173', endpoint_source_fingerprint: 'c'.repeat(64), endpoint_confirmed_at_us: 2, endpoint_last_checked_at_us: 2, endpoint_reachable: true, source_analysis_authorized: true, source_analysis_authorized_at_us: 3, source_fingerprint: 'd'.repeat(64), analysis_completed_at_us: 4, role_candidates: [], action_candidates: [], revision: 3 }
    const refreshed = { ...restored, source_fingerprint: 'e'.repeat(64), role_candidates: [role], action_candidates: [action], revision: 4 }
    mockProjects.understanding.mockResolvedValue(restored)
    mockProjects.analyzeSource.mockResolvedValue(refreshed)
    render(<ApplicationSetup selected={{ project_id: 'app-demo', name: 'demo', status: 'DRAFT' }} onConnected={vi.fn()} onChanged={vi.fn()} onBack={vi.fn()} onContinue={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: '重新分析当前源码' }))
    fireEvent.click(await screen.findByRole('button', { name: '重新分析' }))

    await waitFor(() => expect(mockProjects.analyzeSource).toHaveBeenCalledWith('app-demo', 3))
    expect(await screen.findByDisplayValue('owner')).toBeInTheDocument()
    expect(screen.getByText('已按当前源码重新发现权限组和业务动作，请继续确认候选。')).toBeInTheDocument()
    expect(mockProjects.authorizeSourceAnalysis).not.toHaveBeenCalled()
  })

  it('刷新当前状态只读取已经保存的应用事实', async () => {
    const onChanged = vi.fn()
    const restored = {
      ...baseUnderstanding,
      confirmed_endpoint: 'http://127.0.0.1:5173',
      source_analysis_authorized: true,
      source_fingerprint: 'd'.repeat(64),
      role_candidates: [{ ...role, decision: 'CONFIRMED' as const, display_name: '普通用户' }],
      action_candidates: [{ ...action, decision: 'CONFIRMED' as const }],
      revision: 3,
    }
    mockProjects.understanding.mockResolvedValue(restored)
    render(<ApplicationSetup selected={{ project_id: 'app-demo', name: 'demo', status: 'DRAFT' }} onConnected={vi.fn()} onChanged={onChanged} onBack={vi.fn()} onContinue={vi.fn()} />)

    expect(await screen.findByText('普通用户')).toBeInTheDocument()
    mockProjects.understanding.mockClear()
    fireEvent.click(screen.getByRole('button', { name: '刷新当前状态' }))

    await waitFor(() => expect(mockProjects.understanding).toHaveBeenCalledOnce())
    expect(mockProjects.understanding).toHaveBeenCalledWith('app-demo')
    expect(onChanged).toHaveBeenCalledOnce()
    expect(mockProjects.analyzeSource).not.toHaveBeenCalled()
    expect(mockProjects.confirmEndpoint).not.toHaveBeenCalled()
    expect(mockProjects.decideRole).not.toHaveBeenCalled()
  })

  it('后端判定地址需要重新确认时不沿用历史地址跳过当前步骤', async () => {
    const restored = {
      ...baseUnderstanding,
      confirmed_endpoint: 'http://127.0.0.1:5173',
      endpoint_source_fingerprint: 'c'.repeat(64),
      endpoint_confirmed_at_us: 2,
      endpoint_last_checked_at_us: 2,
      endpoint_reachable: true,
      source_analysis_authorized: true,
      source_fingerprint: 'd'.repeat(64),
      role_candidates: [{ ...role, decision: 'CONFIRMED' as const }],
      action_candidates: [{ ...action, decision: 'CONFIRMED' as const }],
      revision: 3,
    }
    mockProjects.understanding.mockResolvedValue(restored)
    render(<ApplicationSetup selected={{ project_id: 'app-demo', name: 'demo', status: 'DRAFT' }} endpointStatus="NEEDS_CONFIRMATION" onConnected={vi.fn()} onChanged={vi.fn()} onBack={vi.fn()} onContinue={vi.fn()} />)

    expect(await screen.findByText('确认本地访问地址', { selector: '.ant-card-head-title' })).toBeInTheDocument()
    expect(mockProjects.discoverEndpoints).toHaveBeenCalledWith('app-demo')
    expect(screen.queryByText('确认权限组与业务动作', { selector: '.ant-card-head-title' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /应用已经由我启动/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /确认这是我的本地应用/ }))
    fireEvent.click(screen.getByRole('button', { name: '确认本地地址' }))

    await waitFor(() => expect(mockProjects.confirmEndpoint).toHaveBeenCalledWith('app-demo', 'http://127.0.0.1:5173', 3))
  })

  it('按事实层级分开确认、待确认、手工补充和已排除候选', async () => {
    const confirmed = { ...role, decision: 'CONFIRMED' as const, display_name: '普通用户' }
    const rejected = { ...role, candidate_id: `role_${'c'.repeat(32)}`, decision: 'REJECTED' as const, display_name: '排除组' }
    const manualRejected = { ...role, candidate_id: `role_${'e'.repeat(32)}`, decision: 'REJECTED' as const, display_name: '手工排除组', origin: 'MANUAL' as const }
    const pending = { ...role, candidate_id: `role_${'d'.repeat(32)}`, display_name: '待确认组' }
    const restored = {
      ...baseUnderstanding,
      confirmed_endpoint: 'http://127.0.0.1:5173',
      source_analysis_authorized: true,
      source_fingerprint: 'd'.repeat(64),
      role_candidates: [confirmed, pending, rejected, manualRejected],
      action_candidates: [{ ...action, decision: 'CONFIRMED' as const, display_name: '修改文档' }],
      revision: 3,
    }
    mockProjects.understanding.mockResolvedValue(restored)
    mockProjects.decideRole.mockResolvedValue({ ...restored, role_candidates: [confirmed, pending, { ...rejected, decision: 'PROPOSED' }, manualRejected], revision: 4 })

    render(<ApplicationSetup selected={{ project_id: 'app-demo', name: 'demo', status: 'DRAFT' }} onConnected={vi.fn()} onChanged={vi.fn()} onBack={vi.fn()} onContinue={vi.fn()} />)

    const confirmedSection = await screen.findByText('已确认的权限组')
    expect(within(confirmedSection.closest('section')!).getByText('普通用户')).toBeInTheDocument()
    expect(within(confirmedSection.closest('section')!).queryByRole('button', { name: /确认这个权限组/ })).not.toBeInTheDocument()
    expect(within(confirmedSection.closest('section')!).getByRole('button', { name: '排除这个权限组' })).toBeInTheDocument()
    expect(screen.getAllByText('系统发现，等待确认')).toHaveLength(2)
    expect(screen.getByDisplayValue('待确认组')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确认这个权限组' })).toBeInTheDocument()
    const rejectButton = screen.getByRole('button', { name: '不是权限组' })
    expect(rejectButton).toBeInTheDocument()
    expect(rejectButton).not.toHaveClass('ant-btn-dangerous')
    expect(screen.getByPlaceholderText('例如：审核员')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: '没有找到？手工补充' })).toHaveLength(2)
    expect(screen.getByText('已排除的候选（2）')).toBeInTheDocument()
    expect(screen.queryByText('角色候选')).not.toBeInTheDocument()
    expect(screen.queryByText('python-role-enum')).not.toBeInTheDocument()
    expect(screen.queryByText('已忽略')).not.toBeInTheDocument()

    expect(screen.getAllByText(/识别依据：app.py:3 · AccountRole/).length).toBeGreaterThan(0)
    expect(screen.queryByText('python-role-enum')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('已排除的候选（2）'))
    expect(await screen.findByText('排除组')).toBeInTheDocument()
    expect(screen.getByText('手工排除组')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '恢复为已确认' })).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: '移回待确认' })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: '移回待确认' }))
    await waitFor(() => expect(mockProjects.decideRole).toHaveBeenCalledWith('app-demo', rejected.candidate_id, 'PROPOSED', '排除组', 3))
  })
})
