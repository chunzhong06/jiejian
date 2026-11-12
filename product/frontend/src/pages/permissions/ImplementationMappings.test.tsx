import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {RuleEditor} from './RuleEditor'
import {businessBoundariesApi as api,type BoundaryMaintenanceDraftDto} from '../../entities/permission/api/businessBoundaries'
import {discardProjectEditorDrafts} from '../../entities/runtime/model/handoff'

const basis={project_id:'app',boundary_state_fingerprint:'basis',
  actors:[{item_id:'owner',actor_id:'original-role',expected_current_revision:1,display_name:'申请人',effective_state:'ACTIVE',source_candidate_ids:[]}],
  actions:[{item_id:'read',action_id:'original-action',expected_current_revision:1,display_name:'查看申请内部详情',effective_state:'ACTIVE',source_candidate_ids:['action-read']}],
  permissions:[{item_id:'rule',intent_id:'original-rule',expected_current_revision:1,effective_state:'ACTIVE',subject_actor_item_id:'owner',resource_owner_actor_item_id:'owner',business_action_item_id:'read',relation:'OWNS',expectation:'ALLOW',protected_effect_item_ids:['note']}],
  candidate_options:[{candidate_kind:'ROLE',candidate_id:'role-applicant',display_name:'申请人',evidence_available:false},{candidate_kind:'ACTION',candidate_id:'action-read',display_name:'详情接口',evidence_available:true}],
  implementation_inspections:[{actor_id:'original-role',actor_revision:1,status:'MISSING'},{action_id:'original-action',action_revision:1,status:'CURRENT'}],
} as unknown as BoundaryMaintenanceDraftDto
const props={projectId:'app',onBack:vi.fn(),onProposal:vi.fn(),onError:vi.fn()}
beforeEach(()=>{sessionStorage.clear();discardProjectEditorDrafts('app');vi.spyOn(api,'maintenanceDraft').mockResolvedValue(basis)})
afterEach(()=>{vi.restoreAllMocks();discardProjectEditorDrafts('app');sessionStorage.clear()})

it('补齐原角色对应时保持正式角色、操作和全部权限的原引用，往返仍保留所选线索',async()=>{
  const save=vi.spyOn(api,'createMaintenanceProposal').mockResolvedValue({proposal:{project_id:'app',proposal_id:'rebind'}} as never)
  const view=render(<RuleEditor {...props}/> )
  fireEvent.click(await screen.findByRole('checkbox',{name:'申请人对应申请人'}))
  fireEvent.change(screen.getByLabelText('变更理由'),{target:{value:'补充申请人对应线索'}})
  view.unmount();render(<RuleEditor {...props}/> )
  expect(await screen.findByRole('checkbox',{name:'申请人对应申请人'})).toBeChecked()
  fireEvent.click(screen.getByRole('button',{name:'生成待审变更'}))
  await waitFor(()=>expect(save).toHaveBeenCalledOnce())
  expect(save.mock.calls[0][1]).toEqual({expected_boundary_state_fingerprint:'basis',actors:[{...basis.actors[0],source_candidate_ids:['role-applicant']}],actions:basis.actions,permissions:basis.permissions,provenance:'补充申请人对应线索'})
})

it('重新核对已有操作线索可单独生成提案，多条原对应不被单选控件丢弃',async()=>{
  const current={...basis,actors:[{...basis.actors[0],source_candidate_ids:['role-applicant']}],actions:[{...basis.actions[0],source_candidate_ids:['action-read','action-other']}],
    candidate_options:[...basis.candidate_options,{candidate_kind:'ACTION',candidate_id:'action-other',display_name:'内部资料接口',confidence:'HIGH',evidence_available:true}],
    implementation_inspections:[{actor_id:'original-role',actor_revision:1,status:'CURRENT'},{action_id:'original-action',action_revision:1,status:'STALE'}]} as BoundaryMaintenanceDraftDto
  vi.mocked(api.maintenanceDraft).mockResolvedValue(current)
  const save=vi.spyOn(api,'createMaintenanceProposal').mockResolvedValue({proposal:{project_id:'app',proposal_id:'recheck'}} as never)
  render(<RuleEditor {...props}/> )
  fireEvent.click(await screen.findByRole('checkbox',{name:'已重新核对查看申请内部详情的当前线索'}))
  fireEvent.change(screen.getByLabelText('变更理由'),{target:{value:'核对已有接口对应'}})
  fireEvent.click(screen.getByRole('button',{name:'生成待审变更'}))
  await waitFor(()=>expect(save).toHaveBeenCalledOnce())
  expect(save.mock.calls[0][1].actions).toEqual(current.actions)
  expect(save.mock.calls[0][1].permissions).toEqual(current.permissions)
})

it('对应来源保存结果未知时锁住修改和重复提交，并保留选择',async()=>{
  vi.spyOn(api,'createMaintenanceProposal').mockRejectedValue(new Error('连接中断'))
  const onError=vi.fn()
  render(<RuleEditor {...props} onError={onError}/> )
  const mapping=await screen.findByRole('checkbox',{name:'申请人对应申请人'})
  fireEvent.click(mapping);fireEvent.change(screen.getByLabelText('变更理由'),{target:{value:'补充对应'}})
  fireEvent.click(screen.getByRole('button',{name:'生成待审变更'}))
  await waitFor(()=>expect(onError).toHaveBeenCalled())
  expect(mapping).toBeChecked();expect(mapping).toBeDisabled()
  expect(screen.getByRole('button',{name:'生成待审变更'})).toBeDisabled()
})
