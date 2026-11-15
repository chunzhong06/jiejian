import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {ExampleLab} from './ExampleLab'
import {experienceApi} from '../../entities/application/api/experience'
import {repairsApi} from '../../entities/check/api/repairs'

afterEach(()=>vi.restoreAllMocks())
function setup(allowed=true){
  let loaded=false
  vi.spyOn(experienceApi,'status').mockImplementation(async()=>({project_id:'project',active:true,scenario_version:loaded?'VULNERABLE':'BASELINE',current_change_id:null}) as never)
  vi.spyOn(experienceApi,'development').mockImplementation(async()=>({project_id:'project',implementation:loaded?'VULNERABLE':'BASELINE',current_change_id:loaded?'change-1':null,transition_basis:'reviewed-basis',change_options:[{version:'VULNERABLE',available:allowed,reason:allowed?null:'先完成正常起点的真实检查。'},{version:'EXPOSE_REVOKE',available:false,reason:'先检查这次修改。'}]}) as never)
  vi.spyOn(repairsApi,'project').mockResolvedValue({project_id:'project',tasks:[]} as never)
  return ()=>{loaded=true}
}
it('先说明修改、原要求和检查目的，取消不切换源码',async()=>{
 setup();const write=vi.spyOn(experienceApi,'switchVersion')
 render(<ExampleLab projectId="project" onChanged={vi.fn()} onError={vi.fn()} focused/>);
 expect(await screen.findByRole('heading',{name:'移除内部包下载限制'})).toBeVisible()
 expect(within(screen.getByRole('region',{name:'移除内部包下载限制'})).getByRole('heading',{name:'保持的访问要求'})).toBeVisible()
 expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
 fireEvent.click(screen.getByRole('button',{name:'加载这次错误修改'}))
 fireEvent.click(screen.getByRole('button',{name:'取消'}))
 expect(write).not.toHaveBeenCalled()
})
it('没有真实正常起点时直接解释不可用原因',async()=>{
 setup(false)
 render(<ExampleLab projectId="project" onChanged={vi.fn()} onError={vi.fn()} focused/>);
 expect(await screen.findByRole('button',{name:'加载这次错误修改'})).toBeDisabled()
 expect(screen.getByText('先完成正常起点的真实检查。')).toBeVisible()
})
it('未知回执只查询原加载，确认完成后恢复准确检查入口',async()=>{
 const loaded=setup(),write=vi.spyOn(experienceApi,'switchVersion').mockRejectedValue(new Error('连接中断'))
 render(<ExampleLab projectId="project" onChanged={vi.fn()} onError={vi.fn()} focused/>);
 fireEvent.click(await screen.findByRole('button',{name:'加载这次错误修改'}))
 fireEvent.click(screen.getByRole('button',{name:'确认加载这份修改'}))
 await screen.findByText('加载结果尚未确认')
 expect(write).toHaveBeenCalledExactlyOnceWith('VULNERABLE',undefined,{project_id:'project',expected_basis:'reviewed-basis'})
 loaded();fireEvent.click(screen.getByRole('button',{name:'查询本次加载结果'}))
 expect(await screen.findByRole('link',{name:'准备这份修改的检查'})).toHaveAttribute('href',expect.stringContaining('change_id=change-1'))
 await waitFor(()=>expect(screen.queryByRole('button',{name:'查询本次加载结果'})).not.toBeInTheDocument())
 expect(write).toHaveBeenCalledTimes(1)
})
it('已检查的修改直接回到准确结果，不再引导重复准备',async()=>{
 setup()
 vi.mocked(experienceApi.status).mockResolvedValue({project_id:'project',active:true,scenario_version:'EXPOSE_REVOKE'} as never)
 vi.mocked(experienceApi.development).mockResolvedValue({project_id:'project',implementation:'EXPOSE_REVOKE',current_change_id:'change-2',run_id:'run-2',transition_basis:'basis',change_options:[]} as never)
 render(<ExampleLab projectId="project" onChanged={vi.fn()} onError={vi.fn()} focused/>);
 expect(await screen.findByRole('link',{name:'阅读这份修改的结果'})).toHaveAttribute('href',expect.stringContaining('run_id=run-2'))
 expect(screen.queryByRole('link',{name:'准备这份修改的检查'})).not.toBeInTheDocument()
})
