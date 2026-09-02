// 验证现场验证只从已发布结果画路径，并按断点精度和证据边界限制主张。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { VerificationPage } from './VerificationPage'

const resultsApi = vi.hoisted(() => ({ presentation: vi.fn() }))
const runsApi = vi.hoisted(() => ({ run: vi.fn() }))
vi.mock('../../api/results', () => ({ resultsApi }))
vi.mock('../../api/runs', () => ({ runsApi }))
vi.mock('../../components/AssistantPanel', () => ({ AssistantPanel: () => <div>AI 辅助解释区</div> }))

const run = { run_id: 'run-current', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED' }
const events = ['ENTRY', 'IDENTITY', 'AUTHORIZATION', 'FINAL_EFFECT'].map((kind, index) => ({
  event_id: `event-${index + 1}`,
  parent_event_ids: index ? [`event-${index}`] : [],
  case_id: 'case-1',
  action_id: 'export-package',
  resource_ids: ['package'],
  kind,
  semantic_key: `business-${index + 1}`,
  subject_id: 'bob',
  actor_id: 'bob',
  credential_source: null,
  authority_scope: { allowed_action_ids: [], allowed_resource_ids: [], origin_authorization_event_id: null, delegated_from_event_id: null },
  authorization_decision: kind === 'AUTHORIZATION' ? 'DENY' : null,
  effect_id: kind === 'FINAL_EFFECT' ? 'internal-effect-id' : null,
  source_component: 'collaboration-server',
  source_location: 'internal-location',
  correlation_kind: 'EXPLICIT_PARENT',
  evidence_refs: ['evidence-1'],
  recorded_at_us: 1_000 + index,
}))

function diagnosis(overrides: Record<string, unknown> = {}) {
  return {
    case_id: 'case-1', action_id: 'export-package', breakpoint_type: 'AUTHORIZATION_LATE', precision: 'EXACT', continuity_state: 'ORPHAN_EFFECT_CONFIRMED',
    first_violation_event_id: 'event-3', range_start_event_id: null, range_end_event_id: null, amplifier_types: [], summary: '权限判断发生过晚。',
    minimal_witness: [], confirmed_impacts: [{ event_id: 'event-4', parent_event_ids: ['event-3'], kind: 'FINAL_EFFECT', semantic_key: 'archive-generated', effect_id: 'internal-effect-id', summary: '完整资料包已经生成', evidence_refs: ['evidence-1'] }], evidence_refs: ['evidence-1'],
    ...overrides,
  }
}

function issue(overrides: Record<string, unknown> = {}) {
  return {
    finding_id: 'finding-1', title: '成员不应导出完整项目资料包', subject_group: '成员账号', action: '导出完整项目资料包', resource: '项目资料', relation: '其他权限组',
    expectation: '成员账号不应完成导出，完整资料包也不应生成。', surface_result: '页面显示已拒绝', actual_result: '完整资料包已经生成', conclusion: '发现权限问题', explanation: '可信外部观察确认资料包已经生成。',
    planned_identity_id: 'member', planned_identity_label: 'Bob · 成员', actual_identity_status: 'CONFIRMED', actual_identity_id: 'bob', actual_identity_label: 'Bob', severity: 'critical',
    evidence_refs: ['evidence-1'], evidence_sources: [], diagnosis: diagnosis(),
    claim_boundary: { surface_response_status: 'DENIED', business_effect_status: 'CONFIRMED', actual_identity_status: 'CONFIRMED', breakpoint_precision: 'EXACT', repair_status: null, supported_statement: 'Bob 凭据的实验中，完整资料包已经生成。', unsupported_statements: ['不能宣称所有导出路径都存在同一问题。'] },
    evidence_explanations: [{ label: '最终资料包观察', source: '目标业务状态', step: '最终业务结果形成', proves: '完整资料包在本次实验中已经生成。', does_not_prove: '不能单独证明所有导出入口。', relevance: '来自当前 Run 的已发布观察事实。', evidence_refs: ['evidence-1'], component: 'collaboration-server', location: '目标应用接口 /api/projects/package/export', observer_id: 'owner-export-observer', observation_phase: 'EVENTUAL', provenance_type: 'OWNER_API', adapter_version: 'owner-api-1', source_sha256: 'c'.repeat(64), observed_at_us: 1_003 }],
    verdict: 'VULNERABLE', occurrence_status: 'APPEARED', repair_requirement: null,
    ...overrides,
  }
}

function presentation(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 'run-current', project_id: 'project-1', project_name: '协作空间', run_lifecycle: 'COMPLETED', verdict: 'BLOCK', policy_epoch: 4, policy_fingerprint: 'a'.repeat(64),
    relevant_intents: [{ intent_id: `pin_${'1'.repeat(32)}`, revision: 2, intent_hash: 'b'.repeat(64), display_label: 'P-001', expectation: 'DENY', business_statement: '成员 Bob 不可以导出项目负责人的完整资料包。' }],
    change_verification: null, repair_verification: null, headline: '发现权限问题', scope_statement: '当前范围确认一个权限问题。', checked_count: 1, safe_count: 0, problem_count: 1, inconclusive_count: 0, uncovered_count: 0, execution_problem: null,
    execution_traces: [{ schema_version: '1', case_id: 'case-1', action_id: 'export-package', planned_subject_id: 'member', events, complete: true, reason_codes: [] }], issues: [issue()], limitations: [],
    ...overrides,
  }
}

describe('VerificationPage', () => {
  it('没有真实 Run 时明确要求先完成检查', () => {
    render(<VerificationPage onError={vi.fn()} />)
    expect(screen.getByText('先完成一次检查')).toBeInTheDocument()
    expect(resultsApi.presentation).not.toHaveBeenCalled()
  })

  it('先展示矛盾、关键链和事实依据，再按需展开完整边界', async () => {
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(presentation())
    render(<VerificationPage run={run} onError={vi.fn()} />)

    expect(await screen.findByText('本轮核心矛盾')).toBeInTheDocument()
    expect(screen.getByText('表面响应')).toBeInTheDocument()
    expect(screen.getByText('页面显示已拒绝')).toBeInTheDocument()
    expect(screen.getByText('独立观察到的真实结果')).toBeInTheDocument()
    expect(screen.getAllByText('完整资料包已经生成').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: '关键执行链' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '决定性证明链' })).toBeInTheDocument()
    expect(screen.getAllByText('目标应用接口 /api/projects/package/export').length).toBeGreaterThan(0)
    expect(screen.queryByText('权限考题已锁定')).not.toBeInTheDocument()
    expect(document.querySelectorAll('.is-exact-break')).toHaveLength(1)
    expect(screen.queryByText('internal-effect-id')).not.toBeInTheDocument()
    expect(screen.getAllByText(/collaboration-server/).length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: '查看“目标应用识别实际账号”证据' }))
    expect(await screen.findByText('证据说明 · 成员不应导出完整项目资料包')).toBeInTheDocument()
    for (const label of ['在哪里看到', '看到什么', '因此支持']) expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    expect(screen.getAllByText('目标应用接口 /api/projects/package/export').length).toBeGreaterThan(0)
    expect(screen.queryByText('这条证据不能单独说明')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /查看观察者与原始引用/ }))
    for (const label of ['具体观察者', '责任组件', '观察时点', '采集来源', '适配器版本', '核对方式', '为什么属于本轮', '采集时间', '源数据摘要', '证据引用']) expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.getByText('owner-export-observer')).toBeInTheDocument()
    expect(screen.getByText('evidence-1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /本轮证据边界/ }))
    expect(screen.getByText('不能单独证明所有导出入口。')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    fireEvent.click(screen.getByText('查看本次锁定的权限规则'))
    expect(await screen.findByText('权限考题已锁定')).toBeInTheDocument()
    expect(screen.getByText('成员 Bob 不可以导出项目负责人的完整资料包。')).toBeInTheDocument()
  })

  it('RANGE 只画两个区间边界，不宣称唯一断点', async () => {
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(presentation({ issues: [issue({ diagnosis: diagnosis({ precision: 'RANGE', first_violation_event_id: null, range_start_event_id: 'event-2', range_end_event_id: 'event-4' }), claim_boundary: { ...issue().claim_boundary, breakpoint_precision: 'RANGE' } })] }))
    render(<VerificationPage run={run} onError={vi.fn()} />)
    expect(await screen.findByText(/不能声称唯一断点/)).toBeInTheDocument()
    expect(document.querySelectorAll('.is-range-boundary')).toHaveLength(2)
    expect(document.querySelectorAll('.is-exact-break')).toHaveLength(0)
  })

  it('VIOLATION_ONLY 与 INCONCLUSIVE 都不画红色断裂点', async () => {
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(presentation({ issues: [issue({ diagnosis: diagnosis({ precision: 'VIOLATION_ONLY', first_violation_event_id: null }), claim_boundary: { ...issue().claim_boundary, breakpoint_precision: 'VIOLATION_ONLY' } })] }))
    const violation = render(<VerificationPage run={run} onError={vi.fn()} />)
    expect(await screen.findByText('违规已确认，但当前证据不足以定位具体断裂点')).toBeInTheDocument()
    expect(document.querySelectorAll('.is-exact-break')).toHaveLength(0)
    violation.unmount()

    resultsApi.presentation.mockResolvedValue(presentation({ verdict: 'INCONCLUSIVE', issues: [issue({ verdict: 'INCONCLUSIVE', conclusion: '证据不足', actual_identity_status: 'UNAVAILABLE', diagnosis: diagnosis(), claim_boundary: { ...issue().claim_boundary, actual_identity_status: 'UNAVAILABLE' } })] }))
    render(<VerificationPage run={{ ...run, run_id: 'run-inconclusive', verdict: 'INCONCLUSIVE' }} onError={vi.fn()} />)
    expect(await screen.findByText('暂不能下安全结论')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '首个可证明断裂' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('查看当前结论能说到哪里'))
    expect(screen.getByText('实际执行身份无法独立确认')).toBeInTheDocument()
    expect(document.querySelectorAll('.is-exact-break')).toHaveLength(0)
  })

  it('原考题复验在同一种路径组件中并列展示前后事实', async () => {
    const source = presentation({ run_id: 'run-source' })
    const repairReference = { source_run_id: 'run-source', source_finding_id: 'finding-1', repair_fingerprint: 'c'.repeat(64) }
    const repairedIssue = issue({ verdict: 'SAFE', actual_result: '完整资料包没有生成', diagnosis: null, claim_boundary: { ...issue().claim_boundary, business_effect_status: 'ABSENT', breakpoint_precision: null, repair_status: 'VERIFIED' }, repair_requirement: { reference: repairReference, must_disappear: '成员导出产生的资料包必须消失。', must_remain: '负责人导出仍可使用。', must_not_change: ['原拒绝权限'] } })
    const current = presentation({ issues: [repairedIssue], repair_verification: { reference: repairReference, verification_run_id: 'run-current', status: 'VERIFIED', message: '原违规后果已消失，合法功能保持。', reason_codes: [], path_results: [] } })
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockImplementation((runId: string) => Promise.resolve(runId === 'run-source' ? source : current))
    render(<VerificationPage run={run} onError={vi.fn()} />)

    expect(await screen.findByText('修复前')).toBeInTheDocument()
    expect(screen.getByText('修复后')).toBeInTheDocument()
    expect(document.querySelectorAll('.verification-repair .verification-path')).toHaveLength(2)
    expect(screen.getAllByText('原考题复验已通过').length).toBeGreaterThan(0)
  })

  it('证据不足的官方示例只转交观察缺口的新 Run 请求', async () => {
    const onObservationGap = vi.fn()
    runsApi.run.mockResolvedValue(run)
    resultsApi.presentation.mockResolvedValue(presentation({ verdict: 'INCONCLUSIVE', issues: [issue({ verdict: 'INCONCLUSIVE', conclusion: '证据不足' })] }))
    render(<VerificationPage run={run} onError={vi.fn()} onObservationGap={onObservationGap} />)
    fireEvent.click(await screen.findByRole('button', { name: '验证关键结果不可读取时会怎样' }))
    await waitFor(() => expect(onObservationGap).toHaveBeenCalledOnce())
  })
})
