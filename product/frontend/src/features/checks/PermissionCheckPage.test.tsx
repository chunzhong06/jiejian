// 验证唯一权限与检查页的连续状态、preview 失效门禁和统一副作用动作。

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PermissionCheckPage } from './PermissionCheckPage'

const api = vi.hoisted(() => ({
  matrix: vi.fn(), confirm: vi.fn(), compile: vi.fn(),
  preview: vi.fn(), submit: vi.fn(),
  run: vi.fn(), progress: vi.fn(), cancel: vi.fn(),
}))
vi.mock('../../api/permissionIntents', () => ({ permissionIntentsApi: { matrix: api.matrix, confirm: api.confirm, compile: api.compile } }))
vi.mock('../../api/checks', () => ({ checksApi: { preview: api.preview, submit: api.submit } }))
vi.mock('../../api/runs', () => ({ runsApi: { run: api.run, progress: api.progress, cancel: api.cancel } }))
vi.mock('../permissions/PermissionAdvancedPanel', () => ({ PermissionAdvancedPanel: () => <div>高级权限工具</div> }))

const actionId = `action_${'1'.repeat(32)}`
const ownerRoleId = `role_${'2'.repeat(32)}`
const peerRoleId = `role_${'3'.repeat(32)}`
const matrix = {
  project_id: 'p1', confirmed_count: 2, review_required_count: 0, unconfirmed_count: 0, executable_count: 2, representative_gap_count: 0, compilable_action_count: 1,
  actions: [{
    action_candidate_id: actionId, action_display_name: '修改测试文档', resource_logical_name: '所有者的测试文档', gaps: [], required_intent_count: 2, confirmed_intent_count: 2, executable_intent_count: 2, representative_gap_count: 0, compilable: true,
    cells: [
      { action_candidate_id: actionId, subject_role_candidate_id: ownerRoleId, subject_role_display_name: '所有者', resource_owner_role_candidate_id: ownerRoleId, resource_owner_role_display_name: '所有者', relation: 'OWNS', expectation: 'ALLOW', status: 'CURRENT', review_reasons: [], intent_fingerprint: 'a'.repeat(64), representative_test_identity_id: 'identity-owner', representative_label: '所有者账号', execution_gap: null },
      { action_candidate_id: actionId, subject_role_candidate_id: peerRoleId, subject_role_display_name: '普通成员', resource_owner_role_candidate_id: ownerRoleId, resource_owner_role_display_name: '所有者', relation: 'OTHER_ROLE', expectation: 'DENY', status: 'CURRENT', review_reasons: [], intent_fingerprint: 'b'.repeat(64), representative_test_identity_id: 'identity-peer', representative_label: '普通成员账号', execution_gap: null },
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
    project: { project_id: 'p1' }, runs: [], onRefresh: vi.fn(), onError: vi.fn(), onResolved: vi.fn(), onNavigate: vi.fn(), onBack: vi.fn(), onNext: vi.fn(),
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
    api.preview.mockResolvedValue(readyPreview)
    api.confirm.mockResolvedValue(matrix)
    api.compile.mockResolvedValue({ project_id: 'p1', covered_action_ids: [actionId], reused: false })
    api.submit.mockResolvedValue({ schema_version: '1', run: { run_id: 'run-new', lifecycle: 'QUEUED', job: { job_id: 'job-new', state: 'QUEUED' } }, job: { job_id: 'job-new', state: 'QUEUED' } })
    api.run.mockResolvedValue({ run_id: 'run-current', lifecycle: 'RUNNING', job: { job_id: 'job-current', state: 'RUNNING' } })
    api.progress.mockResolvedValue({ job_id: 'job-current', attempt: 1, events: [] })
    api.cancel.mockResolvedValue({})
  })

  it('用一条自然流程展示权限要求、准备、预览、进度和结果入口', async () => {
    renderPage()

    for (const label of ['确认权限要求', '准备检查条件', '核对本次范围', '开始检查', '查看当前进度', '完成并查看结果']) expect((await screen.findAllByText(label)).length).toBeGreaterThan(0)
    expect(screen.getAllByText('修改测试文档')).toHaveLength(2)
    expect(screen.getByText('所有者账号')).toBeInTheDocument()
    expect(screen.getByText('普通成员账号')).toBeInTheDocument()
    expect(screen.getByText('应该允许')).toBeInTheDocument()
    expect(screen.getByText('应该拒绝')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始检查' })).toBeEnabled()
    expect(screen.queryByText(/Profile|Contract|Observer|profile_id|contract_id/)).not.toBeInTheDocument()
  })

  it('权限修改后拒绝旧 preview，直到 compile 完成并取得新 preview 才允许提交', async () => {
    let resolveConfirm: (value: typeof matrix) => void = () => undefined
    let resolvePreview: (value: typeof readyPreview) => void = () => undefined
    const newPreview = { ...readyPreview, case_count: 3 }
    api.confirm.mockImplementationOnce(() => new Promise((resolve) => { resolveConfirm = resolve }))
    api.preview.mockResolvedValueOnce(readyPreview).mockImplementationOnce(() => new Promise((resolve) => { resolvePreview = resolve }))
    renderPage()

    expect(await screen.findByRole('button', { name: '开始检查' })).toBeEnabled()
    const ownerPermission = screen.getByLabelText('所有者权限组以自己的资源关系对修改测试文档的权限')
    fireEvent.click(within(ownerPermission).getByText('拒绝'))

    await waitFor(() => expect(api.confirm).toHaveBeenCalledOnce())
    expect(screen.queryByRole('button', { name: '开始检查' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /正在保存权限要求/ })).toBeDisabled()
    expect(screen.getByText('权限要求已经更新，旧检查预览已失效')).toBeInTheDocument()
    expect(api.submit).not.toHaveBeenCalled()

    resolveConfirm(matrix)
    fireEvent.click(await screen.findByRole('button', { name: '准备本次检查' }))
    await waitFor(() => expect(api.compile).toHaveBeenCalledWith('p1', 'local-user'))
    expect(api.preview).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('button', { name: '开始检查' })).not.toBeInTheDocument()
    expect(api.submit).not.toHaveBeenCalled()

    resolvePreview(newPreview)
    fireEvent.click(await screen.findByRole('button', { name: '开始检查' }))
    await waitFor(() => expect(api.submit).toHaveBeenCalledWith('p1'))
  })

  it('只读刷新不会确认权限、编译、提交或取消检查', async () => {
    renderPage()
    expect(await screen.findByRole('button', { name: /刷新当前状态/ })).toBeInTheDocument()
    vi.clearAllMocks()
    api.matrix.mockResolvedValue(matrix)
    api.preview.mockResolvedValue(readyPreview)

    fireEvent.click(screen.getByRole('button', { name: /刷新当前状态/ }))

    await waitFor(() => expect(api.matrix).toHaveBeenCalledOnce())
    expect(api.preview).toHaveBeenCalledOnce()
    expect(api.confirm).not.toHaveBeenCalled()
    expect(api.compile).not.toHaveBeenCalled()
    expect(api.submit).not.toHaveBeenCalled()
    expect(api.cancel).not.toHaveBeenCalled()
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
