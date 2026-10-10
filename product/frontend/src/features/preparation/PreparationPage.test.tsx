// 动作准备页验证：服务端唯一主任务、真实身份槽位、写后刷新与失效响应隔离。
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PreparationView } from '../../api/preparation/preparation'
import type { PreparationSuggestionView, SuggestedMaterial } from '../../api/preparation/preparationSuggestions'
import type { PrimaryTaskDto, WorkspaceViewDto } from '../../api/workspace'
import { PreparationPage } from './PreparationPage'
const api = vi.hoisted(() => ({ get: vi.fn(), create: vi.fn(), start: vi.fn(), select: vi.fn(), evidence: vi.fn(), draft: vi.fn(), saveDraft: vi.fn(), guidance: vi.fn(), suggestion: vi.fn(), automate: vi.fn() }))
vi.mock('./proof-sources/prepareProvidedProofs',()=>({prepareProvidedProofs:api.automate}))
vi.mock('../../api/preparation/preparationSuggestions', () => ({preparationSuggestionsApi: {show: api.suggestion}}))
vi.mock('../../api/preparation/proofSources', () => ({proofSourcesApi: {context: api.guidance}}))
vi.mock('../../api/preparation/preparation', () => ({ preparationApi: { get: api.get, selectAllowControl: api.select, evidence: api.evidence, draft: api.draft, saveDraft: api.saveDraft } }))
vi.mock('../../api/preparation/testIdentities', () => ({ testIdentitiesApi: { create: api.create, startPreparation: api.start } }))
vi.mock('../assistant/AssistantPanel', () => ({ AssistantPanel: () => null }))
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
beforeEach(() => { vi.clearAllMocks(); api.automate.mockImplementation(async (_project,prepare)=>prepare()); api.guidance.mockResolvedValue({project_id:'p1'}); api.draft.mockResolvedValue({schema_version:"1",revision:0,action_id:null,material:null}); api.get.mockResolvedValue(material()); api.create.mockResolvedValue({ identity_id: 'identity2' }); api.start.mockResolvedValue({ preparation_id: 'login2' }) })
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

function suggestions(approved = false): PreparationSuggestionView {
  const materials: SuggestedMaterial[] = [{kind:'identity',account_requirement:'准备能发布资料的负责人测试账号'},
    {kind:'execution',normal_steps:['打开项目资料，再按发布按钮']},
    {kind:'resource',resource_concept:'新建的合成资料',fields:[{field:'state',requirement:'初始值为草稿'}],preparation_steps:['从正常创建入口建立测试资料']},
    {kind:'evidence',capability:'MANAGED_TRANSACTION_RECORDS',observable_result:'业务存储中的状态改为已发布',field_hints:['state']},
    {kind:'recovery',expected_state:'测试资料恢复为草稿'}]
  return {suggestion:{project_id:'p1',suggestion_id:'psg_one',revision:1,basis_id:'psb_current',submitted_via:'MCP',content:{unresolved_questions:[],
    items:materials.map((value,index)=>({item_id:`psi_${index}`,material:value,description:`${index+1}：核对这类材料的建立办法`,gap:null,depends_on:index?['psi_0']:[],handler:'AGENT',
      target:{kind:'CANDIDATE',candidate_id:'rc_one',revision:2},source:{classification:'HYPOTHESIS',explanation:'需要核对实现',candidate_ids:[]}}))}},
    state:'CURRENT',current_basis_id:'psb_current',latest_revision:1,review_url:'#/tests?materials=1',items:materials.map((_,index)=>({item_id:`psi_${index}`,current:true,return_url:'#/tests?materials=1',source_locations:[],
      resolved_target:{state:approved?'APPROVED':'WAITING_APPROVAL',action_id:approved?'a1':null,action_revision:approved?2:null,action_label:'发布资料',actor_label:'负责人'}}))}
}

describe('五类材料建议续接', () => {
  it('无运行材料时先看建立办法，五类均有位置且不会冒充实际齐备', async () => {
    api.get.mockResolvedValue(material({actions:[]}))
    api.guidance.mockResolvedValue({project_id:'p1',suggestion_context:{project_id:'p1',state:'CURRENT',basis_id:'psb_current',latest:suggestions()}})
    const p=props(workspace(null));render(<PreparationPage {...p} requestedMaterialKind="resource"/>)
    const table=await screen.findByRole('table',{name:'预先整理的材料'})
    expect(within(table).getAllByRole('row')).toHaveLength(6)
    expect(within(table).getByText('从正常创建入口建立测试资料')).toBeInTheDocument()
    expect(screen.queryByText('可复用')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'核对规则'}))
    expect(p.onNavigate).toHaveBeenCalledWith('/permissions?project_id=p1&candidate=rc_one&revision=2')
    expect(screen.getAllByRole('button',{name:'Agent 协助'})).toHaveLength(1)
    expect(screen.getAllByRole('button',{name:'读取建议'})).toHaveLength(1)
    expect(api.saveDraft).not.toHaveBeenCalled();expect(api.create).not.toHaveBeenCalled()
  })
  it('正式动作建议放入原材料行，打开账号仍走原入口', async () => {
    api.guidance.mockResolvedValue({project_id:'p1',suggestion_context:{project_id:'p1',state:'CURRENT',basis_id:'psb_current',latest:suggestions(true)}})
    render(<PreparationPage {...props()} requestedMaterialKind="identity"/>)
    await screen.findByText('准备能发布资料的负责人测试账号')
    expect(screen.queryByRole('table',{name:'预先整理的材料'})).not.toBeInTheDocument()
    expect(screen.getAllByRole('table')).toHaveLength(1)
    fireEvent.click(screen.getAllByRole('button',{name:'管理测试账号'})[0])
    expect(await screen.findByText('登录准备页面')).toBeInTheDocument()
    expect(api.start).not.toHaveBeenCalled();expect(api.create).not.toHaveBeenCalled()
  })
  it('指定旧修订可回看，读取新建议保留动作、批次与任务引用', async () => {
    const old={...suggestions(true),state:'SUPERSEDED',latest_revision:2}
    api.suggestion.mockResolvedValue(old)
    api.guidance.mockResolvedValue({project_id:'p1',suggestion_context:{project_id:'p1',state:'CURRENT',basis_id:'psb_current',latest:suggestions(true)}})
    const p=props();render(<PreparationPage {...p} requestedActionId="a1" requestedMaterialKind="evidence" requestedSuggestionId="psg_one" requestedSuggestionRevision="1" assistReturnTo="/tests?materials=1&change_id=change-two&task_id=task-two"/>)
    await screen.findByText(/这份建议已有新修订/)
    expect(api.suggestion).toHaveBeenCalledWith('p1','psg_one','1')
    fireEvent.click(screen.getByRole('button',{name:'读取建议'}))
    const query=new URLSearchParams(p.onNavigate.mock.calls[0][0].split('?')[1])
    expect(Object.fromEntries(query)).toEqual({project_id:'p1',materials:'1',change_id:'change-two',task_id:'task-two',action_id:'a1',suggestion_id:'psg_one',material_kind:'evidence'})
  })
  it('指定建议读取失败不换成另一份建议，真实材料仍可使用', async () => {
    api.suggestion.mockRejectedValue(new Error('not found'))
    api.guidance.mockResolvedValue({project_id:'p1',suggestion_context:{project_id:'p1',state:'CURRENT',basis_id:'psb_current',latest:suggestions(true)}})
    render(<PreparationPage {...props()} requestedSuggestionId="missing" requestedSuggestionRevision="0" requestedMaterialKind="identity"/>)
    await screen.findByText(/无法读取指定的材料建议/)
    expect(api.suggestion).toHaveBeenCalledWith('p1','missing','0')
    expect(screen.queryByText('准备能发布资料的负责人测试账号')).not.toBeInTheDocument()
    expect(screen.getByRole('table',{name:'检查材料清单'})).toBeInTheDocument()
    expect(screen.getAllByRole('button',{name:'管理测试账号'})).toHaveLength(2)
  })
  it('别的应用返回的建议不能混入当前材料', async () => {
    const other=suggestions(true);other.suggestion.project_id='p2'
    api.guidance.mockResolvedValue({project_id:'p1',suggestion_context:{project_id:'p1',state:'CURRENT',basis_id:'psb_current',latest:other}})
    render(<PreparationPage {...props()} requestedMaterialKind="identity"/>)
    await screen.findByText(/材料建议暂时无法读取/)
    expect(screen.queryByText('准备能发布资料的负责人测试账号')).not.toBeInTheDocument()
    expect(screen.getByRole('table',{name:'检查材料清单'})).toBeInTheDocument()
  })
  it('精确修订与准备上下文来自不同依据时隐藏当前源码定位', async () => {
    const changed=suggestions(true);changed.current_basis_id='psb_new'
    changed.suggestion.content.items[0].source={classification:'SOURCE_CANDIDATE',explanation:'源码定位',candidate_ids:['action_source']}
    changed.items[0].source_locations=[{candidate_id:'action_source',relative_path:'routes.py',line_start:1,line_end:2,symbol:'publish'}]
    api.suggestion.mockResolvedValue(changed)
    api.guidance.mockResolvedValue({project_id:'p1',suggestion_context:{project_id:'p1',state:'CURRENT',basis_id:'psb_current',latest:suggestions(true)}})
    render(<PreparationPage {...props()} requestedSuggestionId="psg_one" requestedMaterialKind="identity"/>)
    await screen.findByText('读取期间准备依据已经变化，请重新读取建议。')
    expect(screen.queryByText('routes.py:1–2')).not.toBeInTheDocument()
    expect(screen.getByText('当前源码对应需要重新核对，原建议仅供回看。')).toBeInTheDocument()
  })
})
describe('动作准备', () => {
  it('采用同一任务的后端建议并保留可沿用材料，不触发准备写入', async () => {
    api.guidance.mockResolvedValue({project_id:'p1',guidance:{project_id:'p1',state:'CURRENT',materials:[],sources:[],next_action:{task_id:'t1',kind:'PREPARE_TEST_IDENTITY',title:'核对当前成员账号',reason:'只有账号需要处理，其他有效材料保留。'}}})
    render(<PreparationPage {...props()}/>)
    expect(await screen.findByRole('heading',{name:'核对当前成员账号'})).toBeInTheDocument()
    expect(screen.getByText('可沿用：动作录制。')).toBeInTheDocument()
    expect(api.create).not.toHaveBeenCalled();expect(api.start).not.toHaveBeenCalled()
  })
  it('旧任务的建议不能替换当前主任务', async () => {
    api.guidance.mockResolvedValue({project_id:'p1',guidance:{project_id:'p1',state:'CURRENT',materials:[],sources:[],next_action:{task_id:'old-task',title:'旧账号任务',reason:'旧状态'}}})
    render(<PreparationPage {...props()}/>)
    expect(await screen.findByRole('heading',{name:'准备成员账号'})).toBeInTheDocument()
    expect(screen.queryByText('旧账号任务')).not.toBeInTheDocument()
  })
  it('账号诊断深链只打开管理页面，不自动登录或修改材料', async () => {
    render(<PreparationPage {...props()} requestedIdentities requestedActionId="a1"/>)
    expect(await screen.findByText('登录准备页面')).toBeInTheDocument()
    expect(api.create).not.toHaveBeenCalled();expect(api.start).not.toHaveBeenCalled()
  })
  it('示例准备只在确认后连续执行，完成后刷新实际材料', async () => {
    const p=props(),provided=vi.fn().mockResolvedValue(undefined)
    render(<PreparationPage {...p} onProvidedMaterials={provided}/>)
    fireEvent.click(await screen.findByRole('button',{name:'一键准备示例材料'}))
    expect(provided).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toHaveTextContent('campus')
    api.get.mockResolvedValue(material({preparation_complete:true}))
    fireEvent.click(screen.getByRole('button',{name:'确认并一键准备'}))
    await waitFor(()=>expect(provided).toHaveBeenCalledOnce())
    await waitFor(()=>expect(p.onStateChanged).toHaveBeenCalled())
    expect(screen.queryByRole('button',{name:'Agent 协助'})).not.toBeInTheDocument()
  })
  it('读取失败不冒充业务动作为空', async () => {
    api.get.mockRejectedValueOnce(new Error('offline'))
    render(<PreparationPage {...props()} />)
    expect(await screen.findByRole('heading', { name: '暂时无法读取检查材料' })).toBeInTheDocument()
    expect(screen.queryByText('请先在业务边界中确认动作和权限')).not.toBeInTheDocument()
    expect(api.create).not.toHaveBeenCalled()
  })
  it('拒绝展示其他应用返回的材料快照', async () => {
    api.get.mockResolvedValueOnce(material({ project_id: 'other-project' }))
    const p = props(); render(<PreparationPage {...p} />)
    expect(await screen.findByRole('heading', { name: '暂时无法读取检查材料' })).toBeInTheDocument()
    expect(p.onError).toHaveBeenCalledWith(expect.objectContaining({ code: 'STATE_PRECONDITION' }))
    expect(screen.queryByRole('table', { name: '检查材料清单' })).not.toBeInTheDocument()
  })
  it('自动准备失败保留重试入口和具体问题，不报告准备完成', async () => {
    api.automate.mockRejectedValue(new Error('测试文件缺失'))
    render(<PreparationPage {...props()} onProvidedMaterials={vi.fn()}/>)
    fireEvent.click(await screen.findByRole('button',{name:'一键准备示例材料'}))
    fireEvent.click(screen.getByRole('button',{name:'确认并一键准备'}))
    expect(await screen.findByText('测试文件缺失')).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'继续准备示例材料'})).toBeEnabled()
  })

  it.each(['AUTHORIZE_SOURCE','PREPARE_PROOF_SOURCE','PREPARE_REFERENCE'])('提供材料入口不遮住后端给出的证明步骤：%s', async kind => {
    const url='#/tests?materials=1&proof_sources=1&action_id=a1&source=source-one'
    api.guidance.mockResolvedValue({project_id:'p1',guidance:{project_id:'p1',state:'CURRENT',materials:[],sources:[],next_action:{task_id:'t1',kind,title:'核对证明来源',reason:'按当前来源继续准备',gui_url:url}}})
    const p=props(workspace(task({task_kind:'COMPLETE_EFFECT_EVIDENCE',effect_id:'e1'}))),provided=vi.fn()
    render(<PreparationPage {...p} />)
    fireEvent.click(await screen.findByRole('button',{name:'核对证明来源'}))
    expect(p.onNavigate).toHaveBeenCalledWith(url.slice(1))
    expect(provided).not.toHaveBeenCalled();expect(api.start).not.toHaveBeenCalled()
    expect(screen.queryByText(/录制任务/)).not.toBeInTheDocument()
  })

  it('只有当前缺口展开，已可检查任务返回总览而不误开录制', async () => {
    const p=props(workspace(task({ task_kind:'RUN_CURRENT_CHECK', title:'运行当前检查' })))
    render(<PreparationPage {...p}/>)
    fireEvent.click(await screen.findByRole('button',{name:'前往处理'}))
    await waitFor(()=>expect(p.onNavigate).toHaveBeenCalledWith('/tests'))
    expect(api.create).not.toHaveBeenCalled(); expect(api.start).not.toHaveBeenCalled()
    expect(screen.queryByText(/录制任务/)).not.toBeInTheDocument()
  })

  it('五类材料显示真实缺口，展开账号不写入或开始登录', async () => {
    render(<PreparationPage {...props()} />)
    const table = await screen.findByRole('table', {name:'检查材料清单'})
    expect(within(table).getByText('普通成员账号 1、普通成员账号 2')).toBeInTheDocument()
    for (const name of ['真实账号','动作录制','测试资源','结果证明','恢复方式']) {
      expect(within(table).getByText(name, {exact:true})).toBeInTheDocument()
    }
    expect(within(table).getByText('只读动作无需恢复')).toBeInTheDocument()
    expect(api.create).not.toHaveBeenCalled(); expect(api.start).not.toHaveBeenCalled()
    expect(screen.queryByText(/Alice|Bob|slot2|最多支持/)).not.toBeInTheDocument()
    fireEvent.click(within(table).getByRole('button', {name:'处理'}))
    expect(screen.getAllByRole('button', {name:'管理测试账号'}).length).toBeGreaterThan(0)
    expect(api.create).not.toHaveBeenCalled();expect(api.start).not.toHaveBeenCalled();expect(api.saveDraft).not.toHaveBeenCalled()
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
    expect(await screen.findByRole('table', { name: '检查材料清单' })).toBeInTheDocument()
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
    await waitFor(() => expect(screen.getByRole('button', { name: '刷新准备材料' })).toHaveAttribute('aria-busy','false')); fireEvent.click(screen.getByRole('button', { name: '刷新准备材料' }))
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
