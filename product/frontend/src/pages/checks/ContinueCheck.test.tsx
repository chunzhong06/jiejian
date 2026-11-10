import {render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {ContinueCheck,continuationDestination} from './ContinueCheck'
import {currentChecksApi,type CheckContinuation} from '../../entities/check/api/currentChecks'
import {readPending} from '../../shared/lib/operations'
import {replaceDestination} from '../../shared/lib/navigation'

vi.mock('../../shared/lib/navigation',async original=>({...await original<object>(),replaceDestination:vi.fn()}))
const project='project',run='run_original',permission={intent_id:'one',revision:3,intent_hash:'a'.repeat(64)}
const value=():CheckContinuation=>({project_id:project,run_id:run,state:'AVAILABLE',message:'已找回原检查',permissions:[permission],routine:null,scenario:null,change_id:null,repair:null,external_recheck:false})
const props=()=>({projectId:project,name:'订单',official:false,refresh:vi.fn(),onError:vi.fn(),route:{path:'/reports',query:new URLSearchParams({resume_run:run,return_to:'/reports?run_id='+run})}})
beforeEach(()=>sessionStorage.clear())
afterEach(()=>vi.restoreAllMocks())

it('仅run深链接恢复准确规则，不读取之前留下的全量选择，也不直接提交',async()=>{
 vi.spyOn(currentChecksApi,'continuation').mockResolvedValue(value())
 render(<ContinueCheck {...props()}/>);await waitFor(()=>expect(replaceDestination).toHaveBeenCalledOnce())
 const path=vi.mocked(replaceDestination).mock.calls[0][0],query=new URL(path,'http://localhost').searchParams
 expect(query.get('view')).toBe('plan');expect(query.get('resume_run')).toBeNull()
 expect(readPending(`jiejian.studio.scope:${project}:${query.get('scope_id')}`)).toEqual({refs:[permission]})
 expect(query.get('return_to')).toBe('/reports?run_id='+run)
})

it.each(['WAITING','UNAVAILABLE'] as const)('原输入%s时保留原记录入口，不进入默认检查',async state=>{
 vi.spyOn(currentChecksApi,'continuation').mockResolvedValue({...value(),state,message:'原运行需要核对'})
 render(<ContinueCheck {...props()}/>);expect(await screen.findByRole('link',{name:state==='WAITING'?'查看原检查进度':'返回原记录'})).toHaveAttribute('href',expect.stringContaining(run))
 expect(replaceDestination).not.toHaveBeenCalled()
})

it('恢复方案准确旧修订、绑定及修改上下文',()=>{
 const current={...value(),routine:{routine_id:'saved',revision:2,binding_id:'binding-old'},change_id:'change-old'}
 const query=new URL(continuationDestination(project,current,'/reports?run_id='+run),'http://localhost').searchParams
 expect(Object.fromEntries(query)).toMatchObject({routine_id:'saved',routine_revision:'2',binding_id:'binding-old',change_id:'change-old'})
 expect(query.has('scope_id')).toBe(false)
})

it('外部复验回到准确原题，业务场景保留原修订',()=>{
 const repair={source_run_id:run,source_case_id:'original-case',repair_fingerprint:'b'.repeat(64)}
 const external=new URL(continuationDestination(project,{...value(),repair,external_recheck:true},'/issues'),'http://localhost')
 expect(external.pathname).toBe('/issues');expect(external.searchParams.get('source_case_id')).toBe('original-case')
 const scenario=new URL(continuationDestination(project,{...value(),scenario:{scenario_id:'scenario',revision:4}},'/testing'),'http://localhost')
 expect(scenario.searchParams.get('scenario_revision')).toBe('4')
})
