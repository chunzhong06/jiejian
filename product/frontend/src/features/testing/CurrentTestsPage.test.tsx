// 验证当前检查的显式提交、竞态隔离、服务端结论与两次点击内的证据访问。
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CheckObservation, CheckOutcome, CheckStatus, ResultStory } from '../../api/currentChecks'
import { CurrentTestsPage } from './CurrentTestsPage'
const api = vi.hoisted(() => ({ preview: vi.fn(), list: vi.fn(), status: vi.fn(), submit: vi.fn(), story: vi.fn(), evidence: vi.fn() }))
vi.mock('../../api/currentChecks', () => ({ currentChecksApi: api }))
vi.mock('../../components/AssistantPanel', () => ({ AssistantPanel: ({ runId }: { runId: string }) => <div>受限结果解释 {runId}</div> }))
vi.mock('../preparation/PreparationPage', () => ({ PreparationPage: ({ onNavigate }: { onNavigate: (path: string) => void }) => <button onClick={() => onNavigate('/tests')}>完成材料准备</button> }))
const ready = { project_id: 'p1', can_execute: true, plan_fingerprint: 'f'.repeat(64), action_count: 1, case_count: 2, actions: [], gaps: [] }
const status = (patch: Partial<CheckStatus> = {}): CheckStatus => ({ run: { run_id: 'r1', project_id: 'p1', lifecycle: 'COMPLETED', verdict: 'BLOCK', plan_fingerprint: ready.plan_fingerprint, policy_epoch: 3, created_at_us: 1780000000000000, finished_at_us: 1780000001000000 }, job: null, progress: null, result_integrity: 'VALID', ...patch })
const observation: CheckObservation = { effect_id: 'e1', proof_fingerprint: 'proof', observer_id: 'source', level: 'VERDICT_REQUIRED', phase: 'AFTER', state: 'CONFIRMED', closure: 'CLOSED', complete: true, reliable: true, correlated: true, authoritative: true, window_start_us: 100, window_end_us: 200, correlation_refs: [], reason_codes: [] }
const source = { source_label: '资源状态', source_location: '/projects/export', observed_fact: observation, supports_claim: '交付包已经生成', does_not_prove: '不能单独证明接口权限检查正确', evidence_refs: ['ev1'] }
const outcome: CheckOutcome = { execution_outcome: 'DENIED', http_status: 403, actual_identity_status: 'UNKNOWN', baseline_trusted: true, recovery_verified: true, run_correlated: true, resource_correlated: true }
const story = (): ResultStory => ({ run_id: 'r1', project_id: 'p1', verdict: 'BLOCK', judgement: '确认禁止的交付包已经生成', policy_epoch: 3, claim_boundary: ['仅覆盖本次规则'], technical_references: [], actions: [{
  action_id: 'a1', action_revision: 1, display_name: '导出资料', case_id: 'c1', permission: { expectation: 'DENY', relation: 'OTHER_ROLE' }, judgement: '本项已确认越权后果',
  fact_comparison: { planned_identity: { identity_id: 'i1', actor_id: 'actor1', label: '计划成员', actor_label: '成员', verification_status: 'PLANNED', namespace: null, application_subject_id: null }, verified_actual_identity: { identity_id: null, actor_id: null, actor_label: null, label: null, verification_status: 'UNKNOWN', namespace: null, application_subject_id: null }, http_surface: outcome, http_explanation: '业务请求被明确拒绝', effects: [{ effect_id: 'e1', business_label: '完整交付包', resource_concept: '项目', observed_state: 'CONFIRMED', judgement: '业务交付包已确认生成', evidence_refs: ['ev1'] }], allow_control: { case_id: 'c2', verdict: 'SAFE', evidence_refs: ['ev2'] } },
  breakpoint: { breakpoint_type: 'AUTHORIZATION_LATE', precision: 'VIOLATION_ONLY', first_violation_event_id: null, range_start_event_id: null, range_end_event_id: null, evidence_refs: ['ev1'] },
  decisive_proof_chain: [source], evidence_explanations: [source], claim_boundary: [], repair_requirement: null, technical_references: [],
}] })
const props = () => ({ project: { project_id: 'p1' }, workspace: null, onStateChanged: vi.fn(), onError: vi.fn(), onNavigate: vi.fn() })
beforeEach(() => {
  vi.clearAllMocks(); api.preview.mockResolvedValue(ready); api.list.mockResolvedValue([]); api.status.mockResolvedValue(status())
  api.submit.mockResolvedValue({ run: status().run, job: null }); api.story.mockResolvedValue(story())
  api.evidence.mockResolvedValue({ schema_version: '1', evidence_id: 'ev1', run_id: 'r1', action_id: 'a1', case: { case_id: 'c1', resource_id: '项目一' }, outcome, observations: [observation], trace: null })
})
afterEach(cleanup)
describe('当前检查工作区', () => {
  it('变化深链只携带精确change_id，仍提交完整服务端计划', async () => {
    render(<CurrentTestsPage {...props()} changeId="chg_exact" />)
    const button = await screen.findByRole('button', { name: '开始检查' })
    expect(api.preview).toHaveBeenCalledWith('p1', 'chg_exact')
    fireEvent.click(button)
    await waitFor(() => expect(api.submit).toHaveBeenCalledOnce())
    expect(api.submit.mock.calls[0][3]).toBe('chg_exact')
    expect(api.submit.mock.calls[0][1]).toBe(ready.plan_fingerprint)
  })
  it('精确Run深链只读取指定结果，不新建检查', async () => {
    render(<CurrentTestsPage {...props()} requestedRunId="r1" />)
    expect(await screen.findByText('确认禁止的交付包已经生成')).toBeInTheDocument()
    expect(api.status).toHaveBeenCalledWith('r1')
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('读取预览和历史不创建检查，准备入口可以自由往返', async () => {
    render(<CurrentTestsPage {...props()} />)
    expect(await screen.findByRole('button', { name: '开始检查' })).toBeEnabled()
    expect(api.submit).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '管理准备材料' }))
    fireEvent.click(screen.getByRole('button', { name: '完成材料准备' }))
    expect(await screen.findByRole('heading', { name: '检查与结果' })).toBeInTheDocument()
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('服务端不允许时材料齐备也不能提交', async () => {
    api.preview.mockResolvedValue({ ...ready, can_execute: false })
    render(<CurrentTestsPage {...props()} />)
    expect(await screen.findByRole('button', { name: '准备检查材料' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '开始检查' })).not.toBeInTheDocument()
  })
  it('显式提交前范围漂移时先展示最新预览，不执行旧计划', async () => {
    const p = props(); render(<CurrentTestsPage {...p} />)
    const button = await screen.findByRole('button', { name: '开始检查' })
    api.preview.mockResolvedValue({ ...ready, plan_fingerprint: 'new-plan' })
    fireEvent.click(button)
    await waitFor(() => expect(p.onError).toHaveBeenCalled())
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('未知提交回执重用原幂等键，快速重复点击只提交一次', async () => {
    const p = props(); api.submit.mockRejectedValueOnce(new Error('connection lost'))
    render(<CurrentTestsPage {...p} />)
    const button = await screen.findByRole('button', { name: '开始检查' })
    fireEvent.click(button); fireEvent.click(button)
    await waitFor(() => expect(p.onError).toHaveBeenCalled())
    expect(api.submit).toHaveBeenCalledTimes(1)
    fireEvent.click(await screen.findByRole('button', { name: '确认上次提交' }))
    await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(2))
    expect(api.submit.mock.calls[0]).toEqual(api.submit.mock.calls[1])
    expect(await screen.findByText('确认禁止的交付包已经生成')).toBeInTheDocument()
  })
  it('403和实际身份未知不被前端改成安全，决定性证据可直接打开', async () => {
    api.list.mockResolvedValue([status()]); render(<CurrentTestsPage {...props()} />)
    fireEvent.click(await screen.findByRole('button', { name: '查看结果' }))
    expect(await screen.findByText('确认禁止的交付包已经生成')).toBeInTheDocument()
    expect(screen.getByText(/HTTP 403/)).toBeInTheDocument()
    expect(screen.getByText('无法独立确认')).toBeInTheDocument()
    const evidenceButtons = screen.getAllByRole('button', { name: '查看资源状态证据' })
    fireEvent.click(evidenceButtons[0])
    const drawer = await screen.findByRole('dialog')
    expect(await within(drawer).findByText('在哪里看到')).toBeInTheDocument()
    expect(within(drawer).getByText('不能单独证明接口权限检查正确')).toBeInTheDocument()
    expect(api.evidence).toHaveBeenCalledWith('r1', 'ev1')
  })
  it('完整性失效时不读取故事或展示旧结论', async () => {
    api.list.mockResolvedValue([status()]); api.status.mockResolvedValue(status({ result_integrity: 'INVALID' }))
    render(<CurrentTestsPage {...props()} />)
    fireEvent.click(await screen.findByRole('button', { name: '查看结果' }))
    expect(await screen.findByText('结果完整性校验失败，不能展示安全结论')).toBeInTheDocument()
    expect(api.story).not.toHaveBeenCalled()
    expect(screen.queryByText('确认禁止的交付包已经生成')).not.toBeInTheDocument()
  })
  it('证据完整性读取失败撤下整轮故事', async () => {
    api.list.mockResolvedValue([status()]); api.evidence.mockRejectedValue(new Error('invalid evidence'))
    render(<CurrentTestsPage {...props()} />)
    fireEvent.click(await screen.findByRole('button', { name: '查看结果' }))
    fireEvent.click((await screen.findAllByRole('button', { name: '查看资源状态证据' }))[0])
    expect(await screen.findByText('暂时无法读取本次检查')).toBeInTheDocument()
    expect(screen.queryByText('确认禁止的交付包已经生成')).not.toBeInTheDocument()
  })
  it('活动检查只恢复进度，手动刷新后读取正式结果', async () => {
    const running = status({ run: { ...status().run, lifecycle: 'RUNNING', verdict: null }, result_integrity: 'NOT_PUBLISHED', progress: { phase: 'EXECUTING', completed_cases: 1, planned_cases: 2 } })
    api.list.mockResolvedValue([running]); api.status.mockResolvedValue(running)
    render(<CurrentTestsPage {...props()} />)
    fireEvent.click(await screen.findByRole('button', { name: '查看当前进度' }))
    expect(await screen.findByRole('status')).toHaveTextContent('已处理 1 / 2')
    expect(api.story).not.toHaveBeenCalled(); expect(api.submit).not.toHaveBeenCalled()
    api.status.mockResolvedValue(status())
    fireEvent.click(screen.getByRole('button', { name: '刷新检查结果' }))
    expect(await screen.findByText('确认禁止的交付包已经生成')).toBeInTheDocument()
  })
  it('切换项目后忽略前一项目延迟的故事', async () => {
    let resolveStory!: (value: ResultStory) => void
    api.list.mockResolvedValue([status()]); api.story.mockImplementationOnce(() => new Promise((resolve) => { resolveStory = resolve }))
    const p = props(); const view = render(<CurrentTestsPage {...p} />)
    fireEvent.click(await screen.findByRole('button', { name: '查看结果' }))
    await waitFor(() => expect(api.story).toHaveBeenCalled())
    api.preview.mockResolvedValue({ ...ready, project_id: 'p2' }); api.list.mockResolvedValue([])
    view.rerender(<CurrentTestsPage {...p} project={{ project_id: 'p2' }} />)
    resolveStory(story())
    await waitFor(() => expect(api.preview).toHaveBeenCalledWith('p2', undefined))
    expect(screen.queryByText('确认禁止的交付包已经生成')).not.toBeInTheDocument()
  })
})
