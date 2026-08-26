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
    render(<ApplicationSetup selected={null} onConnected={onConnected} onChanged={vi.fn()} onContinue={vi.fn()} />)

    expect(screen.queryByText(/Profile path|resource id|read path|recovery path/i)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '选择应用文件夹' }))
    expect(await screen.findByText('2. 确认本地访问地址')).toBeInTheDocument()
    expect(screen.getByText(/只探测 127\.0\.0\.1/)).toBeInTheDocument()
    expect(screen.queryByText(/::1/)).not.toBeInTheDocument()
    expect(screen.getByText('Vite')).toBeInTheDocument()
    expect(screen.getByText(/可能启动方式：Vite 开发服务候选/)).toBeInTheDocument()
    expect(screen.getByText(/vite.config.ts/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /应用已经由我启动/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /确认这是我的本地应用/ }))
    fireEvent.click(screen.getByRole('button', { name: '确认本地地址' }))
    expect(await screen.findByText('3. 分析权限组与关键业务动作')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: /只读分析当前应用源码/ }))
    fireEvent.click(screen.getByRole('button', { name: '授权并开始分析' }))
    expect(await screen.findByText('4. 确认权限组与业务动作')).toBeInTheDocument()
    expect(screen.getByText(/候选，不是权限结论/)).toBeInTheDocument()
    expect(screen.getByDisplayValue('owner')).toBeInTheDocument()
    expect(screen.getByDisplayValue('修改文档')).toBeInTheDocument()
    expect(screen.getByText(/下一步：为已确认权限组准备测试账号/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '去准备测试账号' })).toBeInTheDocument()
    expect(onConnected).toHaveBeenCalledWith(expect.objectContaining({ project_id: 'app-demo' }))
  })

  it('重新打开页面时从后端事实恢复候选并保存人工决定', async () => {
    const restored = { ...baseUnderstanding, confirmed_endpoint: 'http://127.0.0.1:5173', endpoint_source_fingerprint: 'c'.repeat(64), endpoint_confirmed_at_us: 2, endpoint_last_checked_at_us: 2, endpoint_reachable: true, source_analysis_authorized: true, source_analysis_authorized_at_us: 3, source_fingerprint: 'd'.repeat(64), analysis_completed_at_us: 4, role_candidates: [role], action_candidates: [action], revision: 3 }
    mockProjects.understanding.mockResolvedValue(restored)
    mockProjects.decideRole.mockResolvedValue({ ...restored, role_candidates: [{ ...role, decision: 'CONFIRMED', display_name: '所有者' }], revision: 4 })
    render(<ApplicationSetup selected={{ project_id: 'app-demo', name: 'demo', status: 'DRAFT' }} onConnected={vi.fn()} onChanged={vi.fn()} onContinue={vi.fn()} />)

    expect(await screen.findByDisplayValue('owner')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('权限组显示名称'), { target: { value: '所有者' } })
    fireEvent.click(screen.getAllByRole('button', { name: /确\s*认/ })[0])
    await waitFor(() => expect(mockProjects.decideRole).toHaveBeenCalledWith('app-demo', role.candidate_id, 'CONFIRMED', '所有者', 3))
    expect(await screen.findByText('所有者')).toBeInTheDocument()
    expect(screen.queryByLabelText('权限组显示名称')).not.toBeInTheDocument()
  })

  it('保留只读授权并允许按当前源码重新发现候选', async () => {
    const restored = { ...baseUnderstanding, confirmed_endpoint: 'http://127.0.0.1:5173', endpoint_source_fingerprint: 'c'.repeat(64), endpoint_confirmed_at_us: 2, endpoint_last_checked_at_us: 2, endpoint_reachable: true, source_analysis_authorized: true, source_analysis_authorized_at_us: 3, source_fingerprint: 'd'.repeat(64), analysis_completed_at_us: 4, role_candidates: [], action_candidates: [], revision: 3 }
    const refreshed = { ...restored, source_fingerprint: 'e'.repeat(64), role_candidates: [role], action_candidates: [action], revision: 4 }
    mockProjects.understanding.mockResolvedValue(restored)
    mockProjects.analyzeSource.mockResolvedValue(refreshed)
    render(<ApplicationSetup selected={{ project_id: 'app-demo', name: 'demo', status: 'DRAFT' }} onConnected={vi.fn()} onChanged={vi.fn()} onContinue={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: '重新分析权限组和业务动作' }))

    await waitFor(() => expect(mockProjects.analyzeSource).toHaveBeenCalledWith('app-demo', 3))
    expect(await screen.findByDisplayValue('owner')).toBeInTheDocument()
    expect(screen.getByText('已按当前源码重新发现权限组和业务动作，请继续确认候选。')).toBeInTheDocument()
    expect(mockProjects.authorizeSourceAnalysis).not.toHaveBeenCalled()
  })

  it('按事实层级分开确认、待确认、手工补充和已忽略候选', async () => {
    const confirmed = { ...role, decision: 'CONFIRMED' as const, display_name: '普通用户' }
    const rejected = { ...role, candidate_id: `role_${'c'.repeat(32)}`, decision: 'REJECTED' as const, display_name: '忽略组' }
    const pending = { ...role, candidate_id: `role_${'d'.repeat(32)}`, display_name: '待确认组' }
    mockProjects.understanding.mockResolvedValue({
      ...baseUnderstanding,
      confirmed_endpoint: 'http://127.0.0.1:5173',
      source_analysis_authorized: true,
      source_fingerprint: 'd'.repeat(64),
      role_candidates: [confirmed, pending, rejected],
      action_candidates: [{ ...action, decision: 'CONFIRMED' as const, display_name: '修改文档' }],
      revision: 3,
    })

    render(<ApplicationSetup selected={{ project_id: 'app-demo', name: 'demo', status: 'DRAFT' }} onConnected={vi.fn()} onChanged={vi.fn()} onContinue={vi.fn()} />)

    const confirmedSection = await screen.findByText('已确认的权限组')
    expect(within(confirmedSection.closest('section')!).getByText('普通用户')).toBeInTheDocument()
    expect(within(confirmedSection.closest('section')!).queryByRole('button', { name: /确认这个权限组/ })).not.toBeInTheDocument()
    expect(screen.getAllByText('系统发现，等待确认')).toHaveLength(2)
    expect(screen.getByDisplayValue('待确认组')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确认这个权限组' })).toBeInTheDocument()
    const rejectButton = screen.getByRole('button', { name: '不是权限组' })
    expect(rejectButton).toBeInTheDocument()
    expect(rejectButton).not.toHaveClass('ant-btn-dangerous')
    expect(screen.getByPlaceholderText('例如：审核员')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: '没有找到？手工补充' })).toHaveLength(2)
    expect(screen.getByText('已忽略的系统候选（1）')).toBeInTheDocument()
    expect(screen.queryByText('角色候选')).not.toBeInTheDocument()
    expect(screen.queryByText('python-role-enum')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('查看来源详情'))
    expect(await screen.findByText('python-role-enum')).toBeInTheDocument()
    fireEvent.click(screen.getByText('已忽略的系统候选（1）'))
    expect(await screen.findByText('忽略组')).toBeInTheDocument()
  })
})
