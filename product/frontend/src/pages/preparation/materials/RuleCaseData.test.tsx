import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {RuleCaseData} from './RuleCaseData'
import {preparationApi,type ActionPreparation} from '../../../entities/preparation/api/preparation'
import {proofSourcesApi} from '../../../entities/preparation/api/proofSources'
import {discardProjectEditorDrafts} from '../../../entities/runtime/model/handoff'

const action={action_id:'read',action_revision:1,permissions:[{intent_id:'rule',revision:2,intent_hash:'current',effective_state:'ACTIVE',conditions:{resource_states:['已批准','待领取']}}],identity_requirements:{slots:[{requirement:{slot_id:'owner-slot'},test_identity_id:'owner'}]},assurance_contract:{identity_requirements:{permissions:[{permission:{intent_id:'rule'},resource_owner_slot_id:'owner-slot'}]}}} as ActionPreparation
const props=(scope='pending')=>({projectId:'app',action,scopeKey:scope,onSaved:vi.fn()})
beforeEach(()=>{
 vi.spyOn(preparationApi,'ruleData').mockResolvedValue([])
 vi.spyOn(proofSourcesApi,'context').mockResolvedValue({resources:[{action_id:'read',case_specific:false,owner_identity_id:'owner',resource_id:'loan-1042',binding_fingerprint:'basis'}]} as never)
})
afterEach(()=>{vi.restoreAllMocks();discardProjectEditorDrafts('app')})
async function edit(){await screen.findByText(/数据 loan-1042/);await waitFor(()=>expect(screen.getByRole('button',{name:'选择数据'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'选择数据'}));fireEvent.change(screen.getByRole('textbox'),{target:{value:'loan-pending'}})}

it('材料切换再返回恢复未提交资源编号，其他检查范围保持独立',async()=>{
 const first=render(<RuleCaseData {...props()}/>);await edit();first.unmount()
 const other=render(<RuleCaseData {...props('other')}/>);await screen.findByText(/数据 loan-1042/);expect(screen.getByRole('button',{name:'选择数据'})).toBeEnabled();expect(screen.queryByRole('textbox')).not.toBeInTheDocument();other.unmount()
 render(<RuleCaseData {...props()}/>);expect(await screen.findByRole('textbox')).toHaveValue('loan-pending')
})

it('取消清除当前草稿，成功保存使用准确规则及归属后再回读',async()=>{
 const saved=vi.spyOn(preparationApi,'selectRuleData').mockResolvedValue({} as never),value=props(),view=render(<RuleCaseData {...value}/>);await edit();fireEvent.click(screen.getByRole('button',{name:'取消'}));view.unmount()
 render(<RuleCaseData {...value}/>);await screen.findByText(/数据 loan-1042/);expect(screen.getByRole('button',{name:'选择数据'})).toBeEnabled();expect(screen.queryByRole('textbox')).not.toBeInTheDocument();await edit();fireEvent.click(screen.getByRole('button',{name:'使用这份数据'}))
 await waitFor(()=>expect(value.onSaved).toHaveBeenCalledOnce())
 expect(saved).toHaveBeenCalledWith('app',{permission:{intent_id:'rule',revision:2,intent_hash:'current'},resource_id:'loan-pending',owner_identity_id:'owner',expected_binding_fingerprint:'basis'})
 expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
})

it('部分规则保存失败仍回读已形成结果，并保留原输入供继续核对',async()=>{
 vi.spyOn(preparationApi,'selectRuleData').mockResolvedValueOnce({} as never).mockRejectedValueOnce(new Error('本次保存未完成'))
 const value=props(),second={...action,permissions:[action.permissions[0],{...action.permissions[0],intent_id:'second'}],assurance_contract:{...action.assurance_contract,identity_requirements:{permissions:[...action.assurance_contract.identity_requirements!.permissions,{permission:{intent_id:'second',revision:2,intent_hash:'current'},subject_slot_id:null,resource_owner_slot_id:'owner-slot'}]}}}
 render(<RuleCaseData {...value} action={second}/>);await edit();fireEvent.click(screen.getByRole('button',{name:'使用这份数据'}))
 await waitFor(()=>expect(value.onSaved).toHaveBeenCalledOnce());expect(screen.getByRole('textbox')).toHaveValue('loan-pending');expect(screen.getByRole('alert')).toBeVisible()
})
