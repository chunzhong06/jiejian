// 核验无情境问题的直接确认、必填依据、限制分类及历史只读。
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { BoundaryReview } from './BoundaryReview'
import type { RuleCandidateView } from '../../api/boundaries/ruleCandidates'

afterEach(cleanup)
const value = (source='unresolved_questions') => ({candidate:{revision:6,content:{permissions:[],examples:[]}},boundary_reviews:[{
  issue_id:'issue1',issue_fingerprint:'fp1',text:'登录接口需要单独建模吗？',source,status:'NEEDS_DECISION',blocking:true,decision:null,
}]} as unknown as RuleCandidateView)

it('无需权限选项也能保存人的范围决定，必须保留依据及实际要求',async()=>{
  const onSave=vi.fn()
  render(<BoundaryReview value={value()} readOnly={false} busy={false} onSave={onSave}/>)
  fireEvent.click(screen.getByText('填写核对意见'))
  expect(screen.getByRole('button',{name:'保存这条核对'})).toBeDisabled()
  fireEvent.mouseDown(screen.getByRole('combobox'))
  fireEvent.click(await screen.findByText('不作为独立业务动作'))
  fireEvent.change(screen.getByRole('textbox',{name:'判断依据'}),{target:{value:'登录是账号准备入口'}})
  expect(screen.getByRole('button',{name:'保存这条核对'})).toBeDisabled()
  fireEvent.change(screen.getByRole('textbox',{name:'仍然需要满足的实际业务要求'}),{target:{value:'评审不得取得内部包'}})
  fireEvent.click(screen.getByRole('button',{name:'保存这条核对'}))
  expect(onSave).toHaveBeenCalledWith({issue_id:'issue1',issue_fingerprint:'fp1',outcome:'NOT_SEPARATE_ACTION',reason:'登录是账号准备入口',retained_requirement:'评审不得取得内部包',permission_item_ids:[]})
})

it('能力限制没有不建模或已由权限表达的跳过选项，历史保留决定且不可编辑',async()=>{
  const page=render(<BoundaryReview value={value('unsupported_constraints')} readOnly={false} busy={false} onSave={vi.fn()}/>)
  fireEvent.click(screen.getByText('填写核对意见'));fireEvent.mouseDown(screen.getByRole('combobox'))
  expect(await screen.findByText('真实要求，缺少证明')).toBeInTheDocument()
  expect(screen.queryByText('不作为独立业务动作')).not.toBeInTheDocument()
  expect(screen.queryByText('实际要求已由下列权限表达')).not.toBeInTheDocument()
  const history=value('unsupported_constraints');history.boundary_reviews![0].decision={issue_id:'issue1',issue_fingerprint:'fp1',outcome:'EVIDENCE_GAP',reason:'缺少过程记录',retained_requirement:'先开放再撤回仍违规',output_revision:7}
  history.boundary_reviews![0].status='OPEN'
  page.rerender(<BoundaryReview value={history} readOnly busy={false} onSave={vi.fn()}/>)
  expect(screen.getByText('先开放再撤回仍违规')).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'保存这条核对'})).not.toBeInTheDocument()
})
