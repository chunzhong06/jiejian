import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {ValidationQuestionDecisions} from './ValidationQuestionDecisions'
import {ruleCandidatesApi,type RuleCandidateView} from '../../entities/permission/api/ruleCandidates'

afterEach(()=>{vi.restoreAllMocks();sessionStorage.clear()})

it('未知决定恢复原请求全文，并保留同候选中的其他问题',async()=>{
  const key='jiejian.validation-answer:app:candidate:2:req_owner'
  const choice={requirement_id:'req_owner',requirement_fingerprint:'f'.repeat(64),disposition:'OUT_OF_SCOPE',requirement:'上次提交的业务含义',reason:'原业务依据',time_scope:'NOT_APPLICABLE'}
  sessionStorage.setItem(key,JSON.stringify({operation:'a'.repeat(32),choice}))
  const receipt=vi.spyOn(ruleCandidatesApi,'receipt').mockResolvedValue({status:'UNKNOWN'})
  const write=vi.spyOn(ruleCandidatesApi,'scope').mockResolvedValue({candidate:{revision:3}} as RuleCandidateView)
  const changed=vi.fn()
  const value={candidate:{candidate_id:'candidate',revision:2,basis_id:'basis'},scope_review:[{fingerprint:'f'.repeat(64),status:'NEEDS_DECISION',decision:null,source:{requirement_id:'req_owner',source_excerpt:'权限边界核对 req_owner',title:'他人资源边界'}}]} as RuleCandidateView
  render(<ValidationQuestionDecisions projectId="app" value={value} busy={false} onChange={changed} onRun={async callback=>{await callback()}}/>)
  fireEvent.change(screen.getByLabelText('实际业务含义'),{target:{value:'本次尚未提交的修改'}})
  fireEvent.click(screen.getByRole('button',{name:'查询并接续原决定'}))
  await waitFor(()=>expect(changed).toHaveBeenCalled())
  expect(receipt).toHaveBeenCalledWith('app','a'.repeat(32),'DECIDE')
  expect(write).toHaveBeenCalledWith('app','candidate',2,'basis','a'.repeat(32),choice)
  expect(sessionStorage.getItem(key)).toBeNull()
})
