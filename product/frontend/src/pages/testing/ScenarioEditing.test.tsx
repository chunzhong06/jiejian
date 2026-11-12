import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {BusinessScenarios} from './BusinessScenarios'
import {businessScenariosApi as api,type BusinessScenario,type ScenarioContext} from '../../entities/preparation/api/businessScenarios'
import {discardProjectEditorDrafts} from '../../entities/runtime/model/handoff'

// 单独试运行的请求合同由原面板测试；这里检查父编辑器的隔离和草稿接续。
vi.mock('./ScenarioNodeTrial',()=>({ScenarioNodeTrial:({onClose}:{onClose:()=>void})=><section><h1>当前动作试运行</h1><button onClick={onClose}>返回场景草稿</button></section>}))

const project='scenario-editing',scenario='bsc_'+'1'.repeat(32)
const permission={intent_id:'permission-owner',revision:3,intent_hash:'a'.repeat(64)}
const context:ScenarioContext={project_id:project,documents:[],gaps:[],identities:[{identity_id:'owner',label:'申请人甲'},{identity_id:'other',label:'申请人乙'}],actions:[{action_id:'read',action_revision:2,label:'查看申请',trial_flow:{flow_id:'flow-read',revision:4},cases:[
 {case_id:'own',subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner',resource_id:'application-1042',permission:{...permission,expectation:'ALLOW'}},
 {case_id:'other',subject_test_identity_id:'other',resource_owner_test_identity_id:'owner',resource_id:'application-1042',permission:{intent_id:'permission-other',revision:5,intent_hash:'b'.repeat(64),expectation:'ALLOW'}},
]}]}
const document:BusinessScenario={document_type:'jiejian.business-scenario',schema_version:'1',id:scenario,project_id:project,revision:7,label:'申请查看',description:'',experiments:[{id:'normal',label:'正常业务',kind:'NORMAL',control_experiment_id:null,invocations:['first','second'].map((id,index)=>({id,label:'查看申请'+(index+1),depends_on:index?['first']:[],batch:null,items:[{id:'resource-'+id,permission,subject_identity_id:'owner',resource_id:'application-1042'}]}))}]}
const props={projectId:project,name:'设备借用台',official:false,refresh:vi.fn(),onError:vi.fn(),route:{path:'/testing',query:new URLSearchParams({scenario,revision:'7'})}}
function setup(){
 sessionStorage.clear()
 discardProjectEditorDrafts(project)
 vi.spyOn(api,'list').mockResolvedValue({project_id:project,documents:[{id:scenario,revision:7,label:document.label,description:'',experiment_count:1}]})
 vi.spyOn(api,'context').mockResolvedValue(context)
 vi.spyOn(api,'read').mockResolvedValue(structuredClone(document))
 const save=vi.spyOn(api,'save').mockImplementation(async(_project,value)=>value)
 render(<BusinessScenarios {...props}/>)
 return save
}
async function choose(label:string,option:string){
 fireEvent.mouseDown(screen.getByRole('combobox',{name:label}))
 fireEvent.click(await screen.findByRole('option',{name:option}))
}
afterEach(()=>{vi.restoreAllMocks();discardProjectEditorDrafts(project)})

it('准备项选择保留准确权限、账号和资源绑定，分项核对不产生保存',async()=>{
 const save=setup()
 await screen.findByRole('combobox',{name:'已准备的操作与数据'})
 await choose('已准备的操作与数据','查看申请 · 申请人乙 · application-1042 · 允许')
 expect(screen.getByLabelText('所选准备项')).toHaveTextContent('操作账号申请人乙')
 expect(save).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'保存并预览检查'}))
 await waitFor(()=>expect(save).toHaveBeenCalledOnce())
 expect(save.mock.calls[0][1].experiments[0].invocations[0].items[0]).toMatchObject({permission:{intent_id:'permission-other',revision:5,intent_hash:'b'.repeat(64)},subject_identity_id:'other',resource_id:'application-1042'})
})

it('范围选择只改变预览范围，显式预览才另存准确前缀，不提交整个场景',async()=>{
 const save=setup()
 await screen.findByRole('combobox',{name:'核对范围'})
 await choose('核对范围','正常流程至「查看申请1」')
 expect(save).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'预览所选检查范围'}))
 await waitFor(()=>expect(save).toHaveBeenCalledOnce())
 const snapshot=save.mock.calls[0][1]
 expect(snapshot.id).not.toBe(scenario)
 expect(snapshot.revision).toBe(1)
 expect(snapshot.experiments[0].invocations.map(item=>item.id)).toEqual(['first'])
 expect(snapshot.experiments[0].invocations[0].items[0].permission).toEqual(permission)
})

it('单独试运行独占任务操作，返回后保留场景草稿与当前步骤',async()=>{
 const save=setup()
 const input=await screen.findByRole('textbox',{name:'步骤说明'})
 fireEvent.change(input,{target:{value:'本步尚未保存的说明'}})
 await choose('核对范围','当前动作（单独试运行）')
 fireEvent.click(screen.getByRole('button',{name:'进入单独试运行'}))
 expect(screen.getByRole('heading',{level:1,name:'当前动作试运行'})).toBeVisible()
 expect(screen.queryByRole('button',{name:'保存并预览检查'})).not.toBeInTheDocument()
 expect(screen.queryByRole('button',{name:'请 Agent 整理'})).not.toBeInTheDocument()
 expect(save).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'返回场景草稿'}))
 expect(screen.getByRole('textbox',{name:'步骤说明'})).toHaveValue('本步尚未保存的说明')
 expect(within(screen.getByLabelText('所选准备项')).getByText('application-1042')).toBeVisible()
})
