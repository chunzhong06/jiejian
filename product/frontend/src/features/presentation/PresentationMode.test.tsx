// 验证四页展示只投影正式 Run、证据、修复合同与净化 validation 汇总。

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PresentationMode } from './PresentationMode'

const mockApi = vi.hoisted(() => ({
  presentation: vi.fn(),
  history: vi.fn(),
  validationSummary: vi.fn(),
}))

vi.mock('../../api/results', () => ({ resultsApi: { presentation: mockApi.presentation, history: mockApi.history } }))
vi.mock('../../api/experience', () => ({ experienceApi: { validationSummary: mockApi.validationSummary } }))

const experience = {
  available: true,
  display_name: '协作空间',
  unavailable_reason: null,
  active: true,
  experience_id: `exp_${'a'.repeat(32)}`,
  experience_mode: 'GUIDED' as const,
  project_id: 'p1',
  origin: 'http://127.0.0.1:12345',
  identities_ready: true,
  authorization_order: 'ENQUEUE_BEFORE_AUTHORIZE' as const,
  blob_observation: 'AVAILABLE' as const,
  repair_change_id: null,
}

const run = {
  run_id: 'run-current',
  lifecycle: 'COMPLETED',
  verdict: 'BLOCK',
  result_integrity: 'VERIFIED',
  created_at_us: 1_800_000_000_000_000,
}

function traceEvent(kind: string, index: number, decision: string | null = null) {
  return {
    event_id: `event-${index}`,
    parent_event_ids: index === 1 ? [] : [`event-${index - 1}`],
    case_id: 'case-export',
    action_id: 'export-package',
    resource_ids: ['campus-digital-museum'],
    kind,
    semantic_key: `semantic-${index}`,
    subject_id: 'bob',
    actor_id: index >= 6 ? 'sample-worker' : 'bob',
    credential_source: 'bob-session',
    authority_scope: { allowed_action_ids: [], allowed_resource_ids: [], origin_authorization_event_id: null, delegated_from_event_id: null },
    authorization_decision: decision,
    effect_id: index === 7 ? 'package-created' : null,
    source_component: index >= 6 ? 'sample-worker' : 'collaboration-api',
    source_location: 'published-trace',
    correlation_kind: 'CASE_MARKER',
    evidence_refs: [`evidence-${index}`],
    recorded_at_us: 1_800_000_000_000_000 + index,
  }
}

function vulnerableIssue(overrides: Record<string, unknown> = {}) {
  return {
    finding_id: 'finding-export',
    title: 'Bob 导出完整项目交付包',
    subject_group: '普通成员',
    action_id: 'export-package',
    action: 'export-package',
    resource: '完整项目交付包',
    relation: '项目成员',
    expectation: 'Bob 不得导出完整项目交付包',
    surface_result: 'HTTP 403 · 请求被拒绝',
    actual_result: '后台任务成功，ZIP 已生成',
    conclusion: '表面拒绝没有阻止真实后果',
    explanation: '权限判断发生过晚。',
    planned_identity_id: 'bob',
    planned_identity_label: 'Bob · 普通成员',
    actual_identity_status: 'CONFIRMED',
    actual_identity_id: 'bob',
    actual_identity_label: 'Bob · 普通成员',
    severity: 'high',
    evidence_refs: ['evidence-7'],
    evidence_sources: [
      { observer_type: 'OWNER_API', label: '目标业务状态', role: 'KEY', status: 'FOUND', evidence_refs: ['evidence-1'] },
      { observer_type: 'READ_ONLY_SQLITE', label: '只读数据库', role: 'SUPPORTING', status: 'FOUND', evidence_refs: ['evidence-2'] },
      { observer_type: 'STRUCTURED_AUDIT_LOG', label: '结构化审计', role: 'SUPPORTING', status: 'FOUND', evidence_refs: ['evidence-3'] },
      { observer_type: 'ASYNC_TASK_STATUS', label: '后台任务', role: 'SUPPORTING', status: 'FOUND', evidence_refs: ['evidence-4'] },
      { observer_type: 'AZURE_QUEUE_PEEK', label: '消息通道', role: 'SUPPORTING', status: 'FOUND', evidence_refs: ['evidence-5'] },
      { observer_type: 'AZURE_BLOB_OBJECT', label: '最终 ZIP', role: 'KEY', status: 'FOUND', evidence_refs: ['evidence-7'] },
    ],
    diagnosis: {
      case_id: 'case-export', action_id: 'export-package', breakpoint_type: 'AUTHORIZATION_LATE', precision: 'EXACT', continuity_state: 'ORPHAN_EFFECT_CONFIRMED',
      first_violation_event_id: 'event-3', range_start_event_id: null, range_end_event_id: null, amplifier_types: [], summary: '可执行任务在权限拒绝前形成。', minimal_witness: [], confirmed_impacts: [], evidence_refs: ['evidence-3'],
    },
    claim_boundary: {
      surface_response_status: 'DENIED', business_effect_status: 'CONFIRMED', actual_identity_status: 'CONFIRMED', breakpoint_precision: 'EXACT', repair_status: null,
      supported_statement: 'Bob 的请求虽然被拒绝，但完整项目交付包在本轮真实形成。', unsupported_statements: ['不能外推到其他应用。'],
    },
    evidence_explanations: [{
      label: '最终 ZIP 已形成', source: '最终对象观察', step: '后台执行完成', proves: '完整项目交付包已经生成。', does_not_prove: '不能单独证明 ZIP 属于当前请求。',
      relevance: 'request marker 同时关联请求、任务、Worker 与 ZIP。', evidence_refs: ['evidence-7'], component: 'sample-worker', observed_at_us: 1_800_000_000_000_007,
    }],
    verdict: 'VULNERABLE',
    occurrence_status: 'APPEARED',
    repair_requirement: null,
    ...overrides,
  }
}

function presentation(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 'run-current', project_id: 'p1', project_name: '协作空间', run_lifecycle: 'COMPLETED', verdict: 'BLOCK', policy_epoch: 4, policy_fingerprint: 'policy-fingerprint',
    relevant_intents: [{ intent_id: 'intent-export', revision: 4, intent_hash: 'intent-hash', display_label: '权限 P-2027-04', expectation: 'DENY', business_statement: 'Bob 可以查看日常协作资料，但不能导出完整项目交付包。' }],
    change_verification: null, repair_verification: null, headline: '发现权限问题', scope_statement: '当前范围确认一项权限问题。', checked_count: 1, safe_count: 0, problem_count: 1, inconclusive_count: 0, uncovered_count: 0, execution_problem: null,
    execution_traces: [{ schema_version: '1', case_id: 'case-export', action_id: 'export-package', planned_subject_id: 'bob', complete: true, reason_codes: [], events: [
      traceEvent('ENTRY', 1), traceEvent('IDENTITY', 2), traceEvent('PERSISTENT_EFFECT', 3), traceEvent('AUTHORIZATION', 4, 'DENY'), traceEvent('MESSAGE', 5), traceEvent('DELEGATION', 6), traceEvent('FINAL_EFFECT', 7),
    ] }],
    issues: [vulnerableIssue()], limitations: ['只适用于当前 Run。'],
    ...overrides,
  }
}

const history = {
  project_id: 'p1',
  intents: [{
    intent_id: 'intent-export', display_label: '权限 P-2027-04', runs: [], revisions: [{ revision: 4, intent_hash: 'intent-hash', policy_epoch: 4, effective_state: 'ACTIVE', business_statement: 'Bob 不得导出完整项目交付包。', approved_by: '项目负责人', approved_at_us: 1_799_000_000_000_000 }],
  }],
  comparisons: [],
}

const validationSummary = {
  available: true,
  unavailable_reason: null,
  summary: {
    schema_version: '1', generated_at_us: 1_800_000_000_000_000, suite: 'validation', status: 'accepted', repetitions: 1, case_count: 30, case_run_count: 30, application_count: 2, mode_count: 5, state_count: 3,
    full_exact_match_count: 30, full_wrong_pass_vulnerable: 0, full_wrong_pass_evidence_gap: 0, http_exact_match_count: 14, http_wrong_pass_vulnerable: 6, http_wrong_pass_evidence_gap: 10, http_wrong_pass_per_matrix: 16,
    source_revision: 'a'.repeat(40), source_dirty: false,
  },
}

describe('PresentationMode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.presentation.mockResolvedValue(presentation())
    mockApi.history.mockResolvedValue(history)
    mockApi.validationSummary.mockResolvedValue(validationSummary)
  })

  it('项目结论展示权限版本、403 与 ZIP 反差以及当次动态数字', async () => {
    render(<PresentationMode experience={experience} projectName="协作空间" runs={[run]} onExit={vi.fn()} onOpenProductRoute={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: 'Bob 收到 403，但完整项目交付包仍在后台生成' })).toBeInTheDocument()
    expect(await screen.findByText('Bob 可以查看日常协作资料，但不能导出完整项目交付包。')).toBeInTheDocument()
    expect(screen.getByText('权限 P-2027-04 · 第 4 版')).toBeInTheDocument()
    expect(screen.getByText('HTTP 403 · 请求被拒绝')).toBeInTheDocument()
    expect(screen.getByText('后台任务成功，ZIP 已生成')).toBeInTheDocument()
    const facts = screen.getByLabelText('当次验证数字')
    expect(within(facts).getByText('6')).toBeInTheDocument()
    expect(within(facts).getByText('7')).toBeInTheDocument()
  })

  it('现场验证默认展示本轮关联和精确断裂，并按问题打开证据说明', async () => {
    render(<PresentationMode experience={experience} projectName="协作空间" runs={[run]} onExit={vi.fn()} onOpenProductRoute={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /现场验证/ }))

    expect(await screen.findByText('request marker 同时关联请求、任务、Worker 与 ZIP。')).toBeInTheDocument()
    expect(screen.getByText('AUTHORIZATION_LATE')).toBeInTheDocument()
    expect(screen.getByText('首个可证明断裂')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '查看 ZIP 为什么属于本轮' }))
    expect(await screen.findByText('完整项目交付包已经生成。')).toBeInTheDocument()
    expect(screen.getByText('不能单独证明 ZIP 属于当前请求。')).toBeInTheDocument()
  })

  it('修复页读取源 Run，并按正式事实分别展示三条修复路径', async () => {
    const repaired = vulnerableIssue({
      actual_result: '任务、消息、Worker 与 ZIP 均未形成',
      verdict: 'SAFE',
      diagnosis: null,
      claim_boundary: { ...vulnerableIssue().claim_boundary, business_effect_status: 'ABSENT', breakpoint_precision: null, repair_status: 'VERIFIED', supported_statement: 'Bob 的违规导出后果已经消失。' },
      repair_requirement: { reference: { source_run_id: 'run-source', source_finding_id: 'finding-export', repair_fingerprint: 'c'.repeat(64) }, must_disappear: 'Bob 导出的任务、消息、Worker 与 ZIP', must_remain: 'Alice 的合法导出', must_not_change: ['Bob 的 DENY', '关键观察标准'] },
    })
    const current = presentation({
      verdict: 'PASS', problem_count: 0, safe_count: 1, issues: [repaired],
      repair_verification: {
        reference: { source_run_id: 'run-source', source_finding_id: 'finding-export', repair_fingerprint: 'c'.repeat(64) },
        verification_run_id: 'run-current', status: 'VERIFIED', message: '三条路径均已验证。', reason_codes: ['REPAIR_REQUIREMENTS_SATISFIED'],
        path_results: [
          { kind: 'DENY_EFFECT_REMOVAL', action_id: 'export-package', subject_id: 'bob', subject_display_name: 'Bob', action_display_name: '导出完整项目交付包', status: 'VERIFIED', message: '任务、消息、Worker 与 ZIP 均未形成。', evidence_refs: ['e-bob'], reason_codes: ['DENY_EFFECT_REMOVED'] },
          { kind: 'ALLOW_CONTROL', action_id: 'export-package', subject_id: 'alice', subject_display_name: 'Alice', action_display_name: '导出完整项目交付包', status: 'VERIFIED', message: '合法导出仍然正常完成。', evidence_refs: ['e-alice'], reason_codes: ['ALLOW_CONTROL_PRESERVED'] },
          { kind: 'REGRESSION_CONTROL', action_id: 'view-collaboration', subject_id: 'bob', subject_display_name: 'Bob', action_display_name: '查看日常协作资料', status: 'VERIFIED', message: '日常协作资料仍可正常查看。', evidence_refs: ['e-view'], reason_codes: ['REGRESSION_CONTROL_PRESERVED'] },
        ],
      },
    })
    const source = presentation({ run_id: 'run-source' })
    mockApi.presentation.mockImplementation((runId: string) => Promise.resolve(runId === 'run-source' ? source : current))
    render(<PresentationMode experience={experience} projectName="协作空间" runs={[{ ...run, verdict: 'PASS' }]} onExit={vi.fn()} onOpenProductRoute={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /修复前后/ }))

    expect(await screen.findByText('三条路径分别核对')).toBeInTheDocument()
    const pathSection = document.querySelector('.presentation-repair-paths')
    expect(pathSection).not.toBeNull()
    expect(within(pathSection as HTMLElement).getAllByText('已验证')).toHaveLength(3)
    const bobView = screen.getByText('Bob 查看日常协作资料').closest('article')
    expect(bobView).not.toBeNull()
    expect(within(bobView as HTMLElement).getByText('已验证')).toBeInTheDocument()
    expect(within(bobView as HTMLElement).getByText('日常协作资料仍可正常查看。')).toBeInTheDocument()
  })

  it('数据页只读取净化汇总，并同时显示 wrong PASS 与适用边界', async () => {
    render(<PresentationMode experience={experience} projectName="协作空间" runs={[run]} onExit={vi.fn()} onOpenProductRoute={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /数据与边界/ }))

    expect(await screen.findByText('30 Case')).toBeInTheDocument()
    expect(screen.getByText('30/30 匹配')).toBeInTheDocument()
    expect(screen.getByText(/共 16 个 wrong PASS/)).toBeInTheDocument()
    expect(screen.getByText(/不能代表任意 Web 应用的漏洞检出率/)).toBeInTheDocument()
    expect(screen.queryByText('private oracle')).not.toBeInTheDocument()
  })

  it('没有正式 Run 时保持空状态，数据页也不伪造历史数字', async () => {
    mockApi.validationSummary.mockResolvedValue({ available: false, unavailable_reason: '尚未发布可展示的验证汇总', summary: null })
    render(<PresentationMode experience={experience} projectName="协作空间" runs={[]} onExit={vi.fn()} onOpenProductRoute={vi.fn()} />)

    expect(screen.getByText(/当前官方示例尚无正式检查结果/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /数据与边界/ }))
    expect(await screen.findByText('尚未发布可展示的验证汇总')).toBeInTheDocument()
    expect(screen.queryByText('30 Case')).not.toBeInTheDocument()
    expect(mockApi.presentation).not.toHaveBeenCalled()
  })

  it('退出和返回正式产品仍由明确按钮触发', async () => {
    const onExit = vi.fn()
    const onOpenProductRoute = vi.fn()
    render(<PresentationMode experience={experience} projectName="协作空间" runs={[run]} onExit={onExit} onOpenProductRoute={onOpenProductRoute} />)
    await screen.findByText('权限 P-2027-04 · 第 4 版')
    fireEvent.click(screen.getByRole('button', { name: /现场验证/ }))
    fireEvent.click(screen.getByRole('button', { name: '进入正式产品核对完整结果' }))
    expect(onOpenProductRoute).toHaveBeenCalledWith('/verification')
    fireEvent.click(screen.getByRole('button', { name: '退出展示模式' }))
    expect(onExit).toHaveBeenCalledOnce()
    await waitFor(() => expect(mockApi.presentation).toHaveBeenCalledWith('run-current'))
  })
})
