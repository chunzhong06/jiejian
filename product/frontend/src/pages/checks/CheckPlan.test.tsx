import {CheckScopePicker} from './CheckScopePicker'
import {fireEvent,render,screen,within,waitFor} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import {Plan} from './CheckPlan'
import {Reports} from './Reports'
import {currentChecksApi} from '../../entities/check/api/currentChecks'
import {workspaceApi} from '../../entities/workspace/api/workspace'
import {preparationApi,type PreparationView} from '../../entities/preparation/api/preparation'
import {testIdentitiesApi} from '../../entities/preparation/api/testIdentities'


// 夹具补齐公开准备投影，测试只覆盖自己声明的差异，不依赖缺字段的非法响应。
function materialView(value:PreparationView):PreparationView{
 const missing={status:'NEEDS_USER' as const,reason_codes:[]}
 return Object.assign({preparation_complete:false,recommended_action_id:null,basis_fingerprint:null,policy_epoch:1,source_fingerprint:null,impacts:[]},value,{actions:value.actions.map(action=>Object.assign({
  action_revision:1,preparation_complete:false,next_material:'identity',permissions:[],assurance_contract:{allow_controls:[]},execution:missing,resources:[],recovery:{status:'NOT_REQUIRED',reason_codes:[]},reason_codes:[],
 },action,{
  identity_requirements:Object.assign({},missing,{allocation_mode:'SLOTS'},action.identity_requirements,{slots:action.identity_requirements.slots.map((slot,index)=>Object.assign({},missing,{test_identity_id:null},slot,{requirement:Object.assign({actor_revision:1,ordinal:1,slot_id:action.action_id+':'+index},slot.requirement)}))}),
  effect_evidence:action.effect_evidence.map(item=>Object.assign({},missing,item)),
 }))})
}
const props=()=>({projectId:'app',name:'展馆',official:false,route:{path:'/reports',query:new URLSearchParams('view=plan')},onError:vi.fn(),refresh:vi.fn()})
beforeEach(()=>{
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([])
  vi.spyOn(workspaceApi,'current').mockResolvedValue({project:{project_id:'app'},actions:[]} as never)
  vi.spyOn(preparationApi,'get').mockResolvedValue(materialView({project_id:'app',actions:['下载','预览'].map((display_name,index)=>({action_id:'action'+index,display_name,identity_requirements:{slots:[]},effect_evidence:[]}))} as never))
  vi.spyOn(currentChecksApi,'preview').mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:2,case_count:0,actions:[],gaps:[0,0,1].map(index=>({action_id:'action'+index,reason:'TEST_IDENTITY_REQUIRED'}))} as never)
})

it('独立预览不提交，返回保留准备入口并恢复焦点',async()=>{
 vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:true,plan_fingerprint:'basis',action_count:0,case_count:0,actions:[],gaps:[]})
 const submit=vi.spyOn(currentChecksApi,'submit')
 render(<main><Plan {...props()}/></main>)
 const origin=await screen.findByRole('button',{name:'预览这次检查'});origin.focus();fireEvent.click(origin)
 expect(screen.getByRole('heading',{name:'确认这次检查'})).toHaveFocus();expect(submit).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'返回检查准备'}))
 expect(screen.getByRole('button',{name:'预览这次检查'})).toBe(origin);await waitFor(()=>expect(origin).toHaveFocus())
})

it('准备页将完整线索和范围交给原范围工作面，返回保留当前操作',async()=>{
 const base=await currentChecksApi.preview('app')
 vi.mocked(currentChecksApi.preview).mockResolvedValue({...base,discovery_coverage:{pending_count:1,recheck_count:0,related_count:0,excluded_count:0,unexecuted_request_count:0,omitted_count:0,items:[{key:'request',kind:'REQUEST',label:'新增审批入口',status:'PENDING',source_id:'source',request_id:'request'}]}} as never)
 const page=render(<Plan {...props()}/> )
 fireEvent.click(await screen.findByRole('button',{name:'切换业务操作'}));fireEvent.click(await screen.findByRole('menuitem',{name:'预览'}))
 fireEvent.click(screen.getByRole('button',{name:'查看本次范围'}));fireEvent.click(screen.getByText('查看待核对线索与已确认范围'))
 expect(screen.getByText('新增审批入口')).toBeVisible()
 fireEvent.click(screen.getByRole('button',{name:'返回检查准备'}))
 expect(page.container.querySelector('.jj-material-workbench-context')).toHaveTextContent('预览')
})

it('未就绪时主操作进入准确缺口并携带回程，不显示无法推进的开始检查',async()=>{
  const submit=vi.spyOn(currentChecksApi,'submit')
  render(<Plan {...props()}/>);
  fireEvent.click(await screen.findByRole('button',{name:'准备测试账号'}))
  const query=new URLSearchParams(location.hash.split('?')[1])
  expect(location.hash).toMatch(/^#\/preparation\?/)
  expect(query.get('action_id')).toBe('action0');expect(query.get('identities')).toBe('1')
  expect(new URLSearchParams(query.get('return_to')!.split('?')[1]).get('plan_item')).toBe('action0:identity')
  expect(submit).not.toHaveBeenCalled()
  expect(screen.queryByRole('button',{name:/开始检查/})).not.toBeInTheDocument()
})

it('账号名称与会话状态成组，核对入口保留准确槽位与检查回程',async()=>{
 vi.mocked(preparationApi.get).mockResolvedValue(materialView({project_id:'app',actions:[{action_id:'action0',display_name:'读取订单',identity_requirements:{slots:[{requirement:{actor_id:'member',slot_id:'member-slot'},actor_display_name:'成员',status:'STALE',reason_codes:['TEST_IDENTITY_LOGIN_REQUIRED']}]},permissions:[{intent_id:'deny',subject_actor_id:'member',expectation:'DENY'}],effect_evidence:[]}]} as never))
 vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:1,case_count:0,actions:[],gaps:[{action_id:'action0',reason:'TEST_IDENTITY_REQUIRED',intent_id:'deny'}]} as never)
 render(<Plan {...props()}/> )
 const link=await screen.findByRole('link',{name:'准备账号：成员账号'}),row=link.closest('article')!
 expect(within(row).getByText('成员账号')).toBeVisible();expect(within(row).getByText('会话需核对')).toBeVisible()
 const query=new URLSearchParams(link.getAttribute('href')!.split('?')[1]);expect(query.get('account_slot')).toBe('member-slot');expect(query.get('action_id')).toBe('action0')
 expect(new URLSearchParams(query.get('return_to')!.split('?')[1]).get('plan_item')).toBe('action0:identity')
})

it('同一资源的多个缺口保留原因，只提供一次准确准备入口',async()=>{
  vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:1,case_count:0,actions:[],gaps:['RESOURCE_REQUIRED','RESOURCE_OWNER_SOURCE_STALE','MATERIAL_OWNER_CHANGED'].map(reason=>({action_id:'action0',intent_id:'rule',reason}))} as never)
  render(<Plan {...props()}/>)
  fireEvent.click(await screen.findByRole('button',{name:/^测试资源/}))
  expect(screen.getAllByRole('link',{name:'确认资源：本次测试数据'})).toHaveLength(1)
  expect(screen.getByRole('link',{name:'确认资源：本次测试数据'})).toHaveAttribute('href',expect.stringContaining('rule_id=rule'))
  expect(document.querySelectorAll('.jj-plan-reasons li')).toHaveLength(3)
  expect(screen.getByText('材料绑定的数据所属账号已变化，需要重新确认归属')).toBeVisible()
})

it('恢复选定范围只构造该范围预览，空选区不隐式检查全部',async()=>{
  const ref={intent_id:'chosen',revision:1,intent_hash:'hash'}
  sessionStorage.setItem('jiejian.studio.scope:app:selection',JSON.stringify({refs:[ref]}))
  const value=props();value.route.query.set('scope_id','selection')
  render(<Plan {...value}/>)
  await screen.findByRole('heading',{name:'检查准备'})
  expect(currentChecksApi.preview).toHaveBeenCalledTimes(1)
  expect(currentChecksApi.preview).toHaveBeenCalledWith('app',null,[ref],undefined)
})

it('空选区保持选择状态且不构造预览',async()=>{
  sessionStorage.setItem('jiejian.studio.scope:app:empty',JSON.stringify({refs:[]}))
  const value=props();value.route.query.set('scope_id','empty')
  render(<Plan {...value}/>)
  await screen.findByRole('heading',{name:'调整检查范围'})
  await waitFor(()=>expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1))
  expect(screen.getByRole('heading',{level:1,name:'调整检查范围'})).toBeVisible()
  expect(screen.queryByRole('link',{name:'全部检查记录'})).not.toBeInTheDocument()
  expect(currentChecksApi.preview).not.toHaveBeenCalled()
})

it('同类缺口保留所属操作，处理入口携带返回检查的上下文',async()=>{
  render(<Plan {...props()}/>);
  const action=await screen.findByRole('region',{name:'当前准备事项'})
  expect(action.querySelectorAll('.jj-plan-reasons li')).toHaveLength(1)
  fireEvent.click(screen.getByRole('button',{name:'切换业务操作'}));expect(await screen.findAllByRole('menuitem')).toHaveLength(2);fireEvent.keyDown(screen.getByRole('menu'),{key:'Escape'})
  expect(workspaceApi.current).not.toHaveBeenCalled()
  const destination=within(action).getByRole('link',{name:'准备账号：所需测试账号'}).getAttribute('href')!
  const query=new URLSearchParams(destination.split('?')[1])
  expect(query.get('action_id')).toBe('action0')
  expect(query.get('focus')).toBe('identity')
  expect(query.get('identities')).toBe('1')
  expect(query.get('return_to')).toContain('/reports?view=plan')
})

it('同一操作合并说明但保留每条规则与结果的处理入口',async()=>{
  vi.mocked(preparationApi.get).mockResolvedValue(materialView({project_id:'app',actions:[{
    action_id:'action0',display_name:'读取订单',
    identity_requirements:{slots:[{requirement:{actor_id:'member'},actor_display_name:'成员'},{requirement:{actor_id:'owner'},actor_display_name:'负责人'}]},
    permissions:[{intent_id:'deny',subject_actor_id:'member',expectation:'DENY'},{intent_id:'allow',subject_actor_id:'owner',expectation:'ALLOW'}],
    effect_evidence:[{effect_id:'effect',business_label:'订单备注可见'}],
  }]} as never))
  vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:1,case_count:0,actions:[],gaps:[
    {action_id:'action0',reason:'EFFECT_VERDICT_PROOF_REQUIRED',intent_id:'deny',effect_id:'effect'},
    {action_id:'action0',reason:'EFFECT_VERDICT_PROOF_REQUIRED',intent_id:'allow',effect_id:'effect'},
    {action_id:'action0',reason:'REGISTERED_OBSERVER_UNAVAILABLE'},
  ]} as never)
  render(<Plan {...props()}/>);
  fireEvent.click(await screen.findByRole('button',{name:/^业务结果证明/}))
  const action=screen.getByRole('region',{name:'当前准备事项'})
  expect(within(action).getByText('业务结果的判断依据还未准备好')).toBeVisible()
  expect(within(action).getByText('证明来源当前不可用')).toBeVisible()
  expect(within(action).getAllByRole('link',{name:/设置依据/})).toHaveLength(3)
  expect(within(action).getByRole('link',{name:'设置依据：负责人可以读取订单'})).toBeVisible()
  const destination=within(action).getByRole('link',{name:'设置依据：成员不得读取订单'}).getAttribute('href')!
  const query=new URLSearchParams(destination.split('?')[1])
  expect(query.get('focus')).toBe('evidence')
  expect(query.get('action_id')).toBe('action0')
  expect(query.get('effect_id')).toBe('effect')
  expect(query.get('rule_id')).toBe('deny')
})

it.each([false,true])('账号定位入口覆盖情况与总入口一致，额外所需身份=%s',async(extra)=>{
  vi.mocked(preparationApi.get).mockResolvedValue(materialView({project_id:'app',actions:[{
    action_id:'action0',display_name:'读取订单',effect_evidence:[],
    identity_requirements:{slots:['member','owner',...(extra?['auditor']:[])].map(actor_id=>({requirement:{actor_id},actor_display_name:actor_id==='member'?'成员':actor_id==='owner'?'负责人':'审核人'}))},
    permissions:[{intent_id:'deny',subject_actor_id:'member',expectation:'DENY'},{intent_id:'allow',subject_actor_id:'owner',expectation:'ALLOW'}],
  }]} as never))
  vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:1,case_count:0,actions:[],gaps:[
    {action_id:'action0',reason:'TEST_IDENTITY_REQUIRED'},
    {action_id:'action0',reason:'TEST_IDENTITY_NOT_READY',intent_id:'deny'},
    {action_id:'action0',reason:'TEST_IDENTITY_NOT_READY',intent_id:'allow'},
  ]} as never)
  render(<Plan {...props()}/>)
  const group=await screen.findByRole('region',{name:'当前准备事项'})
  expect(within(group).getByRole('link',{name:'准备账号：成员账号'})).toHaveAttribute('href',expect.stringContaining('account_slot=action0%3A0'))
  expect(within(group).getByRole('link',{name:'准备账号：负责人账号'})).toHaveAttribute('href',expect.stringContaining('account_slot=action0%3A1'))
  expect(within(group).getAllByRole('link',{name:/准备账号：/})).toHaveLength(extra?3:2)
  const information=within(group).getByText('材料核对信息').closest('details')!
  fireEvent.click(within(group).getByText('材料核对信息'))
  expect(information.querySelectorAll('ul>li')).toHaveLength(2)
})
it('原范围不可执行时仍可只读找回已经提交的检查',async()=>{
  sessionStorage.setItem('jiejian.studio.check:app',JSON.stringify({fingerprint:'old',operation:'op',change:null}))
  const receipt=vi.spyOn(currentChecksApi,'receipt').mockResolvedValue({run:{project_id:'app',run_id:'original'}} as never)
  const submit=vi.spyOn(currentChecksApi,'submit')
  render(<Plan {...props()}/>);
  fireEvent.click(await screen.findByRole('button',{name:'查看上次提交结果'}))
  await waitFor(()=>expect(new URLSearchParams(location.hash.split('?')[1]).get('run_id')).toBe('original'))
  expect(receipt).toHaveBeenCalledWith('app','op')
  expect(submit).not.toHaveBeenCalled()
})

it('另一范围的未知提交不覆盖当前规则，回读原回执也不冒用当前范围',async()=>{
  const old={intent_id:'old-rule',revision:2,intent_hash:'old-hash'},current={intent_id:'current-rule',revision:1,intent_hash:'current-hash'}
  sessionStorage.setItem('jiejian.studio.check:app',JSON.stringify({fingerprint:'old',operation:'original-operation',change:'old-change',selected:[old]}))
  vi.mocked(preparationApi.get).mockResolvedValue(materialView({project_id:'app',actions:[{action_id:'read',display_name:'读取',identity_requirements:{slots:[]},effect_evidence:[],permissions:[{...current,effective_state:'ACTIVE'}]}]} as never))
  vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:1,case_count:0,actions:[],gaps:[]} as never)
  vi.spyOn(currentChecksApi,'receipt').mockResolvedValue({run:{project_id:'app',run_id:'original-run'}} as never)
  const value=props();value.route.query.set('rule_id','current-rule')
  render(<Plan {...value}/>)
  await waitFor(()=>expect(currentChecksApi.preview).toHaveBeenCalledWith('app',null,[current],undefined))
  fireEvent.click(await screen.findByRole('button',{name:'查看上次提交结果'}))
  await waitFor(()=>expect(new URLSearchParams(location.hash.split('?')[1]).get('run_id')).toBe('original-run'))
  const query=new URLSearchParams(location.hash.split('?')[1])
  expect(query.get('change_id')).toBe('old-change');expect(query.has('rule_id')).toBe(false)
  expect(JSON.parse(sessionStorage.getItem('jiejian.studio.scope:app:'+query.get('scope_id'))!)).toEqual({refs:[old]})
})

it('应用已有运行时打开原运行，本次选择仅作为回程而不标成原运行的范围',async()=>{
  const current={intent_id:'chosen',revision:1,intent_hash:'hash'}
  vi.mocked(preparationApi.get).mockResolvedValue(materialView({project_id:'app',actions:[{action_id:'read',display_name:'读取',identity_requirements:{slots:[]},effect_evidence:[],permissions:[{...current,effective_state:'ACTIVE'}]}]} as never))
  vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:true,plan_fingerprint:'basis',action_count:1,case_count:1,actions:[],gaps:[]} as never)
  vi.spyOn(currentChecksApi,'list').mockResolvedValue([{run:{project_id:'app',run_id:'already-running'}}] as never)
  const submit=vi.spyOn(currentChecksApi,'submit'),value=props();value.route.query.set('rule_id','chosen')
  render(<Plan {...value}/>);fireEvent.click(await screen.findByRole('button',{name:'预览这次检查'}));expect(submit).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'开始检查'}))
  await waitFor(()=>expect(new URLSearchParams(location.hash.split('?')[1]).get('run_id')).toBe('already-running'))
  const query=new URLSearchParams(location.hash.split('?')[1])
  expect(query.has('scope_id')).toBe(false);expect(query.has('rule_id')).toBe(false)
  expect(new URLSearchParams(query.get('return_to')!.split('?')[1]).get('rule_id')).toBe('chosen')
  expect(submit).not.toHaveBeenCalled()
})

it('选定禁止规则时显示并保留必要正常对照',()=>{
  const allow={intent_id:'normal',revision:1,intent_hash:'normal-hash',subject_actor_id:'owner',resource_owner_actor_id:'owner',relation:'OWNS',expectation:'ALLOW',effective_state:'ACTIVE'}
  const deny={...allow,intent_id:'challenge',intent_hash:'deny-hash',subject_actor_id:'member',relation:'OTHER_ROLE',expectation:'DENY'}
  const change=vi.fn()
  render(<CheckScopePicker disabled={false} selected={[{intent_id:'challenge',revision:1,intent_hash:'deny-hash'}]} onChange={change} materials={{actions:[{display_name:'更新工单',permissions:[allow,deny],assurance_contract:{allow_controls:[{deny_permission:deny,resolved_allow_permission:allow}]},identity_requirements:{slots:[{requirement:{actor_id:'owner'},actor_display_name:'负责人'},{requirement:{actor_id:'member'},actor_display_name:'成员'}]}}]} as never}/>);
  const normal=screen.getByRole('checkbox',{name:/负责人可以更新工单/})
  expect(normal).toBeChecked()
  expect(normal).toBeDisabled()
  expect(screen.getByText('必要正常对照')).toBeVisible()
  fireEvent.click(screen.getByRole('checkbox',{name:/成员不得更新工单/}))
  expect(change).toHaveBeenCalledWith([])
})

it('未批准要求保留全文、准确对象与返回当前事项的位置',async()=>{
 vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:0,case_count:0,actions:[],gaps:[],boundary_review_gaps:['owner','member'].map(id=>({candidate_id:id,revision:1,issue_id:id,message:'已确认要求需要重新核对',status:'PLAN_NOT_COVERED',review_url:'#/permissions?candidate_id='+id})),requirement_scope:['owner','member'].map(id=>({candidate_id:id,revision:1,requirements:[{requirement_id:id,requirement:id==='owner'?'负责人可修改自己的工单':'成员不能修改负责人的工单'}]}))} as never)
 render(<Plan {...props()}/> )
 const sections=await screen.findAllByRole('region',{name:'待核对权限要求'});expect(sections).toHaveLength(2)
 expect(within(sections[0]).getByText('负责人可修改自己的工单')).toBeVisible();expect(within(sections[1]).getByText('成员不能修改负责人的工单')).toBeVisible()
 const query=new URLSearchParams(within(sections[1]).getByRole('link',{name:'核对要求'}).getAttribute('href')!.split('?')[1]);expect(query.get('candidate_id')).toBe('member');expect(query.get('return_to')).toContain('plan_item=requirement%3Amember')
})

it('缺口处理回程显示已解决反馈，不自动替用户选择其他缺口',async()=>{
  const value=props();value.route.query.set('plan_tab','prepare');value.route.query.set('plan_item','action0:execution')
  render(<Plan {...value}/>)
  expect(await screen.findByText(/刚才处理的准备项已不在当前缺口中/)).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'继续处理下一项'}))
  expect(screen.getByRole('region',{name:'当前准备事项'})).toHaveTextContent('测试账号尚未就绪')
})

it('同页进入丢失的准确范围时不沿用上一份选择',async()=>{
  const value=props(),page=render(<Reports {...value}/>)
  await screen.findByRole('region',{name:'当前准备事项'})
  const next={...value,route:{...value.route,query:new URLSearchParams('view=plan&scope_id=missing')}}
  page.rerender(<Reports {...next}/>)
  expect(await screen.findByRole('heading',{name:'调整检查范围'})).toBeVisible()
  expect(screen.getByRole('button',{name:'核对本次检查'})).toBeDisabled()
  expect(currentChecksApi.preview).toHaveBeenCalledTimes(1)
})

it('范围获得新身份或主题重渲染后，仍停留在范围编辑且保留选择',async()=>{
 location.hash='#/reports?view=plan'
 const material=await preparationApi.get('app')
 material.actions[0].permissions=[{intent_id:'chosen',revision:1,intent_hash:'hash',effective_state:'ACTIVE',expectation:'ALLOW',subject_actor_id:'actor',resource_owner_actor_id:'actor',relation:'OWNS'} as never]
 vi.mocked(preparationApi.get).mockResolvedValue(material)
 const value=props(),page=render(<Reports {...value}/>)
 fireEvent.click(await screen.findByRole('button',{name:'查看本次范围'}))
 fireEvent.click(screen.getByRole('button',{name:'选定规则'}))
 fireEvent.click(screen.getByRole('checkbox',{name:/可以下载/}))
 const query=new URLSearchParams(location.hash.split('?')[1])
 expect(query.get('plan_tab')).toBe('scope')
 page.rerender(<Reports {...value} route={{path:'/reports',query}}/>)
 expect(await screen.findByRole('heading',{name:'调整检查范围'})).toBeVisible()
 expect(screen.getByRole('checkbox',{name:/可以下载/})).toBeChecked()
 fireEvent.click(screen.getByRole('button',{name:'返回检查准备'}))
 expect(new URLSearchParams(location.hash.split('?')[1]).get('plan_tab')).toBe('review')
})

it('同角色的准确身份分别保留，操作切换只改变所属槽位',async()=>{
 const slots=[{id:'applicant-a',slot:'first'},{id:'applicant-b',slot:'second'}]
 vi.mocked(testIdentitiesApi.list).mockResolvedValue(slots.map(item=>({project_id:'app',identity_id:item.id,label:item.id})) as never)
 vi.mocked(preparationApi.get).mockResolvedValue(materialView({project_id:'app',actions:[0,1].map(index=>({action_id:'action'+index,display_name:'操作'+index,effect_evidence:[],identity_requirements:{slots:slots.map(item=>({status:'STALE',reason_codes:['TEST_IDENTITY_LOGIN_REQUIRED'],test_identity_id:item.id,actor_display_name:'申请人',requirement:{slot_id:item.slot+'-'+index,actor_id:'applicant'}}))}}))} as never))
 render(<Plan {...props()}/> )
 const links=await screen.findAllByRole('link',{name:/核对账号：申请人账号/})
 expect(links.map(link=>new URLSearchParams(link.getAttribute('href')!.split('?')[1]).get('identity_id'))).toEqual(['applicant-a','applicant-b'])
 fireEvent.click(screen.getByRole('button',{name:'切换业务操作'}));fireEvent.click(await screen.findByRole('menuitem',{name:'操作1'}))
 const next=screen.getAllByRole('link',{name:/核对账号：申请人账号/})
 expect(next.map(link=>new URLSearchParams(link.getAttribute('href')!.split('?')[1]).get('account_slot'))).toEqual(['first-1','second-1'])
 expect(next.map(link=>new URLSearchParams(link.getAttribute('href')!.split('?')[1]).get('identity_id'))).toEqual(['applicant-a','applicant-b'])
})

it('选定范围只展示同次预览需要的身份槽位，不展开整项操作的其他账号',async()=>{
 vi.mocked(preparationApi.get).mockResolvedValue(materialView({project_id:'app',actions:[{action_id:'action0',display_name:'读取订单',effect_evidence:[],identity_requirements:{slots:[{test_identity_id:'owner',actor_display_name:'负责人',requirement:{slot_id:'owner-slot',actor_id:'owner'}},{test_identity_id:'other',actor_display_name:'成员',requirement:{slot_id:'other-slot',actor_id:'member'}}]}}]} as never))
 vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',plan_fingerprint:'current',can_execute:false,actions:[],gaps:[{action_id:'action0',reason:'TEST_IDENTITY_LOGIN_REQUIRED'}],preparation_work:{project_id:'app',plan_fingerprint:'current',impacts:[{action_id:'action0',kind:'identity',slot_id:'owner-slot',member_id:'owner',status:'STALE',reason_codes:['TEST_IDENTITY_LOGIN_REQUIRED'],permission_ids:['chosen'],member_label:'负责人',explanation:'本次需要负责人账号'}]}} as never)
 render(<Plan {...props()}/> )
 expect(await screen.findByRole('link',{name:'核对账号：负责人账号'})).toHaveAttribute('href',expect.stringContaining('account_slot=owner-slot'))
 expect(screen.queryByRole('link',{name:'核对账号：成员账号'})).not.toBeInTheDocument()
})
