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
 vi.spyOn(api,'read').mockImplementation(async(_project,id,revision)=>document(id,revision))
})
afterEach(()=>vi.restoreAllMocks())

it('场景目录读取失败保留测试分类，场景内容错误不吞掉长期入口',async()=>{
 vi.mocked(api.list).mockRejectedValue(new Error('场景目录暂不可读'))
 render(<BusinessScenarios {...props}/> )
 expect(await screen.findByRole('alert')).toHaveTextContent('场景目录暂不可读')
 expect(screen.getByRole('navigation',{name:'测试工作'})).toBeVisible()
 expect(screen.getByRole('link',{name:'检查记录'})).toHaveAttribute('href','#/reports?project_id='+project)
})

it('目录就近展示实际实验，按准确修订编辑并恢复选择',async()=>{
 const save=vi.spyOn(api,'save'),context=vi.spyOn(api,'context')
 const firstView=render(<BusinessScenarios {...props}/>)
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
 expect(save).not.toHaveBeenCalled();expect(context).not.toHaveBeenCalled()
})

it('目录读取到其他修订时显示错误，不展示错位实验或发起执行',async()=>{
 vi.mocked(api.read).mockResolvedValue(document(first,2))
 render(<BusinessScenarios {...props}/>)
 expect(await screen.findByRole('alert')).toHaveTextContent('业务场景内容与所选修订不一致')
 expect(screen.queryByText('读取订单')).not.toBeInTheDocument()
 expect(screen.getByRole('link',{name:'编辑场景'})).toHaveAttribute('href',expect.stringContaining('revision=1'))
})
