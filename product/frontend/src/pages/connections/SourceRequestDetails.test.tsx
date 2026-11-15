import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {SourceRequestDetails} from './SourceRequestDetails'
import {projectsApi} from '../../entities/application/api/projects'
import {workbenchApi} from '../../entities/application/api/workbench'

it('明确排除绑定展示时的来源修订，保存后回读当前事实',async()=>{
  vi.spyOn(projectsApi,'understanding').mockResolvedValue({revision:7} as never)
  const review=vi.spyOn(workbenchApi,'review').mockResolvedValue({revision:8} as never)
  const reload=vi.fn()
  render(<SourceRequestDetails projectId="app" source={{source_id:'source',revision:2,name:'订单接口',kind:'OPENAPI',requests:[],warnings:[],created_at_us:1}}
    request={{item_id:'request',method:'GET',path:'/orders',label:'订单列表',pointer:'pointer',parameters:[]}}
    actions={[]} businessReady onDraft={()=>{}} onSave={async()=>{}} onUpdate={()=>{}} onReviewed={reload}
    act={async task=>{await task()}} busy={false}/>)
  fireEvent.click(screen.getByRole('button',{name:'此线索不纳入当前要求'}))
  await waitFor(()=>expect(review).toHaveBeenCalledWith('app','source','request',7,2,'REJECTED'))
  expect(reload).toHaveBeenCalledOnce()
})
