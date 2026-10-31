import {act,renderHook,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {useApplication} from './useApplication'
import {projectsApi} from '../../entities/application/api/projects'
import {experienceApi} from '../../entities/application/api/experience'
import {workspaceApi} from '../../entities/workspace/api/workspace'

it('准备页不读取完整工作区，返回概览后才读取',async()=>{
  vi.spyOn(projectsApi,'projects').mockResolvedValue([{project_id:'a',name:'展馆'}] as never)
  vi.spyOn(experienceApi,'status').mockResolvedValue({} as never)
  vi.spyOn(workspaceApi,'revision').mockResolvedValue({revision:'1'})
  const workspace=vi.spyOn(workspaceApi,'current').mockResolvedValue({project:{project_id:'a'}} as never)
  const view=renderHook(({path})=>useApplication(path,{path,query:new URLSearchParams()}),{initialProps:{path:'/preparation'}})
  await waitFor(()=>expect(view.result.current.project?.project_id).toBe('a'))
  expect(workspace).not.toHaveBeenCalled()
  view.rerender({path:'/workspace'})
  await waitFor(()=>expect(workspace).toHaveBeenCalledTimes(1))
  view.rerender({path:'/preparation'})
  expect(workspace).toHaveBeenCalledTimes(1)
})

it('修订变化提前刷新工作区，独立文件核验仍按原周期进行',async()=>{
  vi.useFakeTimers()
  vi.spyOn(projectsApi,'projects').mockResolvedValue([{project_id:'a',name:'展馆'}] as never)
  vi.spyOn(experienceApi,'status').mockResolvedValue({} as never)
  const revision=vi.spyOn(workspaceApi,'revision').mockResolvedValue({revision:'1'})
  const workspace=vi.spyOn(workspaceApi,'current').mockResolvedValue({project:{project_id:'a'}} as never)
  const view=renderHook(()=>useApplication('/workspace',{path:'/workspace',query:new URLSearchParams()}))
  try{
    await act(async()=>{})
    expect(workspace).toHaveBeenCalledTimes(1)
    await act(async()=>{await vi.advanceTimersByTimeAsync(2000)})
    expect(revision).toHaveBeenCalledTimes(2)
    expect(workspace).toHaveBeenCalledTimes(1)
    revision.mockResolvedValue({revision:'2'})
    await act(async()=>{await vi.advanceTimersByTimeAsync(2000)})
    expect(workspace).toHaveBeenCalledTimes(2)
    await act(async()=>{await vi.advanceTimersByTimeAsync(10000)})
    expect(workspace).toHaveBeenCalledTimes(3)
  }finally{view.unmount();vi.useRealTimers()}
})
