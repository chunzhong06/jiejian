// 验证检查结果页直接消费后端 ResultPresentation 与 ExecutionTrace，并保留证据入口。

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CheckResultsPage } from './CheckResultsPage'

const resultsApi = vi.hoisted(() => ({ presentation: vi.fn(), evidence: vi.fn(), evidenceDetail: vi.fn(), reports: vi.fn(), report: vi.fn(), reportFormat: vi.fn((runId: string, reportId: string, format: string) => `/api/runs/${runId}/reports/${reportId}/formats/${format}`) }))
const runsApi = vi.hoisted(() => ({ run: vi.fn() }))
vi.mock('../../api/results', () => ({ resultsApi }))
vi.mock('../../api/runs', () => ({ runsApi }))

const basePresentation = (overrides: Record<string, unknown> = {}) => ({
  run_id: 'run-demo', project_id: 'project-demo', project_name: '演示应用', run_lifecycle: 'COMPLETED', verdict: 'PASS',
  policy_epoch: 7, policy_fingerprint: 'f'.repeat(64), relevant_intents: [{ intent_id: `pin_${'a'.repeat(32)}`, revision: 3, intent_hash: 'a'.repeat(64) }],
  headline: '当前范围未发现确认问题', scope_statement: '当前实际检查范围内未发现已确认权限问题；这不代表应用绝对安全。',
  checked_count: 1, safe_count: 1, problem_count: 0, inconclusive_count: 0, uncovered_count: 0,
  execution_problem: null, execution_traces: [], issues: [], limitations: [], ...overrides,
})

const traceKinds = ['ENTRY', 'IDENTITY', 'PERSISTENT_EFFECT', 'AUTHORIZATION', 'MESSAGE', 'DELEGATION', 'FINAL_EFFECT', 'FINAL_EFFECT'] as const

const traceEvent = (semanticKey: string, sequence: number, overrides: Record<string, unknown> = {}) => ({
  event_id: `trace-${sequence}`, parent_event_ids: sequence > 1 ? [`trace-${sequence - 1}`] : [], case_id: 'case-bob', action_id: 'export-package', resource_ids: ['project-package'], kind: traceKinds[sequence - 1], semantic_key: semanticKey, subject_id: 'bob', actor_id: sequence >= 6 ? 'export-worker' : 'bob', credential_source: null, authority_scope: { allowed_action_ids: ['export-package'], allowed_resource_ids: ['project-package'], origin_authorization_event_id: sequence >= 5 ? 'trace-4' : null, delegated_from_event_id: sequence >= 6 ? `trace-${sequence - 1}` : null }, authorization_decision: semanticKey === 'authorization_decided' ? 'DENY' : null, effect_id: null, source_component: sequence >= 6 ? 'export-worker' : 'collaboration-server', source_location: sequence >= 6 ? 'worker:export' : 'api:/projects/export', correlation_kind: sequence > 1 ? 'EXPLICIT_PARENT' : 'CASE_MARKER', evidence_refs: ['ev-block'], recorded_at_us: 1000 + sequence, ...overrides,
})

const vulnerableTrace = {
  schema_version: '1', case_id: 'case-bob', action_id: 'export-package', planned_subject_id: 'member-subject', complete: true, reason_codes: [],
  events: ['request_received', 'server_identity_resolved', 'export_request_created', 'authorization_decided', 'export_message_sent', 'export_job_started', 'archive_generated', 'export_job_completed'].map((key, index) => traceEvent(key, index + 1)),
}

const exactDiagnosis = (overrides: Record<string, unknown> = {}) => ({
  case_id: 'case-bob', action_id: 'export-package', breakpoint_type: 'AUTHORIZATION_LATE', precision: 'EXACT', summary: '首个可证明断裂：权限决定发生过晚',
  minimal_witness: [
    { kind: 'PERMISSION_REQUIREMENT', label: '权限要求', detail: '成员不应导出资料包', event_id: null, evidence_refs: ['ev-block'] },
    { kind: 'ACTUAL_IDENTITY', label: '实际身份', detail: 'Bob', event_id: 'trace-2', evidence_refs: ['ev-block'] },
    { kind: 'AUTHORIZATION_DECISION', label: '权限决定', detail: '拒绝', event_id: 'trace-4', evidence_refs: ['ev-block'] },
    { kind: 'BREAKPOINT', label: '首个可证明断裂', detail: '权限决定发生过晚', event_id: 'trace-5', evidence_refs: ['ev-block'] },
    { kind: 'CONFIRMED_EFFECT', label: '已确认最终后果', detail: '真实资料包已经生成', event_id: 'trace-7', evidence_refs: ['ev-block'] },
  ],
  confirmed_impacts: [{ event_id: 'trace-7', parent_event_ids: ['trace-6'], kind: 'FINAL_EFFECT', semantic_key: 'archive_generated', effect_id: 'effect-1', summary: '已确认：最终后果', evidence_refs: ['ev-block'] }],
  evidence_refs: ['ev-block'],
  ...overrides,
})

describe('CheckResultsPage', () => {
  it('只在调用方确认活跃导览结果后显示修复验证，并仍等待用户点击', () => {
    const run = { run_id: 'run-fix', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED' }
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(basePresentation({ run_id: 'run-fix', verdict: 'BLOCK', headline: '发现权限问题' }))
    resultsApi.evidence.mockResolvedValue([])
    const verify = vi.fn()
    render(<CheckResultsPage run={run} onError={vi.fn()} canVerifyFix onVerifyFix={verify} />)
    fireEvent.click(screen.getByRole('button', { name: '验证修复后的行为' }))
    expect(verify).toHaveBeenCalledOnce()
    expect(screen.queryByText(/预期.*通过/)).not.toBeInTheDocument()
  })

  it('原样展示后端对表面拒绝与真实变化的业务解释', async () => {
    const run = { run_id: 'run-block', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED', observer_health: { required_observations: ['resource_state'], resource_state: { configured: true } } }
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(basePresentation({
      run_id: 'run-block', verdict: 'BLOCK', headline: '发现权限问题', problem_count: 1, safe_count: 0, execution_traces: [vulnerableTrace],
      issues: [{ finding_id: 'finding-block', title: '后端确认：禁止操作造成真实变化', subject_group: '成员账号', action: '修改', resource: '文档', relation: '拥有', expectation: '不应允许这次操作，资源也不应发生变化', surface_result: '页面或接口显示已拒绝', actual_result: '真实资源已经发生变化', conclusion: '发现权限问题', explanation: '页面或接口虽然显示已拒绝，但外部可信观察确认真实资源已经变化；权限限制没有真正阻止修改，表面拒绝没有阻止真实副作用。', planned_identity_id: 'member-a', planned_identity_label: '成员 A', actual_identity_status: 'CONFIRMED', actual_identity_id: 'bob', actual_identity_label: 'Bob', severity: 'critical', evidence_refs: ['ev-block'], evidence_sources: [
        { observer_type: 'OWNER_API', label: '目标业务状态', role: 'KEY', status: 'FOUND', evidence_refs: ['ev-block'] },
        { observer_type: 'READ_ONLY_SQLITE', label: '只读数据库', role: 'SUPPORTING', status: 'NOT_FOUND', evidence_refs: ['ev-block'] },
        { observer_type: 'STRUCTURED_AUDIT_LOG', label: '结构化审计记录', role: 'SUPPORTING', status: 'FOUND', evidence_refs: ['ev-block'] },
        { observer_type: 'ASYNC_TASK_STATUS', label: '后台任务', role: 'SUPPORTING', status: 'FOUND', evidence_refs: ['ev-block'] },
        { observer_type: 'AZURE_QUEUE_PEEK', label: '消息通道', role: 'SUPPORTING', status: 'UNAVAILABLE', evidence_refs: ['ev-block'] },
        { observer_type: 'AZURE_BLOB_OBJECT', label: '最终对象/文件', role: 'KEY', status: 'FOUND', evidence_refs: ['ev-block'] },
      ], diagnosis: exactDiagnosis(), verdict: 'VULNERABLE', occurrence_status: 'APPEARED' }],
    }))
    resultsApi.evidence.mockResolvedValue([{ evidence_id: 'ev-block' }])
    resultsApi.evidenceDetail.mockResolvedValue({ evidence_id: 'ev-block', case_snapshot: { subject_id: 'member', action_id: 'modify', resource_ids: ['owner-document'], expectations: ['DENY'], required_observations: ['resource_state'] }, twin_role: 'DENY_VARIANT', allow_control_valid: true, baseline_integrity: true, execution_fact: { outcome: 'DENIED' }, observation_facts: [{ requirement_id: 'resource_state', resource_id: 'owner-document', effect: 'CONFIRMED', complete: true, reliable: true }], security_effect_facts: [{ kind: 'STATE_MUTATION', state: 'CONFIRMED', temporal_closure: 'CLOSED', baseline_integrity: true, complete: true, reliable: true, correlated: true }], verdict: 'VULNERABLE' })

    render(<CheckResultsPage run={run} onError={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: '发现权限问题' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '后端确认：禁止操作造成真实变化' })).toBeInTheDocument()
    expect(screen.getByText('成员账号 · 修改 · 文档 · 拥有')).toBeInTheDocument()
    expect(screen.getByText('真实资源已经发生变化')).toBeInTheDocument()
    expect(screen.getByText(/权限限制没有真正阻止修改/)).toBeInTheDocument()
    expect(screen.getByText('计划使用的账号')).toBeInTheDocument()
    expect(screen.getByText('成员 A')).toBeInTheDocument()
    expect(screen.getByText('目标实际识别的账号')).toBeInTheDocument()
    expect(screen.getAllByText('Bob').length).toBeGreaterThan(0)
    expect(screen.queryByText(/不会把计划账号冒充为实际账号/)).not.toBeInTheDocument()
    expect(screen.getByText('真实结果证据来源')).toBeInTheDocument()
    expect(screen.getByText(/佐证来源补充执行过程/)).toBeInTheDocument()
    expect(screen.getByText('确定性诊断')).toBeInTheDocument()
    expect(screen.getByText('首个可证明断裂：权限决定发生过晚')).toBeInTheDocument()
    expect(['权限要求', '实际身份', '权限决定', '首个可证明断裂', '已确认最终后果'].map((label) => screen.getByText(label))).toHaveLength(5)
    expect(screen.getByText('已确认：最终后果')).toBeInTheDocument()
    expect(screen.getAllByText('关键来源')).toHaveLength(2)
    expect(screen.getAllByText('佐证来源')).toHaveLength(4)
    expect(['目标业务状态', '只读数据库', '结构化审计记录', '后台任务', '消息通道', '最终对象/文件'].map((label) => screen.getByText(label))).toHaveLength(6)
    expect(screen.getAllByText('已发现')).toHaveLength(4)
    expect(screen.getByText('未发现')).toBeInTheDocument()
    expect(screen.getAllByText('无法确认')).toHaveLength(1)
    expect(screen.getByRole('heading', { name: '执行路径' })).toBeInTheDocument()
    const traceToggle = screen.getByRole('button', { name: /查看完整执行路径/ })
    expect(traceToggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('request_received')).not.toBeInTheDocument()
    fireEvent.click(traceToggle)
    expect(traceToggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('请求进入目标应用')).toBeInTheDocument()
    expect(screen.getByText('服务器识别实际账号')).toBeInTheDocument()
    expect(screen.getByText('应用作出权限判断')).toBeInTheDocument()
    expect(screen.getByText('任务进入消息链路')).toBeInTheDocument()
    expect(screen.getAllByText('最终业务结果形成').length).toBeGreaterThan(0)
    expect(screen.queryByText('case-bob')).not.toBeInTheDocument()
    expect(screen.queryByText('EXPLICIT_PARENT')).not.toBeInTheDocument()
    expect(screen.queryByText('成员账号不应对文档执行修改')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('查看对应证据'))
    expect(await screen.findByText('证据时间线')).toBeInTheDocument()
  })

  it('INCONCLUSIVE 使用后端说明且不显示执行失败', async () => {
    const run = { run_id: 'run-inconclusive', lifecycle: 'COMPLETED', verdict: 'INCONCLUSIVE', result_integrity: 'VERIFIED', observer_health: { required_observations: ['resource_state'], resource_state: { configured: true } } }
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(basePresentation({ run_id: 'run-inconclusive', verdict: 'INCONCLUSIVE', headline: '证据不足', scope_statement: '操作已经执行，但真实资源最终状态无法可靠确认；这不代表安全，也不代表已经确认漏洞。', safe_count: 0, inconclusive_count: 1, execution_traces: [{ ...vulnerableTrace, complete: false, reason_codes: ['TRACE_AUDIT_INCOMPLETE'], events: vulnerableTrace.events.slice(0, 2) }], issues: [{ finding_id: 'finding-1', title: '读取文档的真实结果暂时无法确认', subject_group: '普通用户账号', action: '读取', resource: '文档', relation: '拥有', expectation: '按当前权限规则执行', surface_result: '表面结果无法确定', actual_result: '真实资源状态尚不能可靠确认', conclusion: '证据不足', explanation: '必需观察不完整或不可靠，当前证据不足以确认资源是否按权限规则变化。', planned_identity_id: 'member-a', planned_identity_label: null, actual_identity_status: 'UNAVAILABLE', actual_identity_id: null, actual_identity_label: null, severity: 'high', evidence_refs: [], evidence_sources: [{ observer_type: 'OWNER_API', label: '目标业务状态', role: 'KEY', status: 'UNAVAILABLE', evidence_refs: [] }], verdict: 'INCONCLUSIVE', occurrence_status: 'APPEARED' }], limitations: ['有 1 项因真实状态观察不完整或不可靠而证据不足。'] }))
    resultsApi.evidence.mockResolvedValue([])
    render(<CheckResultsPage run={run} onError={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: '证据不足' })).toBeInTheDocument()
    expect((await screen.findAllByText('证据不足')).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: '完善真实结果确认方式' })).toBeInTheDocument()
    expect(screen.queryByText('检查执行未完整结束')).not.toBeInTheDocument()
    const traceToggle = screen.getByRole('button', { name: /查看完整执行路径/ })
    expect(traceToggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(traceToggle)
    expect(screen.getByText('当前只能确认部分执行路径')).toBeInTheDocument()
    expect(screen.queryByText('export_message_sent')).not.toBeInTheDocument()
  })

  it('RANGE 和 VIOLATION_ONLY 原样展示后端诊断文案', async () => {
    const run = { run_id: 'run-range', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED' }
    runsApi.run.mockResolvedValue(run)
    resultsApi.evidence.mockResolvedValue([])
    resultsApi.presentation.mockResolvedValue(basePresentation({ run_id: 'run-range', verdict: 'BLOCK', problem_count: 1, safe_count: 0, issues: [{ finding_id: 'finding-range', title: '范围诊断', subject_group: '成员账号', action: '导出', resource: '资料包', relation: '拥有', expectation: '不应导出', surface_result: '已拒绝', actual_result: '已生成', conclusion: '发现权限问题', explanation: '后端已确认问题。', planned_identity_id: 'member-a', planned_identity_label: '成员 A', actual_identity_status: 'CONFIRMED', actual_identity_id: 'bob', actual_identity_label: 'Bob', severity: 'high', evidence_refs: ['ev-block'], evidence_sources: [], diagnosis: exactDiagnosis({ precision: 'RANGE', summary: '断裂发生在 A 与 B 之间' }), verdict: 'VULNERABLE', occurrence_status: 'APPEARED' }] }))
    const view = render(<CheckResultsPage run={run} onError={vi.fn()} />)
    expect(await screen.findByText('断裂发生在 A 与 B 之间')).toBeInTheDocument()
    view.unmount()

    const violationRun = { ...run, run_id: 'run-violation' }
    runsApi.run.mockResolvedValue(violationRun)
    resultsApi.presentation.mockResolvedValue(basePresentation({ run_id: 'run-violation', verdict: 'BLOCK', problem_count: 1, safe_count: 0, issues: [{ finding_id: 'finding-violation', title: '违规诊断', subject_group: '成员账号', action: '导出', resource: '资料包', relation: '拥有', expectation: '不应导出', surface_result: '已拒绝', actual_result: '无法定位', conclusion: '发现权限问题', explanation: '后端已确认问题。', planned_identity_id: 'member-a', planned_identity_label: '成员 A', actual_identity_status: 'UNAVAILABLE', actual_identity_id: null, actual_identity_label: null, severity: 'high', evidence_refs: ['ev-block'], evidence_sources: [], diagnosis: exactDiagnosis({ precision: 'VIOLATION_ONLY', summary: '违规已确认，但当前证据不足以进一步定位' }), verdict: 'VULNERABLE', occurrence_status: 'APPEARED' }] }))
    render(<CheckResultsPage run={violationRun} onError={vi.fn()} />)
    expect(await screen.findByText('违规已确认，但当前证据不足以进一步定位')).toBeInTheDocument()
  })

  it('diagnosis 缺失时保持结果问题卡兼容', async () => {
    const run = { run_id: 'run-legacy', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED' }
    runsApi.run.mockResolvedValue(run)
    resultsApi.evidence.mockResolvedValue([])
    resultsApi.presentation.mockResolvedValue(basePresentation({ run_id: 'run-legacy', verdict: 'BLOCK', problem_count: 1, safe_count: 0, issues: [{ finding_id: 'finding-legacy', title: '缺少诊断的旧结果', subject_group: '成员账号', action: '读取', resource: '文档', relation: '拥有', expectation: '不应读取', surface_result: '已拒绝', actual_result: '无法确认', conclusion: '证据不足', explanation: '后端未提供诊断。', planned_identity_id: 'member-a', planned_identity_label: null, actual_identity_status: 'UNAVAILABLE', actual_identity_id: null, actual_identity_label: null, severity: 'high', evidence_refs: [], evidence_sources: [], verdict: 'INCONCLUSIVE', occurrence_status: 'APPEARED' }] }))
    render(<CheckResultsPage run={run} onError={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: '缺少诊断的旧结果' })).toBeInTheDocument()
    expect(screen.queryByText('确定性诊断')).not.toBeInTheDocument()
  })

  it('PASS 首屏展示后端范围限制与五项计数', async () => {
    const run = { run_id: 'run-pass', lifecycle: 'COMPLETED', verdict: 'PASS', result_integrity: 'VERIFIED', observer_health: { required_observations: [] } }
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(basePresentation({ checked_count: 2, safe_count: 2, uncovered_count: 1, limitations: ['仍有 1 项权限要求未覆盖；本次结论只适用于实际执行范围。'] }))
    resultsApi.evidence.mockResolvedValue([])
    render(<CheckResultsPage run={run} onError={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: '当前范围未发现确认问题' })).toBeInTheDocument()
    expect(screen.getByText(/不代表应用绝对安全/)).toBeInTheDocument()
    expect(screen.getByText('未覆盖')).toBeInTheDocument()
    expect(screen.getAllByText('2 项')).toHaveLength(2)
    expect(screen.getByText(/本次结论只适用于实际执行范围/)).toBeInTheDocument()
  })

  it('普通区显示冻结权限版本且不泄露 fingerprint 和相关意图标识', async () => {
    const run = { run_id: 'run-policy', lifecycle: 'COMPLETED', verdict: 'PASS', result_integrity: 'VERIFIED' }
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(basePresentation({ run_id: 'run-policy', policy_epoch: 9, policy_fingerprint: 'b'.repeat(64), relevant_intents: [{ intent_id: `pin_${'c'.repeat(32)}`, revision: 4, intent_hash: 'c'.repeat(64) }] }))
    resultsApi.evidence.mockResolvedValue([])
    render(<CheckResultsPage run={run} onError={vi.fn()} />)
    expect(await screen.findByText('本次检查依据权限版本 9')).toBeInTheDocument()
    expect(screen.queryByText(`pin_${'c'.repeat(32)}`)).not.toBeInTheDocument()
    expect(screen.queryByText('b'.repeat(64))).not.toBeInTheDocument()
    expect(screen.queryByText(`pin_${'c'.repeat(32)}@4:${'c'.repeat(64)}`)).not.toBeInTheDocument()
  })

  it('代码变化重验只显示有界权限数量，不泄露内部标识或源码指纹', async () => {
    const intentId = `pin_${'d'.repeat(32)}`
    const run = { run_id: 'run-change', lifecycle: 'COMPLETED', verdict: 'PASS', result_integrity: 'VERIFIED' }
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(basePresentation({ run_id: 'run-change', change_verification: { change_id: `chg_${'e'.repeat(32)}`, required_intents: [{ intent_id: intentId, revision: 2, intent_hash: 'f'.repeat(64), display_label: 'P-001' }] } }))
    resultsApi.evidence.mockResolvedValue([])
    render(<CheckResultsPage run={run} onError={vi.fn()} />)
    expect(await screen.findByText(`本次为代码变化 chg_${'e'.repeat(32)} 的重新验证`)).toBeInTheDocument()
    expect(screen.getByText('需要重验的权限：P-001')).toBeInTheDocument()
    expect(screen.queryByText(intentId)).not.toBeInTheDocument()
    expect(screen.queryByText('f'.repeat(64))).not.toBeInTheDocument()
  })
})
