// 验证应用壳的权威状态恢复、导航、运行状态和安全退出入口。

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { aiStatusLabel, systemStatusLabel } from './AppHeader'
import ControlShell from './ControlShell'

const mockApi = vi.hoisted(() => ({
  projects: vi.fn().mockResolvedValue([]), readiness: vi.fn(), runs: vi.fn().mockResolvedValue([]), run: vi.fn(),
  llmProfiles: vi.fn().mockResolvedValue([]), settings: vi.fn().mockResolvedValue({ enabled: false, default_profile_name: null, updated_at_us: 0 }), systemStatus: vi.fn().mockResolvedValue({ api: 'available', worker: 'stopped', browser: 'unknown' }), shutdown: vi.fn().mockResolvedValue({ status: 'stopping' }),
  cacheStatus: vi.fn().mockResolvedValue({ schema_version: '1', entries: {}, protected: { data: 'var/data', data_unchanged: true, current_runtime_unchanged_by_cache: true } }),
  cacheOperation: vi.fn(),
  assistantGuidance: vi.fn(), assistantRefresh: vi.fn(),
  checkPreview: vi.fn(), checkSubmit: vi.fn(),
  profiles: vi.fn(), contract: vi.fn(), summary: vi.fn().mockResolvedValue({ schema_version: '1', workflows: [], effect_bindings: [] }), submit: vi.fn(), cancel: vi.fn().mockResolvedValue({}), findings: vi.fn().mockResolvedValue([]), evidence: vi.fn().mockResolvedValue([]), evidenceDetail: vi.fn().mockResolvedValue({}), presentation: vi.fn(), history: vi.fn(), reports: vi.fn().mockResolvedValue([]), report: vi.fn().mockResolvedValue({}), reportView: vi.fn((runId: string, reportId: string) => `/api/runs/${runId}/reports/${reportId}/view`), contracts: vi.fn().mockResolvedValue([]), contractGovernance: vi.fn().mockResolvedValue({ project: {}, requirements: [], candidates: [], versions: [] }),
}))

vi.mock('../api/projects', () => ({ projectsApi: { projects: mockApi.projects, readiness: mockApi.readiness } }))
vi.mock('../api/runs', () => ({ runsApi: { runs: mockApi.runs, run: mockApi.run, cancel: mockApi.cancel, createRun: vi.fn() } }))
vi.mock('../api/llm', () => ({ llmApi: { profiles: mockApi.llmProfiles, settings: mockApi.settings } }))
vi.mock('../api/assistant', () => ({ assistantApi: { guidance: mockApi.assistantGuidance, refresh: mockApi.assistantRefresh } }))
vi.mock('../api/system', () => ({ systemApi: { status: mockApi.systemStatus, cacheStatus: mockApi.cacheStatus, cacheOperation: mockApi.cacheOperation, shutdown: mockApi.shutdown } }))
vi.mock('../api/checks', () => ({ checksApi: { preview: mockApi.checkPreview, submit: mockApi.checkSubmit } }))
vi.mock('../api/executionProfiles', () => ({ executionProfilesApi: { profiles: mockApi.profiles, contract: mockApi.contract, summary: mockApi.summary, submit: mockApi.submit, register: vi.fn() } }))
vi.mock('../api/contracts', () => ({ contractsApi: { contracts: mockApi.contracts, contractGovernance: mockApi.contractGovernance } }))
vi.mock('../api/results', () => ({ resultsApi: { findings: mockApi.findings, evidence: mockApi.evidence, evidenceDetail: mockApi.evidenceDetail, presentation: mockApi.presentation, history: mockApi.history, reports: mockApi.reports, report: mockApi.report, reportView: mockApi.reportView, reportFormat: (runId: string, reportId: string, format: string) => `/api/runs/${runId}/reports/${reportId}/formats/${format}` } }))
vi.mock('../api/http', () => ({ ApiError: class extends Error {}, request: vi.fn() }))

describe('应用壳', () => {
  afterEach(() => cleanup())
  beforeEach(() => { localStorage.clear(); window.location.hash = ''; vi.clearAllMocks(); mockApi.projects.mockResolvedValue([]); mockApi.readiness.mockResolvedValue({ project_id: 'p1', project_status: 'READY', application_connected: true, endpoint_status: 'LEGACY_PROFILE', source_analysis_status: 'LEGACY_PROFILE', discovered_role_count: 0, confirmed_role_count: 0, discovered_action_count: 0, confirmed_action_count: 0, execution_profile_available: true, completed_flow_available: false, active_contract_available: false, active_tasks: [], latest_verified_run_id: null, next_required_action: 'RECORD_FLOW' }); mockApi.runs.mockResolvedValue([]); mockApi.llmProfiles.mockResolvedValue([]); mockApi.settings.mockResolvedValue({ enabled: false, default_profile_name: null, updated_at_us: 0 }); mockApi.systemStatus.mockResolvedValue({ api: 'available', worker: 'stopped', browser: 'unknown' }); mockApi.profiles.mockResolvedValue([]); mockApi.summary.mockResolvedValue({ schema_version: '1', workflows: [], effect_bindings: [] }); mockApi.presentation.mockResolvedValue({ run_id: 'run-current', project_id: 'p1', project_name: '演示应用', run_lifecycle: 'COMPLETED', verdict: 'BLOCK', headline: '发现权限问题', scope_statement: '当前范围已检查。', checked_count: 1, safe_count: 0, problem_count: 1, inconclusive_count: 0, uncovered_count: 0, execution_problem: null, issues: [], limitations: [] }); mockApi.history.mockResolvedValue({ project_id: 'p1', comparisons: [{ run_id: 'run-history', previous_run_id: null, checked_at_us: 1, changes: [{ finding_id: 'finding-1', title: '权限问题', subject_group: '普通用户账号', action: '读取', resource: '文档', relation: '拥有', status: 'NEW', status_label: '新发现', explanation: '首次确认。', severity: 'high', evidence_refs: [], current_verdict: 'VULNERABLE', occurrence_status: 'APPEARED' }] }] }); mockApi.assistantGuidance.mockRejectedValue(new Error('assistant unavailable')); mockApi.checkPreview.mockResolvedValue({ project_id: 'p1', ready: false, actions: [], gaps: [], next_path: null, next_label: null, case_count: 0, differential_pair_count: 0 }) })

  it('显示工作台、任务导航和真实运行状态', async () => {
    render(<ControlShell />)
    expect(await screen.findByText('还没有选择要检查的应用。')).toBeInTheDocument()
    expect(screen.getByText('尚未选择应用')).toBeInTheDocument()
    for (const item of ['工作台', '应用', '应用接入', '业务流程', '权限规则', '检查', '开始检查', '检查结果', '历史变化']) expect(screen.getAllByText(item).length).toBeGreaterThan(0)
    expect(screen.queryByText('设置', { selector: '.ant-menu-item-group-title' })).not.toBeInTheDocument()
    expect(screen.getByText('AI辅助 · 未开启')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '系统需处理' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '设置与更多' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '退出界鉴' })).toBeInTheDocument()
    expect(document.querySelector('.phase-steps')).not.toBeInTheDocument()
  })

  it('顶部状态标签只由结构化状态决定', () => {
    const disabled = { enabled: false, default_profile_name: null, updated_at_us: 0 }
    const enabled = { enabled: true, default_profile_name: 'default', updated_at_us: 0 }
    expect(aiStatusLabel([], disabled, false, false)).toBe('AI辅助 · 未开启')
    expect(aiStatusLabel([], enabled, false, false)).toBe('AI辅助 · 待配置')
    expect(aiStatusLabel([], enabled, true, false)).toBe('AI辅助 · 状态未知')
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

  it('工作台菜单项可从其他路由点击返回', async () => {
    window.location.hash = '#/apps/access'
    render(<ControlShell />)
    fireEvent.click((await screen.findAllByText('工作台'))[0])
    await waitFor(() => expect(window.location.hash).toBe('#/workspace'))
    expect(await screen.findByText('还没有选择要检查的应用。')).toBeInTheDocument()
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
        route: '/apps/access', headline: '不能检查界鉴自身',
        short_message: '请返回应用接入页确认真正的被测应用地址。', cleanup_warnings: [],
      },
    })
    render(<ControlShell />)
    expect((await screen.findAllByText('不能检查界鉴自身')).length).toBeGreaterThan(0)
    expect((await screen.findAllByText('请返回应用接入页确认真正的被测应用地址。')).length).toBeGreaterThan(0)
    fireEvent.click(screen.getAllByRole('button', { name: '前往处理页面' })[0])
    await waitFor(() => expect(window.location.hash).toBe('#/apps/access'))
  })

  it('页面操作错误只进入右下角通知，不重复覆盖当前页面', async () => {
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.checkPreview.mockRejectedValueOnce({
      code: 'CHECK_NOT_READY',
      message: '请求失败',
      diagnosis: {
        route: '/apps/rules', headline: '权限检查条件尚未准备好',
        short_message: '请返回权限规则页处理当前缺口。', cleanup_warnings: [], intervention: 'USER_ACTION',
      },
    })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/checks/start'

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
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('陈旧项目不会绕过项目选择边界', async () => {
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'stale-project' }))
    render(<ControlShell />)
    expect(await screen.findByText('还没有选择要检查的应用。')).toBeInTheDocument()
    expect(localStorage.getItem('jiejian.project')).toBeNull()
  })

  it('串起执行配置、矩阵、已发布结果、证据、报告和历史入口', async () => {
    const contract = { subjects: [{ subject_id: 'member', roles: ['reader'] }], resources: [{ resource_id: 'document', resource_type: '文档' }], relations: [{ relation_id: 'owns-document', relation: '拥有', source: { endpoint_type: 'subject', endpoint_id: 'member' }, target: { endpoint_type: 'resource', endpoint_id: 'document' } }], rules: [{ rule_id: 'read-document', subject_id: 'member', action_id: 'read', resource_id: 'document', expectation: 'DENY', severity: 'high' }], batch_rules: [] }
    const run = { run_id: 'run-current', created_at_us: 3, execution_schema_version: '1', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED', case_progress: { completed: 1, total: 1 }, observer_health: { required_observations: ['resource_state'], resource_state: { configured: true, required: true } } }
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.runs.mockResolvedValue([run, { run_id: 'run-history', created_at_us: 1, lifecycle: 'COMPLETED', result_integrity: 'VERIFIED' }])
    mockApi.run.mockResolvedValue(run)
    mockApi.profiles.mockResolvedValue([{ profile_id: 'profile-1', project_id: 'p1', contract_id: 'contract-1', contract_version: 1 }])
    mockApi.contract.mockResolvedValue(contract)
    mockApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [] })
    mockApi.contracts.mockResolvedValue([])
    mockApi.checkPreview.mockResolvedValue({ project_id: 'p1', ready: true, actions: [{ action_candidate_id: 'read', action_display_name: '读取文档', resource_logical_name: '文档', ready: true, checks: [{ subject_label: '成员账号', subject_role_display_name: '成员', relation: 'OWNS', expectation: 'DENY', ready: true, gaps: [] }], gaps: [] }], gaps: [], next_path: null, next_label: null, case_count: 1, differential_pair_count: 1 })
    mockApi.checkSubmit.mockResolvedValue({ schema_version: '1', run, job: { job_id: 'job-1', state: 'QUEUED' } })
    mockApi.findings.mockResolvedValue([{ finding: { finding_id: 'finding-1', identity: { permission_intent: '读取文档', subject_class: '成员', action: 'read', resource_class: '文档' } }, occurrence: { occurrence_id: 'occ-1', status: 'APPEARED', verdict: 'BLOCK', severity: 'high', evidence_refs: ['evidence-1'] } }])
    mockApi.evidence.mockResolvedValue([{ evidence_id: 'evidence-1' }])
    mockApi.evidenceDetail.mockResolvedValue({ case_snapshot: { case_id: 'case-1', subject_id: 'member', action_id: 'read', resource_ids: ['document'], required_observations: ['resource_state'] }, execution_fact: { target_type: 'WEB', action_id: 'read', outcome: 'DENIED', reason_codes: [] }, observation_facts: [{ requirement_id: 'resource_state', resource_id: 'document', effect: 'CONFIRMED', complete: true, reliable: true, reason_codes: [] }], observations: [], outcomes: [], verdict: 'BLOCK', reason_codes: [] })
    mockApi.reports.mockResolvedValue([{ report_id: 'report-1', gate_decision: 'PASS' }])
    mockApi.report.mockResolvedValue({ runtime: { verdict: 'BLOCK', findings: [{}] }, gate: { decision: 'PASS' }, limitations: [] })
    localStorage.setItem('jiejian.project', JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/apps/rules'
    render(<ControlShell />)
    await screen.findByText('当前执行配置')
    expect(screen.getByText('当前应用：未命名应用')).toBeInTheDocument()
    expect(await screen.findByText('权限矩阵')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /高级：生成配置与规则详情/ }))
    fireEvent.click(screen.getByRole('tab', { name: '关系图' }))
    expect(await screen.findByRole('region', { name: '权限关系图' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: '开始检查' }))
    expect(await screen.findByText('检查预览')).toBeInTheDocument()
    expect(screen.queryByLabelText('选择执行配置')).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '开始检查' }))
    fireEvent.click(await screen.findByRole('button', { name: '查看检查结果' }))
    fireEvent.click(await screen.findByText('查看证据'))
    expect(await screen.findByText('检查对象')).toBeInTheDocument()
    fireEvent.click(screen.getByText('完整报告'))
    fireEvent.click(await screen.findByRole('button', { name: /导出/ }))
    expect(await screen.findByRole('link', { name: 'JSON' })).toBeInTheDocument()
    fireEvent.click(screen.getByText('历史变化'))
    expect((await screen.findAllByText('新发现')).length).toBeGreaterThan(0)
  })
})
