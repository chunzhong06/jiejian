// 验证应用壳的权威状态恢复、导航、运行状态和安全退出入口。

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { aiStatusLabel, mcpStatusLabel, systemStatusLabel } from './AppHeader'
import ControlShell from './ControlShell'

const mockApi = vi.hoisted(() => ({
  projects: vi.fn().mockResolvedValue([]), readiness: vi.fn(), runs: vi.fn().mockResolvedValue([]), run: vi.fn(),
  projectRevalidation: vi.fn().mockReturnValue(null),
  projectRepair: vi.fn().mockReturnValue(null),
  inconclusiveRecovery: vi.fn().mockReturnValue(null),
  prepareSafe: vi.fn().mockResolvedValue({}),
  removeProject: vi.fn().mockResolvedValue({ project_id: 'p1', status: 'ARCHIVED' }),
  llmProfiles: vi.fn().mockResolvedValue([]), settings: vi.fn().mockResolvedValue({ enabled: false, default_profile_name: null, updated_at_us: 0 }), systemStatus: vi.fn().mockResolvedValue({ api: 'available', worker: 'stopped', browser: 'unknown' }), shutdown: vi.fn().mockResolvedValue({ status: 'stopping' }),
  mcpStatus: vi.fn().mockResolvedValue({ schema_version: '1', paired: false, accepting_connections: false, endpoint: 'http://127.0.0.1:8765/mcp', default_level: 'READ', project_grants: [], client_connected: false, client_name: null, client_version: null, last_seen_at_us: null, connection_state: 'DISABLED', last_authenticated_at_us: null, last_auth_failure_at_us: null }),
  maintenanceStatus: vi.fn().mockResolvedValue({
    schema_version: '1',
    entries: {
      assistant: { path: 'var/cache/assistant', bytes: 0, files: 0 },
      logs: { path: 'var/logs', bytes: 0, files: 0, categories: {} },
      temporary: { path: 'var', bytes: 0, files: 0 },
    },
    protected: { data: 'var/data' },
  }),
  maintenanceOperation: vi.fn(),
  assistantProject: vi.fn(), assistantGenerateProject: vi.fn(), assistantResult: vi.fn(), assistantGenerateResult: vi.fn(), assistantGenerateError: vi.fn(),
  experienceStatus: vi.fn().mockResolvedValue({ available: false, display_name: '协作空间', unavailable_reason: '未配置官方示例目录', active: false, experience_id: null, project_id: null, origin: null, scenario_prepared: false, scenario_version: null, vulnerable_change_id: null, repair_change_id: null }),
  validationSummary: vi.fn().mockResolvedValue({ available: false, unavailable_reason: '尚未发布可展示的验证汇总', summary: null }),
  experienceStart: vi.fn(), experiencePrepare: vi.fn(), experienceSwitch: vi.fn(), experienceStop: vi.fn(),
  checkPreview: vi.fn(), checkPrepare: vi.fn(), checkSubmit: vi.fn(), permissionMatrix: vi.fn(), permissionProposals: vi.fn(), permissionConfirm: vi.fn(),
  cancel: vi.fn().mockResolvedValue({}), progress: vi.fn().mockResolvedValue({ job_id: 'job', attempt: 1, events: [] }), findings: vi.fn().mockResolvedValue([]), evidence: vi.fn().mockResolvedValue([]), evidenceDetail: vi.fn().mockResolvedValue({}), presentation: vi.fn(), history: vi.fn(), reports: vi.fn().mockResolvedValue([]), report: vi.fn().mockResolvedValue({}), reportView: vi.fn((runId: string, reportId: string) => `/api/runs/${runId}/reports/${reportId}/view`),
}))

vi.mock('../api/projects', () => ({ projectsApi: {
  projects: mockApi.projects,
  remove: mockApi.removeProject,
  prepareSafe: mockApi.prepareSafe,
  status: async (projectId: string) => {
    const readiness = await mockApi.readiness(projectId)
    const resultReady = readiness.next_required_action === 'OPEN_RESULT'
    const checkReady = readiness.next_required_action === 'RUN_CHECK'
    return {
      project: { project_id: projectId, name: '未命名应用', status: readiness.project_status, target_type: 'WEB' },
      readiness,
      revalidation: mockApi.projectRevalidation(projectId),
      repair: mockApi.projectRepair(projectId),
      areas: [
        { key: 'overview', label: '工作台', description: '查看当前状态。', route: '/workspace', status: 'AVAILABLE', status_label: '持续更新' },
        { key: 'changes', label: '变化', description: '核对 Agent 修改。', route: '/changes', status: 'EMPTY', status_label: '暂无变化' },
        { key: 'permissions', label: '权限', description: '维护权限边界。', route: '/permissions', status: 'READY', status_label: '规则可用' },
        { key: 'tests', label: '测试', description: '准备、运行与结果。', route: '/tests', status: resultReady ? 'AVAILABLE' : checkReady ? 'READY' : 'NEEDS_ATTENTION', status_label: resultReady ? '已有结果' : checkReady ? '可以检查' : '需要处理' },
      ],
      primary_attention_key: resultReady ? null : 'prepare',
      attention_items: resultReady ? [] : [{ key: 'prepare', label: checkReady ? '开始验证运行' : '完善测试准备', description: '处理当前检查条件。', route: checkReady ? '/validation' : '/preparation', tone: 'ACTION' }],
      latest_change: null,
      latest_result: resultReady ? { run_id: 'run-current', verdict: 'BLOCK', headline: '发现权限问题', scope_statement: '当前范围已检查。', verified_change_id: null } : null,
      inconclusive_recovery: mockApi.inconclusiveRecovery(projectId),
    }
  },
} }))
vi.mock('../api/runs', () => ({ runsApi: { runs: mockApi.runs, run: mockApi.run, cancel: mockApi.cancel, progress: mockApi.progress, createRun: vi.fn() } }))
vi.mock('../api/llm', () => ({ llmApi: { profiles: mockApi.llmProfiles, settings: mockApi.settings } }))
vi.mock('../api/mcp', () => ({ mcpAccessApi: { status: mockApi.mcpStatus } }))
vi.mock('../api/assistant', () => ({ assistantApi: {
  project: mockApi.assistantProject,
  generateProject: mockApi.assistantGenerateProject,
  result: mockApi.assistantResult,
  generateResult: mockApi.assistantGenerateResult,
  generateError: mockApi.assistantGenerateError,
} }))
vi.mock('../api/experience', () => ({ experienceApi: { status: mockApi.experienceStatus, validationSummary: mockApi.validationSummary, start: mockApi.experienceStart, prepare: mockApi.experiencePrepare, switchVersion: mockApi.experienceSwitch, stop: mockApi.experienceStop } }))
vi.mock('../api/system', () => ({ systemApi: { status: mockApi.systemStatus, maintenanceStatus: mockApi.maintenanceStatus, maintenanceOperation: mockApi.maintenanceOperation, shutdown: mockApi.shutdown } }))
vi.mock('../api/checks', () => ({ checksApi: { preview: mockApi.checkPreview, prepare: mockApi.checkPrepare, submit: mockApi.checkSubmit } }))
vi.mock('../api/permissionIntents', () => ({ permissionIntentsApi: { matrix: mockApi.permissionMatrix, proposals: mockApi.permissionProposals, confirm: mockApi.permissionConfirm } }))
vi.mock('../api/results', () => ({ resultsApi: { findings: mockApi.findings, evidence: mockApi.evidence, evidenceDetail: mockApi.evidenceDetail, presentation: mockApi.presentation, history: mockApi.history, reports: mockApi.reports, report: mockApi.report, reportView: mockApi.reportView, reportFormat: (runId: string, reportId: string, format: string) => `/api/runs/${runId}/reports/${reportId}/formats/${format}` } }))
vi.mock('../api/http', () => ({ ApiError: class extends Error {}, request: vi.fn() }))

describe('应用壳', () => {
  afterEach(() => cleanup())
  beforeEach(() => { localStorage.clear(); window.location.hash = ''; vi.clearAllMocks(); mockApi.projects.mockResolvedValue([]); mockApi.projectRevalidation.mockReturnValue(null); mockApi.projectRepair.mockReturnValue(null); mockApi.inconclusiveRecovery.mockReturnValue(null); mockApi.readiness.mockResolvedValue({ project_id: 'p1', project_status: 'READY', application_connected: true, endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED', discovered_role_count: 1, confirmed_role_count: 1, discovered_action_count: 1, confirmed_action_count: 1, execution_profile_available: false, completed_flow_available: false, active_contract_available: false, permission_actions: [], current_scope_runnable: false, remaining_gap_count: 1, active_tasks: [], latest_verified_run_id: null, next_required_action: 'RECORD_FLOW' }); mockApi.runs.mockResolvedValue([]); mockApi.llmProfiles.mockResolvedValue([]); mockApi.settings.mockResolvedValue({ enabled: false, default_profile_name: null, updated_at_us: 0 }); mockApi.mcpStatus.mockResolvedValue({ schema_version: '1', paired: false, accepting_connections: false, endpoint: 'http://127.0.0.1:8765/mcp', default_level: 'READ', project_grants: [], client_connected: false, client_name: null, client_version: null, last_seen_at_us: null, connection_state: 'DISABLED', last_authenticated_at_us: null, last_auth_failure_at_us: null }); mockApi.systemStatus.mockResolvedValue({ api: 'available', worker: 'stopped', browser: 'unknown' }); mockApi.permissionMatrix.mockResolvedValue({ project_id: 'p1', actions: [], confirmed_count: 0, review_required_count: 0, unconfirmed_count: 0, executable_count: 0, representative_gap_count: 0, compilable_action_count: 0, actionable_confirmation_count: 0, required_confirmation_count: 0 }); mockApi.validationSummary.mockResolvedValue({ available: false, unavailable_reason: '尚未发布可展示的验证汇总', summary: null }); mockApi.presentation.mockResolvedValue({ run_id: 'run-current', project_id: 'p1', project_name: '演示应用', run_lifecycle: 'COMPLETED', verdict: 'BLOCK', policy_epoch: 1, policy_fingerprint: 'fingerprint', relevant_intents: [{ intent_id: 'intent-export', revision: 1, intent_hash: 'intent-hash', display_label: '权限 P-2027-01', expectation: 'DENY', business_statement: 'Bob 可以查看日常协作资料，但不能导出完整项目交付包。' }], change_verification: null, repair_verification: null, headline: '发现权限问题', scope_statement: '当前范围已检查。', checked_count: 1, safe_count: 0, problem_count: 1, inconclusive_count: 0, uncovered_count: 0, execution_problem: null, issues: [{ finding_id: 'finding-export', title: 'Bob 导出完整项目交付包', subject_group: '普通成员', action_id: 'export-package', action: 'export-package', resource: '完整项目交付包', relation: '项目成员', expectation: 'Bob 不得导出完整项目交付包', surface_result: 'HTTP 403 · 请求被拒绝', actual_result: '后台任务成功，ZIP 已生成', conclusion: '表面拒绝没有阻止真实后果', explanation: '权限判断发生过晚。', planned_identity_id: 'bob', planned_identity_label: 'Bob · 普通成员', actual_identity_status: 'CONFIRMED', actual_identity_id: 'bob', actual_identity_label: 'Bob · 普通成员', severity: 'high', evidence_refs: [], evidence_sources: [], diagnosis: null, claim_boundary: { surface_response_status: 'DENIED', business_effect_status: 'CONFIRMED', actual_identity_status: 'CONFIRMED', breakpoint_precision: null, repair_status: null, supported_statement: 'Bob 的请求虽然被拒绝，但完整项目交付包在本轮真实形成。', unsupported_statements: [] }, evidence_explanations: [], verdict: 'VULNERABLE', occurrence_status: 'APPEARED', repair_requirement: null }], limitations: [], execution_traces: [] }); mockApi.history.mockResolvedValue({ project_id: 'p1', intents: [], comparisons: [{ run_id: 'run-history', previous_run_id: null, checked_at_us: 1, changes: [{ finding_id: 'finding-1', title: '权限问题', subject_group: '普通用户账号', action: '读取', resource: '文档', relation: '拥有', status: 'NEW', status_label: '新发现', explanation: '首次确认。', severity: 'high', evidence_refs: [], current_verdict: 'VULNERABLE', occurrence_status: 'APPEARED' }] }] }); mockApi.assistantProject.mockRejectedValue(new Error('assistant unavailable')); mockApi.assistantResult.mockRejectedValue(new Error('assistant unavailable')); mockApi.checkPreview.mockResolvedValue({ project_id: 'p1', ready: false, actions: [], gaps: [], next_path: null, next_label: null, case_count: 0, differential_pair_count: 0 }) })
  beforeEach(() => mockApi.permissionProposals.mockResolvedValue({ project_id: 'p1', proposals: [] }))
  beforeEach(() => mockApi.experienceStatus.mockResolvedValue({ available: false, display_name: '协作空间', unavailable_reason: '未配置官方示例目录', active: false, experience_id: null, project_id: null, origin: null, scenario_prepared: false, scenario_version: null, vulnerable_change_id: null, repair_change_id: null }))

  it('显示工作台、任务导航和真实运行状态', async () => {
    render(<ControlShell />)
    expect(await screen.findByText('建立第一份权限安全基线')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '切换应用，当前：尚未选择' })).toBeInTheDocument()
    for (const item of ['工作台', '变化', '权限', '测试']) expect(screen.getAllByText(item).length).toBeGreaterThan(0)
    expect(document.querySelectorAll('.module-navigation .module-workbench-button, .module-navigation .module-navigation-button')).toHaveLength(4)
    expect(document.querySelector('.module-navigation')).toBeInTheDocument()
    expect(screen.getByText('AI辅助 · 未开启')).toBeInTheDocument()
    expect(screen.getByText('AI 工具 · 未准备')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '系统需处理' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '设置与更多' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '退出界鉴' })).toBeInTheDocument()
    expect(document.querySelector('.phase-steps')).not.toBeInTheDocument()
  })

  it('只有用户主动进入时才用单一样例四幕替换正式产品壳，退出后恢复原上下文', async () => {
    const run = { run_id: 'run-current', created_at_us: 3, lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED' }
    const experience = { available: true, display_name: '协作空间', unavailable_reason: null, active: true, experience_id: `exp_${'1'.repeat(32)}`, project_id: 'p1', origin: 'http://127.0.0.1:1', scenario_prepared: true, scenario_version: 'VULNERABLE', scenario_changed_at_us: 2, vulnerable_change_id: `chg_${'2'.repeat(32)}`, repair_change_id: null }
    mockApi.experienceStatus.mockResolvedValue(experience)
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', name: '协作空间', status: 'READY' }])
    mockApi.readiness.mockResolvedValue({ project_id: 'p1', project_status: 'READY', application_connected: true, endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED', discovered_role_count: 2, confirmed_role_count: 2, discovered_action_count: 1, confirmed_action_count: 1, execution_profile_available: true, completed_flow_available: true, active_contract_available: true, permission_actions: [], current_scope_runnable: true, remaining_gap_count: 0, active_tasks: [], latest_verified_run_id: 'run-current', next_required_action: 'OPEN_RESULT', preparation: { project_id: 'p1', ready: true, items: [], next_item_key: null, auto_action_count: 0, user_action_count: 0, blocked_count: 0, external_blockers: [] } })
    mockApi.runs.mockResolvedValue([run])
    window.location.hash = '#/workspace'

    render(<ControlShell />)

    fireEvent.click(await screen.findByRole('button', { name: '切换应用，当前：尚未选择' }))
    const menuLabel = (await screen.findAllByText('协作空间')).find((element) => element.classList.contains('ant-dropdown-menu-title-content'))
    expect(menuLabel).toBeDefined()
    fireEvent.click(menuLabel!)
    expect(document.querySelector('.module-navigation')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '进入完整展示' }))

    expect(await screen.findByRole('heading', { name: 'Bob 收到 403，完整项目交付包却仍在后台生成' })).toBeInTheDocument()
    const chapterNavigation = screen.getByRole('navigation', { name: '展示章节' })
    for (const item of ['发现矛盾', '回看变化', '展开证据', '验证修复']) expect(within(chapterNavigation).getByRole('button', { name: new RegExp(item) })).toBeInTheDocument()
    expect(document.querySelector('.module-navigation')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('官方示例状态')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '返回工作台' }))
    expect(await screen.findByRole('heading', { name: '协作空间', level: 2 })).toBeInTheDocument()
    expect(window.location.hash).toBe('#/workspace')
    expect(document.querySelector('.module-navigation')).toBeInTheDocument()
  })

  it('启动官方示例时使用单一产品入口并保留后端完整准备能力', async () => {
    const available = { available: true, display_name: '协作空间', unavailable_reason: null, active: false, experience_id: null, project_id: null, origin: null, scenario_prepared: false, scenario_version: null, vulnerable_change_id: null, repair_change_id: null }
    const started = { ...available, active: true, experience_id: `exp_${'1'.repeat(32)}`, project_id: 'p1', origin: 'http://127.0.0.1:1', scenario_version: 'VULNERABLE' }
    mockApi.experienceStatus.mockResolvedValue(available)
    mockApi.experienceStart.mockResolvedValue(started)
    mockApi.projects.mockResolvedValueOnce([]).mockResolvedValue([{ project_id: 'p1', name: '协作空间', status: 'READY' }])

    render(<ControlShell />)

    fireEvent.click(await screen.findByRole('button', { name: '启动官方示例' }))
    fireEvent.click(await screen.findByRole('button', { name: '启动问题版' }))
    await waitFor(() => expect(mockApi.experienceStart).toHaveBeenCalledWith())
    await waitFor(() => expect(window.location.hash).toBe('#/workspace'))
    expect(await screen.findByLabelText('官方样例状态')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '评委导览' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '完整体验' })).not.toBeInTheDocument()
  })

  it('顶部状态标签只由结构化状态决定', () => {
    const disabled = { enabled: false, default_profile_name: null, updated_at_us: 0 }
    const enabled = { enabled: true, default_profile_name: 'default', updated_at_us: 0 }
    expect(aiStatusLabel([], disabled, false, false)).toBe('AI辅助 · 未开启')
    expect(aiStatusLabel([], enabled, false, false)).toBe('AI辅助 · 待配置')
    expect(aiStatusLabel([], enabled, true, false)).toBe('AI辅助 · 状态未知')
    const mcp = { schema_version: '1' as const, paired: true, accepting_connections: true, endpoint: 'http://127.0.0.1:8765/mcp', default_level: 'READ' as const, project_grants: [], client_connected: false, client_name: null, client_version: null, last_seen_at_us: null, connection_state: 'CREDENTIAL_READY' as const, last_authenticated_at_us: null, last_auth_failure_at_us: null }
    expect(mcpStatusLabel({ ...mcp, paired: false, connection_state: 'DISABLED' }, false)).toBe('AI 工具 · 未准备')
    expect(mcpStatusLabel(mcp, false)).toBe('AI 工具 · 等待连接')
    expect(mcpStatusLabel({ ...mcp, client_connected: true, client_name: 'Codex', connection_state: 'CONNECTED' }, false)).toBe('AI 工具 · Codex')
    expect(mcpStatusLabel(mcp, true)).toBe('AI 工具 · 状态未知')
    expect(systemStatusLabel({ api: 'available', worker: 'running', browser: 'available' })).toBe('系统正常')
    expect(systemStatusLabel({ api: 'available', worker: 'stopped', browser: 'available' })).toBe('系统需处理')
  })

  it('客户端在壳层首次读取后连接时会自动更新顶部状态', async () => {
    const waiting = {
      schema_version: '1', paired: true, accepting_connections: true,
      endpoint: 'http://127.0.0.1:8765/mcp', default_level: 'READ', project_grants: [],
      client_connected: false, client_name: null, client_version: null, last_seen_at_us: null,
      connection_state: 'CREDENTIAL_READY', last_authenticated_at_us: null, last_auth_failure_at_us: null,
    }
    mockApi.mcpStatus
      .mockResolvedValueOnce(waiting)
      .mockResolvedValue({ ...waiting, client_connected: true, client_name: 'Codex', connection_state: 'CONNECTED' })

    render(<ControlShell />)
    expect(await screen.findByText('AI 工具 · 等待连接')).toBeInTheDocument()

    expect(await screen.findByText('AI 工具 · Codex', {}, { timeout: 3_000 })).toBeInTheDocument()
  })

  it('通过明确确认入口请求安全退出', async () => {
    render(<ControlShell />)
    fireEvent.click(await screen.findByRole('button', { name: '退出界鉴' }))
    expect(await screen.findByText('退出界鉴？')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: '继续使用' })).toHaveFocus())
    fireEvent.click(screen.getByRole('button', { name: '安全退出' }))
    await waitFor(() => expect(mockApi.shutdown).toHaveBeenCalledOnce())
    expect(await screen.findByText('界鉴正在安全退出')).toBeInTheDocument()
  })

  it('移除当前应用前说明保留源码和历史，并在成功后清空当前选择', async () => {
    const project = { project_id: 'p1', name: '演示应用', status: 'READY' }
    mockApi.projects.mockResolvedValueOnce([project]).mockResolvedValueOnce([])
    render(<ControlShell />)

    fireEvent.click(await screen.findByRole('button', { name: '切换应用，当前：尚未选择' }))
    fireEvent.click(await screen.findByText('演示应用'))
    fireEvent.click(await screen.findByRole('button', { name: '切换应用，当前：演示应用' }))
    fireEvent.click(await screen.findByText('移除当前应用'))

    expect(await screen.findByText(/不会删除应用源码、检查结果和历史记录/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认移除' }))
    await waitFor(() => expect(mockApi.removeProject).toHaveBeenCalledWith('p1'))
    await waitFor(() => expect(screen.getByRole('button', { name: '切换应用，当前：尚未选择' })).toBeInTheDocument())
  })

  it('关闭退出确认后把焦点还给触发按钮', async () => {
    render(<ControlShell />)
    const trigger = await screen.findByRole('button', { name: '退出界鉴' })
    trigger.focus()
    fireEvent.click(trigger)
    const cancel = await screen.findByRole('button', { name: '继续使用' })
    await waitFor(() => expect(cancel).toHaveFocus())
    fireEvent.click(cancel)
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('旧 route 不再作为兼容入口，未知路径回到工作台', async () => {
    window.location.hash = '#/apps/access'
    render(<ControlShell />)
    await waitFor(() => expect(window.location.hash).toBe('#/workspace'))
    expect(await screen.findByText('建立第一份权限安全基线')).toBeInTheDocument()
  })

  it('测试准备自动动作经项目 API 执行后重新读取权威工作区', async () => {
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.readiness.mockResolvedValue({
      project_id: 'p1', project_status: 'READY', application_connected: true,
      endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED',
      discovered_role_count: 1, confirmed_role_count: 1,
      discovered_action_count: 1, confirmed_action_count: 1,
      execution_profile_available: false, completed_flow_available: false,
      active_contract_available: false, current_scope_runnable: false,
      remaining_gap_count: 1, active_tasks: [], latest_verified_run_id: null,
      next_required_action: 'RECORD_FLOW',
      preparation: {
        project_id: 'p1', ready: false, next_item_key: 'identity:alice',
        auto_action_count: 1, user_action_count: 0, blocked_count: 0,
        external_blockers: [],
        items: [{
          key: 'identity:alice', kind: 'IDENTITY', label: 'Alice 测试账号',
          status: 'AUTO', description: '可以创建非秘密测试账号记录。',
          next_path: '/identities', next_label: '管理测试账号',
          reason_codes: ['TEST_IDENTITY_MISSING'], auto_action: 'ENSURE_IDENTITY_RECORD',
          role_candidate_id: null, action_candidate_id: null, recording_id: null,
          identity_id: null, owner_test_identity_id: null,
        }],
      },
    })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/preparation'
    render(<ControlShell />)

    fireEvent.click(await screen.findByRole('button', { name: '继续准备' }))
    await waitFor(() => expect(mockApi.prepareSafe).toHaveBeenCalledWith('p1'))
    await waitFor(() => expect(mockApi.readiness.mock.calls.length).toBeGreaterThan(1))
  })

  it('从详细确认页返回测试准备时重新读取权威状态', async () => {
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/permissions'
    render(<ControlShell />)

    expect(await screen.findByRole('heading', { name: '权限', level: 2 })).toBeInTheDocument()
    const beforeReturn = mockApi.readiness.mock.calls.length
    window.location.hash = '#/preparation'
    window.dispatchEvent(new HashChangeEvent('hashchange'))

    expect(await screen.findByRole('heading', { name: '测试准备' })).toBeInTheDocument()
    await waitFor(() => expect(mockApi.readiness.mock.calls.length).toBeGreaterThan(beforeReturn))
  })

  it('详细页继续准备先读取新快照，再按顶层准备状态进入下一任务', async () => {
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/permissions'
    render(<ControlShell />)

    expect(await screen.findByRole('heading', { name: '权限', level: 2 })).toBeInTheDocument()
    mockApi.readiness.mockClear()
    mockApi.readiness.mockResolvedValue({
      project_id: 'p1', project_status: 'READY', application_connected: true,
      endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED',
      discovered_role_count: 1, confirmed_role_count: 1, discovered_action_count: 1, confirmed_action_count: 1,
      execution_profile_available: true, completed_flow_available: true, active_contract_available: true,
      current_scope_runnable: true, remaining_gap_count: 0, active_tasks: [], latest_verified_run_id: null,
      next_required_action: 'RUN_CHECK',
      preparation: {
        project_id: 'p1', ready: true, items: [], next_item_key: null, next_path: '/validation', next_label: '前往验证运行',
        auto_action_count: 0, user_action_count: 0, blocked_count: 0, external_blockers: [],
      },
    })

    fireEvent.click(screen.getByRole('button', { name: '继续准备' }))

    await waitFor(() => expect(mockApi.readiness).toHaveBeenCalledOnce())
    await waitFor(() => expect(window.location.hash).toBe('#/validation'))
    expect(await screen.findByText('核对本次检查')).toBeInTheDocument()
  })

  it('没有应用时模型服务和运行环境仍可访问', async () => {
    window.location.hash = '#/settings/models'
    const models = render(<ControlShell />)
    expect((await screen.findAllByText('AI 辅助')).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: '打开 AI 辅助设置' }).length).toBeGreaterThan(0)
    expect(screen.getByRole('table', { name: 'AI参与范围' })).toBeInTheDocument()
    models.unmount()
    window.location.hash = '#/settings/system'
    render(<ControlShell />)
    expect((await screen.findAllByText('运行环境')).length).toBeGreaterThan(0)
    expect(screen.getByText('状态来自当前运行环境')).toBeInTheDocument()
  })

  it('错误恢复使用服务端诊断路由，不按错误码正则猜页面', async () => {
    mockApi.projects.mockRejectedValueOnce({
      code: 'SELF_TARGET_FORBIDDEN',
      message: '请求失败',
      diagnosis: {
        route: '/application', headline: '不能检查界鉴自身',
        short_message: '请返回应用接入页确认真正的被测应用地址。', cleanup_warnings: [],
      },
    })
    render(<ControlShell />)
    expect((await screen.findAllByText('不能检查界鉴自身')).length).toBeGreaterThan(0)
    expect((await screen.findAllByText('请返回应用接入页确认真正的被测应用地址。')).length).toBeGreaterThan(0)
    fireEvent.click(screen.getAllByRole('button', { name: '前往处理页面' })[0])
    await waitFor(() => expect(window.location.hash).toBe('#/application'))
  })

  it('页面操作错误只进入右下角通知，不重复覆盖当前页面', async () => {
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.readiness.mockResolvedValue({ project_id: 'p1', project_status: 'READY', application_connected: true, endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED', discovered_role_count: 1, confirmed_role_count: 1, discovered_action_count: 1, confirmed_action_count: 1, execution_profile_available: true, completed_flow_available: true, active_contract_available: true, permission_actions: [], current_scope_runnable: true, remaining_gap_count: 0, active_tasks: [], latest_verified_run_id: null, next_required_action: 'RUN_CHECK' })
    mockApi.checkPreview.mockRejectedValueOnce({
      code: 'CHECK_NOT_READY',
      message: '请求失败',
      diagnosis: {
        route: '/validation', headline: '权限检查条件尚未准备好',
        short_message: '请返回权限规则页处理当前缺口。', cleanup_warnings: [], intervention: 'USER_ACTION',
      },
    })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/validation'

    render(<ControlShell />)

    expect(await screen.findByText('权限检查条件尚未准备好')).toBeInTheDocument()
    expect(screen.getByLabelText('全局通知')).toHaveTextContent('请返回权限规则页处理当前缺口。')
    expect(screen.queryByText('这一步没有完成')).not.toBeInTheDocument()
  })

  it('只有统一重验状态 READY 才把服务端 change_id 交给验证页', async () => {
    const changeId = `chg_${'7'.repeat(32)}`
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.projectRevalidation.mockReturnValue({ status: 'READY', change_id: changeId, summary: '可以开始重新验证', next_path: '/validation', next_label: '开始重新验证' })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/validation'

    render(<ControlShell />)

    expect(await screen.findByText('核对本次检查')).toBeInTheDocument()
    expect(mockApi.checkPreview).toHaveBeenCalledWith('p1', changeId)
  })

  it('正式修复待复验时优先使用 ProjectRepair 关联变化，不读取 Sample 修复标识', async () => {
    const repairChangeId = `chg_${'6'.repeat(32)}`
    const ordinaryChangeId = `chg_${'7'.repeat(32)}`
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.projectRevalidation.mockReturnValue({ status: 'READY', change_id: ordinaryChangeId, summary: '普通变化可以验证', next_path: '/validation', next_label: '开始验证' })
    mockApi.projectRepair.mockReturnValue({
      project_id: 'p1', status: 'READY_TO_VERIFY', next_path: '/validation', next_label: '复验这次修复', reason_codes: ['REPAIR_VERIFICATION_REQUIRED'],
      tasks: [{ source_run_id: 'run-block', source_finding_id: 'finding-block', status: 'READY_TO_VERIFY', must_disappear: '越权变化必须消失。', must_remain: '合法修改必须保持。', must_not_change: ['权限要求', '关键证据'], linked_change_id: repairChangeId, verification_run_id: null, verification_status: null, next_path: '/validation', next_label: '复验这次修复', reason_codes: ['REPAIR_VERIFICATION_REQUIRED'] }],
    })
    mockApi.experienceStatus.mockResolvedValue({ available: true, display_name: '协作空间', unavailable_reason: null, active: true, experience_id: `exp_${'1'.repeat(32)}`, project_id: 'p1', origin: 'http://127.0.0.1:1', scenario_prepared: true, scenario_version: 'FIXED', vulnerable_change_id: `chg_${'7'.repeat(32)}`, repair_change_id: `chg_${'8'.repeat(32)}` })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/validation'

    render(<ControlShell />)

    expect(await screen.findByText('核对本次检查')).toBeInTheDocument()
    expect(mockApi.checkPreview).toHaveBeenCalledWith('p1', repairChangeId)
    expect(mockApi.checkPreview).not.toHaveBeenCalledWith('p1', ordinaryChangeId)
    expect(mockApi.checkPreview).not.toHaveBeenCalledWith('p1', `chg_${'8'.repeat(32)}`)
  })

  it('重验前置状态阻止前端拼接 change_id，并导航到服务端指定区域', async () => {
    const changeId = `chg_${'8'.repeat(32)}`
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.projectRevalidation.mockReturnValue({ status: 'REVIEW_REQUIRED', change_id: changeId, summary: '需要重新确认实现映射', next_path: '/permissions', next_label: '确认权限实现' })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/validation'

    render(<ControlShell />)

    await waitFor(() => expect(window.location.hash).toBe('#/permissions'))
    expect(await screen.findByRole('heading', { name: '权限', level: 2 })).toBeInTheDocument()
    expect(mockApi.checkPreview).not.toHaveBeenCalledWith('p1', changeId)
    expect(mockApi.checkSubmit).not.toHaveBeenCalled()
  })

  it('运行环境展示实际解释器与工具链来源', async () => {
    mockApi.systemStatus.mockResolvedValue({
      api: 'available', worker: 'running', browser: 'available', recovered_jobs: 2,
      environment: {
        python: { ok: true, version: '3.13.15', executable: 'D:\\env\\python.exe', prefix: 'D:\\env', environment_type: 'Conda', user_site_on_sys_path: false, issues: [] },
        node: { version: '24.13.0', executable: 'D:\\runtime\\node.exe' },
        pnpm: { version: '11.21.0', executable: 'D:\\runtime\\pnpm.cmd' },
        playwright: { package_version: '1.58.0', chromium_executable: 'D:\\runtime\\chromium.exe' },
        frontend: { mode: 'prebuilt', dependencies: '已验证并复用' },
      },
    })
    window.location.hash = '#/settings/system'
    render(<ControlShell />)
    expect(await screen.findByText(/3\.13\.15/)).toBeInTheDocument()
    expect(screen.getByText('未使用')).toBeInTheDocument()
    expect(screen.getByText('已验证并复用')).toBeInTheDocument()
    expect(screen.getByText('本次自动恢复任务').closest('tr')).toHaveTextContent('2')
  })

  it('陈旧项目不会绕过项目选择边界', async () => {
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'stale-project' }))
    render(<ControlShell />)
    expect(await screen.findByText('建立第一份权限安全基线')).toBeInTheDocument()
    expect(localStorage.getItem('jiejian.project')).toBeNull()
  })

  it('进入结果与历史页面时发现当前 SPA 之外新形成的 Run', async () => {
    const run = { run_id: 'run-current', created_at_us: 3, execution_schema_version: '1', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED', case_progress: { completed: 1, total: 1 }, observer_health: { required_observations: ['resource_state'], resource_state: { configured: true, required: true } } }
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.runs.mockResolvedValueOnce([]).mockResolvedValue([run])
    mockApi.run.mockResolvedValue(run)
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/workspace'

    render(<ControlShell />)

    expect(await screen.findByRole('button', { name: '切换应用，当前：未命名应用' })).toBeInTheDocument()
    await waitFor(() => expect(mockApi.runs).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: '进入测试' }))
    await waitFor(() => expect(mockApi.runs).toHaveBeenCalledTimes(2))
    fireEvent.click(await screen.findByRole('button', { name: '查看结果与历史' }))
    await waitFor(() => expect(mockApi.runs).toHaveBeenCalledTimes(3))
    await waitFor(() => expect(document.querySelector('#result-headline')).toHaveTextContent('发现权限问题'))

    fireEvent.click(await screen.findByRole('button', { name: '查看历史变化' }))
    await waitFor(() => expect(mockApi.runs).toHaveBeenCalledTimes(4))
    await waitFor(() => expect(mockApi.history).toHaveBeenCalledWith('p1'))
    expect((await screen.findAllByText('新发现')).length).toBeGreaterThan(0)
  })

  it('串起检查预览、已发布结果、证据、报告和历史入口', async () => {
    const run = { run_id: 'run-current', created_at_us: 3, execution_schema_version: '1', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED', case_progress: { completed: 1, total: 1 }, observer_health: { required_observations: ['resource_state'], resource_state: { configured: true, required: true } } }
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.readiness.mockResolvedValue({ project_id: 'p1', project_status: 'READY', application_connected: true, endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED', discovered_role_count: 1, confirmed_role_count: 1, discovered_action_count: 1, confirmed_action_count: 1, execution_profile_available: true, completed_flow_available: true, active_contract_available: true, permission_actions: [], current_scope_runnable: true, remaining_gap_count: 0, active_tasks: [], latest_verified_run_id: 'run-current', next_required_action: 'RUN_CHECK' })
    mockApi.runs.mockResolvedValue([run, { run_id: 'run-history', created_at_us: 1, lifecycle: 'COMPLETED', result_integrity: 'VERIFIED' }])
    mockApi.run.mockResolvedValue(run)
    mockApi.checkPreview.mockResolvedValue({ project_id: 'p1', ready: true, actions: [{ action_candidate_id: 'read', action_display_name: '读取文档', resource_logical_name: '文档', ready: true, checks: [{ subject_label: '成员账号', subject_role_display_name: '成员', relation: 'OWNS', expectation: 'DENY', ready: true, gaps: [] }], gaps: [] }], gaps: [], next_path: null, next_label: null, case_count: 1, differential_pair_count: 1 })
    mockApi.checkSubmit.mockResolvedValue({ schema_version: '1', run, job: { job_id: 'job-1', state: 'QUEUED' } })
    mockApi.findings.mockResolvedValue([{ finding: { finding_id: 'finding-1', identity: { permission_intent: '读取文档', subject_class: '成员', action: 'read', resource_class: '文档' } }, occurrence: { occurrence_id: 'occ-1', status: 'APPEARED', verdict: 'BLOCK', severity: 'high', evidence_refs: ['evidence-1'] } }])
    mockApi.evidence.mockResolvedValue([{ evidence_id: 'evidence-1' }])
    mockApi.evidenceDetail.mockResolvedValue({ case_snapshot: { case_id: 'case-1', subject_id: 'member', action_id: 'read', resource_ids: ['document'], required_observations: ['resource_state'] }, execution_fact: { target_type: 'WEB', action_id: 'read', outcome: 'DENIED', reason_codes: [] }, observation_facts: [{ requirement_id: 'resource_state', resource_id: 'document', effect: 'CONFIRMED', complete: true, reliable: true, reason_codes: [] }], observations: [], outcomes: [], verdict: 'BLOCK', reason_codes: [] })
    mockApi.reports.mockResolvedValue([{ report_id: 'report-1', gate_decision: 'PASS' }])
    mockApi.report.mockResolvedValue({ runtime: { verdict: 'BLOCK', findings: [{}] }, gate: { decision: 'PASS' }, limitations: [] })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/validation'
    render(<ControlShell />)
    expect(await screen.findByRole('button', { name: '切换应用，当前：未命名应用' })).toBeInTheDocument()
    expect(await screen.findByText('核对本次检查')).toBeInTheDocument()
    expect(screen.queryByLabelText('选择执行配置')).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '查看检查结果' }))
    expect(await screen.findByText('检查对象')).toBeInTheDocument()
    fireEvent.click(screen.getByText('完整报告'))
    fireEvent.click(await screen.findByRole('button', { name: /导出/ }))
    expect(await screen.findByRole('link', { name: 'JSON' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '查看历史变化' }))
    expect((await screen.findAllByText('新发现')).length).toBeGreaterThan(0)
  })

  it('普通证据不足恢复只导航到验证页，不自动创建 Run', async () => {
    const run = { run_id: 'run-current', created_at_us: 3, lifecycle: 'COMPLETED', verdict: 'INCONCLUSIVE', result_integrity: 'VERIFIED' }
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.readiness.mockResolvedValue({ project_id: 'p1', project_status: 'READY', application_connected: true, endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED', discovered_role_count: 2, confirmed_role_count: 2, discovered_action_count: 1, confirmed_action_count: 1, execution_profile_available: true, completed_flow_available: true, active_contract_available: true, permission_actions: [], current_scope_runnable: true, remaining_gap_count: 0, active_tasks: [], latest_verified_run_id: 'run-current', next_required_action: 'OPEN_RESULT', preparation: { project_id: 'p1', ready: true, items: [], next_item_key: null, auto_action_count: 0, user_action_count: 0, blocked_count: 0, external_blockers: [] } })
    mockApi.inconclusiveRecovery.mockReturnValue({ source_run_id: 'run-current', summary: '当前测试条件已经恢复；旧结果仍保持证据不足，可以开始一次新的独立检查。', next_path: '/validation', next_label: '重新检查原权限考题', reason_codes: ['ORIGINAL_PERMISSION_INTENT_READY'] })
    mockApi.runs.mockResolvedValue([run])
    mockApi.run.mockResolvedValue(run)
    mockApi.presentation.mockResolvedValue({ run_id: 'run-current', project_id: 'p1', project_name: '演示应用', run_lifecycle: 'COMPLETED', verdict: 'INCONCLUSIVE', policy_epoch: 1, policy_fingerprint: 'a'.repeat(64), relevant_intents: [], change_verification: null, repair_verification: null, headline: '证据不足', scope_statement: '真实结果暂时无法确认。', checked_count: 0, safe_count: 0, problem_count: 0, inconclusive_count: 1, uncovered_count: 0, execution_problem: null, issues: [], limitations: [], execution_traces: [] })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/results'
    render(<ControlShell />)

    fireEvent.click(await screen.findByRole('button', { name: '重新检查原权限考题' }))

    await waitFor(() => expect(window.location.hash).toBe('#/validation'))
    expect(mockApi.checkSubmit).not.toHaveBeenCalled()
  })

  it('切换证据受限实验只改变样例事实并回到工作台，不自动创建 Run', async () => {
    const experience = { available: true, display_name: '协作空间', unavailable_reason: null, active: true, experience_id: `exp_${'1'.repeat(32)}`, project_id: 'p1', origin: 'http://127.0.0.1:1', scenario_prepared: true, scenario_version: 'VULNERABLE', vulnerable_change_id: `chg_${'2'.repeat(32)}`, repair_change_id: null }
    mockApi.experienceStatus.mockResolvedValue(experience)
    mockApi.experienceSwitch.mockResolvedValue({ ...experience, scenario_version: 'EVIDENCE_LIMITED' })
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/workspace'
    render(<ControlShell />)

    fireEvent.click(await screen.findByRole('button', { name: '证据受限实验' }))
    fireEvent.click(await screen.findByRole('button', { name: '确认切换' }))

    await waitFor(() => expect(mockApi.experienceSwitch).toHaveBeenCalledWith('EVIDENCE_LIMITED', undefined))
    expect(mockApi.checkSubmit).not.toHaveBeenCalled()
    await waitFor(() => expect(window.location.hash).toBe('#/workspace'))
  })

  it('样例切换后不把旧 BLOCK 当成当前结果，并允许发起新检查', async () => {
    const oldRun = { run_id: 'run-current', created_at_us: 3, lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED' }
    const experience = { available: true, display_name: '协作空间', unavailable_reason: null, active: true, experience_id: `exp_${'1'.repeat(32)}`, project_id: 'p1', origin: 'http://127.0.0.1:1', scenario_prepared: true, scenario_version: 'EVIDENCE_LIMITED', scenario_changed_at_us: 10, vulnerable_change_id: `chg_${'2'.repeat(32)}`, repair_change_id: null }
    mockApi.experienceStatus.mockResolvedValue(experience)
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', name: '协作空间', status: 'READY' }])
    mockApi.readiness.mockResolvedValue({ project_id: 'p1', project_status: 'READY', application_connected: true, endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED', discovered_role_count: 2, confirmed_role_count: 2, discovered_action_count: 1, confirmed_action_count: 1, execution_profile_available: true, completed_flow_available: true, active_contract_available: true, permission_actions: [], current_scope_runnable: true, remaining_gap_count: 0, active_tasks: [], latest_verified_run_id: 'run-current', next_required_action: 'OPEN_RESULT', preparation: { project_id: 'p1', ready: true, items: [], next_item_key: null, auto_action_count: 0, user_action_count: 0, blocked_count: 0, external_blockers: [] } })
    mockApi.runs.mockResolvedValue([oldRun])
    mockApi.checkPreview.mockResolvedValue({ project_id: 'p1', ready: true, actions: [], gaps: [], next_path: null, next_label: null, case_count: 3, differential_pair_count: 1 })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/tests'

    render(<ControlShell />)

    expect(await screen.findByRole('heading', { name: '当前版本还没有检查结果' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '进入运行检查' }))
    await waitFor(() => expect(window.location.hash).toBe('#/validation'))
    expect(await screen.findByText('核对本次检查')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始真实检查' })).toBeEnabled()
  })
})
