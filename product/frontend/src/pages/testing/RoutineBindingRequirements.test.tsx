import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {RoutineBindingRequirements} from '../../entities/check/ui/RoutineBindingRequirements'
import {preparationApi} from '../../entities/preparation/api/preparation'

const actor='bar_'+'a'.repeat(32),action='bac_'+'b'.repeat(32),slot='isl_'+'c'.repeat(32),required=actor+'@1'
const document={routine_id:'csp_'+'d'.repeat(32),revision:1,requirements:[{kind:'ACCOUNT',slot:required,label:'成员',minimum_count:2,actor:{actor_id:actor,revision:1}},
 {kind:'FLOW',slot:action+'@1',label:'读取订单',minimum_count:1,action:{action_id:action,revision:1}}]}
const props={projectId:'binding-ui',document:document as never,assets:[],origin:'/testing?view=plans&routine_id='+document.routine_id+'&routine_revision=1&section=binding',dirty:false}
afterEach(()=>vi.restoreAllMocks())

it('只缺结果证明时，已有账号和步骤继续保留，不要求重新准备',()=>{
 const complete=[{kind:'ACCOUNT',slot:required,status:'PRESENT',count:2,minimum_count:2,reason_codes:[]},{kind:'FLOW',slot:action+'@1',status:'PRESENT',count:1,minimum_count:1,reason_codes:[]}]
 const current={...document,requirements:[...document.requirements,{kind:'PROOF',slot:'proof',label:'订单备注',minimum_count:1,action:{action_id:action,revision:1},effect_id:'note'}]}
 render(<RoutineBindingRequirements {...props} document={current as never} progress={complete as never}/>)
 expect(screen.getByRole('button',{name:'订单备注 业务结果证明 · 需要准备'})).toBeVisible()
 expect(screen.queryByText('尚未准备可用于本次检查的账号。')).not.toBeInTheDocument()
 fireEvent.click(screen.getByText('已有材料 · 2'))
 fireEvent.click(screen.getByRole('button',{name:'成员的测试账号 测试账号 · 已有材料，等待确认'}))
 expect(screen.getByText('已经准备了这项材料。补齐当前其余缺口后，再一起确认用于本次检查。')).toBeVisible()
})

it('材料未齐时仍显示逻辑要求，补账号定位未满足的准确槽位并保留回程事项',async()=>{
 vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'binding-ui',actions:[{action_id:action,action_revision:1,identity_requirements:{slots:[
  {requirement:{slot_id:'isl_'+'e'.repeat(32),actor_id:actor,actor_revision:1},status:'SATISFIED'},
  {requirement:{slot_id:slot,actor_id:actor,actor_revision:1},status:'NEEDS_USER'}]}}]} as never)
 render(<RoutineBindingRequirements {...props}/>)
 expect(screen.getByRole('button',{name:'成员的测试账号 测试账号 · 需要准备'})).toBeVisible()
 expect(screen.getByText('需要准备',{selector:'.jj-badge'})).toBeVisible()
 expect(screen.queryByRole('alert')).not.toBeInTheDocument()
 fireEvent.click(screen.getByRole('button',{name:'去准备账号'}))
 await waitFor(()=>expect(location.hash).toContain('account_slot='+slot))
 const query=new URLSearchParams(location.hash.split('?')[1])
 expect(query.get('action_id')).toBe(action)
 expect(new URLSearchParams(query.get('return_to')!.split('?')[1]).get('binding_slot')).toBe('ACCOUNT:'+required)
})

it('方案操作修订失效时保留原事项并报错，不选同名的新修订代替',async()=>{
 location.hash='#/testing?unchanged=1'
 vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'binding-ui',actions:[{action_id:action,action_revision:2,identity_requirements:{slots:[]}}]} as never)
 render(<RoutineBindingRequirements {...props} initialSlot={'FLOW:'+action+'@1'}/>)
 fireEvent.click(screen.getByRole('button',{name:'核对操作步骤'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('这项操作要求已变化，请核对方案引用的修订。')
 expect(location.hash).toBe('#/testing?unchanged=1')
})
