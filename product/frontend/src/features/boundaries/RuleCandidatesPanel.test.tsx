// 候选页面必须保留业务含义、精确对象与未知回执，不通过UI自动批准。
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { RuleCandidatesPanel } from './RuleCandidatesPanel'
import { ApiError } from '../../api/http'

const api = vi.hoisted(() => ({context: vi.fn(), show: vi.fn(), propose: vi.fn(), receipt: vi.fn()}))
vi.mock('../../api/boundaries/ruleCandidates', () => ({ruleCandidatesApi: api}))
const item = {
  candidate: {project_id:'app_a', candidate_id:'rcd_a', revision:1, submitted_via:'MCP', content:{
    original_text:'成员不得导出他人的项目包', actors:[], actions:[], permissions:[{item_id:'p1', expectation:'DENY'}],
    examples:[{description:'成员尝试导出他人的项目包', permission_item_id:'p1'}], unresolved_questions:[], unsupported_constraints:[]}},
  assessment:'REVIEWABLE', issues:[], proposal_id:null, decision:null, reuse:{message:'批准后重新核对准备材料'},
}
beforeEach(() => { vi.resetAllMocks(); api.context.mockResolvedValue({candidates:[],next_offset:null}); api.show.mockResolvedValue(item) })
afterEach(cleanup)

it('展示原文和例子，只创建待审提案并交回普通审批', async () => {
  const onProposal=vi.fn().mockResolvedValue(undefined)
  api.propose.mockResolvedValue({...item, proposal_id:'bpr_exact'})
  render(<RuleCandidatesPanel projectId="app_a" requestedId="rcd_a" requestedRevision={1} onSelected={vi.fn()} onProposal={onProposal}/>)
  expect(await screen.findByText('成员不得导出他人的项目包')).toBeInTheDocument()
  expect(screen.getByText('应当拒绝')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'继续审阅完整变更'}))
  await waitFor(()=>expect(onProposal).toHaveBeenCalledWith('bpr_exact'))
  expect(api.propose.mock.calls[0].slice(0,3)).toEqual(['app_a','rcd_a',1])
})

it('未知写结果仅查询原操作，不能再次创建提案', async () => {
  api.propose.mockRejectedValue(new ApiError('API_ERROR','连接中断'))
  api.receipt.mockResolvedValue({status:'UNKNOWN'})
  render(<RuleCandidatesPanel projectId="app_a" requestedId="rcd_a" onSelected={vi.fn()} onProposal={vi.fn()}/>)
  fireEvent.click(await screen.findByRole('button',{name:'继续审阅完整变更'}))
  fireEvent.click(await screen.findByRole('button',{name:'查询原操作结果'}))
  await waitFor(()=>expect(api.receipt).toHaveBeenCalledTimes(1))
  expect(api.propose).toHaveBeenCalledTimes(1)
  expect(api.receipt.mock.calls[0][1]).toBe(api.propose.mock.calls[0][3])
})

it('有未覆盖条件时禁用提案入口，并明确解释', async () => {
  api.show.mockResolvedValue({...item,assessment:'NEEDS_CHANGES',issues:[{code:'RULE_KIND_UNSUPPORTED',message:'本版不支持并发唯一性'}]})
  render(<RuleCandidatesPanel projectId="app_a" requestedId="rcd_a" onSelected={vi.fn()} onProposal={vi.fn()}/>)
  expect(await screen.findByText('本版不支持并发唯一性')).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'继续审阅完整变更'})).toBeDisabled()
})

it('刷新后恢复URL中的原操作引用，只查询不重新提交', async () => {
  api.receipt.mockResolvedValue({status:'FOUND',candidate:{...item,proposal_id:'bpr_saved'}})
  const onProposal=vi.fn().mockResolvedValue(undefined)
  render(<RuleCandidatesPanel projectId="app_a" requestedId="rcd_a" recoveryOperation={'a'.repeat(32)} onSelected={vi.fn()} onProposal={onProposal}/>)
  fireEvent.click(await screen.findByRole('button',{name:'查询原操作结果'}))
  await waitFor(()=>expect(onProposal).toHaveBeenCalledWith('bpr_saved'))
  expect(api.propose).not.toHaveBeenCalled()
  expect(api.receipt).toHaveBeenCalledWith('app_a','a'.repeat(32))
})

it('切换项目后忽略旧候选响应', async () => {
  let resolveOld: (value: typeof item)=>void=()=>{}
  api.show.mockImplementation((project:string)=>project==='app_a' ? new Promise(resolve=>{resolveOld=resolve}) : Promise.resolve({...item,candidate:{...item.candidate,project_id:'app_b',content:{...item.candidate.content,original_text:'新项目规则'}}}))
  const props={onSelected:vi.fn(),onProposal:vi.fn()}
  const view=render(<RuleCandidatesPanel {...props} projectId="app_a" requestedId="rcd_a"/>)
  await waitFor(()=>expect(api.show).toHaveBeenCalled())
  view.rerender(<RuleCandidatesPanel {...props} projectId="app_b" requestedId="rcd_b"/>)
  expect(await screen.findByText('新项目规则')).toBeInTheDocument()
  resolveOld(item)
  await waitFor(()=>expect(screen.queryByText('成员不得导出他人的项目包')).not.toBeInTheDocument())
})

it('已有相同规则时返回当前规则，不再生成待批提案', async () => {
  api.show.mockResolvedValue({...item,assessment:'ALREADY_CONFIRMED',reuse:{message:'批准后仍需核对准备',actions:[{item_id:'a',display_name:'导出项目包',status:'MISSING',materials:[],message:'尚无该动作的准备材料。'}]}})
  const onExit=vi.fn()
  render(<RuleCandidatesPanel projectId="app_a" requestedId="rcd_a" onExit={onExit} onSelected={vi.fn()} onProposal={vi.fn()}/>)
  expect(await screen.findByText('与当前规则一致')).toBeInTheDocument()
  expect(screen.getByText('需要准备')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'查看当前规则'}))
  expect(onExit).toHaveBeenCalledOnce()
  expect(api.propose).not.toHaveBeenCalled()
})
