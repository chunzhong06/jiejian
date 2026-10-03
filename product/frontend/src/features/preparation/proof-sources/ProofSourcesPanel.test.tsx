// 核对来源准备的确认边界、失联回执和稀疏状态；预检查成功不得自动采用或冒充权限通过。
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {ProofSourcesPanel} from './ProofSourcesPanel'
const api = vi.hoisted(() => ({context:vi.fn(),write:vi.fn(),receipt:vi.fn(),adoptionPreview:vi.fn()}))
vi.mock('../../../api/preparation/proofSources',() => ({proofSourcesApi:api}))
const config = {action_id:'action',action_revision:1,effect_id:'effect',observation_identity_id:'alice',resource_binding_id:'res',relative_path_template:'/collections/units/{resource_id}',collection:'units',source_kind:'MANAGED_TRANSACTION_RECORDS',mappings:{state:['state']},identity_claims:[{identity_id:'alice',application_subject_id:'alice',request_path:'/identity/current'}],source_files:['app.mjs'],max_response_bytes:262144,timeout_us:5000000,source_contract_id:'TRANSACTION_HISTORY_V1'}
const source = {source_id:'source',revision:1,config,submitted_via:'MCP',client_name:'Agent',adopted:false,preflight:null}
const initial = () => ({project_id:'app_a',basis_id:'basis',runtime_available:true,runtime_origin:'http://127.0.0.1:3000',actions:[{action_id:'action',label:'发布资料',effects:[{effect_id:'effect',label:'资料被发布'}]}],identities:[{identity_id:'alice',label:'Alice'}],resources:[{resource_binding_id:'res',resource_id:'alpha'}],sources:[source],read_scopes:[]})
const props = {projectId:'app_a',onBack:vi.fn(),onChanged:vi.fn().mockResolvedValue(undefined)}
beforeEach(() => {vi.resetAllMocks();sessionStorage.clear();api.context.mockResolvedValue(initial())})
afterEach(cleanup)

it('确认读取范围必须展示地址和账号，并由用户勾选',async () => {
  render(<ProofSourcesPanel {...props}/>);
  fireEvent.click(await screen.findByRole('button',{name:'确认读取范围'}))
  expect(screen.getByRole('button',{name:'允许这些读取'})).toBeDisabled()
  expect(screen.getByText('http://127.0.0.1:3000')).toBeInTheDocument()
  expect(api.write).not.toHaveBeenCalled()
  api.write.mockImplementation(async (_project,kind,body) => ({project_id:'app_a',operation_kind:kind,operation_id:body.operation_id,result:{state:'GRANTED'}}))
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button',{name:'允许这些读取'}))
  await waitFor(() => expect(api.write).toHaveBeenCalledTimes(1))
  expect(api.write.mock.calls[0][1]).toBe('GRANT_SCOPE')
})

it('预检查可用只展示采用入口，不自动采用',async () => {
  const value = initial()
  api.context.mockResolvedValue({...value,read_scopes:[{scope_id:'scope',origin:value.runtime_origin,identity_ids:['alice'],resource_binding_ids:['res'],path_templates:['/identity/current',config.relative_path_template],max_response_bytes:262144,timeout_us:5000000}],sources:[{...source,preflight:{preflight_id:'preflight',state:'SUCCEEDED',current_basis:true,report:{assessment:'USABLE',checks:[{code:'MAPPING_READABLE',status:'CONFIRMED',mapping_key:'state'}]}}}]})
  render(<ProofSourcesPanel {...props}/>);
  expect(await screen.findByRole('button',{name:'预览采用影响'})).toBeEnabled()
  expect(screen.getByText('1 项字段映射')).toBeInTheDocument()
  expect(screen.queryByText('符合要求')).not.toBeInTheDocument()
  expect(api.write).not.toHaveBeenCalled()
})

it('取消的预检查即使残留可用报告也不显示采用入口',async () => {
  api.context.mockResolvedValue({...initial(),sources:[{...source,preflight:{preflight_id:'cancelled',state:'CANCELLED',current_basis:true,report:{assessment:'USABLE',checks:[]}}}]})
  render(<ProofSourcesPanel {...props}/>)
  await screen.findByRole('heading',{name:'让规则有据可验'})
  expect(screen.queryByRole('button',{name:'预览采用影响'})).not.toBeInTheDocument()
  expect(api.write).not.toHaveBeenCalled()
})

it('网络响应丢失后跨刷新只查询同一回执',async () => {
  api.write.mockRejectedValue(new Error('network'))
  const view = render(<ProofSourcesPanel {...props}/>);
  fireEvent.click(await screen.findByRole('button',{name:'确认读取范围'}))
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button',{name:'允许这些读取'}))
  await waitFor(() => expect(api.write).toHaveBeenCalledTimes(1))
  const operation = api.write.mock.calls[0][2].operation_id
  await waitFor(() => expect(screen.getByRole('button',{name:'返回核对'})).toBeEnabled())
  view.unmount();render(<ProofSourcesPanel {...props}/>);
  await screen.findByRole('heading',{name:'让规则有据可验'})
  // 未确认操作在界面中持续显现，不能因刷新变为可再次提交。
  expect(screen.getByRole('button',{name:'确认读取范围'})).toBeDisabled()
  expect(api.write).toHaveBeenCalledTimes(1)
  expect(sessionStorage.getItem('jiejian-proof-operation:app_a')).toContain(operation)
})

it('手动新增不会覆盖列表中的第一个来源',async () => {
  render(<ProofSourcesPanel {...props}/>);
  fireEvent.click(await screen.findByRole('button',{name:'手动补充来源'}))
  fireEvent.change(screen.getByRole('textbox',{name:'证明来源配置'}),{target:{value:JSON.stringify(config)}})
  api.write.mockImplementation(async (_project,kind,body) => ({project_id:'app_a',operation_kind:kind,operation_id:body.operation_id,result:{state:'CANDIDATE'}}))
  fireEvent.click(screen.getByRole('button',{name:'保存来源候选'}))
  await waitFor(() => expect(api.write).toHaveBeenCalled())
  expect(api.write.mock.calls[0][2]).toMatchObject({source_id:null,expected_revision:null})
})

it('缺口建议携带精确账号入口，点击只导航不执行准备',async () => {
  const value=initial(), onNavigate=vi.fn()
  api.context.mockResolvedValue({...value,guidance:{project_id:'app_a',basis_id:'basis',state:'CURRENT',materials:[],sources:[],next_action:{kind:'REVIEW_IDENTITY',handler:'USER',title:'核对测试账号与角色',reason:'实际账号与当前规则不一致。',gui_url:'#/tests?project_id=app_a&materials=1&identities=1&action_id=action'}}})
  render(<ProofSourcesPanel {...props} onNavigate={onNavigate}/>)
  fireEvent.click(await screen.findByRole('button',{name:'前往处理'}))
  expect(onNavigate).toHaveBeenCalledWith('/tests?project_id=app_a&materials=1&identities=1&action_id=action')
  expect(api.write).not.toHaveBeenCalled()
})

it('复制准备说明要求重新读取最新依据，不把旧建议当执行命令',async () => {
  const copy=vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:copy}})
  api.context.mockResolvedValue({...initial(),guidance:{project_id:'app_a',basis_id:'basis',state:'CURRENT',materials:[],sources:[],next_action:{kind:'REVIEW_SOURCE',handler:'AGENT',title:'核对状态字段',reason:'没有读到指定字段。'}}})
  render(<ProofSourcesPanel {...props}/>)
  fireEvent.click(await screen.findByRole('button',{name:'复制给 Agent 的准备说明'}))
  expect(copy).toHaveBeenCalledWith(expect.stringContaining('先重新调用 jiejian_preparation_context'))
  expect(copy).toHaveBeenCalledWith(expect.stringContaining('修订 1，动作 action'))
  expect(api.write).not.toHaveBeenCalled()
})


it('操作定位无法保存时不提交读取授权',async () => {
  const save=vi.spyOn(Storage.prototype,'setItem').mockImplementation(() => {throw new Error('unavailable')})
  try {
    render(<ProofSourcesPanel {...props}/>)
    fireEvent.click(await screen.findByRole('button',{name:'确认读取范围'}))
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button',{name:'允许这些读取'}))
    expect(await screen.findByText('浏览器暂时不能保留操作回执，本次尚未提交。请恢复浏览器存储后再试。')).toBeInTheDocument()
    expect(api.write).not.toHaveBeenCalled()
  } finally {save.mockRestore()}
})

it('错项目回执保留原操作，核对成功后只清除同次定位',async () => {
  api.write.mockImplementation(async (_project,kind,body) => ({project_id:'another_app',operation_kind:kind,operation_id:body.operation_id,result:{state:'GRANTED'}}))
  api.receipt.mockImplementation(async (project,kind,operation) => ({project_id:project,operation_kind:kind,operation_id:operation,result:{state:'GRANTED'}}))
  render(<ProofSourcesPanel {...props}/>)
  fireEvent.click(await screen.findByRole('button',{name:'确认读取范围'}))
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button',{name:'允许这些读取'}))
  const recover=await screen.findByRole('button',{name:'查询原操作'})
  const pending=JSON.parse(sessionStorage.getItem('jiejian-proof-operation:app_a')!)
  fireEvent.click(recover)
  await waitFor(() => expect(sessionStorage.getItem('jiejian-proof-operation:app_a')).toBeNull())
  expect(api.receipt).toHaveBeenCalledWith('app_a','GRANT_SCOPE',pending.operation)
  expect(api.write).toHaveBeenCalledTimes(1)
})

it('切换项目后迟到的读取不会覆盖新项目',async () => {
  let finishFirst!: (value: ReturnType<typeof initial>) => void
  const first=new Promise<ReturnType<typeof initial>>(resolve => {finishFirst=resolve})
  const second={...initial(),project_id:'app_b',actions:[{...initial().actions[0],label:'第二应用动作'}]}
  api.context.mockImplementation(project => project==='app_a' ? first : Promise.resolve(second))
  const panel=render(<ProofSourcesPanel {...props}/>)
  panel.rerender(<ProofSourcesPanel {...props} projectId="app_b"/>)
  expect(await screen.findByText('第二应用动作 · Agent')).toBeInTheDocument()
  await act(async () => {finishFirst(initial());await first})
  expect(screen.getByText('第二应用动作 · Agent')).toBeInTheDocument()
  expect(api.write).not.toHaveBeenCalled()
})
