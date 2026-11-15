import {render,screen} from '@testing-library/react'
import {expect,it} from 'vitest'
import {PreparationReview} from './PreparationReview'
import type {CheckPreview} from '../../check/api/currentChecks'

const preview={project_id:'app',plan_fingerprint:'current',preparation_work:{project_id:'app',plan_fingerprint:'current',impacts:[
  {action_id:'edit',action_label:'修改申请',kind:'identity',member_id:'owner',member_label:'原资源所有者',handling:'KEEP',handler:'SYSTEM',explanation:'保留原主体与资源对应。',next_step:'提交前重核。'},
  {action_id:'edit',action_label:'修改申请',kind:'resource',member_id:'resource',member_label:'申请记录',handling:'DECIDE',handler:'USER',explanation:'资源归属发生冲突。',next_step:'核对实际归属。'},
]}} as unknown as CheckPreview

it('同一预览中能一起审阅保留项和需要用户决定的冲突',()=>{
  render(<PreparationReview preview={preview}/>)
  expect(screen.getByText('沿用')).toBeInTheDocument()
  expect(screen.getByText('需要决定')).toBeInTheDocument()
  expect(screen.getByText('保留原主体与资源对应。')).toBeInTheDocument()
  expect(screen.getByText('用户确认')).toBeInTheDocument()
})

it('材料属于其他预览时不混入当前处理方案',()=>{
  render(<PreparationReview preview={{...preview,plan_fingerprint:'changed'}}/>)
  expect(screen.queryByText('本次材料处理方案')).not.toBeInTheDocument()
})
