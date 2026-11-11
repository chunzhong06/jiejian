import {fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {collaborationApi} from '../../entities/runtime/api/collaboration'
import {CollaborationHub} from './CollaborationHub'

afterEach(()=>{vi.restoreAllMocks();sessionStorage.clear()})
it('筛选无匹配保留任务事实，清除条件后恢复原范围',async()=>{
  sessionStorage.clear()
  vi.spyOn(collaborationApi,'list').mockResolvedValue([
    {task_id:'first',project_id:'app',goal:'整理展馆访问要求',purpose:'CHECK',state:'PAUSED',references:{},updated_at_us:1},
    {task_id:'second',project_id:'app',goal:'解释上次检查',purpose:'CHECK',state:'COMPLETED',references:{},updated_at_us:2},
  ] as never)
  render(<CollaborationHub projectId="app"/>);
  await screen.findByRole('link',{name:/整理展馆访问要求/})
  fireEvent.click(screen.getByRole('button',{name:'全部任务'}))
  const input=screen.getByRole('searchbox',{name:'查找协作任务'})
  fireEvent.change(input,{target:{value:'没有这个目标'}})
  expect(screen.getByRole('heading',{name:'没有符合条件的协作任务'})).toBeVisible()
  expect(screen.queryByText('当前没有进行中的任务')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'清除筛选'}))
  expect(screen.getByRole('link',{name:/解释上次检查/})).toBeVisible()
  expect(input).toHaveValue('')
})
