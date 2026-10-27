import {renderHook,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {useApplication} from './useApplication'
import {projectsApi} from '../../entities/application/api/projects'
import {experienceApi} from '../../entities/application/api/experience'
import {workspaceApi} from '../../entities/workspace/api/workspace'

it('准备页不读取完整工作区，返回概览后才读取',async()=>{
  vi.spyOn(projectsApi,'projects').mockResolvedValue([{project_id:'a',name:'展馆'}] as never)
  vi.spyOn(experienceApi,'status').mockResolvedValue({} as never)
  const workspace=vi.spyOn(workspaceApi,'current').mockResolvedValue({project:{project_id:'a'}} as never)
  const view=renderHook(({path})=>useApplication(path),{initialProps:{path:'/preparation'}})
  await waitFor(()=>expect(view.result.current.project?.project_id).toBe('a'))
  expect(workspace).not.toHaveBeenCalled()
  view.rerender({path:'/workspace'})
  await waitFor(()=>expect(workspace).toHaveBeenCalledTimes(1))
  view.rerender({path:'/preparation'})
  expect(workspace).toHaveBeenCalledTimes(1)
})
