// 动作准备页验证：服务端唯一主任务、真实身份槽位、写后刷新与失效响应隔离。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PreparationView } from '../../api/preparation'
import type { PrimaryTaskDto, WorkspaceViewDto } from '../../api/workspace'
import { PreparationPage } from './PreparationPage'
const api = vi.hoisted(() => ({ get: vi.fn(), create: vi.fn(), start: vi.fn(), select: vi.fn() }))
vi.mock('../../api/preparation', () => ({ preparationApi: { get: api.get, selectAllowControl: api.select } }))
vi.mock('../../api/testIdentities', () => ({ testIdentitiesApi: { create: api.create, startPreparation: api.start } }))
vi.mock('../../components/AssistantPanel', () => ({ AssistantPanel: () => null }))
vi.mock('../identities/TestIdentityPage', () => ({ TestIdentityPage: () => <div>登录准备页面</div> }))
vi.mock('../recording/RecordingPage', () => ({ RecordingPage: ({ task, effectName }: { task: PrimaryTaskDto; effectName?: string }) => <div>录制任务 {task.recording_id ?? task.test_identity_id} {effectName}</div> }))
const task = (patch: Partial<PrimaryTaskDto> = {}): PrimaryTaskDto => ({ task_id: 't1', task_kind: 'PREPARE_TEST_IDENTITY', business_action_id: 'a1', business_actor_id: 'u1', title: '准备成员账号', why_now: '需要两个独立账号', user_responsibility: '请使用真实账号登录', system_will_do: '保存登录状态', route: '/tests', can_execute: true, stale_fingerprint: 'current', action_revision: 2, identity_slot_id: 'slot2', test_identity_id: null, ...patch })
const workspace = (primary: PrimaryTaskDto | null): WorkspaceViewDto => ({ project: { project_id: 'p1', name: '项目', status: 'READY', target_type: 'WEB' }, connection: { endpoint_status: 'CONFIRMED', source_analysis_status: 'COMPLETED' }, actors: [], actions: [], areas: [], primary_task: primary })
const material = (patch: Partial<PreparationView> = {}): PreparationView => ({ project_id: 'p1', preparation_complete: false, actions: [{ action_id: 'a1', action_revision: 2, display_name: '导出交付包', preparation_complete: false,
  permissions: [], assurance_contract: { allow_controls: [] },
  identity_requirements: { status: 'NEEDS_USER', reason_codes: [], allocation_mode: 'EXACT', slots: [1, 2].map((ordinal) => ({ requirement: { slot_id: `slot${ordinal}`, actor_id: 'u1', actor_revision: 3, ordinal }, actor_display_name: '普通成员', test_identity_id: null, status: 'NEEDS_USER', reason_codes: [] })) },
  execution: { status: 'SATISFIED', reason_codes: [] }, resources: [], effect_evidence: [{ effect_id: 'e1', status: 'STALE', reason_codes: [] }], recovery: { status: 'NOT_REQUIRED', reason_codes: [] }, reason_codes: [],
}], ...patch })
const props = (current = workspace(task())) => ({ project: { project_id: 'p1' }, workspace: current, onStateChanged: vi.fn().mockResolvedValue(current), onError: vi.fn(), onNavigate: vi.fn() })
beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue(material()); api.create.mockResolvedValue({ identity_id: 'identity2' }); api.start.mockResolvedValue({ preparation_id: 'login2' }) })
function selectionMaterial() {
  const value = material()
  const reference = (id: string) => ({ intent_id: id, revision: 1, intent_hash: `${id}-hash` })
  value.actions[0].permissions = ['deny', 'allow-one', 'allow-two'].map((id) => ({ ...reference(id),
    subject_actor_id: id, subject_actor_revision: 1, business_action_id: 'a1', action_revision: 2,
    resource_owner_actor_id: 'u1', resource_owner_actor_revision: 1, relation: 'OTHER_ROLE',
    expectation: id === 'deny' ? 'DENY' : 'ALLOW', protected_effect_ids: ['e1'], effective_state: 'ACTIVE',
  }))
  value.actions[0].assurance_contract.allow_controls = [{ deny_permission: reference('deny'),
    candidate_allow_permissions: [reference('allow-one'), reference('allow-two')], protected_effect_ids: ['e1'],
    resolved_allow_permission: null, selection_fingerprint: 'current-candidate-set',
  }]
  return value
}
describe('动作准备', () => {
  it('显示实际两个账号需求、静态材料与失效证明，不在加载时写入', async () => {
    render(<PreparationPage {...props()} />)
    expect(await screen.findByText('普通成员账号 1')).toBeInTheDocument()
    expect(screen.getByText('普通成员账号 2')).toBeInTheDocument()
    expect(screen.getByText('需要更新')).toBeInTheDocument()
    expect(screen.getByText('只读动作不需要恢复')).toBeInTheDocument()
    expect(api.create).not.toHaveBeenCalled(); expect(api.start).not.toHaveBeenCalled()
    expect(screen.queryByText(/Alice|Bob|slot2|最多支持/)).not.toBeInTheDocument()
  })
  it('外部主任务优先，页面材料不自行选取下一项', async () => {
    const p = props(workspace(task({ task_kind: 'COMPLETE_ALLOW_CONTROL', route: '/permissions' })))
    render(<PreparationPage {...p} />)
    fireEvent.click(await screen.findByRole('button', { name: '前往处理' }))
    await waitFor(() => expect(p.onNavigate).toHaveBeenCalledWith('/permissions'))
    expect(api.create).not.toHaveBeenCalled()
  })
  it('BLOCKED 任务没有写入入口', async () => {
    render(<PreparationPage {...props(workspace(task({ can_execute: false })))} />)
    expect(await screen.findByRole('button', { name: '创建账号并登录' })).toBeDisabled()
    expect(api.start).not.toHaveBeenCalled()
  })
  it('材料全部齐备也不提供 Run 或验证运行入口', async () => {
    api.get.mockResolvedValue(material({ preparation_complete: true }))
    render(<PreparationPage {...props(workspace(null))} />)
    expect(await screen.findByText('测试材料已准备完成，请返回检查总览核对执行条件。')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /开始检查|验证运行|继续准备这项材料/ })).not.toBeInTheDocument()
  })
  it('创建指定 slot 账号后先刷新材料和 Workspace，才打开登录', async () => {
    const order: string[] = []
    api.get.mockImplementation(async () => { order.push('materials'); return material() })
    api.create.mockImplementation(async () => { order.push('create'); return { identity_id: 'identity2' } })
    api.start.mockImplementation(async () => { order.push('login'); return { preparation_id: 'login2' } })
    const p = props()
    p.onStateChanged.mockImplementationOnce(async () => { order.push('workspace'); return workspace(task()) }).mockImplementation(async () => { order.push('workspace'); return workspace(task({ test_identity_id: 'identity2' })) })
    render(<PreparationPage {...p} />)
    fireEvent.click(await screen.findByRole('button', { name: '创建账号并登录' }))
    expect(await screen.findByText('登录准备页面')).toBeInTheDocument()
    expect(api.create).toHaveBeenCalledWith('p1', 'u1', 3, '普通成员账号 2')
    expect(order.slice(order.indexOf('create'), order.indexOf('login') + 1)).toEqual(['create', 'materials', 'workspace', 'login'])
  })
  it('创建后的同步失败不重复创建或自动打开旧任务', async () => {
    const p = props(); p.onStateChanged.mockResolvedValueOnce(workspace(task())).mockResolvedValue(undefined)
    render(<PreparationPage {...p} />)
    fireEvent.click(await screen.findByRole('button', { name: '创建账号并登录' }))
    expect(await screen.findByText(/下一步尚未同步/)).toBeInTheDocument()
    expect(api.create).toHaveBeenCalledOnce(); expect(api.start).not.toHaveBeenCalled()
  })
  it('已有账号只登录，不重复创建', async () => {
    render(<PreparationPage {...props(workspace(task({ test_identity_id: 'identity2' })))} />)
    fireEvent.click(await screen.findByRole('button', { name: '打开登录浏览器' }))
    await waitFor(() => expect(api.start).toHaveBeenCalledWith('identity2'))
    expect(api.create).not.toHaveBeenCalled()
  })
  it('pending review 使用当前主任务的 recording ID', async () => {
    render(<PreparationPage {...props(workspace(task({ task_kind: 'REVIEW_RECORDING', recording_id: 'pending-specific' })))} />)
    fireEvent.click(await screen.findByRole('button', { name: '继续准备这项材料' }))
    expect(await screen.findByText(/录制任务 pending-specific/)).toBeInTheDocument()
    expect(api.create).not.toHaveBeenCalled()
  })
  it('创建后任务已转向其他 slot 时不启动原账号登录', async () => {
    const p = props(); p.onStateChanged.mockResolvedValueOnce(workspace(task())).mockResolvedValue(workspace(task({ identity_slot_id: 'slot1', test_identity_id: 'identity1' })))
    render(<PreparationPage {...p} />)
    fireEvent.click(await screen.findByRole('button', { name: '创建账号并登录' }))
    await waitFor(() => expect(api.create).toHaveBeenCalledOnce())
    await waitFor(() => expect(p.onStateChanged).toHaveBeenCalledTimes(2))
    expect(api.start).not.toHaveBeenCalled()
  })
  it('同级候选不默认选择，明确选择后只提交绑定并刷新当前任务', async () => {
    const materials = selectionMaterial(); api.get.mockResolvedValue(materials); api.select.mockResolvedValue({})
    const p = props(workspace(task({ task_kind: 'SELECT_ALLOW_CONTROL' })))
    p.onStateChanged.mockResolvedValue(workspace(task()))
    render(<PreparationPage {...p} />)
    const button = await screen.findByRole('button', { name: '确认正常对照' })
    expect(button).toBeDisabled(); expect(api.select).not.toHaveBeenCalled()
    expect(screen.getAllByRole('radio').every((radio) => !(radio as HTMLInputElement).checked)).toBe(true)
    expect(screen.queryByRole('button', { name: '继续准备这项材料' })).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('radio')[1]); fireEvent.click(button)
    const control = materials.actions[0].assurance_contract.allow_controls[0]
    await waitFor(() => expect(api.select).toHaveBeenCalledWith('p1', control, control.candidate_allow_permissions[1]))
    expect(await screen.findByRole('button', { name: '创建账号并登录' })).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledTimes(2); expect(api.create).not.toHaveBeenCalled(); expect(api.start).not.toHaveBeenCalled()
  })
  it('保存后的同步失败阻止重复提交，刷新候选变化后清除旧选择', async () => {
    const materials = selectionMaterial(); api.get.mockResolvedValue(materials); api.select.mockResolvedValue({})
    const p = props(workspace(task({ task_kind: 'SELECT_ALLOW_CONTROL' }))); p.onStateChanged.mockResolvedValue(undefined)
    render(<PreparationPage {...p} />)
    const button = await screen.findByRole('button', { name: '确认正常对照' })
    fireEvent.click(screen.getAllByRole('radio')[0]); fireEvent.click(button)
    expect(await screen.findByText(/下一步尚未同步/)).toBeInTheDocument(); expect(button).toBeDisabled()
    const updated = selectionMaterial(); updated.actions[0].assurance_contract.allow_controls[0].selection_fingerprint = 'changed-candidate-set'
    api.get.mockResolvedValue(updated); p.onStateChanged.mockResolvedValue(workspace(task({ task_kind: 'SELECT_ALLOW_CONTROL' })))
    fireEvent.click(screen.getByRole('button', { name: '刷新准备材料' }))
    await waitFor(() => expect(screen.queryByText(/下一步尚未同步/)).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: '确认正常对照' })).toBeDisabled()
    expect(api.select).toHaveBeenCalledOnce()
  })
  it('选择被拒绝时保留错误并不进入演示或登录', async () => {
    api.get.mockResolvedValue(selectionMaterial()); const error = new Error('候选已变化'); api.select.mockRejectedValue(error)
    const p = props(workspace(task({ task_kind: 'SELECT_ALLOW_CONTROL' })))
    render(<PreparationPage {...p} />)
    const button = await screen.findByRole('button', { name: '确认正常对照' })
    fireEvent.click(screen.getAllByRole('radio')[0]); fireEvent.click(button)
    await waitFor(() => expect(p.onError).toHaveBeenCalledWith(error))
    expect(screen.queryByText(/录制任务|登录准备页面/)).not.toBeInTheDocument()
    expect(api.start).not.toHaveBeenCalled()
  })
})
