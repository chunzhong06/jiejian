import {fireEvent,render,screen,waitFor} from '@testing-library/react'
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
