import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {RuleEditor} from './RuleEditor'
import {businessBoundariesApi as api} from '../../entities/permission/api/businessBoundaries'
import {editorDraft,rememberEditorDraft,discardProjectEditorDrafts} from '../../entities/runtime/model/handoff'

const key='rule-editor:app'
const basis={project_id:'app',boundary_state_fingerprint:'basis',actors:[{item_id:'owner',display_name:'负责人'}],actions:[{item_id:'read',display_name:'查看订单'}],permissions:[{item_id:'rule',effective_state:'ACTIVE',subject_actor_item_id:'owner',resource_owner_actor_item_id:'owner',business_action_item_id:'read',relation:'OWNS',expectation:'ALLOW'}]}
const draft={changes:{rule:'DENY'},reason:'保留审批限制',conditions:{},expanded:null,basis:'basis'}
const props={projectId:'app',onBack:vi.fn(),onProposal:vi.fn(),onError:vi.fn()}
beforeEach(()=>{vi.spyOn(api,'maintenanceDraft').mockResolvedValue(basis as never);rememberEditorDraft(key,draft,'app')})
afterEach(()=>{vi.restoreAllMocks();discardProjectEditorDrafts('app');sessionStorage.clear()})

it('整表内可直接调整要求，进入条件编辑后沿用同一草稿',async()=>{
  render(<RuleEditor {...props}/>);await screen.findByRole('table')
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'调整负责人查看订单对自己的资源的权限'}))
  fireEvent.click(await screen.findByRole('option',{name:'允许'}))
  expect(screen.getByRole('table')).toBeVisible()
  expect(screen.queryByRole('button',{name:'收起规则编辑'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'编辑负责人查看订单对自己的资源的访问要求'}))
  expect(screen.getByRole('combobox',{name:'调整后的要求'}).closest('.jj-choice')).toHaveAttribute('data-value','ALLOW')
})

it('右侧条件只归属所选规则，切换后分别恢复各自输入',async()=>{
  vi.mocked(api.maintenanceDraft).mockResolvedValue({...basis,actions:[...basis.actions,{item_id:'update',display_name:'修改订单'}],permissions:[...basis.permissions,{...basis.permissions[0],item_id:'second',business_action_item_id:'update'}]} as never)
  render(<RuleEditor {...props}/>);await screen.findByText('当前生效的访问规则')
  expect(screen.getByRole('table')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'编辑负责人查看订单对自己的资源的访问要求'}))
  const first=screen.getByRole('region',{name:'负责人查看订单对自己的资源的适用条件'})
  expect(within(first).getByRole('heading',{name:'负责人查看订单的适用条件'})).toBeVisible()
  fireEvent.change(within(first).getByLabelText('仅检查这些数据状态（选填）'),{target:{value:'OPEN'}})
  fireEvent.blur(within(first).getByLabelText('仅检查这些数据状态（选填）'))
  fireEvent.click(screen.getByRole('button',{name:'编辑负责人修改订单对自己的资源的访问要求'}))
  expect(screen.queryByRole('region',{name:'负责人查看订单对自己的资源的适用条件'})).not.toBeInTheDocument()
  expect(within(screen.getByRole('region',{name:'负责人修改订单对自己的资源的适用条件'})).getByLabelText('仅检查这些数据状态（选填）')).toHaveValue('')
  fireEvent.click(screen.getByRole('button',{name:'编辑负责人查看订单对自己的资源的访问要求'}))
  expect(within(screen.getByRole('region',{name:'负责人查看订单对自己的资源的适用条件'})).getByLabelText('仅检查这些数据状态（选填）')).toHaveValue('OPEN')
  fireEvent.click(screen.getByRole('button',{name:'收起规则编辑'}))
  expect(screen.getByRole('table')).toBeVisible()
  await waitFor(()=>expect(screen.getByRole('button',{name:'编辑负责人查看订单对自己的资源的访问要求'})).toHaveFocus())
  fireEvent.click(screen.getByRole('button',{name:'编辑负责人查看订单对自己的资源的访问要求'}))
  expect(screen.getByLabelText('仅检查这些数据状态（选填）')).toHaveValue('OPEN')
})

it('往返恢复理由和具体规则；远端依据变化保留编辑并要求重新核对',async()=>{
  const first=render(<RuleEditor {...props}/>);await screen.findByText('当前生效的访问规则')
  expect(screen.getByLabelText('变更理由')).toHaveValue(draft.reason)
  first.unmount()
  vi.mocked(api.maintenanceDraft).mockResolvedValue({...basis,boundary_state_fingerprint:'new-basis'} as never)
  render(<RuleEditor {...props}/>);await screen.findByText(/正式规则已变化/)
  expect(screen.getByLabelText('变更理由')).toHaveValue(draft.reason)
  expect(screen.getByRole('button',{name:'生成待审变更'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'已核对当前规则，继续编辑'}))
  expect(screen.getByRole('button',{name:'生成待审变更'})).toBeEnabled()
})

it('提案已保存而详情读取失败时保留回执，不重复创建',async()=>{
  const save=vi.spyOn(api,'createMaintenanceProposal').mockResolvedValue({proposal:{project_id:'app',proposal_id:'saved'}} as never)
  const onProposal=vi.fn().mockRejectedValue(new Error('详情不可读')),onError=vi.fn()
  render(<RuleEditor {...props} onProposal={onProposal} onError={onError}/>);await screen.findByText('当前生效的访问规则')
  fireEvent.click(screen.getByRole('button',{name:'生成待审变更'}))
  await waitFor(()=>expect(onError).toHaveBeenCalledWith(expect.objectContaining({message:expect.stringContaining('提案已保存')})))
  expect(screen.getByRole('button',{name:'生成待审变更'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'审阅提案 1'}))
  await waitFor(()=>expect(onProposal).toHaveBeenCalledTimes(2))
  expect(save).toHaveBeenCalledOnce()
})

it('离开后的迟到保存不清较新草稿，也不跳回旧提案',async()=>{
  let finish!:(value:unknown)=>void
  vi.spyOn(api,'createMaintenanceProposal').mockImplementation(()=>new Promise(resolve=>{finish=value=>resolve(value as never)}))
  const onProposal=vi.fn(),view=render(<RuleEditor {...props} onProposal={onProposal}/>);await screen.findByText('当前生效的访问规则')
  fireEvent.click(screen.getByRole('button',{name:'生成待审变更'}));view.unmount()
  rememberEditorDraft(key,{...draft,reason:'后续继续编辑'},'app')
  finish({proposal:{project_id:'app',proposal_id:'old'}})
  await waitFor(()=>expect(sessionStorage.getItem('jiejian.studio.maintenance:app')).toBeNull())
  expect(editorDraft<{reason:string}>(key,'app')?.reason).toBe('后续继续编辑')
  expect(onProposal).not.toHaveBeenCalled()
})

it('条件编辑与访问要求进入同一完整提案，浏览条件本身不提交',async()=>{
  const save=vi.spyOn(api,'createMaintenanceProposal').mockResolvedValue({proposal:{project_id:'app',proposal_id:'saved'}} as never)
  render(<RuleEditor {...props}/>);await screen.findByText('当前生效的访问规则')
  fireEvent.click(screen.getByRole('button',{name:/编辑负责人查看订单对自己的资源的访问要求/}))
  const states=screen.getByLabelText('仅检查这些数据状态（选填）')
  fireEvent.change(states,{target:{value:'OPEN、ARCHIVED'}});fireEvent.blur(states)
  expect(save).not.toHaveBeenCalled()
  expect(screen.getByText('原条件：已登录账号')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'生成待审变更'}))
  await waitFor(()=>expect(save).toHaveBeenCalledOnce())
  const command=save.mock.calls[0][1]
  expect(command.permissions).toHaveLength(1)
  expect(command.permissions[0]).toMatchObject({item_id:'rule',expectation:'DENY',conditions:{resource_states:['OPEN','ARCHIVED']}})
})
