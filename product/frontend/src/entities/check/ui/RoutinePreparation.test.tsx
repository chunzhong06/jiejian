import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {RoutinePreparation} from './RoutinePreparation'
import {routinesApi,type CheckRoutine,type RoutineBinding} from '../api/routines'
import {currentChecksApi} from '../api/currentChecks'

afterEach(()=>{vi.restoreAllMocks();sessionStorage.clear()})
it('确认材料只采用准确方案修订并进入预览，回执未到前不能开始检查',async()=>{
 const document={project_id:'app',routine_id:'exact',revision:7,name:'日常检查',requirements:[]} as unknown as CheckRoutine
 vi.spyOn(routinesApi,'preparation').mockResolvedValue({project_id:'app',can_bind:true,assets:[],environment:{environment_id:'env',revision:1,target:{base_url:'http://127.0.0.1:8080'}},environment_fingerprint:'environment',material_fingerprint:'materials'} as never)
 vi.spyOn(routinesApi,'bindings').mockResolvedValue([])
 const binding:RoutineBinding={document_type:'jiejian.check-routine-binding',schema_version:'1',project_id:'app',routine_id:'exact',routine_revision:7,binding_id:'binding',routine_fingerprint:'routine',environment_id:'env',environment_revision:1,environment_fingerprint:'environment',material_fingerprint:'materials',assets:[],created_at_us:1}
 let complete!:(value:RoutineBinding)=>void
 const bind=vi.spyOn(routinesApi,'bind').mockImplementation(()=>new Promise(resolve=>{complete=resolve}))
 const submit=vi.spyOn(currentChecksApi,'submit'),onBound=vi.fn()
 render(<RoutinePreparation projectId="app" document={document} dirty={false} origin="/reports?view=plan&routine_id=exact&routine_revision=7" onBound={onBound}/>)
 fireEvent.click(await screen.findByRole('button',{name:'确认使用这些材料'}))
 expect(onBound).not.toHaveBeenCalled();expect(submit).not.toHaveBeenCalled()
 expect(bind.mock.calls[0].slice(0,2)).toEqual(['app','exact'])
 expect(bind.mock.calls[0][2]).toMatchObject({revision:7,expected_material_fingerprint:'materials',expected_environment_fingerprint:'environment'})
 complete(binding);await waitFor(()=>expect(onBound).toHaveBeenCalledExactlyOnceWith(binding))
 expect(submit).not.toHaveBeenCalled()
})

it('没有检查连接时引导补充连接并保留准确方案回程，不重复准备材料',async()=>{
 const document={project_id:'app',routine_id:'exact',revision:7,name:'日常检查',requirements:[]} as unknown as CheckRoutine
 vi.spyOn(routinesApi,'preparation').mockResolvedValue({project_id:'app',can_bind:false,assets:[],environment:null,environment_fingerprint:null,material_fingerprint:null} as never)
 vi.spyOn(routinesApi,'bindings').mockResolvedValue([])
 const bind=vi.spyOn(routinesApi,'bind')
 render(<RoutinePreparation official projectId="app" document={document} dirty={false} origin="/reports?view=plan&routine_id=exact&routine_revision=7"/>)
 const link=await screen.findByRole('link',{name:'设置检查连接'})
 const target=new URL(link.getAttribute('href')!.slice(1),'http://local')
 expect(target.pathname).toBe('/application')
 expect(target.searchParams.get('return_to')).toContain('routine_revision=7')
 expect(screen.queryByRole('link',{name:'核对应用连接'})).not.toBeInTheDocument()
 const content=new URL(screen.getByRole('link',{name:'查看方案内容'}).getAttribute('href')!.slice(1),'http://local')
 expect(content.pathname).toBe('/testing')
 expect(content.searchParams.get('routine_revision')).toBe('7')
 expect(content.searchParams.get('section')).toBe('content')
 expect(content.searchParams.get('return_to')).toContain('routine_revision=7')
 expect(screen.queryByRole('button',{name:'一键准备示例材料'})).not.toBeInTheDocument()
 expect(bind).not.toHaveBeenCalled()
})
