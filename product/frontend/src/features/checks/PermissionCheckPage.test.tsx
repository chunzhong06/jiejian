// 验证权限规则与验证运行共享事实、分离任务，并保留 Agent 变化门禁。

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PermissionCheckPage } from './PermissionCheckPage'

const api = vi.hoisted(() => ({
  matrix: vi.fn(), proposals: vi.fn(), approve: vi.fn(), approveProposal: vi.fn(), rejectProposal: vi.fn(),
  preview: vi.fn(), prepare: vi.fn(), submit: vi.fn(),
  run: vi.fn(), progress: vi.fn(), cancel: vi.fn(),
}))
vi.mock('../../api/permissionIntents', () => ({ permissionIntentsApi: { matrix: api.matrix, proposals: api.proposals, approve: api.approve, approveProposal: api.approveProposal, rejectProposal: api.rejectProposal } }))
vi.mock('../../api/checks', () => ({ checksApi: { preview: api.preview, prepare: api.prepare, submit: api.submit } }))
vi.mock('../../api/runs', () => ({ runsApi: { run: api.run, progress: api.progress, cancel: api.cancel } }))

const actionId = `action_${'1'.repeat(32)}`
const ownerRoleId = `role_${'2'.repeat(32)}`
const peerRoleId = `role_${'3'.repeat(32)}`
const matrix = {
  project_id: 'p1', policy_epoch: 2, confirmed_count: 2, review_required_count: 0, unconfirmed_count: 0, executable_count: 2, representative_gap_count: 0, compilable_action_count: 1,
  actions: [{
    action_candidate_id: actionId, action_display_name: '修改测试文档', resource_logical_name: '所有者的测试文档', gaps: [], required_intent_count: 2, confirmed_intent_count: 2, executable_intent_count: 2, representative_gap_count: 0, compilable: true,
    cells: [
      { action_candidate_id: actionId, subject_role_candidate_id: ownerRoleId, subject_role_display_name: '所有者', resource_owner_role_candidate_id: ownerRoleId, resource_owner_role_display_name: '所有者', relation: 'OWNS', expectation: 'ALLOW', protected_effects: [{ kind: 'STATE_MUTATION', resource_type: 'document', business_label: '测试文档内容', protected_fields: ['content'] }], status: 'CURRENT', review_reasons: [], intent_id: `pin_${'a'.repeat(32)}`, intent_revision: 1, intent_hash: 'a'.repeat(64), policy_epoch: 1, binding_fingerprint: 'c'.repeat(64), representative_test_identity_id: 'identity-owner', representative_label: '所有者账号', execution_gap: null },
      { action_candidate_id: actionId, subject_role_candidate_id: peerRoleId, subject_role_display_name: '普通成员', resource_owner_role_candidate_id: ownerRoleId, resource_owner_role_display_name: '所有者', relation: 'OTHER_ROLE', expectation: 'DENY', protected_effects: [{ kind: 'OBJECT_CREATION', resource_type: 'document', business_label: '测试文档', protected_fields: [] }], status: 'CURRENT', review_reasons: [], intent_id: `pin_${'b'.repeat(32)}`, intent_revision: 1, intent_hash: 'b'.repeat(64), policy_epoch: 2, binding_fingerprint: 'd'.repeat(64), representative_test_identity_id: 'identity-peer', representative_label: '普通成员账号', execution_gap: null },
    ],
  }],
}
const readyPreview = {
  project_id: 'p1', ready: true, gaps: [], next_path: null, next_label: null, case_count: 2, differential_pair_count: 1,
  actions: [{
    action_candidate_id: actionId, action_display_name: '修改测试文档', resource_logical_name: '所有者的测试文档', ready: true, gaps: [],
    checks: [
      { subject_label: '所有者账号', subject_role_display_name: '所有者', relation: 'OWNS', expectation: 'ALLOW', ready: true, gaps: [] },
      { subject_label: '普通成员账号', subject_role_display_name: '普通成员', relation: 'OTHER_ROLE', expectation: 'DENY', ready: true, gaps: [] },
    ],
  }],
}

function renderPage(overrides: Record<string, unknown> = {}) {
  const props = {
    mode: 'validation', project: { project_id: 'p1' }, runs: [], onRefresh: vi.fn(), onError: vi.fn(), onResolved: vi.fn(), onNavigate: vi.fn(), onBack: vi.fn(), onNext: vi.fn(),
    ...overrides,
  }
  render(<PermissionCheckPage {...props as any} />)
  return props
}

describe('PermissionCheckPage', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    vi.clearAllMocks()
    api.matrix.mockResolvedValue(matrix)
    api.proposals.mockResolvedValue({ project_id: 'p1', proposals: [] })
    api.preview.mockResolvedValue(readyPreview)
    api.approve.mockResolvedValue(matrix)
    api.approveProposal.mockResolvedValue({})
    api.rejectProposal.mockResolvedValue({})
    api.prepare.mockResolvedValue(readyPreview)
    api.submit.mockResolvedValue({ schema_version: '1', run: { run_id: 'run-new', lifecycle: 'QUEUED', job: { job_id: 'job-new', state: 'QUEUED' } }, job: { job_id: 'job-new', state: 'QUEUED' } })
    api.run.mockResolvedValue({ run_id: 'run-current', lifecycle: 'RUNNING', job: { job_id: 'job-current', state: 'RUNNING' } })
    api.progress.mockResolvedValue({ job_id: 'job-current', attempt: 1, events: [] })
    api.cancel.mockResolvedValue({})
  })

  it('验证运行只展示准备、预览、进度和结果入口', async () => {
    renderPage()

    for (const label of ['准备检查条件', '核对本次检查', '开始检查并查看进度']) expect((await screen.findAllByText(label)).length).toBeGreaterThan(0)
    expect(screen.queryByText('确认权限要求')).not.toBeInTheDocument()
    expect(screen.queryByRole('list', { name: '权限与检查进度' })).not.toBeInTheDocument()
    expect(screen.getAllByText('修改测试文档').length).toBeGreaterThan(0)
    expect(screen.getAllByText('所有者账号').length).toBeGreaterThan(0)
    expect(screen.getAllByText('普通成员账号').length).toBeGreaterThan(0)
    expect(screen.getByText('应该允许')).toBeInTheDocument()
    expect(screen.getByText('应该拒绝')).toBeInTheDocument()
    expect(screen.getByText('合法对照')).toBeInTheDocument()
    expect(screen.getByText('禁止实验')).toBeInTheDocument()
    expect(screen.getByText('真实业务后果')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始真实检查' })).toBeEnabled()
    expect(screen.queryByText(/Profile|Contract|Observer|profile_id|contract_id/)).not.toBeInTheDocument()
  })

  it('权限规则只展示人确认与 Agent 建议，不混入运行按钮', async () => {
    renderPage({ mode: 'permissions' })
    expect(await screen.findByText('确认权限要求')).toBeInTheDocument()
    expect(screen.queryByText('准备检查条件')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '开始真实检查' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '继续测试准备' })).toBeInTheDocument()
  })

  it('原考题复验沿用普通 preview 和 submit，并传入服务端形成的 change_id', async () => {
    const changeId = `chg_${'9'.repeat(32)}`
    renderPage({ changeId })

    expect(await screen.findByRole('button', { name: '开始真实检查' })).toBeEnabled()
    expect(api.preview).toHaveBeenCalledWith('p1', changeId)
    fireEvent.click(screen.getByRole('button', { name: '开始真实检查' }))
    await waitFor(() => expect(api.submit).toHaveBeenCalledWith('p1', changeId))
  })

  it('点击 Segmented 只打开确认 Modal，确认后才保存并使旧 preview 失效', async () => {
    renderPage({ mode: 'permissions' })

    const ownerPermission = await screen.findByLabelText('所有者权限组以自己的资源关系对修改测试文档的权限')
    fireEvent.click(within(ownerPermission).getByText('拒绝'))

    expect(api.approve).not.toHaveBeenCalled()
    expect(screen.getByText('当前要求：允许')).toBeInTheDocument()
    expect(screen.getByText('准备变成：拒绝')).toBeInTheDocument()
    expect(screen.getByText('受保护业务后果：')).toBeInTheDocument()
    expect(screen.getAllByText('测试文档内容').length).toBeGreaterThan(0)
    expect(screen.getByText('确认后将从版本 2 推进到 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确认权限变更' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '暂不变更' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '暂不变更' }))
    expect(api.approve).not.toHaveBeenCalled()

    fireEvent.click(within(ownerPermission).getByText('拒绝'))
    fireEvent.click(screen.getByRole('button', { name: '确认权限变更' }))
    await waitFor(() => expect(api.approve).toHaveBeenCalledWith('p1', {
      action_candidate_id: actionId,
      subject_role_candidate_id: ownerRoleId,
      resource_owner_role_candidate_id: ownerRoleId,
      relation: 'OWNS',
    }, 'DENY'))
    expect(api.submit).not.toHaveBeenCalled()
    expect(api.prepare).not.toHaveBeenCalled()
  })

  it('权限要求保存完成前不能进入测试准备', async () => {
    let finishSave!: (value: unknown) => void
    api.approve.mockReturnValue(new Promise((resolve) => { finishSave = resolve }))
    renderPage({ mode: 'permissions' })

    const ownerPermission = await screen.findByLabelText('所有者权限组以自己的资源关系对修改测试文档的权限')
    fireEvent.click(within(ownerPermission).getByText('拒绝'))
    fireEvent.click(screen.getByRole('button', { name: '确认权限变更' }))

    expect(await screen.findByRole('button', { name: '正在保存权限要求' })).toBeDisabled()
    finishSave(matrix)
    expect(await screen.findByRole('button', { name: '继续测试准备' })).toBeEnabled()
  })

  it('同一期望值复核只提示重新确认映射，Proposal 批准和拒绝按权威事实刷新', async () => {
    const reviewMatrix = { ...matrix, review_required_count: 1, unconfirmed_count: 0, actions: [{ ...matrix.actions[0], cells: [{ ...matrix.actions[0].cells[0], status: 'NEEDS_REVIEW' as const }, matrix.actions[0].cells[1]] }] }
    const proposals = [{ proposal_id: 'proposal-semantic', project_id: 'p1', kind: 'SEMANTIC_CHANGE' as const, status: 'PENDING' as const, intent_id: matrix.actions[0].cells[0].intent_id, semantic_change: { effective_state: 'RETIRED' as const, subject_display_name: '所有者', action_display_name: '修改测试文档', resource_owner_display_name: '所有者', relation: 'OWNS' as const, expectation: 'ALLOW' as const, protected_effects: matrix.actions[0].cells[0].protected_effects }, implementation_rebind: null, proposed_by: 'Agent', reason: '建议收紧权限', created_at_us: 1, decided_at_us: null }, { proposal_id: 'proposal-rebind', project_id: 'p1', kind: 'IMPLEMENTATION_REBIND' as const, status: 'PENDING' as const, intent_id: matrix.actions[0].cells[0].intent_id, semantic_change: null, implementation_rebind: { action_candidate_id: actionId, subject_role_candidate_id: ownerRoleId, resource_owner_role_candidate_id: ownerRoleId, understanding_revision: 2, action_safety_setup_fingerprint: 'f'.repeat(64) }, proposed_by: 'Agent', reason: '实现映射需要复核', created_at_us: 2, decided_at_us: null }]
    api.matrix.mockResolvedValue(reviewMatrix)
    api.proposals.mockResolvedValue({ project_id: 'p1', proposals })
    renderPage({ mode: 'permissions' })
    expect(await screen.findByText('Agent 建议等待确认')).toBeInTheDocument()
    expect(screen.getAllByText('当前值')).toHaveLength(2)
    expect(screen.getAllByText('Agent 建议')).toHaveLength(2)
    expect(screen.getByText('建议收紧权限')).toBeInTheDocument()
    expect(screen.getByText('退役为未确认')).toBeInTheDocument()
    expect(screen.getByText('实现映射待复核')).toBeInTheDocument()
    expect(screen.getByText('重新确认当前实现映射')).toBeInTheDocument()
    expect(screen.getByText(/权限版本 1/)).toBeInTheDocument()
    expect(screen.getAllByText(/修订 1/)).toHaveLength(2)
    expect(screen.getByText(/实现映射可用/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '重新确认当前要求' }))
    expect(screen.getByText('当前要求：允许')).toBeInTheDocument()
    expect(screen.getByText('准备变成：允许')).toBeInTheDocument()
    expect(screen.getByText('权限语义不变，不推进版本；仅重新确认当前实现映射')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '暂不变更' }))

    const approveButtons = screen.getAllByRole('button', { name: /批\s*准/ })
    fireEvent.click(approveButtons[0])
    await waitFor(() => expect(api.approveProposal).toHaveBeenCalledWith('p1', 'proposal-semantic'))
    fireEvent.click(screen.getAllByRole('button', { name: /拒\s*绝/ })[1])
    await waitFor(() => expect(api.rejectProposal).toHaveBeenCalledWith('p1', 'proposal-rebind'))
  })

  it('只根据后端缺口在观察恢复与检查预览之间选择一个 AssistantPanel', async () => {
    api.matrix.mockResolvedValue({ ...matrix, actions: [{ ...matrix.actions[0], gaps: ['OBSERVATION_UNCONFIRMED'] }] })
    renderPage()
    expect(await screen.findByText('观察与恢复说明')).toBeInTheDocument()
    expect(screen.queryByText('权限要求复核')).not.toBeInTheDocument()
    expect(screen.queryByText('本次检查范围')).not.toBeInTheDocument()

    cleanup()
    api.matrix.mockResolvedValue(matrix)
    renderPage()
    expect(await screen.findByText('本次检查范围')).toBeInTheDocument()
    expect(screen.queryByText('权限要求复核')).not.toBeInTheDocument()
    expect(screen.queryByText('观察与恢复说明')).not.toBeInTheDocument()
  })

  it('只读刷新不会确认权限、准备、提交或取消检查', async () => {
    renderPage()
    expect(await screen.findByRole('button', { name: /刷新当前状态/ })).toBeInTheDocument()
    vi.clearAllMocks()
    api.matrix.mockResolvedValue(matrix)
    api.proposals.mockResolvedValue({ project_id: 'p1', proposals: [] })
    api.preview.mockResolvedValue(readyPreview)

    fireEvent.click(screen.getByRole('button', { name: /刷新当前状态/ }))

    await waitFor(() => expect(api.matrix).toHaveBeenCalledOnce())
    expect(api.proposals).toHaveBeenCalledOnce()
    expect(api.preview).toHaveBeenCalledOnce()
    expect(api.approve).not.toHaveBeenCalled()
    expect(api.prepare).not.toHaveBeenCalled()
    expect(api.submit).not.toHaveBeenCalled()
    expect(api.cancel).not.toHaveBeenCalled()
  })

  it('当前范围可编译且检查配置缺失时先准备，不被其他未确认关系送回权限页', async () => {
    const onNavigate = vi.fn()
    api.preview.mockResolvedValue({
      ...readyPreview,
      ready: false,
      gaps: [
        { code: 'PERMISSION_INTENT_UNCONFIRMED', message: '还有非代表关系未确认', next_path: '/permissions', next_label: '去确认权限规则' },
        { code: 'GENERATED_PROFILE_MISSING', message: '尚未生成当前检查配置', next_path: '/validation', next_label: '去准备本次检查' },
      ],
      next_path: '/permissions',
      next_label: '去确认权限规则',
    })
    renderPage({ onNavigate })

    fireEvent.click(await screen.findByRole('button', { name: '准备本次检查' }))
    await waitFor(() => expect(api.prepare).toHaveBeenCalledWith('p1', undefined))
    expect(await screen.findByText('检查条件已经重新确认')).toBeInTheDocument()
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('活动检查只能通过带后果说明的底部动作取消', async () => {
    const activeRun = { run_id: 'run-current', lifecycle: 'RUNNING', job: { job_id: 'job-current', state: 'RUNNING' } }
    renderPage({ runs: [activeRun] })

    fireEvent.click(await screen.findByRole('button', { name: '取消当前检查' }))
    expect(await screen.findByText('界鉴会请求后台停止尚未完成的检查，并保留已经形成的运行记录；取消不会产生安全结论。')).toBeInTheDocument()
    expect(api.cancel).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '确认取消' }))
    await waitFor(() => expect(api.cancel).toHaveBeenCalledWith('job-current'))
  })

  it('可信终态提供查看结果主动作，并保留明确的新检查入口', async () => {
    const completed = { run_id: 'run-completed', lifecycle: 'COMPLETED', result_integrity: 'VERIFIED', verdict: 'BLOCK', job: { job_id: 'job-completed', state: 'SUCCEEDED' } }
    api.run.mockResolvedValue(completed)
    const props = renderPage({ runs: [completed] })

    fireEvent.click(await screen.findByRole('button', { name: '查看检查结果' }))
    expect(props.onNext).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: '重新检查当前范围' }))
    expect(await screen.findByText('界鉴会创建一次新的受控检查；已经发布的结果和历史记录不会被覆盖。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '开始新检查' }))
    await waitFor(() => expect(api.submit).toHaveBeenCalledWith('p1'))
  })
})
