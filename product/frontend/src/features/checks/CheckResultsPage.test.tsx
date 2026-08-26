// 验证检查结果页直接消费后端 ResultPresentation，并保留证据入口。

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CheckResultsPage } from './CheckResultsPage'

const resultsApi = vi.hoisted(() => ({ presentation: vi.fn(), evidence: vi.fn(), evidenceDetail: vi.fn(), reports: vi.fn(), report: vi.fn(), reportFormat: vi.fn((runId: string, reportId: string, format: string) => `/api/runs/${runId}/reports/${reportId}/formats/${format}`) }))
const runsApi = vi.hoisted(() => ({ run: vi.fn() }))
vi.mock('../../api/results', () => ({ resultsApi }))
vi.mock('../../api/runs', () => ({ runsApi }))

const basePresentation = (overrides: Record<string, unknown> = {}) => ({
  run_id: 'run-demo', project_id: 'project-demo', project_name: '演示应用', run_lifecycle: 'COMPLETED', verdict: 'PASS',
  headline: '当前范围未发现确认问题', scope_statement: '当前实际检查范围内未发现已确认权限问题；这不代表应用绝对安全。',
  checked_count: 1, safe_count: 1, problem_count: 0, inconclusive_count: 0, uncovered_count: 0,
  execution_problem: null, issues: [], limitations: [], ...overrides,
})

describe('CheckResultsPage', () => {
  it('原样展示后端对表面拒绝与真实变化的业务解释', async () => {
    const run = { run_id: 'run-block', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED', observer_health: { required_observations: ['resource_state'], resource_state: { configured: true } } }
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(basePresentation({
      run_id: 'run-block', verdict: 'BLOCK', headline: '发现权限问题', problem_count: 1, safe_count: 0,
      issues: [{ finding_id: 'finding-block', title: '后端确认：禁止操作造成真实变化', subject_group: '成员账号', action: '修改', resource: '文档', relation: '拥有', expectation: '不应允许这次操作，资源也不应发生变化', surface_result: '页面或接口显示已拒绝', actual_result: '真实资源已经发生变化', conclusion: '发现权限问题', explanation: '页面或接口虽然显示已拒绝，但外部可信观察确认真实资源已经变化；权限限制没有真正阻止修改，表面拒绝没有阻止真实副作用。', severity: 'critical', evidence_refs: ['ev-block'], verdict: 'VULNERABLE', occurrence_status: 'APPEARED' }],
    }))
    resultsApi.evidence.mockResolvedValue([{ evidence_id: 'ev-block' }])
    resultsApi.evidenceDetail.mockResolvedValue({ evidence_id: 'ev-block', case_snapshot: { subject_id: 'member', action_id: 'modify', resource_ids: ['owner-document'], expectations: ['DENY'], required_observations: ['resource_state'] }, twin_role: 'DENY_VARIANT', allow_control_valid: true, baseline_integrity: true, execution_fact: { outcome: 'DENIED' }, observation_facts: [{ requirement_id: 'resource_state', resource_id: 'owner-document', effect: 'CONFIRMED', complete: true, reliable: true }], security_effect_facts: [{ kind: 'STATE_MUTATION', state: 'CONFIRMED', temporal_closure: 'CLOSED', baseline_integrity: true, complete: true, reliable: true, correlated: true }], verdict: 'VULNERABLE' })

    render(<CheckResultsPage run={run} onError={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: '发现权限问题' })).toBeInTheDocument()
    expect(await screen.findByText('后端确认：禁止操作造成真实变化')).toBeInTheDocument()
    expect(screen.getByText('真实资源已经发生变化')).toBeInTheDocument()
    expect(screen.getByText(/权限限制没有真正阻止修改/)).toBeInTheDocument()
    expect(screen.queryByText('成员账号不应对文档执行修改')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('查看证据'))
    expect(await screen.findByText('页面或接口显示已拒绝')).toBeInTheDocument()
  })

  it('INCONCLUSIVE 使用后端说明且不显示执行失败', async () => {
    const run = { run_id: 'run-inconclusive', lifecycle: 'COMPLETED', verdict: 'INCONCLUSIVE', result_integrity: 'VERIFIED', observer_health: { required_observations: ['resource_state'], resource_state: { configured: true } } }
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(basePresentation({ run_id: 'run-inconclusive', verdict: 'INCONCLUSIVE', headline: '证据不足', scope_statement: '操作已经执行，但真实资源最终状态无法可靠确认；这不代表安全，也不代表已经确认漏洞。', safe_count: 0, inconclusive_count: 1, issues: [{ finding_id: 'finding-1', title: '读取文档的真实结果暂时无法确认', subject_group: '普通用户账号', action: '读取', resource: '文档', relation: '拥有', expectation: '按当前权限规则执行', surface_result: '表面结果无法确定', actual_result: '真实资源状态尚不能可靠确认', conclusion: '证据不足', explanation: '必需观察不完整或不可靠，当前证据不足以确认资源是否按权限规则变化。', severity: 'high', evidence_refs: [], verdict: 'INCONCLUSIVE', occurrence_status: 'APPEARED' }], limitations: ['有 1 项因真实状态观察不完整或不可靠而证据不足。'] }))
    resultsApi.evidence.mockResolvedValue([])
    render(<CheckResultsPage run={run} onError={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: '证据不足' })).toBeInTheDocument()
    expect((await screen.findAllByText('证据不足')).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: '完善真实结果确认方式' })).toBeInTheDocument()
    expect(screen.queryByText('检查执行未完整结束')).not.toBeInTheDocument()
  })

  it('PASS 首屏展示后端范围限制与五项计数', async () => {
    const run = { run_id: 'run-pass', lifecycle: 'COMPLETED', verdict: 'PASS', result_integrity: 'VERIFIED', observer_health: { required_observations: [] } }
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(basePresentation({ checked_count: 2, safe_count: 2, uncovered_count: 1, limitations: ['仍有 1 项权限要求未覆盖；本次结论只适用于实际执行范围。'] }))
    resultsApi.evidence.mockResolvedValue([])
    render(<CheckResultsPage run={run} onError={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: '当前范围未发现确认问题' })).toBeInTheDocument()
    expect(screen.getByText(/不代表应用绝对安全/)).toBeInTheDocument()
    expect(screen.getByText('权限要求未覆盖')).toBeInTheDocument()
    expect(screen.getAllByText('2 项')).toHaveLength(2)
    expect(screen.getByText(/本次结论只适用于实际执行范围/)).toBeInTheDocument()
  })
})
