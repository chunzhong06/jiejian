import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {CheckRoutines} from './CheckRoutines'
import {routinesApi,type CheckRoutine} from '../../entities/check/api/routines'
import {ruleWorkspaceApi} from '../../entities/permission/api/ruleWorkspace'
import {businessScenariosApi} from '../../entities/preparation/api/businessScenarios'
import {discardProjectEditorDrafts} from '../../entities/runtime/model/handoff'

const project='routine-ui',id='csp_'+'1'.repeat(32),ref={intent_id:'pin_'+'3'.repeat(32),revision:1,intent_hash:'a'.repeat(64)}
const document:CheckRoutine={document_type:'jiejian.check-routine',schema_version:'2',routine_id:id,project_id:project,revision:1,name:'订单日常',scope:{permissions:[ref],scenario:null},limits:{max_duration_us:300_000_000,max_cases:100},created_at_us:1}
const props=()=>({projectId:project,name:'订单',official:false,refresh:vi.fn(),onError:vi.fn(),route:{path:'/testing',query:new URLSearchParams({view:'plans',routine_id:id,routine_revision:'1'})}})
beforeEach(()=>{
 sessionStorage.clear();discardProjectEditorDrafts(project)
 vi.spyOn(routinesApi,'catalog').mockResolvedValue({project_id:project,routines:[{routine_id:id,revision:1,name:document.name,scope_kind:'PERMISSIONS',permission_count:1,created_at_us:1}],legacy_selections:[]})
 vi.spyOn(ruleWorkspaceApi,'read').mockResolvedValue({schema_version:'1',project_id:project,policy_epoch:1,rules:[{permission:ref,title:'成员不能读取他人订单'}],change_history_limited:false} as never)
 vi.spyOn(businessScenariosApi,'list').mockResolvedValue({project_id:project,documents:[]})
 vi.spyOn(routinesApi,'read').mockResolvedValue(document)
 vi.spyOn(routinesApi,'preparation').mockResolvedValue({project_id:project,routine:document,preview:{can_execute:false},environment:null,environment_fingerprint:null,material_fingerprint:null,assets:[],can_bind:false} as never)
 vi.spyOn(routinesApi,'bindings').mockResolvedValue([])
 vi.spyOn(routinesApi,'history').mockResolvedValue([{revision:1,name:document.name,created_at_us:1}])
})
afterEach(()=>{vi.restoreAllMocks();discardProjectEditorDrafts(project)})

it('方案目录首次读取失败保留测试分类及当前应用',async()=>{
 vi.mocked(routinesApi.catalog).mockRejectedValue(new Error('方案目录暂不可读'))
 const value=props();value.route.query.delete('routine_id');value.route.query.delete('routine_revision')
 render(<CheckRoutines {...value}/> )
 expect(await screen.findByRole('alert')).toHaveTextContent('方案目录暂不可读')
 expect(screen.getByRole('navigation',{name:'测试工作'})).toBeVisible()
 expect(screen.getByRole('link',{name:'操作与材料'})).toHaveAttribute('href','#/testing?project_id='+project)
})

it('准备读取失败保留方案、草稿与准确修订回程，不嵌入另一张页面',async()=>{
 vi.mocked(routinesApi.preparation).mockRejectedValue(new Error('准备来源已变化'))
 const value=props();value.route.query.set('section','binding')
 render(<CheckRoutines {...value}/> )
 expect(await screen.findByRole('alert')).toHaveTextContent('准备来源已变化')
 expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1)
 expect(screen.getByRole('link',{name:'核对应用连接'})).toHaveAttribute('href',expect.stringContaining(encodeURIComponent('routine_revision=1')))
 expect(screen.getByRole('button',{name:'重新读取准备'})).toBeVisible()
})

it('同一方案的深链接切换实际分类，同时保留未保存内容',async()=>{
 const initial=props(),view=render(<CheckRoutines {...initial}/> )
 fireEvent.change(await screen.findByRole('textbox',{name:'方案名称'}),{target:{value:'保留这份草稿'}})
 const route=(section:string)=>({...initial,route:{...initial.route,query:new URLSearchParams({...Object.fromEntries(initial.route.query),section})}})
 view.rerender(<CheckRoutines {...route('limits')}/> )
 expect(screen.queryByRole('tablist',{name:'方案内容'})).not.toBeInTheDocument()
 expect(screen.queryByRole('tab',{name:'运行限制'})).not.toBeInTheDocument()
 expect(await screen.findByLabelText('最长运行时间（秒）')).toBeVisible()
 view.rerender(<CheckRoutines {...route('content')}/> )
 expect(await screen.findByRole('textbox',{name:'方案名称'})).toHaveValue('保留这份草稿')
})

it('保存未知时锁定原请求，回读成功仍沿用同一操作标识',async()=>{
 const save=vi.spyOn(routinesApi,'save').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce({...document,name:'待保存草稿',revision:2})
 render(<CheckRoutines {...props()}/>)
 const name=await screen.findByRole('textbox',{name:'方案名称'})
 expect(screen.queryByRole('alert')).not.toBeInTheDocument()
 fireEvent.change(name,{target:{value:'待保存草稿'}})
 fireEvent.click(screen.getByRole('button',{name:'保存修改'}))
 const recover=await screen.findByRole('button',{name:'继续上次保存'})
 await waitFor(()=>expect(recover).not.toBeDisabled())
 expect(name).toBeDisabled()
 fireEvent.click(recover)
 await waitFor(()=>expect(save).toHaveBeenCalledTimes(2))
 expect(save.mock.calls[1][1]).toEqual(save.mock.calls[0][1])
 expect(save.mock.calls[0][1].expected_revision).toBe(1)
 await waitFor(()=>expect(location.hash).toContain('routine_revision=2'))
})

it('离开后恢复未保存名称、约束和分类，绑定分类不运行草稿',async()=>{
 const value=props(),bind=vi.spyOn(routinesApi,'bind')
 const first=render(<CheckRoutines {...value}/>)
 fireEvent.change(await screen.findByRole('textbox',{name:'方案名称'}),{target:{value:'本地草稿'}})
 fireEvent.change(screen.getByRole('spinbutton',{name:'最多检查场景'}),{target:{value:'12'}})
 first.unmount();const restored=render(<CheckRoutines {...value}/>)
 expect(await screen.findByRole('spinbutton',{name:'最多检查场景'})).toHaveValue(12)

 expect(screen.getByRole('textbox',{name:'方案名称'})).toHaveValue('本地草稿')
 restored.rerender(<CheckRoutines {...value} route={{...value.route,query:new URLSearchParams({...Object.fromEntries(value.route.query),section:'binding'})}}/>)
 expect(await screen.findByText('请先保存这份方案的修改，再准备本次检查。')).toBeVisible()
 expect(screen.queryByRole('button',{name:'确认使用这些材料'})).not.toBeInTheDocument()
 expect(screen.queryByRole('link',{name:'预览这次检查'})).not.toBeInTheDocument()
 expect(bind).not.toHaveBeenCalled()
})


it('目录读取所选准确修订的实际范围，进入准备后回到原选择',async()=>{
 const second='csp_'+'2'.repeat(32)
 vi.mocked(routinesApi.catalog).mockResolvedValue({project_id:project,routines:[{routine_id:id,revision:1,name:document.name,scope_kind:'PERMISSIONS',permission_count:1,created_at_us:1},{routine_id:second,revision:3,name:'结算日常',scope_kind:'PERMISSIONS',permission_count:1,created_at_us:1}],legacy_selections:[]})
 vi.mocked(routinesApi.read).mockImplementation(async(_project,id,revision)=>({...document,routine_id:id,revision,name:id===second?'结算日常':document.name}))
 const value=props();value.route.query=new URLSearchParams({view:'plans'})
 const first=render(<CheckRoutines {...value}/>)
 expect(await screen.findByText('成员不能读取他人订单')).toBeVisible()
 fireEvent.click(screen.getByRole('button',{name:/结算日常/}))
 const link=await screen.findByRole('link',{name:'准备这次检查'})
 await waitFor(()=>expect(link).toHaveAttribute('href',expect.stringContaining('routine_revision=3')))
 expect(link).toHaveAttribute('href',expect.stringContaining(second))
 expect(routinesApi.read).toHaveBeenCalledWith(project,second,3)
 fireEvent.click(link)
 first.unmount();render(<CheckRoutines {...value}/>)
 expect(await screen.findByRole('button',{name:/结算日常/})).toHaveAttribute('aria-pressed','true')
 fireEvent.click(screen.getByRole('button',{name:'收起详情'}))
 await waitFor(()=>expect(screen.getByRole('button',{name:/结算日常/})).toHaveFocus())
 expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
})

it('目录范围读取失败保留准确对象，不以其他方案或当前全部规则代替',async()=>{
 vi.mocked(routinesApi.read).mockResolvedValue({...document,revision:2})
 const value=props();value.route.query=new URLSearchParams({view:'plans'})
 render(<CheckRoutines {...value}/>)
 expect(await screen.findByRole('alert')).toHaveTextContent('保存内容与所选方案修订不一致')
 expect(screen.queryByText('成员不能读取他人订单')).not.toBeInTheDocument()
 expect(screen.getByRole('link',{name:'编辑检查内容'})).toHaveAttribute('href',expect.stringContaining('routine_revision=1'))
 expect(routinesApi.preparation).not.toHaveBeenCalled()
})


it('只有一份方案时直接展示内容，免去无选择价值的半页目录',async()=>{
 const value=props();value.route.query=new URLSearchParams({view:'plans'})
 render(<CheckRoutines {...value}/>)
 expect(await screen.findByText('成员不能读取他人订单')).toBeVisible()
 expect(screen.queryByRole('table')).not.toBeInTheDocument()
 expect(screen.queryByRole('button',{name:'收起详情'})).not.toBeInTheDocument()
 expect(screen.getByRole('link',{name:'准备这次检查'})).toHaveAttribute('href',expect.stringContaining('routine_revision=1'))
})
