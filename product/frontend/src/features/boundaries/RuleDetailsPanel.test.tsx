// 单规则详情保留精确修订与异步隔离，当前材料和历史安全结果独立呈现。
import {cleanup,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {RuleDetailsPanel} from './RuleDetailsPanel'
const api = vi.hoisted(()=>({read:vi.fn()}))
vi.mock('../../api/ruleDetails',()=>({ruleDetailsApi:api}))
const value = {project_id:'app_a',intent_id:'intent_a',revision:2,current:true,expectation:'DENY',sentence:'普通成员不得发布他人的资料。',action_id:'action',action_label:'发布资料',effects:[{effect_id:'effect',label:'资料被发布',description:'持久保存的发布事实'}],approval:{approved_at_us:1000000,reason:'保留所有者边界',approved_by:'本机界鉴用户'},preparation_complete:false,materials:[{key:'proof',label:'结果证明',status:'STALE',reason_codes:[]}],latest_result:{run_id:'run_old',created_at_us:1000000,applies_to_current_implementation:false,cases:[{case_id:'case_a',verdict:'SAFE',reason_codes:[]}]},history_has_more:false,unreadable_history:false,preparation_url:'/tests?materials=1',check_url:'/tests',history_url:'/history'}
const props = {projectId:'app_a',intentId:'intent_a',revision:2,onBack:vi.fn(),onEdit:vi.fn(),onNavigate:vi.fn()}
beforeEach(()=>{vi.resetAllMocks();api.read.mockResolvedValue(value)})
afterEach(cleanup)
it('历史通过不表示当前准备完成或当前实现通过',async()=>{
  render(<RuleDetailsPanel {...props}/>);
  expect(await screen.findByText('普通成员不得发布他人的资料。')).toBeInTheDocument()
  expect(api.read).toHaveBeenCalledWith('app_a','intent_a',2)
  expect(screen.getByText('仍有材料待准备')).toBeInTheDocument()
  expect(screen.getByText('有历史记录，当前实现未核验')).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'继续准备材料'})).toBeEnabled()
})
it('修订回读不匹配时不显示另一条规则',async()=>{
  api.read.mockResolvedValue({...value,revision:3})
  render(<RuleDetailsPanel {...props}/>);
  expect(await screen.findByText('这条规则暂时无法读取')).toBeInTheDocument()
  expect(screen.queryByText(value.sentence)).not.toBeInTheDocument()
})
it('较早规则请求晚返回时不覆盖当前规则',async()=>{
  let resolve:(value:unknown)=>void = ()=>undefined
  api.read.mockReturnValueOnce(new Promise(done=>{resolve=done})).mockResolvedValueOnce({...value,intent_id:'intent_b',sentence:'负责人可以发布自己的资料。'})
  const view=render(<RuleDetailsPanel {...props}/>);
  view.rerender(<RuleDetailsPanel {...props} intentId="intent_b"/>);
  expect(await screen.findByText('负责人可以发布自己的资料。')).toBeInTheDocument()
  resolve(value)
  await waitFor(()=>expect(screen.queryByText(value.sentence)).not.toBeInTheDocument())
})
