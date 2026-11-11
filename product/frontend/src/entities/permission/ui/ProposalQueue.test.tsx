import {fireEvent,render,screen} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import type {BoundaryEditorDto} from '../api/businessBoundaries'
import type {RuleCandidateContext} from '../api/ruleCandidates'
import {ProposalQueue,RequirementQueue} from './ProposalQueue'

it('同类待审提案可区分并打开准确原对象，忙碌期间不重复打开',()=>{
  const review=vi.fn(),items:BoundaryEditorDto['pending_proposals']=[
    {proposal_id:'first',created_at_us:1_000_000,change_summary:null},
    {proposal_id:'second',created_at_us:2_000_000,change_summary:{new_actor_count:2,new_action_count:1,permission_updates:['rule'],permission_retirements:[],business_revision_updates:[],retirements:[],permission_carry_forwards:[],implementation_rebinds:[],unresolved_count:0,change_codes:[]}},
  ]
  const view=render(<ProposalQueue items={items} onReview={review}/>)
  const second=screen.getByRole('button',{name:/新增 2 个角色，新增 1 项操作，调整 1 条访问要求/})
  fireEvent.click(second);expect(review).toHaveBeenCalledExactlyOnceWith('second')
  view.rerender(<ProposalQueue items={items} busy onReview={review}/>);fireEvent.click(second)
  expect(review).toHaveBeenCalledTimes(1)
})

it('业务要求保留准确修订，已决定和归档内容不混入当前队列',()=>{
  const review=vi.fn(),items=[
    {candidate_id:'active',revision:3,original_text:'评审只能下载公开展示版',created_at_us:1_000_000,decision:null},
    {candidate_id:'decided',revision:1,original_text:'已经决定的要求',created_at_us:1_000_000,decision:'APPROVED'},
    {candidate_id:'archived',revision:2,original_text:'已归档要求',created_at_us:1_000_000,decision:null,visibility:{archived:true}},
  ] as RuleCandidateContext['candidates']
  render(<RequirementQueue items={items} onReview={review}/>)
  fireEvent.click(screen.getByRole('button',{name:/评审只能下载公开展示版/}))
  expect(review).toHaveBeenCalledExactlyOnceWith('active',3)
  expect(screen.queryByRole('button',{name:/已经决定|已归档/})).not.toBeInTheDocument()
})
