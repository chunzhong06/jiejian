// 核对来源准备的确认边界、失联回执和稀疏状态；预检查成功不得自动采用或冒充权限通过。
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {ProofSourcesPanel} from './ProofSourcesPanel'
const api = vi.hoisted(() => ({context:vi.fn(),write:vi.fn(),receipt:vi.fn(),adoptionPreview:vi.fn()}))
vi.mock('../../api/proofSources',() => ({proofSourcesApi:api}))
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
