import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {OfficialRepair} from './OfficialRepair'
import {experienceApi} from '../../application/api/experience'
import {sourceChangesApi} from '../../source-change/api/sourceChanges'
import type {RepairContract} from '../api/repairs'

const contract={source_run_id:'original',source_case_id:'original-case',repair_fingerprint:'exact'} as RepairContract
afterEach(()=>vi.restoreAllMocks())
function setup(){
  vi.spyOn(experienceApi,'status').mockResolvedValue({project_id:'project',active:true,scenario_version:'VULNERABLE'} as never)
  vi.spyOn(experienceApi,'development').mockResolvedValue({project_id:'project',implementation:'VULNERABLE',transition_basis:'basis',has_active_tasks:false} as never)
  vi.spyOn(sourceChangesApi,'show').mockResolvedValue({manifest:{project_id:'project',repair_reference:contract}} as never)
  const onLoaded=vi.fn(),onError=vi.fn()
  render(<OfficialRepair projectId="project" contract={contract} onLoaded={onLoaded} onError={onError} fallback={<p>自行登记修改</p>}/>)
  return {onLoaded,onError}
}
it('取消不写入，确认携带当前原题和依据，加载完成仍不显示复验通过',async()=>{
  const write=vi.spyOn(experienceApi,'switchVersion').mockResolvedValue({project_id:'project',scenario_version:'FIXED',current_change_id:'change'} as never)
  const {onLoaded}=setup()
  fireEvent.click(await screen.findByRole('button',{name:'加载这份预置修复'}))
  fireEvent.click(screen.getByRole('button',{name:'取消'}))
  expect(write).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'加载这份预置修复'}))
  fireEvent.click(screen.getByRole('button',{name:'确认加载修复'}))
  await waitFor(()=>expect(onLoaded).toHaveBeenCalledWith('change'))
  expect(write).toHaveBeenCalledExactlyOnceWith('FIXED',contract,{project_id:'project',expected_basis:'basis'})
  expect(screen.queryByText('原问题已解决')).not.toBeInTheDocument()
})
it('未知响应只查询原加载并核对准确关联，不重复切换源码',async()=>{
  const write=vi.spyOn(experienceApi,'switchVersion').mockRejectedValue(new Error('中断'))
  const {onLoaded}=setup()
  fireEvent.click(await screen.findByRole('button',{name:'加载这份预置修复'}))
  fireEvent.click(screen.getByRole('button',{name:'确认加载修复'}))
  await screen.findByText('修复加载结果尚未确认')
  vi.mocked(experienceApi.status).mockResolvedValue({project_id:'project',scenario_version:'FIXED',current_change_id:'change'} as never)
  vi.mocked(sourceChangesApi.show).mockResolvedValueOnce({manifest:{project_id:'project',repair_reference:{...contract,source_case_id:'other'}}} as never)
  fireEvent.click(screen.getByRole('button',{name:'查询本次修复加载'}))
  await waitFor(()=>expect(sourceChangesApi.show).toHaveBeenCalledTimes(1))
  expect(onLoaded).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'查询本次修复加载'}))
  await waitFor(()=>expect(onLoaded).toHaveBeenCalledWith('change'))
  expect(write).toHaveBeenCalledTimes(1)
})

it('选择自行修改时只保留该方式的推进动作',async()=>{
  setup()
  await screen.findByRole('button',{name:'加载这份预置修复'})
  fireEvent.click(screen.getByText('自行修改代码'))
  await waitFor(()=>expect(screen.queryByRole('button',{name:'加载这份预置修复'})).not.toBeInTheDocument())
  expect(screen.getByText('自行登记修改')).toBeVisible()
  expect(screen.getByText('在开发工具中修改代码，再登记并按本题复验。')).toBeVisible()
})
