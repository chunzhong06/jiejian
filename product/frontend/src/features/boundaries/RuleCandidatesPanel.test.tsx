// 候选页面必须保留业务含义、精确对象与未知回执，不通过UI自动批准。
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { RuleCandidatesPanel } from './RuleCandidatesPanel'
import { ApiError } from '../../api/http'

const api = vi.hoisted(() => ({context: vi.fn(), show: vi.fn(), propose: vi.fn(), receipt: vi.fn(), decide: vi.fn()}))
vi.mock('../../api/boundaries/ruleCandidates', () => ({ruleCandidatesApi: api}))
const item = {
  candidate: {project_id:'app_a', candidate_id:'rcd_a', revision:1, submitted_via:'MCP', content:{
    original_text:'成员不得导出他人的项目包', actors:[], actions:[], permissions:[{item_id:'p1', expectation:'DENY'}],
    examples:[{description:'成员尝试导出他人的项目包', permission_item_id:'p1'}], unresolved_questions:[], unsupported_constraints:[]}},
  assessment:'REVIEWABLE', issues:[], proposal_id:null, decision:null, reuse:{message:'批准后重新核对准备材料'},
}
beforeEach(() => { vi.resetAllMocks(); api.context.mockResolvedValue({candidates:[],next_offset:null}); api.show.mockResolvedValue(item) })
afterEach(cleanup)

const meaning = () => ({...item,assessment:'NEEDS_CHANGES',issues:[{code:'NEEDS_DECISION',message:'先核对含义'}],
  candidate:{...item.candidate,basis_id:'rb_current',content:{...item.candidate.content,
    actors:[{item_id:'actor',display_name:'成员'}],actions:[{item_id:'action',display_name:'下载资料',effect_catalog:[{item_id:'effect',business_label:'文件收到'}]}],
    scenarios:[{scenario_id:'scene',scenario_fingerprint:'f'.repeat(64),original_excerpt:'成员不得导出',question:'能否下载展示版？',
      options:[{option_id:'allow',label:'允许下载',explanation:'可以收到展示版。',replacements:[{item_id:'p1',subject_actor_item_id:'actor',resource_owner_actor_item_id:'actor',business_action_item_id:'action',expectation:'ALLOW',relation:'OWNS',protected_effect_item_ids:['effect']}]},
        {option_id:'deny',label:'仅允许预览',explanation:'不提供展示版下载。',replacements:[{item_id:'p1',subject_actor_item_id:'actor',resource_owner_actor_item_id:'actor',business_action_item_id:'action',expectation:'DENY',relation:'OWNS',protected_effect_item_ids:['effect']}]}]}]}}})

it('含义选项与纠正待定同级，未选择时不预选，保存后仍需完整审阅',async()=>{
  const first=meaning();api.show.mockResolvedValue(first)
  api.decide.mockResolvedValue({...first,assessment:'REVIEWABLE',issues:[],candidate:{...first.candidate,revision:2},scenario_decisions:[{scenario_id:'scene',status:'SELECT',decision:{decision_id:'d1',option_id:'allow'}}]})
  render(<RuleCandidatesPanel projectId="app_a" requestedId="rcd_a" onSelected={vi.fn()} onProposal={vi.fn()}/> )
  await screen.findByRole('heading',{name:'能否下载展示版？'})
  expect(screen.getAllByRole('radio')).toHaveLength(4)
  screen.getAllByRole('radio').forEach(radio=>expect(radio).not.toBeChecked())
  expect(screen.queryByRole('button',{name:'继续审阅完整变更'})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'复制补充请求'})).toBeEnabled()
  fireEvent.click(screen.getByRole('radio',{name:/允许下载 可以收到/}))
  expect(screen.getByText(/针对的结果：文件收到/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'保存这个含义'}))
  await waitFor(()=>expect(screen.getByRole('button',{name:'继续审阅完整变更'})).toBeEnabled())
  expect(api.decide).toHaveBeenCalledWith('app_a','rcd_a',1,'rb_current',expect.any(String),{scenario_id:'scene',scenario_fingerprint:'f'.repeat(64),action:'SELECT',option_id:'allow'})
  expect(api.propose).not.toHaveBeenCalled()
})

it('纠正保留原话，未知结果恢复只查询DECIDE原操作',async()=>{
  api.show.mockResolvedValue(meaning());api.decide.mockRejectedValue(new ApiError('API_ERROR','连接中断'));api.receipt.mockResolvedValue({status:'UNKNOWN'})
  render(<RuleCandidatesPanel projectId="app_a" requestedId="rcd_a" onSelected={vi.fn()} onProposal={vi.fn()}/> )
  fireEvent.click(await screen.findByRole('radio',{name:/不是这个意思/}))
  expect(screen.getByRole('button',{name:'保存说明'})).toBeDisabled()
  fireEvent.change(screen.getByRole('textbox',{name:'请说明你的意思'}),{target:{value:'仅预览公开部分'}})
  fireEvent.click(screen.getByRole('button',{name:'保存说明'}))
  fireEvent.click(await screen.findByRole('button',{name:'查询原操作结果'}))
  await waitFor(()=>expect(api.receipt).toHaveBeenCalledWith('app_a',api.decide.mock.calls[0][4],'DECIDE'))
  expect(api.decide).toHaveBeenCalledOnce()
  expect(api.decide.mock.calls[0][5]).toMatchObject({action:'CORRECT',correction:'仅预览公开部分'})
  expect(api.propose).not.toHaveBeenCalled()
})

it('刷新后按URL保存的DECIDE身份查询，不重新提交人的决定',async()=>{
  api.show.mockResolvedValue(meaning());api.receipt.mockResolvedValue({status:'FOUND',candidate:{...meaning(),candidate:{...meaning().candidate,revision:2}}})
  render(<RuleCandidatesPanel projectId="app_a" requestedId="rcd_a" recoveryOperation={`DECIDE:${'a'.repeat(32)}`} onSelected={vi.fn()} onProposal={vi.fn()}/> )
  fireEvent.click(await screen.findByRole('button',{name:'查询原操作结果'}))
  await waitFor(()=>expect(api.receipt).toHaveBeenCalledWith('app_a','a'.repeat(32),'DECIDE'))
  expect(api.decide).not.toHaveBeenCalled();expect(api.propose).not.toHaveBeenCalled()
})

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
  expect(screen.queryByRole('button',{name:'继续审阅完整变更'})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'复制补充请求'})).toBeEnabled()
})

it('旧问题明确等待Agent保存情境，补充请求携带原问题和服务端修订指引', async () => {
  const question='曾开放后撤回仍违规，如何保留这一要求？'
  const original={...item,assessment:'NEEDS_CHANGES',revision_guidance:['情境选择本身不会建立历史证据。'],
    candidate:{...item.candidate,content:{...item.candidate.content,unresolved_questions:[question]}},
    issues:[{code:'NEEDS_CLARIFICATION',message:question,path:'candidate.content.unresolved_questions[0]'}]}
  api.show.mockResolvedValue(original)
  const copy=vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:copy}})
  render(<RuleCandidatesPanel projectId="app_a" requestedId="rcd_a" requestedRevision={1} onSelected={vi.fn()} onProposal={vi.fn()}/> )
  expect(await screen.findByRole('heading',{name:'还有 1 条问题等待 Agent 整理'})).toBeInTheDocument()
  expect(screen.queryByRole('region',{name:'含义核对'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'复制补充请求'}))
  await waitFor(()=>expect(copy).toHaveBeenCalledOnce())
  expect(copy.mock.calls[0][0]).toContain(question)
  expect(copy.mock.calls[0][0]).toContain('question逐字保留')
  expect(copy.mock.calls[0][0]).toContain('情境选择本身不会建立历史证据')
  expect(copy.mock.calls[0][0]).toContain('保存带情境的新修订后')
  expect(api.decide).not.toHaveBeenCalled()
  expect(api.propose).not.toHaveBeenCalled()
})

it('指定旧修订进入后显式读取最新候选，出现含义核对并更新精确引用', async () => {
  const old={...item,assessment:'NEEDS_CHANGES',candidate:{...item.candidate,content:{...item.candidate.content,unresolved_questions:['能否下载展示版？']}},issues:[]}
  const latest={...meaning(),candidate:{...meaning().candidate,revision:2}}
  api.show.mockImplementation((_project:string,_id:string,revision?:number)=>Promise.resolve(revision===1?old:latest))
  const selected=vi.fn()
  render(<RuleCandidatesPanel projectId="app_a" requestedId="rcd_a" requestedRevision={1} onSelected={selected} onProposal={vi.fn()}/> )
  await screen.findByRole('heading',{name:'还有 1 条问题等待 Agent 整理'})
  expect(api.show).toHaveBeenCalledWith('app_a','rcd_a',1)
  fireEvent.click(screen.getByRole('button',{name:'读取候选'}))
  await screen.findByRole('heading',{name:'能否下载展示版？'})
  expect(api.show).toHaveBeenLastCalledWith('app_a','rcd_a',undefined)
  expect(selected).toHaveBeenLastCalledWith('rcd_a',2)
  expect(screen.queryByRole('heading',{name:'还有 1 条问题等待 Agent 整理'})).not.toBeInTheDocument()
  expect(api.decide).not.toHaveBeenCalled()
})

it('选择已保存但仍有能力限制时引导补充，不要求重复确认', async () => {
  api.show.mockResolvedValue({...meaning(),scenario_decisions:[{scenario_id:'scene',status:'SELECT',decision:{decision_id:'d1',option_id:'deny'}}],
    issues:[{code:'RULE_KIND_UNSUPPORTED',message:'跨检查窗口的历史记录尚未确认'}]})
  render(<RuleCandidatesPanel projectId="app_a" requestedId="rcd_a" onSelected={vi.fn()} onProposal={vi.fn()}/> )
  expect(await screen.findByRole('heading',{name:'请先补充候选'})).toBeInTheDocument()
  expect(screen.queryByRole('heading',{name:'请在下方核对含义'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'继续审阅完整变更'})).not.toBeInTheDocument()
  expect(screen.getByText('跨检查窗口的历史记录尚未确认')).toBeInTheDocument()
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
