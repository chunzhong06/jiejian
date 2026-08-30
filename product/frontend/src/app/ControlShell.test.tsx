// 验证应用壳的权威状态恢复、导航、运行状态和安全退出入口。

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { aiStatusLabel, mcpStatusLabel, systemStatusLabel } from './AppHeader'
import ControlShell from './ControlShell'

const mockApi = vi.hoisted(() => ({
  projects: vi.fn().mockResolvedValue([]), readiness: vi.fn(), runs: vi.fn().mockResolvedValue([]), run: vi.fn(),
  removeProject: vi.fn().mockResolvedValue({ project_id: 'p1', status: 'ARCHIVED' }),
  llmProfiles: vi.fn().mockResolvedValue([]), settings: vi.fn().mockResolvedValue({ enabled: false, default_profile_name: null, updated_at_us: 0 }), systemStatus: vi.fn().mockResolvedValue({ api: 'available', worker: 'stopped', browser: 'unknown' }), shutdown: vi.fn().mockResolvedValue({ status: 'stopping' }),
  mcpStatus: vi.fn().mockResolvedValue({ schema_version: '1', paired: false, accepting_connections: false, endpoint: 'http://127.0.0.1:8765/mcp', default_level: 'READ', project_grants: [], client_connected: false, client_name: null, client_version: null, last_seen_at_us: null }),
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
  experienceStatus: vi.fn().mockResolvedValue({ available: false, display_name: '协作空间', unavailable_reason: '未配置官方示例目录', active: false, experience_id: null, experience_mode: null, project_id: null, origin: null, identities_ready: false, authorization_order: null, blob_observation: null }),
  experienceStart: vi.fn(), experienceIdentities: vi.fn(), experienceFix: vi.fn(), experienceGap: vi.fn(), experienceStop: vi.fn(),
  latestChange: vi.fn().mockResolvedValue(null),
  checkPreview: vi.fn(), checkSubmit: vi.fn(), permissionMatrix: vi.fn(), permissionProposals: vi.fn(), permissionConfirm: vi.fn(), permissionCompile: vi.fn(),
  cancel: vi.fn().mockResolvedValue({}), progress: vi.fn().mockResolvedValue({ job_id: 'job', attempt: 1, events: [] }), findings: vi.fn().mockResolvedValue([]), evidence: vi.fn().mockResolvedValue([]), evidenceDetail: vi.fn().mockResolvedValue({}), presentation: vi.fn(), history: vi.fn(), reports: vi.fn().mockResolvedValue([]), report: vi.fn().mockResolvedValue({}), reportView: vi.fn((runId: string, reportId: string) => `/api/runs/${runId}/reports/${reportId}/view`),
}))

vi.mock('../api/projects', () => ({ projectsApi: {
  projects: mockApi.projects,
  remove: mockApi.removeProject,
  status: async (projectId: string) => {
    const readiness = await mockApi.readiness(projectId)
    const resultReady = readiness.next_required_action === 'OPEN_RESULT'
    const checkReady = readiness.next_required_action === 'RUN_CHECK'
    return {
      project: { project_id: projectId, name: '未命名应用', status: readiness.project_status, target_type: 'WEB' },
      readiness,
      steps: [],
      next_action: resultReady
        ? { action: 'OPEN_RESULT', label: '查看检查结果', description: '查看可信检查结果。', route: '/results', cli_command: 'jiejian result show' }
        : checkReady
          ? { action: 'RUN_CHECK', label: '开始权限检查', description: '开始当前检查。', route: '/check', cli_command: 'jiejian check run' }
          : { action: 'RECORD_FLOW', label: '准备测试账号', description: '准备安全登录状态。', route: '/identities', cli_command: 'jiejian account' },
      latest_result: null,
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
vi.mock('../api/experience', () => ({ experienceApi: { status: mockApi.experienceStatus, start: mockApi.experienceStart, prepareIdentities: mockApi.experienceIdentities, verifyFixedBehavior: mockApi.experienceFix, useUnavailableObservation: mockApi.experienceGap, stop: mockApi.experienceStop } }))
vi.mock('../api/system', () => ({ systemApi: { status: mockApi.systemStatus, maintenanceStatus: mockApi.maintenanceStatus, maintenanceOperation: mockApi.maintenanceOperation, shutdown: mockApi.shutdown } }))
vi.mock('../api/sourceChanges', () => ({ sourceChangesApi: { latest: mockApi.latestChange } }))
vi.mock('../api/checks', () => ({ checksApi: { preview: mockApi.checkPreview, submit: mockApi.checkSubmit } }))
vi.mock('../api/permissionIntents', () => ({ permissionIntentsApi: { matrix: mockApi.permissionMatrix, proposals: mockApi.permissionProposals, confirm: mockApi.permissionConfirm, compile: mockApi.permissionCompile } }))
vi.mock('../api/results', () => ({ resultsApi: { findings: mockApi.findings, evidence: mockApi.evidence, evidenceDetail: mockApi.evidenceDetail, presentation: mockApi.presentation, history: mockApi.history, reports: mockApi.reports, report: mockApi.report, reportView: mockApi.reportView, reportFormat: (runId: string, reportId: string, format: string) => `/api/runs/${runId}/reports/${reportId}/formats/${format}` } }))
vi.mock('../api/http', () => ({ ApiError: class extends Error {}, request: vi.fn() }))

describe('应用壳', () => {
  afterEach(() => cleanup())
  beforeEach(() => { localStorage.clear(); window.location.hash = ''; vi.clearAllMocks(); mockApi.latestChange.mockResolvedValue(null); mockApi.projects.mockResolvedValue([]); mockApi.readiness.mockResolvedValue({ project_id: 'p1', project_status: 'READY', application_connected: true, endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED', discovered_role_count: 1, confirmed_role_count: 1, discovered_action_count: 1, confirmed_action_count: 1, execution_profile_available: false, completed_flow_available: false, active_contract_available: false, permission_actions: [], current_scope_runnable: false, remaining_gap_count: 1, active_tasks: [], latest_verified_run_id: null, next_required_action: 'RECORD_FLOW' }); mockApi.runs.mockResolvedValue([]); mockApi.llmProfiles.mockResolvedValue([]); mockApi.settings.mockResolvedValue({ enabled: false, default_profile_name: null, updated_at_us: 0 }); mockApi.mcpStatus.mockResolvedValue({ schema_version: '1', paired: false, accepting_connections: false, endpoint: 'http://127.0.0.1:8765/mcp', default_level: 'READ', project_grants: [], client_connected: false, client_name: null, client_version: null, last_seen_at_us: null }); mockApi.systemStatus.mockResolvedValue({ api: 'available', worker: 'stopped', browser: 'unknown' }); mockApi.permissionMatrix.mockResolvedValue({ project_id: 'p1', actions: [], confirmed_count: 0, review_required_count: 0, unconfirmed_count: 0, executable_count: 0, representative_gap_count: 0, compilable_action_count: 0 }); mockApi.presentation.mockResolvedValue({ run_id: 'run-current', project_id: 'p1', project_name: '演示应用', run_lifecycle: 'COMPLETED', verdict: 'BLOCK', headline: '发现权限问题', scope_statement: '当前范围已检查。', checked_count: 1, safe_count: 0, problem_count: 1, inconclusive_count: 0, uncovered_count: 0, execution_problem: null, issues: [], limitations: [], execution_traces: [] }); mockApi.history.mockResolvedValue({ project_id: 'p1', comparisons: [{ run_id: 'run-history', previous_run_id: null, checked_at_us: 1, changes: [{ finding_id: 'finding-1', title: '权限问题', subject_group: '普通用户账号', action: '读取', resource: '文档', relation: '拥有', status: 'NEW', status_label: '新发现', explanation: '首次确认。', severity: 'high', evidence_refs: [], current_verdict: 'VULNERABLE', occurrence_status: 'APPEARED' }] }] }); mockApi.assistantProject.mockRejectedValue(new Error('assistant unavailable')); mockApi.assistantResult.mockRejectedValue(new Error('assistant unavailable')); mockApi.checkPreview.mockResolvedValue({ project_id: 'p1', ready: false, actions: [], gaps: [], next_path: null, next_label: null, case_count: 0, differential_pair_count: 0 }) })
  beforeEach(() => mockApi.permissionProposals.mockResolvedValue({ project_id: 'p1', proposals: [] }))

  it('显示工作台、任务导航和真实运行状态', async () => {
    render(<ControlShell />)
    expect(await screen.findByText('开始一次安全检查')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '切换应用，当前：尚未选择' })).toBeInTheDocument()
    for (const item of ['工作台', '应用接入', '测试账号', '业务流程', '权限与检查', '检查结果', '历史变化']) expect(screen.getAllByText(item).length).toBeGreaterThan(0)
    expect(document.querySelector('.process-navigation')).toBeInTheDocument()
    expect(screen.getByText('AI辅助 · 未开启')).toBeInTheDocument()
    expect(screen.getByText('AI 工具 · 未连接')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '系统需处理' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '设置与更多' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '退出界鉴' })).toBeInTheDocument()
    expect(document.querySelector('.phase-steps')).not.toBeInTheDocument()
  })

  it('顶部状态标签只由结构化状态决定', () => {
    const disabled = { enabled: false, default_profile_name: null, updated_at_us: 0 }
    const enabled = { enabled: true, default_profile_name: 'default', updated_at_us: 0 }
    expect(aiStatusLabel([], disabled, false, false)).toBe('AI辅助 · 未开启')
    expect(aiStatusLabel([], enabled, false, false)).toBe('AI辅助 · 待配置')
    expect(aiStatusLabel([], enabled, true, false)).toBe('AI辅助 · 状态未知')
    const mcp = { schema_version: '1' as const, paired: true, accepting_connections: true, endpoint: 'http://127.0.0.1:8765/mcp', default_level: 'READ' as const, project_grants: [], client_connected: false, client_name: null, client_version: null, last_seen_at_us: null }
    expect(mcpStatusLabel({ ...mcp, paired: false }, false)).toBe('AI 工具 · 未连接')
    expect(mcpStatusLabel(mcp, false)).toBe('AI 工具 · 等待连接')
    expect(mcpStatusLabel({ ...mcp, client_connected: true, client_name: 'Codex' }, false)).toBe('AI 工具 · Codex')
    expect(mcpStatusLabel(mcp, true)).toBe('AI 工具 · 状态未知')
    expect(systemStatusLabel({ api: 'available', worker: 'running', browser: 'available' })).toBe('系统正常')
    expect(systemStatusLabel({ api: 'available', worker: 'stopped', browser: 'available' })).toBe('系统需处理')
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
    expect(await screen.findByText('开始一次安全检查')).toBeInTheDocument()
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
        route: '/check', headline: '权限检查条件尚未准备好',
        short_message: '请返回权限规则页处理当前缺口。', cleanup_warnings: [], intervention: 'USER_ACTION',
      },
    })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/check'

    render(<ControlShell />)

    expect(await screen.findByText('权限检查条件尚未准备好')).toBeInTheDocument()
    expect(screen.getByLabelText('全局通知')).toHaveTextContent('请返回权限规则页处理当前缺口。')
    expect(screen.queryByText('这一步没有完成')).not.toBeInTheDocument()
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
    expect(await screen.findByText('开始一次安全检查')).toBeInTheDocument()
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
    fireEvent.click(screen.getAllByText('检查结果')[0])
    await waitFor(() => expect(mockApi.runs).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(document.querySelector('#result-headline')).toHaveTextContent('发现权限问题'))

    fireEvent.click(await screen.findByRole('button', { name: '查看历史变化' }))
    await waitFor(() => expect(mockApi.runs).toHaveBeenCalledTimes(3))
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
    window.location.hash = '#/check'
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

  it('官方证据缺口动作切换真实观察后经正式检查接口创建新 Run', async () => {
    const run = { run_id: 'run-current', created_at_us: 3, lifecycle: 'COMPLETED', verdict: 'INCONCLUSIVE', result_integrity: 'VERIFIED' }
    const experience = { available: true, display_name: '协作空间', unavailable_reason: null, active: true, experience_id: 'exp-1', experience_mode: 'GUIDED', project_id: 'p1', origin: 'http://127.0.0.1:1', identities_ready: true, authorization_order: 'ENQUEUE_BEFORE_AUTHORIZE', blob_observation: 'AVAILABLE', repair_change_id: null }
    mockApi.experienceStatus.mockResolvedValue(experience)
    mockApi.experienceGap.mockResolvedValue({ ...experience, blob_observation: 'UNAVAILABLE' })
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.runs.mockResolvedValue([run])
    mockApi.run.mockResolvedValue(run)
    mockApi.checkPreview.mockResolvedValue({ project_id: 'p1', ready: true, actions: [], gaps: [], next_path: null, next_label: null, case_count: 1, differential_pair_count: 1, change_id: null, required_intent_count: 1 })
    mockApi.checkSubmit.mockResolvedValue({ schema_version: '1', run: { ...run, run_id: 'run-new', lifecycle: 'QUEUED' }, job: { job_id: 'job-new', state: 'QUEUED' } })
    mockApi.presentation.mockResolvedValue({
      run_id: 'run-current', project_id: 'p1', project_name: '协作空间', run_lifecycle: 'COMPLETED', verdict: 'INCONCLUSIVE', policy_epoch: 1, policy_fingerprint: 'a'.repeat(64),
      relevant_intents: [{ intent_id: `pin_${'1'.repeat(32)}`, revision: 1, intent_hash: 'b'.repeat(64), display_label: 'P-001', expectation: 'DENY', business_statement: '成员不可以导出资料包。' }], change_verification: null, repair_verification: null,
      headline: '证据不足', scope_statement: '真实状态无法确认。', checked_count: 1, safe_count: 0, problem_count: 0, inconclusive_count: 1, uncovered_count: 0, execution_problem: null, execution_traces: [], limitations: [],
      issues: [{ finding_id: 'finding-1', title: '导出结果无法确认', subject_group: '成员', action: '导出', resource: '资料包', relation: '其他权限组', expectation: '不应导出', surface_result: '页面已拒绝', actual_result: '真实结果无法确认', conclusion: '证据不足', explanation: '必需观察不可用。', planned_identity_id: 'member', planned_identity_label: 'Bob', actual_identity_status: 'UNAVAILABLE', actual_identity_id: null, actual_identity_label: null, severity: 'high', evidence_refs: [], evidence_sources: [], diagnosis: null, claim_boundary: { surface_response_status: 'DENIED', business_effect_status: 'UNKNOWN', actual_identity_status: 'UNAVAILABLE', breakpoint_precision: null, repair_status: null, supported_statement: '只能确认页面拒绝。', unsupported_statements: ['不能确认真实结果。'] }, evidence_explanations: [], verdict: 'INCONCLUSIVE', occurrence_status: 'APPEARED', repair_requirement: null }],
    })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/verification'
    render(<ControlShell />)

    fireEvent.click(await screen.findByRole('button', { name: '验证关键结果不可读取时会怎样' }))
    await waitFor(() => expect(mockApi.experienceGap).toHaveBeenCalledWith('ENQUEUE_BEFORE_AUTHORIZE'))
    expect(mockApi.checkPreview).toHaveBeenCalledWith('p1')
    expect(mockApi.checkSubmit).toHaveBeenCalledWith('p1')
    await waitFor(() => expect(window.location.hash).toBe('#/check'))
  })
})
