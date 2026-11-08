import {fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {CheckWorkspace} from './CheckWorkspace'
import {useWorkflow} from '../shared/lib/workflow'
import {readRoute} from '../shared/lib/navigation'
import {ActionLink} from '../shared/ui/actions'

// 用原链接与组合上下文驱动导航，领域组件不发起写入或目标请求。
vi.mock('../pages/checks/Reports',()=>({Reports:()=> <ActionLink href="#/preparation?action_id=read&identities=1&return_to=%2Freports%3Fview%3Dplan%26rule_id%3Ddeny%26plan_item%3Dread%253Aidentity">准备当前账号</ActionLink>}))
vi.mock('../pages/preparation/Preparation',()=>({Preparation:()=>{const work=useWorkflow()!;return <><h1>当前材料</h1><p>{work.route!.query.get('account_slot')}</p><button onClick={work.finish}>完成材料核对</button><button onClick={()=>work.open('/testing?action_id=read&resume_draft=1')}>编辑操作</button></>}}))
vi.mock('../pages/testing/TestingEditor',()=>({TestingEditor:()=>{const work=useWorkflow()!;return <><h1>当前流程草稿</h1><button onClick={()=>work.open('/preparation?action_id=read&identities=1&account_slot=owner&return_to='+encodeURIComponent('/testing?action_id=read&resume_draft=1'))}>准备流程账号</button><output aria-label="当前回程">{work.origin}</output><output aria-label="证明配置回程">{work.resume!('/preparation?action_id=read&effect_id=result&proof_sources=1&configure=new&private_value=hidden')}</output></>}}))
const props={projectId:'app',project:{project_id:'app'} as never,name:'订单',official:false,refresh:vi.fn(),onError:vi.fn()}
afterEach(()=>{location.hash='';vi.clearAllMocks()})
const mount=(query:string)=>render(<CheckWorkspace {...props} route={{path:'/reports',query:new URLSearchParams(query)}}/>)

it('完整往返保留规则与缺口定位，退出编辑只重新核对，不宣称准备成功',async()=>{
 const first=mount('view=plan&rule_id=deny&return_to=%2Fpermissions%3Frule_id%3Ddeny')
 fireEvent.click(await screen.findByRole('link',{name:'准备当前账号'}))
 let query=readRoute().query
 expect(query.get('rule_id')).toBe('deny');expect(query.get('plan_item')).toBe('read:identity')
 expect(new URLSearchParams(query.get('work_item')!.split('?')[1]).get('action_id')).toBe('read')
 first.unmount();const next=mount(query.toString())
 fireEvent.click(await screen.findByRole('button',{name:'完成材料核对'}))
 query=readRoute().query
 expect(query.get('rule_id')).toBe('deny');expect(query.get('plan_item')).toBe('read:identity')
 expect(query.get('work_reviewed')).toBe('1');expect(query.has('work_item')).toBe(false)
 next.unmount()
})

it('流程补账号后回原流程草稿，协作回程只保存白名单对象',async()=>{
 const first=mount('view=plan&routine_id=exact&routine_revision=7&work_item='+encodeURIComponent('/testing?action_id=read&private_value=hidden'))
 const editor=await screen.findByRole('heading',{name:'当前流程草稿'})
 expect(editor).toBeVisible();expect(screen.getByRole('status',{name:'当前回程'})).not.toHaveTextContent('hidden')
 fireEvent.click(screen.getByRole('button',{name:'准备流程账号'}))
 const query=readRoute().query;expect(query.get('routine_revision')).toBe('7')
 first.unmount();const account=mount(query.toString())
 await screen.findByText('owner');fireEvent.click(screen.getByRole('button',{name:'完成材料核对'}))
 const returned=readRoute().query
 expect(returned.get('routine_id')).toBe('exact')
 const child=new URLSearchParams(returned.get('work_item')!.split('?')[1])
 expect(child.get('action_id')).toBe('read');expect(child.get('resume_draft')).toBe('1')
 account.unmount()
})

it.each(['/preparation?project_id=other&action_id=read','/testing?scenario=other','https://example.com','/unknown'])('拒绝不属于当前工作面的嵌入位置 %s',async child=>{
 mount('view=plan&rule_id=deny&work_item='+encodeURIComponent(child))
 expect(await screen.findByText('这项准备位置无效，请返回原检查范围。')).toBeVisible()
 expect(screen.queryByRole('heading',{name:'当前材料'})).not.toBeInTheDocument()
})

it('交接回程保留原发起页和证明配置位置，原始表单查询不会进入历史',async()=>{
 mount('view=plan&rule_id=deny&return_to='+encodeURIComponent('/issues?issue=original&section=repair')+'&work_item='+encodeURIComponent('/testing?action_id=read'))
 const destination=(await screen.findByRole('status',{name:'证明配置回程'})).textContent!
 const query=new URLSearchParams(destination.split('?')[1])
 expect(query.get('rule_id')).toBe('deny')
 expect(query.get('return_to')).toContain('issue=original')
 const child=new URLSearchParams(query.get('work_item')!.split('?')[1])
 expect(child.get('configure')).toBe('new');expect(child.get('effect_id')).toBe('result');expect(child.get('proof_sources')).toBe('1')
 expect(query.toString()).not.toContain('hidden')
})

it('链接保留新标签与调用方取消的行为',async()=>{
 const open=vi.fn(),finish=vi.fn()
 const {WorkflowContext}=await import('../shared/lib/workflow')
 render(<WorkflowContext.Provider value={{open,finish,label:'本次检查'}}><ActionLink href="#/preparation">普通链接</ActionLink><ActionLink href="#/preparation" target="_blank">新标签链接</ActionLink><ActionLink href="#/preparation" onClick={event=>event.preventDefault()}>已取消链接</ActionLink></WorkflowContext.Provider>)
 fireEvent.click(screen.getByRole('link',{name:'普通链接'}),{ctrlKey:true})
 fireEvent.click(screen.getByRole('link',{name:'已取消链接'}))
 fireEvent.click(screen.getByRole('link',{name:'新标签链接'}))
 expect(open).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('link',{name:'普通链接'}))
 expect(open).toHaveBeenCalledExactlyOnceWith('/preparation')
})
