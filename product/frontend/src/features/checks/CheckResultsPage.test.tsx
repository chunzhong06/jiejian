import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CheckResultsPage } from './CheckResultsPage'

const resultsApi = vi.hoisted(() => ({ findings: vi.fn(), evidence: vi.fn(), evidenceDetail: vi.fn(), reports: vi.fn(), report: vi.fn(), reportFormat: vi.fn((runId: string, reportId: string, format: string) => `/api/runs/${runId}/reports/${reportId}/formats/${format}`) }))
const runsApi = vi.hoisted(() => ({ run: vi.fn() }))
vi.mock('../../api/results', () => ({ resultsApi }))
vi.mock('../../api/runs', () => ({ runsApi }))

describe('CheckResultsPage', () => {
  it('把表面拒绝但真实资源已改变的 Finding 作为首要权限问题解释', async () => {
    const run = { run_id: 'run-block', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED', observer_health: { schema_version: '1', required_observations: ['resource_state'], resource_state: { configured: true } } }
    runsApi.run.mockResolvedValue(run)
    resultsApi.findings.mockResolvedValue([{ finding: { finding_id: 'finding-block', identity: { permission_intent: '成员不能修改他人文档', subject_class: '成员', action: 'modify', resource_class: 'document' } }, occurrence: { occurrence_id: 'occ-block', status: 'APPEARED', verdict: 'VULNERABLE', severity: 'critical', evidence_refs: ['ev-block'] } }])
    resultsApi.evidence.mockResolvedValue([{ evidence_id: 'ev-block' }])
    resultsApi.evidenceDetail.mockResolvedValue({ evidence_id: 'ev-block', case_snapshot: { subject_id: 'member', action_id: 'modify', resource_ids: ['owner-document'], expectations: ['DENY'], required_observations: ['resource_state'] }, execution_fact: { outcome: 'DENIED' }, observation_facts: [{ requirement_id: 'resource_state', resource_id: 'owner-document', effect: 'CONFIRMED', complete: true, reliable: true }], verdict: 'VULNERABLE' })

    render(<CheckResultsPage run={run} onError={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: '发现 1 个权限问题' })).toBeInTheDocument()
    expect(await screen.findByText('页面或接口显示已拒绝')).toBeInTheDocument()
    expect(screen.getByText('真实资源已经发生变化')).toBeInTheDocument()
    expect(screen.getByText(/表面拒绝没有阻止真实副作用/)).toBeInTheDocument()
    expect(screen.getAllByText('成员（member）').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('owner-document').length).toBeGreaterThanOrEqual(1)
  })

  it('展示稳定 Finding、当前 Evidence 时间线并分开报告结论和门禁', async () => {
    const run = { run_id: 'run-1', execution_schema_version: '2', lifecycle: 'COMPLETED', verdict: 'INCONCLUSIVE', result_integrity: 'VERIFIED', coverage_record_count: 1, coverage_gap_count: 0, case_progress: { completed: 1, total: 1 }, observer_health: { schema_version: '1', required_observations: ['resource_state'], resource_state: { configured: true, required: true } } }
    runsApi.run.mockResolvedValue(run)
    resultsApi.findings.mockResolvedValue([{ finding: { finding_id: 'finding-1', identity: { permission_intent: '读取文档', subject_class: '用户', action: 'read', resource_class: 'document' } }, occurrence: { occurrence_id: 'occ-1', status: 'APPEARED', verdict: 'INCONCLUSIVE', severity: 'high', evidence_refs: ['ev-1'] } }])
    resultsApi.evidence.mockResolvedValue([{ evidence_id: 'ev-1' }])
    resultsApi.evidenceDetail.mockResolvedValue({ evidence_id: 'ev-1', case_snapshot: { case_id: 'case-1', subject_id: 'member', action_id: 'read', resource_ids: ['document'], expectations: ['ALLOW'], required_observations: ['resource_state'] }, execution_fact: { target_type: 'WEB', action_id: 'read', outcome: 'DENIED', reason_codes: [] }, observation_facts: [{ requirement_id: 'resource_state', resource_id: 'document', effect: 'UNKNOWN', complete: false, reliable: false, reason_codes: ['MISSING_OBSERVATION'] }], observations: [], outcomes: [], verdict: 'INCONCLUSIVE', reason_codes: ['MISSING_OBSERVATION'] })
    resultsApi.reports.mockResolvedValue([{ report_id: 'report-1', gate_decision: 'PASS' }])
    resultsApi.report.mockResolvedValue({ runtime: { verdict: 'INCONCLUSIVE', findings: [] }, gate: { decision: 'PASS' }, limitations: [] })
    render(<CheckResultsPage run={run} onError={vi.fn()} />)
    expect((await screen.findAllByText('证据不足')).length).toBeGreaterThan(0)
    expect(await screen.findByText('读取文档')).toBeInTheDocument()
    expect(await screen.findByText('检查对象')).toBeInTheDocument()
    expect(screen.getByText('资源状态 · 已配置')).toBeInTheDocument()
    expect(screen.queryByText('请求事实')).not.toBeInTheDocument()
    expect(screen.getAllByText('1', { selector: '.ant-descriptions-item-content' }).length).toBeGreaterThanOrEqual(2)
    fireEvent.click(screen.getByText('完整报告'))
    expect((await screen.findAllByText(/安全检查结论/)).length).toBeGreaterThan(0)
    expect((await screen.findAllByText(/交付门禁/)).length).toBeGreaterThan(0)
    expect(await screen.findByRole('link', { name: '导出JSON' })).toHaveAttribute('href', '/api/runs/run-1/reports/report-1/formats/json')
  })

  it('必需观察缺失时明确显示缺失而不是已配置', async () => {
    const run = { run_id: 'run-missing', execution_schema_version: '2', lifecycle: 'COMPLETED', verdict: 'INCONCLUSIVE', result_integrity: 'VERIFIED', observer_health: { schema_version: '1', required_observations: ['resource_state'], resource_state: { configured: false, required: true } } }
    runsApi.run.mockResolvedValue(run)
    resultsApi.findings.mockResolvedValue([])
    resultsApi.evidence.mockResolvedValue([])
    render(<CheckResultsPage run={run} onError={vi.fn()} />)
    expect(await screen.findByText('资源状态 · 缺失')).toBeInTheDocument()
    expect(screen.queryByText('资源状态 · 已配置')).not.toBeInTheDocument()
  })

  it('PASS 首屏明确限制结论范围', async () => {
    const run = { run_id: 'run-pass', lifecycle: 'COMPLETED', verdict: 'PASS', result_integrity: 'VERIFIED', observer_health: { schema_version: '1', required_observations: [] } }
    runsApi.run.mockResolvedValue(run)
    resultsApi.findings.mockResolvedValue([])
    resultsApi.evidence.mockResolvedValue([])
    render(<CheckResultsPage run={run} onError={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: '当前范围内未发现已确认的权限问题' })).toBeInTheDocument()
    expect(screen.getByText(/不代表绝对安全/)).toBeInTheDocument()
  })
})
