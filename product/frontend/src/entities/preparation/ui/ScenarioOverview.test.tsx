import {cleanup,fireEvent,render,screen,within} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {ScenarioOverview} from './ScenarioOverview'
import {businessScenariosApi as api,type BusinessScenario,type ScenarioContext} from '../api/businessScenarios'

afterEach(()=>{cleanup();vi.restoreAllMocks()})
const permission={intent_id:'rule',revision:1,intent_hash:'a'.repeat(64)}
const item={id:'member-item',permission,subject_identity_id:'member',resource_id:'alpha'}
const document:BusinessScenario={document_type:'jiejian.business-scenario',schema_version:'1',id:'scene',project_id:'app',revision:2,label:'资料发布',description:'完整说明继续保留。',experiments:[{id:'changed',label:'成员发布负责人资料',kind:'CHANGE_SUBJECT',control_experiment_id:'normal',invocations:[{id:'publish',label:'发布 alpha',items:[item],depends_on:[],batch:null}]}]}
const context:ScenarioContext={project_id:'app',documents:[],identities:[{identity_id:'member',label:'普通成员 bob'}],actions:[{action_id:'publish',action_revision:1,label:'发布资料',cases:[{case_id:'case',subject_test_identity_id:'member',resource_owner_test_identity_id:'owner',resource_id:'alpha',permission:{...permission,expectation:'DENY'}}]}],gaps:[]}

it('收起时比较实验关系，展开后阅读步骤；收起恢复原按钮焦点且没有写入',async()=>{
 vi.spyOn(api,'read').mockResolvedValue(document);vi.spyOn(api,'context').mockResolvedValue(context)
 const save=vi.spyOn(api,'save')
 render(<ScenarioOverview projectId="app" id="scene" revision={2}/>)
 const table=await screen.findByRole('table',{name:'业务实验与预期要求'})
 expect(await within(table).findByText('普通成员 bob')).toBeVisible()
 expect(within(table).getByText('禁止')).toBeVisible()
 const button=within(table).getByRole('button',{name:/成员发布负责人资料/})
 expect(button).toHaveAttribute('aria-expanded','false')
 fireEvent.click(button)
 expect(screen.getByRole('region',{name:'成员发布负责人资料的实验安排'})).toBeVisible()
 expect(screen.getByRole('heading',{name:'执行步骤'})).toBeVisible()
 fireEvent.click(screen.getByRole('button',{name:'收起实验安排'}))
 expect(button).toHaveAttribute('aria-expanded','false')
 expect(screen.queryByRole('region',{name:'成员发布负责人资料的实验安排'})).not.toBeInTheDocument()
 expect(save).not.toHaveBeenCalled()
})

it('同名最新规则不匹配旧引用时保留缺口，不显示当前规则的允许结论',async()=>{
 vi.spyOn(api,'read').mockResolvedValue(document)
 vi.spyOn(api,'context').mockResolvedValue({...context,actions:[{...context.actions[0],cases:[{...context.actions[0].cases[0],permission:{...permission,revision:2,expectation:'ALLOW'}}]}]})
 render(<ScenarioOverview projectId="app" id="scene" revision={2}/>)
 const table=await screen.findByRole('table')
 expect(await within(table).findByText('要求待核对')).toBeVisible()
 expect(within(table).queryByText('允许')).not.toBeInTheDocument()
})

it('上下文读取失败仍保留准确场景和原说明，拒绝使用其他项目的名字',async()=>{
 vi.spyOn(api,'read').mockResolvedValue(document)
 vi.spyOn(api,'context').mockResolvedValue({...context,project_id:'other'})
 render(<ScenarioOverview projectId="app" id="scene" revision={2}/>)
 expect(await screen.findByRole('button',{name:'重新读取对应依据'})).toBeVisible()
 expect(screen.queryByText('普通成员 bob')).not.toBeInTheDocument()
 const original=screen.getByText('场景补充说明').closest('details')!
 expect(within(original).getByText(document.description)).toBeInTheDocument()
})

it('执行样本为空时仍显示场景准确修订的要求，不因材料失效丢失业务意图',async()=>{
 vi.spyOn(api,'read').mockResolvedValue(document)
 vi.spyOn(api,'context').mockResolvedValue({...context,scenario:{id:'scene',revision:2},actions:[],requirements:[{permission,expectation:'DENY'}]})
 render(<ScenarioOverview projectId="app" id="scene" revision={2}/>)
 expect(await screen.findByText('禁止')).toBeVisible()
 expect(api.context).toHaveBeenCalledWith('app',undefined,{scenario_id:'scene',revision:2})
})
