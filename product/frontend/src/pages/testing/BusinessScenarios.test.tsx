import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {BusinessScenarios} from './BusinessScenarios'
import {businessScenariosApi as api,type BusinessScenario} from '../../entities/preparation/api/businessScenarios'

const project='scenario-directory',first='bsc_'+'1'.repeat(32),second='bsc_'+'2'.repeat(32)
const props={projectId:project,name:'订单',official:false,refresh:vi.fn(),onError:vi.fn(),route:{path:'/testing',query:new URLSearchParams({scenario:'list'})}}
const document=(id:string,revision:number):BusinessScenario=>({document_type:'jiejian.business-scenario',schema_version:'1',project_id:project,id,revision,label:id===first?'提交订单':'查看结算',description:'保留正常流程，再核对步骤省略后的结果。',experiments:[{id:'normal',label:'正常流程',kind:'NORMAL',control_experiment_id:null,invocations:[{id:'read',label:'读取订单',items:[],depends_on:[],batch:null}]},{id:'omit',label:'省略确认',kind:'OMIT',control_experiment_id:'normal',invocations:[]}]})
beforeEach(()=>{
 sessionStorage.clear()
 vi.spyOn(api,'list').mockResolvedValue({project_id:project,documents:[{id:first,revision:1,label:'提交订单',description:'正常提交与省略确认',experiment_count:2},{id:second,revision:3,label:'查看结算',description:'结算权限',experiment_count:2}]})
 vi.spyOn(api,'context').mockResolvedValue({project_id:project,documents:[],actions:[],identities:[],gaps:[]})
 vi.spyOn(api,'read').mockImplementation(async(_project,id,revision)=>document(id,revision))
})
afterEach(()=>vi.restoreAllMocks())

it('历史场景允许切换步骤阅读，全部修改动作保持只读',async()=>{
 const item={id:'item1',permission:{intent_id:'pin1',revision:1,intent_hash:'a'.repeat(64)},subject_identity_id:'actor',resource_id:'order1'}
 const saved=document(first,1);saved.experiments=[{...saved.experiments[0],invocations:[{id:'read',label:'读取订单',items:[item],depends_on:[],batch:null},{id:'confirm',label:'确认订单',items:[{...item,id:'item2'}],depends_on:['read'],batch:null}]}]
 vi.mocked(api.list).mockResolvedValue({project_id:project,documents:[{id:first,revision:2,label:'当前订单',description:'',experiment_count:1}]})
 vi.mocked(api.read).mockResolvedValue(saved)
 vi.mocked(api.context).mockResolvedValue({project_id:project,documents:[],gaps:[],identities:[{identity_id:'actor',label:'成员'}],actions:[{action_id:'a1',action_revision:1,label:'读取订单',cases:[{case_id:'c1',subject_test_identity_id:'actor',resource_owner_test_identity_id:'actor',resource_id:'order1',permission:{...item.permission,expectation:'ALLOW'}}]}]})
 const save=vi.spyOn(api,'save')
 render(<BusinessScenarios {...props} route={{path:'/testing',query:new URLSearchParams({scenario:first,revision:'1'})}}/> )
 expect(await screen.findByRole('textbox',{name:'场景名称'})).toBeDisabled()
 fireEvent.click(screen.getByRole('button',{name:/2 确认订单/}))
 expect(screen.getByRole('textbox',{name:'步骤说明'})).toHaveValue('确认订单')
 expect(screen.getByRole('button',{name:'添加动作'})).toBeDisabled()
 expect(screen.getByRole('button',{name:'移除此步'})).toBeDisabled()
 expect(screen.getByRole('button',{name:'添加对照变化'})).toBeDisabled()
 expect(save).not.toHaveBeenCalled()
})

it('场景目录读取失败保留测试分类，场景内容错误不吞掉长期入口',async()=>{
 vi.mocked(api.list).mockRejectedValue(new Error('场景目录暂不可读'))
 render(<BusinessScenarios {...props}/> )
 expect(await screen.findByRole('alert')).toHaveTextContent('场景目录暂不可读')
 expect(screen.getByRole('navigation',{name:'测试工作'})).toBeVisible()
 expect(screen.getByRole('link',{name:'检查记录'})).toHaveAttribute('href','#/reports?project_id='+project)
})

it('目录就近展示实际实验，按准确修订编辑并恢复选择',async()=>{
 const save=vi.spyOn(api,'save')
 const firstView=render(<BusinessScenarios {...props}/>)
 fireEvent.click(await screen.findByRole('button',{name:/^正常流程/}))
 expect(await screen.findByText('读取订单')).toBeVisible()
 fireEvent.click(screen.getByRole('button',{name:/查看结算/}))
 const edit=screen.getByRole('link',{name:'编辑场景'})
 expect(edit).toHaveAttribute('href',expect.stringContaining('revision=3'))
 expect(edit).toHaveAttribute('href',expect.stringContaining(second))
 await waitFor(()=>expect(api.read).toHaveBeenCalledWith(project,second,3))
 expect(screen.getByRole('link',{name:'核对检查范围'})).toHaveAttribute('href',expect.stringContaining('scenario_revision=3'))
 fireEvent.click(edit);firstView.unmount();render(<BusinessScenarios {...props}/>)
 expect(await screen.findByRole('button',{name:/查看结算/})).toHaveAttribute('aria-pressed','true')
 fireEvent.click(screen.getByRole('button',{name:'收起详情'}))
 await waitFor(()=>expect(screen.getByRole('button',{name:/查看结算/})).toHaveFocus())
 expect(save).not.toHaveBeenCalled()
})

it('目录读取到其他修订时显示错误，不展示错位实验或发起执行',async()=>{
 vi.mocked(api.read).mockResolvedValue(document(first,2))
 render(<BusinessScenarios {...props}/>)
 expect(await screen.findByRole('alert')).toHaveTextContent('业务场景内容与所选修订不一致')
 expect(screen.queryByText('读取订单')).not.toBeInTheDocument()
 expect(screen.getByRole('link',{name:'编辑场景'})).toHaveAttribute('href',expect.stringContaining('revision=1'))
})

it('从协作进入准确场景后直接返回原事项，不绕回业务场景目录',async()=>{
 const permission={intent_id:'rule',revision:1,intent_hash:'a'.repeat(64)}
 const item={id:'item',permission,subject_identity_id:'actor',resource_id:'alpha'}
 const saved=document(first,1);saved.experiments=[{...saved.experiments[0],invocations:[{id:'read',label:'读取订单',items:[item],depends_on:[],batch:null}]}]
 vi.mocked(api.read).mockResolvedValue(saved)
 vi.mocked(api.context).mockResolvedValue({project_id:project,documents:[],identities:[{identity_id:'actor',label:'负责人'}],gaps:[],actions:[{action_id:'read',action_revision:1,label:'读取订单',cases:[{case_id:'case',subject_test_identity_id:'actor',resource_owner_test_identity_id:'actor',resource_id:'alpha',permission:{...permission,expectation:'ALLOW'}}]}]})
 const origin='/workspace?view=collaboration&task_id=task-original&task_view=work&task_item=review%3Ascene'
 render(<BusinessScenarios {...props} route={{path:'/testing',query:new URLSearchParams({scenario:first,revision:'1',return_to:origin})}}/>)
 fireEvent.click(await screen.findByRole('button',{name:'返回协作任务'}))
 const query=new URLSearchParams(location.hash.split('?')[1])
 expect(query.get('task_id')).toBe('task-original')
 expect(query.get('task_item')).toBe('review:scene')
})
