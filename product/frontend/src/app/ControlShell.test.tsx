import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ControlShell, { remembered } from './ControlShell'

const mockApi = vi.hoisted(() => ({
  projects: vi.fn().mockResolvedValue([]), runs: vi.fn().mockResolvedValue([]), run: vi.fn(),
  llmProfiles: vi.fn().mockResolvedValue([]), systemStatus: vi.fn().mockResolvedValue({ api: 'available', worker: 'stopped', browser: 'unknown' }),
  profiles: vi.fn().mockResolvedValue([]), contract: vi.fn(), submit: vi.fn(), cancel: vi.fn().mockResolvedValue({}), findings: vi.fn().mockResolvedValue([]), evidence: vi.fn().mockResolvedValue([]), evidenceDetail: vi.fn().mockResolvedValue({}), reports: vi.fn().mockResolvedValue([]), report: vi.fn().mockResolvedValue({}), contracts: vi.fn().mockResolvedValue([]), contractGovernance: vi.fn().mockResolvedValue({ project: {}, requirements: [], candidates: [], versions: [], llm_available: false }),
}))

vi.mock('../api/projects', () => ({ projectsApi: { projects: mockApi.projects } }))
vi.mock('../api/runs', () => ({ runsApi: { runs: mockApi.runs, run: mockApi.run, cancel: mockApi.cancel, createRun: vi.fn() } }))
vi.mock('../api/llm', () => ({ llmApi: { profiles: mockApi.llmProfiles } }))
vi.mock('../api/system', () => ({ systemApi: { status: mockApi.systemStatus } }))
vi.mock('../api/onboarding', () => ({ onboardingApi: { demoStatus: vi.fn().mockResolvedValue({}), } }))
vi.mock('../api/executionProfiles', () => ({ executionProfilesApi: { profiles: mockApi.profiles, contract: mockApi.contract, submit: mockApi.submit, register: vi.fn() } }))
vi.mock('../api/contracts', () => ({ contractsApi: { contracts: mockApi.contracts, contractGovernance: mockApi.contractGovernance } }))
vi.mock('../api/results', () => ({ resultsApi: { findings: mockApi.findings, evidence: mockApi.evidence, evidenceDetail: mockApi.evidenceDetail, reports: mockApi.reports, report: mockApi.report, reportFormat: (runId: string, reportId: string, format: string) => `/api/runs/${runId}/reports/${reportId}/formats/${format}` } }))
vi.mock('../api/http', () => ({ ApiError: class extends Error {}, request: vi.fn() }))

describe('应用壳', () => {
  afterEach(() => cleanup())
  beforeEach(() => { localStorage.clear(); window.location.hash = ''; vi.clearAllMocks(); mockApi.projects.mockResolvedValue([]); mockApi.runs.mockResolvedValue([]); mockApi.llmProfiles.mockResolvedValue([]); mockApi.systemStatus.mockResolvedValue({ api: 'available', worker: 'stopped', browser: 'unknown' }); mockApi.profiles.mockResolvedValue([]) })

  it('显示工作台、任务导航和真实运行状态', async () => {
    render(<ControlShell />)
    expect(await screen.findByText('还没有选择要检查的应用。')).toBeInTheDocument()
    for (const item of ['工作台', '应用', '应用接入', '权限规则', '检查', '开始检查', '检查结果', '历史变化', '高级', '流程录制', '模型服务', '运行环境']) expect(screen.getAllByText(item).length).toBeGreaterThan(0)
    expect(screen.getByText('服务 · 可用')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '模型服务' })).toBeInTheDocument()
    expect(document.querySelector('.phase-steps')).not.toBeInTheDocument()
  })

  it('旧报告路径重定向到检查结果并保留无应用提示', async () => {
    window.location.hash = '#/report'
    render(<ControlShell />)
    expect(await screen.findByText('先选择要检查的应用')).toBeInTheDocument()
    await waitFor(() => expect(window.location.hash).toBe('#/checks/results?view=report'))
  })

  it('工作台菜单项可从其他路由点击返回', async () => {
    window.location.hash = '#/apps/access'
    render(<ControlShell />)
    fireEvent.click((await screen.findAllByText('工作台'))[0])
    await waitFor(() => expect(window.location.hash).toBe('#/workspace'))
    expect(await screen.findByText('还没有选择要检查的应用。')).toBeInTheDocument()
  })

  it('没有应用时模型服务和运行环境仍可访问', async () => {
    window.location.hash = '#/advanced/models'
    const models = render(<ControlShell />)
    expect((await screen.findAllByText('模型服务')).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: '管理模型服务' })).toBeInTheDocument()
    models.unmount()
    window.location.hash = '#/advanced/system'
    render(<ControlShell />)
    expect((await screen.findAllByText('运行环境')).length).toBeGreaterThan(0)
    expect(screen.getByText('状态来自当前运行环境')).toBeInTheDocument()
  })

  it('陈旧项目不会绕过项目选择边界', async () => {
    localStorage.setItem(remembered.project, JSON.stringify({ project_id: 'stale-project' }))
    render(<ControlShell />)
    expect(await screen.findByText('还没有选择要检查的应用。')).toBeInTheDocument()
    expect(localStorage.getItem(remembered.project)).toBeNull()
  })

  it('串起执行配置、矩阵、已发布结果、证据、报告和历史入口', async () => {
    const contract = { subjects: [{ subject_id: 'member', roles: ['reader'] }], resources: [{ resource_id: 'document', resource_type: '文档' }], relations: [{ relation_id: 'owns-document', relation: '拥有', source: { endpoint_type: 'subject', endpoint_id: 'member' }, target: { endpoint_type: 'resource', endpoint_id: 'document' } }], rules: [{ rule_id: 'read-document', subject_id: 'member', action_id: 'read', resource_id: 'document', expectation: 'DENY', severity: 'high' }], batch_rules: [] }
    const run = { run_id: 'run-current', created_at_us: 3, execution_schema_version: '2', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED', case_progress: { completed: 1, total: 1 }, observer_health: { schema_version: '1', required_observations: ['resource_state'], resource_state: { configured: true, required: true } } }
    mockApi.projects.mockResolvedValue([{ project_id: 'p1', status: 'READY' }])
    mockApi.runs.mockResolvedValue([run, { run_id: 'run-history', created_at_us: 1, lifecycle: 'COMPLETED', result_integrity: 'VERIFIED' }])
    mockApi.run.mockResolvedValue(run)
    mockApi.profiles.mockResolvedValue([{ profile_id: 'profile-1', project_id: 'p1', contract_id: 'contract-1', contract_version: 1 }])
    mockApi.contract.mockResolvedValue(contract)
    mockApi.contractGovernance.mockResolvedValue({ project: { project_id: 'p1' }, requirements: [], candidates: [], versions: [], llm_available: false })
    mockApi.contracts.mockResolvedValue([])
    mockApi.submit.mockResolvedValue({ run })
    mockApi.findings.mockResolvedValue([{ finding: { finding_id: 'finding-1', identity: { permission_intent: '读取文档', subject_class: '成员', action: 'read', resource_class: '文档' } }, occurrence: { occurrence_id: 'occ-1', status: 'APPEARED', verdict: 'BLOCK', severity: 'high', evidence_refs: ['evidence-1'] } }])
    mockApi.evidence.mockResolvedValue([{ evidence_id: 'evidence-1' }])
    mockApi.evidenceDetail.mockResolvedValue({ case_snapshot: { case_id: 'case-1', subject_id: 'member', action_id: 'read', resource_ids: ['document'], required_observations: ['resource_state'] }, execution_fact: { target_type: 'WEB', action_id: 'read', outcome: 'DENIED', reason_codes: [] }, observation_facts: [{ requirement_id: 'resource_state', resource_id: 'document', effect: 'CONFIRMED', complete: true, reliable: true, reason_codes: [] }], observations: [], outcomes: [], verdict: 'BLOCK', reason_codes: [] })
    mockApi.reports.mockResolvedValue([{ report_id: 'report-1', gate_decision: 'PASS' }])
    mockApi.report.mockResolvedValue({ runtime: { verdict: 'BLOCK', findings: [{}] }, gate: { decision: 'PASS' }, limitations: [] })
    localStorage.setItem(remembered.project, JSON.stringify({ project_id: 'p1' }))
    window.location.hash = '#/apps/rules'
    render(<ControlShell />)
    await screen.findByText('当前执行配置')
    expect(await screen.findByText('权限矩阵')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: '关系图' }))
    expect(await screen.findByRole('region', { name: '权限关系图' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '开始检查' }))
    expect(await screen.findByText('选择执行配置')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '开始检查' }))
    fireEvent.click(await screen.findByRole('button', { name: '查看检查结果' }))
    expect(await screen.findByText('检查对象')).toBeInTheDocument()
    fireEvent.click(screen.getByText('完整报告'))
    expect(await screen.findByRole('link', { name: '导出JSON' })).toBeInTheDocument()
    fireEvent.click(screen.getByText('历史变化'))
    expect((await screen.findAllByText('首次出现')).length).toBeGreaterThan(0)
  })
})
