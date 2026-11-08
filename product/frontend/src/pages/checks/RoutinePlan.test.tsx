import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {RoutinePlan} from './RoutinePlan'
import {routinesApi} from '../../entities/check/api/routines'
import {currentChecksApi} from '../../entities/check/api/currentChecks'
import {preparationApi} from '../../entities/preparation/api/preparation'
import {testIdentitiesApi} from '../../entities/preparation/api/testIdentities'

const project='routine-plan',id='csp_'+'1'.repeat(32),binding='crb_'+'2'.repeat(32),reference={routine_id:id,revision:1,binding_id:binding}
const preview={project_id:project,can_execute:true,plan_fingerprint:'a'.repeat(64),action_count:1,case_count:1,actions:[],gaps:[],boundary_review_gaps:[]}
const document={project_id:project,routine_id:id,revision:1,name:'订单日常方案',schema_version:'2'}
const props=(bound=false)=>({projectId:project,name:'订单',official:false,refresh:vi.fn(),onError:vi.fn(),route:{path:'/reports',query:new URLSearchParams({view:'plan',routine_id:id,routine_revision:'1',...(bound?{binding_id:binding}:{})})}})
beforeEach(()=>{
 sessionStorage.clear()
 vi.spyOn(routinesApi,'read').mockResolvedValue(document as never)
 vi.spyOn(routinesApi,'preparation').mockResolvedValue({project_id:project,preview} as never)
 vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:project,actions:[]} as never)
 vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([])
 vi.spyOn(currentChecksApi,'preview').mockResolvedValue(preview as never)
})
afterEach(()=>vi.restoreAllMocks())

it('尚未确认环境绑定时只能准备，不把可执行预览冒充方案授权',async()=>{
 const submit=vi.spyOn(currentChecksApi,'submit')
 render(<RoutinePlan {...props()}/>)
 expect(await screen.findByRole('link',{name:'返回方案继续准备'})).toBeVisible()
 expect(screen.queryByRole('alert')).not.toBeInTheDocument()
 expect(screen.queryByRole('button',{name:'开始检查'})).not.toBeInTheDocument()
 expect(currentChecksApi.preview).not.toHaveBeenCalled()
 expect(submit).not.toHaveBeenCalled()
})

it('执行始终带准确方案与绑定，报告回程不丢失原对象',async()=>{
 const submit=vi.spyOn(currentChecksApi,'submit').mockResolvedValue({run:{run_id:'run-result',project_id:project}} as never)
 render(<RoutinePlan {...props(true)}/>)
 fireEvent.click(await screen.findByRole('button',{name:'开始检查'}))
 await waitFor(()=>expect(submit).toHaveBeenCalledTimes(1))
 expect(submit.mock.calls[0][7]).toEqual(reference)
 expect(currentChecksApi.preview).toHaveBeenCalledWith(project,null,null,undefined,reference)
 await waitFor(()=>expect(location.hash).toContain('run_id=run-result'))
 const query=new URLSearchParams(location.hash.split('?')[1])
 expect(query.get('routine_id')).toBe(id)
 expect(query.get('binding_id')).toBe(binding)
 expect(query.get('return_to')).toContain('routine_revision=1')
 expect(query.get('return_to')).not.toContain('section=binding')
})

it('缺少方案修订明确停止，不回退全部检查',()=>{
 const value=props(true);value.route.query.delete('routine_revision')
 render(<RoutinePlan {...value}/>)
 expect(screen.getByText('这次检查的方案版本或材料确认信息不完整，请返回方案重新核对。')).toBeVisible()
 fireEvent.click(screen.getByRole('link',{name:'返回检查方案'}))
 const query=new URLSearchParams(location.hash.split('?')[1])
 expect(location.hash.split('?')[0]).toBe('#/testing')
 expect(query.get('view')).toBe('plans')
 expect(query.has('routine_id')).toBe(false)
 expect(currentChecksApi.preview).not.toHaveBeenCalled()
 expect(routinesApi.preparation).not.toHaveBeenCalled()
})

it('方案读取失败仍可回到原修订准备，不替换检查范围',async()=>{
 vi.mocked(routinesApi.read).mockRejectedValue(new Error('方案暂时无法读取'))
 const submit=vi.spyOn(currentChecksApi,'submit')
 render(<RoutinePlan {...props()}/>)
 expect(await screen.findByRole('alert')).toHaveTextContent('方案暂时无法读取')
 fireEvent.click(screen.getByRole('link',{name:'返回方案继续准备'}))
 const query=new URLSearchParams(location.hash.split('?')[1])
 expect(query.get('routine_id')).toBe(id)
 expect(query.get('routine_revision')).toBe('1')
 expect(query.get('section')).toBeNull()
 expect(submit).not.toHaveBeenCalled()
})
