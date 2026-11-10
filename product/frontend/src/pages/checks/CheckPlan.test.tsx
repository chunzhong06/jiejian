import {CheckScopePicker} from './CheckScopePicker'
import {fireEvent,render,screen,within,waitFor} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import {Plan} from './CheckPlan'
import {Reports} from './Reports'
import {currentChecksApi} from '../../entities/check/api/currentChecks'
import {workspaceApi} from '../../entities/workspace/api/workspace'
import {preparationApi} from '../../entities/preparation/api/preparation'
import {testIdentitiesApi} from '../../entities/preparation/api/testIdentities'

const props=()=>({projectId:'app',name:'展馆',official:false,route:{path:'/reports',query:new URLSearchParams('view=plan')},onError:vi.fn(),refresh:vi.fn()})
beforeEach(()=>{
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([])
  vi.spyOn(workspaceApi,'current').mockResolvedValue({project:{project_id:'app'},actions:[]} as never)
  vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'app',actions:['下载','预览'].map((display_name,index)=>({action_id:'action'+index,display_name,identity_requirements:{slots:[]},effect_evidence:[]}))} as never)
  vi.spyOn(currentChecksApi,'preview').mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:2,case_count:0,actions:[],gaps:[0,0,1].map(index=>({action_id:'action'+index,reason:'TEST_IDENTITY_REQUIRED'}))} as never)
})
it('恢复选定范围只构造该范围预览，空选区不隐式检查全部',async()=>{
  const ref={intent_id:'chosen',revision:1,intent_hash:'hash'}
  sessionStorage.setItem('jiejian.studio.scope:app:selection',JSON.stringify({refs:[ref]}))
  const value=props();value.route.query.set('scope_id','selection')
  render(<Plan {...value}/>)
  await screen.findByRole('heading',{name:'检查尚待准备'})
  expect(currentChecksApi.preview).toHaveBeenCalledTimes(1)
  expect(currentChecksApi.preview).toHaveBeenCalledWith('app',null,[ref],undefined)
})

it('空选区保持选择状态且不构造预览',async()=>{
  sessionStorage.setItem('jiejian.studio.scope:app:empty',JSON.stringify({refs:[]}))
  const value=props();value.route.query.set('scope_id','empty')
  render(<Plan {...value}/>)
  await screen.findByRole('heading',{name:'调整检查范围'})
  expect(currentChecksApi.preview).not.toHaveBeenCalled()
})

it('同类缺口保留所属操作，处理入口携带返回检查的上下文',async()=>{
  render(<Plan {...props()}/>);
  const action=await screen.findByRole('region',{name:'当前准备事项'})
  expect(within(action).getAllByText('测试账号尚未就绪')).toHaveLength(1)
  expect(within(screen.getByRole('navigation',{name:'准备事项'})).getAllByRole('button')).toHaveLength(2)
  expect(workspaceApi.current).not.toHaveBeenCalled()
  const destination=within(action).getByRole('link',{name:'准备测试账号'}).getAttribute('href')!
  const query=new URLSearchParams(destination.split('?')[1])
  expect(query.get('action_id')).toBe('action0')
  expect(query.get('focus')).toBe('identity')
  expect(query.get('identities')).toBe('1')
  expect(query.get('return_to')).toContain('/reports?view=plan')
})

it('同一操作合并说明但保留每条规则与结果的处理入口',async()=>{
  vi.mocked(preparationApi.get).mockResolvedValue({project_id:'app',actions:[{
    action_id:'action0',display_name:'读取订单',
    identity_requirements:{slots:[{requirement:{actor_id:'member'},actor_display_name:'成员'},{requirement:{actor_id:'owner'},actor_display_name:'负责人'}]},
    permissions:[{intent_id:'deny',subject_actor_id:'member',expectation:'DENY'},{intent_id:'allow',subject_actor_id:'owner',expectation:'ALLOW'}],
    effect_evidence:[{effect_id:'effect',business_label:'订单备注可见'}],
  }]} as never)
  vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:1,case_count:0,actions:[],gaps:[
    {action_id:'action0',reason:'EFFECT_VERDICT_PROOF_REQUIRED',intent_id:'deny',effect_id:'effect'},
    {action_id:'action0',reason:'EFFECT_VERDICT_PROOF_REQUIRED',intent_id:'allow',effect_id:'effect'},
    {action_id:'action0',reason:'REGISTERED_OBSERVER_UNAVAILABLE'},
  ]} as never)
  render(<Plan {...props()}/>);
  const action=await screen.findByRole('region',{name:'当前准备事项'})
  expect(within(action).getByText('业务结果的判断依据还未准备好')).toBeVisible()
  expect(within(action).getByText('证明来源当前不可用')).toBeVisible()
  expect(within(action).getAllByRole('link',{name:/准备结果判断依据/})).toHaveLength(3)
  expect(within(action).getByRole('link',{name:'负责人可以读取订单：准备结果判断依据'})).toBeVisible()
  const destination=within(action).getByRole('link',{name:'成员不得读取订单：准备结果判断依据'}).getAttribute('href')!
  const query=new URLSearchParams(destination.split('?')[1])
  expect(query.get('focus')).toBe('evidence')
  expect(query.get('action_id')).toBe('action0')
  expect(query.get('effect_id')).toBe('effect')
  expect(query.get('rule_id')).toBe('deny')
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
  vi.mocked(preparationApi.get).mockResolvedValue({project_id:'app',actions:[{action_id:'read',display_name:'读取',identity_requirements:{slots:[]},effect_evidence:[],permissions:[{...current,effective_state:'ACTIVE'}]}]} as never)
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
  vi.mocked(preparationApi.get).mockResolvedValue({project_id:'app',actions:[{action_id:'read',display_name:'读取',identity_requirements:{slots:[]},effect_evidence:[],permissions:[{...current,effective_state:'ACTIVE'}]}]} as never)
  vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:true,plan_fingerprint:'basis',action_count:1,case_count:1,actions:[],gaps:[]} as never)
  vi.spyOn(currentChecksApi,'list').mockResolvedValue([{run:{project_id:'app',run_id:'already-running'}}] as never)
  const submit=vi.spyOn(currentChecksApi,'submit'),value=props();value.route.query.set('rule_id','chosen')
  render(<Plan {...value}/>);fireEvent.click(await screen.findByRole('button',{name:/开始检查/}))
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

it('逐项核对要求，保留每份要求和返回当前事项的位置',async()=>{
  vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:0,case_count:0,actions:[],gaps:[],
    boundary_review_gaps:['owner','member'].map(id=>({candidate_id:id,revision:1,issue_id:id,message:'已确认要求需要重新核对',status:'PLAN_NOT_COVERED',review_url:'#/permissions?candidate_id='+id})),
    requirement_scope:['owner','member'].map(id=>({candidate_id:id,revision:1,requirements:[{requirement_id:id,requirement:id==='owner'?'负责人可修改自己的工单':'成员不能修改负责人的工单'}]}))} as never)
  render(<Plan {...props()}/>);
  const detail=await screen.findByRole('region',{name:'当前准备事项'})
  expect(within(detail).getByText('负责人可修改自己的工单')).toBeVisible()
  const index=screen.getByRole('navigation',{name:'准备事项'})
  fireEvent.click(within(index).getAllByRole('button',{name:/核对权限要求/})[1])
  expect(within(screen.getByRole('region',{name:'当前准备事项'})).getByText('成员不能修改负责人的工单')).toBeVisible()
  fireEvent.click(within(screen.getByRole('region',{name:'当前准备事项'})).getByRole('button',{name:'核对要求'}))
  const query=new URLSearchParams(location.hash.split('?')[1])
  expect(query.get('candidate_id')).toBe('member')
  expect(query.get('return_to')).toContain('plan_item=requirement%3Amember')
})

it('缺口处理回程显示已解决反馈，不自动替用户选择其他缺口',async()=>{
  const value=props();value.route.query.set('plan_tab','prepare');value.route.query.set('plan_item','action0:execution')
  render(<Plan {...value}/>)
  expect(await screen.findByRole('heading',{name:'这项准备已不在当前缺口中'})).toBeVisible()
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
