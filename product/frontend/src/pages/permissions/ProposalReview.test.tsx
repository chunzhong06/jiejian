import {fireEvent,render,screen,within} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import type {BoundaryProposalViewDto,BoundaryReviewValueDto} from '../../entities/permission/api/businessBoundaries'
import {ProposalReview} from './ProposalReview'

const rule=(patch:Partial<BoundaryReviewValueDto>={}):BoundaryReviewValueDto=>({display_name:'下载资料',description:'',effective_state:'ACTIVE',resource_concept:'资料',operation_kind:null,state_changing:null,effects:[],subject:'负责人',resource_owner:'负责人',action:'下载资料',relation:'OWNS',expectation:'ALLOW',protected_effects:['资料已接收'],...patch})
const item=(id:string,value:BoundaryReviewValueDto)=>({entity_kind:'PERMISSION' as const,item_id:id,entity_id:null,basis_revision:null,change_kind:'CREATE' as const,basis_available:true,before:null,after:value})
function proposal():BoundaryProposalViewDto{return {
  proposal:{proposal_id:'proposal',project_id:'app',proposal_fingerprint:'basis',created_at_us:1,source_snapshot:{},provenance:'负责人确认的资料访问要求',proposed_actors:[],proposed_actions:[],proposed_permissions:[]},
  decision:null,change_summary:null,
  review:{basis_state:'COMPLETE',current_state_changed:false,items:[item('owner',rule()),item('reviewer',rule({subject:'评审',relation:'OTHER_ROLE',expectation:'DENY',protected_effects:['内部资料已接收','内部访问权被开放']})),{...item('definition',rule({expectation:null,action:null,description:'下载已有资料，不改变业务状态',effects:[]})),entity_kind:'ACTION'}]},
}}

it('概览保留全部规则，单项详情与分类切换保留阅读对象',()=>{
  const back=vi.fn()
  render(<ProposalReview value={proposal()} onBack={back}><footer>整份提案的确认区域</footer></ProposalReview>)
  const detail=()=>within(screen.getByRole('complementary'))
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  expect(screen.getByRole('table')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:/^负责人可以下载资料/}))
  expect(detail().getByText('资料已接收')).toBeVisible()
  expect(detail().queryByText('内部访问权被开放')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:/^评审不得下载资料/}))
  expect(detail().getByText('评审不得下载资料')).toBeVisible()
  expect(detail().getByText('内部资料已接收')).toBeVisible()
  expect(detail().getByText('内部访问权被开放')).toBeVisible()
  fireEvent.click(screen.getByRole('tab',{name:'业务定义 1'}))
  expect(detail().getByText('下载已有资料，不改变业务状态')).toBeVisible()
  fireEvent.click(screen.getByText('提案来源',{selector:'summary'}))
  expect(screen.getByText('负责人确认的资料访问要求')).toBeVisible()
  fireEvent.click(screen.getByRole('tab',{name:'访问规则 2'}))
  expect(detail().getByText('评审不得下载资料')).toBeVisible()
  expect(screen.getByText('整份提案的确认区域')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'收起详情'}))
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:/^评审不得下载资料/})).toHaveFocus()
  fireEvent.click(screen.getByRole('button',{name:'全部权限规则'}))
  expect(back).toHaveBeenCalledOnce()
})

it('调整保留准确的前后规则，原版本不可用时明确保留核对缺口',()=>{
  const value=proposal(),first=value.review!.items[0]
  first.change_kind='UPDATE';first.before=rule({protected_effects:['旧的接收范围']})
  const rendered=render(<ProposalReview value={value} onBack={vi.fn()}>确认</ProposalReview>)
  fireEvent.click(screen.getByRole('button',{name:/^负责人可以下载资料/}))
  const detail=within(screen.getByRole('complementary'))
  expect(detail.getByText('现在')).toBeVisible()
  expect(detail.getByText('旧的接收范围')).toBeVisible()
  expect(detail.getByText('批准后')).toBeVisible()
  expect(detail.getByText('资料已接收')).toBeVisible()
  first.basis_available=false
  rendered.rerender(<ProposalReview value={value} onBack={vi.fn()}>确认</ProposalReview>)
  expect(screen.getByText('原版本不可用，无法核对变化。')).toBeVisible()
  expect(screen.queryByText('旧的接收范围')).not.toBeInTheDocument()
})

it('停用与沿用有区别，缺失审阅投影不会显示虚构的规则',()=>{
  const value=proposal(),first=value.review!.items[0]
  first.change_kind='RETIRE';first.before=rule();first.after={...first.after,effective_state:'RETIRED'}
  const rendered=render(<ProposalReview value={value} onBack={vi.fn()}>确认</ProposalReview>)
  fireEvent.click(screen.getByRole('button',{name:/^负责人可以下载资料/}))
  expect(screen.getByText('将停用')).toBeVisible()
  first.change_kind='REFERENCE';first.after={...first.after,effective_state:'ACTIVE'}
  rendered.rerender(<ProposalReview value={value} onBack={vi.fn()}>确认</ProposalReview>)
  expect(within(screen.getByRole('complementary')).getByText('沿用')).toBeVisible()
  rendered.rerender(<ProposalReview value={{...value,review:null}} onBack={vi.fn()}>确认</ProposalReview>)
  expect(screen.getByText('这份提案没有调整访问规则。')).toBeVisible()
})
