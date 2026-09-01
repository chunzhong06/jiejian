// 验证单一样例四幕只关联正式权限、Change、源 Run、修复 Run 与证据说明。

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PresentationMode } from './PresentationMode'

const mockApi = vi.hoisted(() => ({ presentation: vi.fn(), history: vi.fn(), sourceChange: vi.fn() }))

vi.mock('../../api/results', () => ({ resultsApi: { presentation: mockApi.presentation, history: mockApi.history } }))
vi.mock('../../api/sourceChanges', () => ({ sourceChangesApi: { show: mockApi.sourceChange } }))

const experience = {
  available: true, display_name: '协作空间', unavailable_reason: null, active: true,
  experience_id: `exp_${'a'.repeat(32)}`, project_id: 'p1',
  origin: 'http://127.0.0.1:12345', scenario_prepared: true,
  scenario_version: 'VULNERABLE' as const, vulnerable_change_id: null, repair_change_id: null,
}
const run = { run_id: 'run-current', lifecycle: 'COMPLETED', verdict: 'BLOCK', result_integrity: 'VERIFIED', created_at_us: 1_800_000_000_000_000 }
const storyChangeId = `chg_${'a'.repeat(32)}`
const repairChangeId = `chg_${'b'.repeat(32)}`

function traceEvent(kind: string, index: number, decision: string | null = null) {
  return {
    event_id: `event-${index}`, parent_event_ids: index === 1 ? [] : [`event-${index - 1}`], case_id: 'case-export', action_id: 'export-package', resource_ids: ['campus-digital-museum'], kind,
    semantic_key: `semantic-${index}`, subject_id: 'bob', actor_id: index >= 6 ? 'sample-worker' : 'bob', credential_source: 'bob-session',
    authority_scope: { allowed_action_ids: [], allowed_resource_ids: [], origin_authorization_event_id: null, delegated_from_event_id: null }, authorization_decision: decision,
    effect_id: index === 7 ? 'package-created' : null, source_component: index >= 6 ? 'sample-worker' : 'collaboration-api', source_location: 'published-trace', correlation_kind: 'CASE_MARKER', evidence_refs: [`evidence-${index}`], recorded_at_us: 1_800_000_000_000_000 + index,
  }
}

function vulnerableIssue(overrides: Record<string, unknown> = {}) {
  return {
    finding_id: 'finding-export', title: 'Bob 导出完整项目交付包', subject_group: '普通成员', action_id: 'export-package', action: 'export-package', resource: '完整项目交付包', relation: '项目成员', expectation: 'Bob 不得导出完整项目交付包',
    surface_result: 'HTTP 403 · 请求被拒绝', actual_result: '后台任务成功，ZIP 已生成', conclusion: '表面拒绝没有阻止真实后果', explanation: '权限判断发生过晚。',
    planned_identity_id: 'bob', planned_identity_label: 'Bob · 普通成员', actual_identity_status: 'CONFIRMED', actual_identity_id: 'bob', actual_identity_label: 'Bob · 普通成员', severity: 'high', evidence_refs: ['evidence-7'],
    evidence_sources: [{ observer_type: 'AZURE_BLOB_OBJECT', label: '最终 ZIP', role: 'KEY', status: 'FOUND', evidence_refs: ['evidence-7'] }],
    diagnosis: { case_id: 'case-export', action_id: 'export-package', breakpoint_type: 'AUTHORIZATION_LATE', precision: 'EXACT', continuity_state: 'ORPHAN_EFFECT_CONFIRMED', first_violation_event_id: 'event-3', range_start_event_id: null, range_end_event_id: null, amplifier_types: [], summary: '可执行任务在权限拒绝前形成。', minimal_witness: [], confirmed_impacts: [], evidence_refs: ['evidence-3'] },
    claim_boundary: { surface_response_status: 'DENIED', business_effect_status: 'CONFIRMED', actual_identity_status: 'CONFIRMED', breakpoint_precision: 'EXACT', repair_status: null, supported_statement: 'Bob 的请求虽然被拒绝，但完整项目交付包在本轮真实形成。', unsupported_statements: ['不能外推到其他应用。'] },
    evidence_explanations: [{ label: '最终 ZIP 已形成', source: '最终对象观察', step: '后台执行完成', proves: '完整项目交付包已经生成。', does_not_prove: '不能单独证明 ZIP 属于当前请求。', relevance: 'request marker 同时关联请求、任务、Worker 与 ZIP。', evidence_refs: ['evidence-7'], component: 'sample-worker', location: '对象存储 http://127.0.0.1:4277/devstore/export-packages/run-current/', observer_id: 'export-blob-observer', observation_phase: 'EVENTUAL', provenance_type: 'AZURE_BLOB_OBJECT', adapter_version: 'blob-1', source_sha256: 'd'.repeat(64), observed_at_us: 1_800_000_000_000_007 }],
    verdict: 'VULNERABLE', occurrence_status: 'APPEARED', repair_requirement: null, ...overrides,
  }
}

function presentation(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 'run-current', project_id: 'p1', project_name: '协作空间', run_lifecycle: 'COMPLETED', verdict: 'BLOCK', policy_epoch: 4, policy_fingerprint: 'policy-fingerprint',
    relevant_intents: [{ intent_id: 'intent-export', revision: 4, intent_hash: 'intent-hash', display_label: '权限 P-2027-04', expectation: 'DENY', business_statement: 'Bob 可以查看日常协作资料，但不能导出完整项目交付包。' }],
    change_verification: { change_id: storyChangeId, required_intents: [] }, repair_verification: null, headline: '发现权限问题', scope_statement: '当前范围确认一项权限问题。', checked_count: 1, safe_count: 0, problem_count: 1, inconclusive_count: 0, uncovered_count: 0, execution_problem: null,
    execution_traces: [{ schema_version: '1', case_id: 'case-export', action_id: 'export-package', planned_subject_id: 'bob', complete: true, reason_codes: [], events: [traceEvent('ENTRY', 1), traceEvent('IDENTITY', 2), traceEvent('PERSISTENT_EFFECT', 3), traceEvent('AUTHORIZATION', 4, 'DENY'), traceEvent('MESSAGE', 5), traceEvent('DELEGATION', 6), traceEvent('FINAL_EFFECT', 7)] }],
    issues: [vulnerableIssue()], limitations: ['只适用于当前 Run。'], ...overrides,
  }
}

const history = { project_id: 'p1', intents: [{ intent_id: 'intent-export', display_label: '权限 P-2027-04', runs: [], revisions: [{ revision: 4, intent_hash: 'intent-hash', policy_epoch: 4, effective_state: 'ACTIVE', business_statement: 'Bob 不得导出完整项目交付包。', approved_by: '项目负责人', approved_at_us: 1_799_000_000_000_000 }] }], comparisons: [] }
const storyChange = { change_id: storyChangeId, project_id: 'p1', reason: '把同步导出改成后台任务', submitted_by: 'MCP · Codex', created_at_us: 1_799_500_000_000_000, status: 'COMPARABLE', complete: true, actual_changed_path_count: 2, added_count: 0, modified_count: 2, removed_count: 0, claimed_paths: ['app/export.py'], added_paths: [], modified_paths: ['app/export.py', 'app/worker.py'], removed_paths: [], directly_affected_count: 1, mapping_review_required_count: 0, no_direct_evidence_count: 0, review_intent_ids: [], summary: '发现 1 条权限要求与本次变化直接相关。', next_path: null }

describe('PresentationMode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.presentation.mockResolvedValue(presentation())
    mockApi.history.mockResolvedValue(history)
    mockApi.sourceChange.mockImplementation((_projectId: string, changeId: string) => Promise.resolve({ ...storyChange, change_id: changeId, reason: changeId === repairChangeId ? '在创建导出任务前判断权限' : storyChange.reason }))
  })

  it('第一幕先展示 403 与 ZIP 矛盾并可解释本轮关联', async () => {
    render(<PresentationMode experience={experience} projectName="协作空间" runs={[run]} onExit={vi.fn()} onOpenProductRoute={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: 'Bob 收到 403，完整项目交付包却仍在后台生成' })).toBeInTheDocument()
    expect(screen.getByText('权限 P-2027-04 · 第 4 版')).toBeInTheDocument()
    expect(screen.getByText('HTTP 403 · 请求被拒绝')).toBeInTheDocument()
    expect(screen.getByText('后台任务成功，ZIP 已生成')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '为什么确定 ZIP 属于本轮？' }))
    expect(await screen.findByText('完整项目交付包已经生成。')).toBeInTheDocument()
  })

  it('第二幕把人的规则、MCP 提交与真实 diff 串成同一变化', async () => {
    render(<PresentationMode experience={experience} projectName="协作空间" runs={[run]} onExit={vi.fn()} onOpenProductRoute={vi.fn()} />)
    fireEvent.click(within(screen.getByRole('navigation', { name: '展示章节' })).getByRole('button', { name: /回看变化/ }))
    expect(await screen.findByText('把同步导出改成后台任务')).toBeInTheDocument()
    expect(screen.getAllByText('MCP · Codex').length).toBeGreaterThan(0)
    expect(screen.getByText('MCP 提交回执')).toBeInTheDocument()
    expect(screen.getByText(storyChange.change_id)).toBeInTheDocument()
    expect(screen.getByText('由本次问题检查精确引用')).toBeInTheDocument()
    expect(screen.getByText('app/worker.py')).toBeInTheDocument()
    expect(mockApi.sourceChange).toHaveBeenCalledWith('p1', storyChangeId)
  })

  it('第三幕展示精确断裂并按证据责任下钻', async () => {
    render(<PresentationMode experience={experience} projectName="协作空间" runs={[run]} onExit={vi.fn()} onOpenProductRoute={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /展开证据/ }))
    expect(await screen.findByText('权限判断发生过晚')).toBeInTheDocument()
    expect(screen.getByText('精确到单一节点')).toBeInTheDocument()
    expect(screen.getByText('已确认存在未受权限约束的后果')).toBeInTheDocument()
    expect(screen.queryByText('AUTHORIZATION_LATE')).not.toBeInTheDocument()
    expect(screen.getByText('首个可证明断裂')).toBeInTheDocument()
    expect(screen.getByText('request marker 同时关联请求、任务、Worker 与 ZIP。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '展开每种证据能证明什么' }))
    expect(await screen.findByText('对象存储 http://127.0.0.1:4277/devstore/export-packages/run-current/')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /本轮证据边界/ }))
    expect(await screen.findByText('不能单独证明 ZIP 属于当前请求。')).toBeInTheDocument()
  })

  it('第四幕读取源 Run、修复变化和三条正式非回归路径', async () => {
    const repaired = vulnerableIssue({ actual_result: '任务、消息、Worker 与 ZIP 均未形成', verdict: 'SAFE', diagnosis: null, claim_boundary: { ...vulnerableIssue().claim_boundary, business_effect_status: 'ABSENT', breakpoint_precision: null, repair_status: 'VERIFIED', supported_statement: 'Bob 的违规导出后果已经消失。' }, repair_requirement: { reference: { source_run_id: 'run-source', source_finding_id: 'finding-export', repair_fingerprint: 'c'.repeat(64) }, must_disappear: 'Bob 导出的任务、消息、Worker 与 ZIP', must_remain: 'Alice 的合法导出', must_not_change: ['Bob 的 DENY', '关键观察标准'] } })
    const current = presentation({ verdict: 'PASS', safe_count: 1, problem_count: 0, change_verification: { change_id: repairChangeId, required_intents: [] }, issues: [repaired], repair_verification: { reference: { source_run_id: 'run-source', source_finding_id: 'finding-export', repair_fingerprint: 'c'.repeat(64) }, verification_run_id: 'run-current', status: 'VERIFIED', message: '三条路径均已验证。', reason_codes: ['REPAIR_REQUIREMENTS_SATISFIED'], path_results: [
      { kind: 'DENY_EFFECT_REMOVAL', action_id: 'export-package', subject_id: 'bob', subject_display_name: 'Bob', action_display_name: '导出完整项目交付包', status: 'VERIFIED', message: '任务、消息、Worker 与 ZIP 均未形成。', evidence_refs: ['e-bob'], reason_codes: [] },
      { kind: 'ALLOW_CONTROL', action_id: 'export-package', subject_id: 'alice', subject_display_name: 'Alice', action_display_name: '导出完整项目交付包', status: 'VERIFIED', message: '合法导出仍然正常完成。', evidence_refs: ['e-alice'], reason_codes: [] },
      { kind: 'REGRESSION_CONTROL', action_id: 'view-collaboration', subject_id: 'bob', subject_display_name: 'Bob', action_display_name: '查看日常协作资料', status: 'VERIFIED', message: '日常协作资料仍可正常查看。', evidence_refs: ['e-view'], reason_codes: [] },
    ] } })
    mockApi.presentation.mockImplementation((runId: string) => Promise.resolve(runId === 'run-source' ? presentation({ run_id: 'run-source' }) : current))
    render(<PresentationMode experience={experience} projectName="协作空间" runs={[{ ...run, verdict: 'PASS' }]} onExit={vi.fn()} onOpenProductRoute={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /验证修复/ }))
    expect(await screen.findByText('三条路径分别核对')).toBeInTheDocument()
    const paths = document.querySelector('.presentation-repair-paths')
    expect(paths).not.toBeNull()
    expect(within(paths as HTMLElement).getAllByText('已验证')).toHaveLength(3)
    expect(screen.getByText('在创建导出任务前判断权限')).toBeInTheDocument()
  })

  it('没有正式 Run 时不拼接最近变化，退出仍回到工作台', async () => {
    const onExit = vi.fn()
    render(<PresentationMode experience={experience} projectName="协作空间" runs={[]} onExit={onExit} onOpenProductRoute={vi.fn()} />)
    expect(screen.getByText(/还没有形成可展示的正式问题 Run/)).toBeInTheDocument()
    expect(mockApi.sourceChange).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '返回工作台' }))
    expect(onExit).toHaveBeenCalledOnce()
    await waitFor(() => expect(mockApi.presentation).not.toHaveBeenCalled())
  })
})
