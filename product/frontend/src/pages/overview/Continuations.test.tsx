import {fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {routinesApi} from '../../entities/check/api/routines'
import {Continuations} from './Continuations'

afterEach(()=>{vi.restoreAllMocks();sessionStorage.clear()})
it('工作台继续准确的方案修订和环境绑定，保留工作台回程',async()=>{
 vi.spyOn(routinesApi,'catalog').mockResolvedValue({project_id:'app',routines:[{routine_id:'exact',revision:7,name:'日常检查',scope_kind:'PERMISSIONS',permission_count:2,created_at_us:1}],legacy_selections:[]})
 render(<Continuations projectId="app" issues={[]}/> )
 const link=await screen.findByRole('link',{name:/日常检查/})
 const query=new URLSearchParams(link.getAttribute('href')!.split('?')[1])
 expect(query.get('routine_id')).toBe('exact')
 expect(query.get('routine_revision')).toBe('7')
 expect(link.getAttribute('href')).toMatch(/^#\/reports\?/)
 expect(query.get('view')).toBe('plan')
 expect(query.get('return_to')).toBe('/workspace')
})

it('切换沿用内容并离开后，恢复所选方案的准确修订而不创建运行',async()=>{
 vi.spyOn(routinesApi,'catalog').mockResolvedValue({project_id:'app',routines:[{routine_id:'first',revision:1,name:'日常检查',scope_kind:'PERMISSIONS',permission_count:2,created_at_us:1},{routine_id:'second',revision:4,name:'每周复验',scope_kind:'SCENARIO',permission_count:0,created_at_us:2}],legacy_selections:[]})
 const first=render(<Continuations projectId="app" issues={[]}/> )
 const choice=await screen.findByRole('combobox',{name:'沿用哪份检查内容'})
 fireEvent.mouseDown(choice)
 fireEvent.click(await screen.findByText('每周复验'))
 const link=await screen.findByRole('link',{name:'准备这次检查：每周复验'})
 expect(new URLSearchParams(link.getAttribute('href')!.split('?')[1]).get('routine_revision')).toBe('4')
 first.unmount();render(<Continuations projectId="app" issues={[]}/> )
 const restored=await screen.findByRole('link',{name:'准备这次检查：每周复验'})
 expect(new URLSearchParams(restored.getAttribute('href')!.split('?')[1]).get('routine_id')).toBe('second')
 expect(screen.queryByText('待处理问题')).not.toBeInTheDocument()
})
