// 验证 R3 总览、单项导航与证据归属隔离；重排界面不能改变服务端结论。
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { StoryTraceEvent } from '../../api/currentChecks'
import { CurrentResultStory } from './CurrentResultStory'
import { story, outcome } from './testing.fixtures'
import { WorkPageVisible } from '../../app/RetainedWorkPages'
const api = vi.hoisted(() => ({ evidence: vi.fn() }))
vi.mock('../../api/currentChecks', () => ({ currentChecksApi: api }))
vi.mock('../assistant/AssistantPanel', () => ({ AssistantPanel: () => null }))
beforeEach(() => { vi.clearAllMocks(); vi.spyOn(window,'scrollTo').mockImplementation(() => {}) })
const node: StoryTraceEvent = { event_id:'task',parent_event_ids:[],kind:'MESSAGE',authorization_decision:null,effect_id:null,dispatch_effect_ids:[],source_component:'应用服务',source_location:'task-record' }
const evidence = () => ({schema_version:'1',run_id:'r1',action_id:'a1',case:{case_id:'c1'},evidence_id:'ev1',outcome,observations:[],trace:null})
const inspect = () => fireEvent.click(screen.getByRole('button',{name:'查看第 1 项依据'}))
const inspectTrace = () => { inspect(); fireEvent.click(screen.getByRole('button',{name:'执行过程'})) }
const openSource = () => { const button=screen.getByRole('button',{name:'查看资源状态证据'}); button.focus(); fireEvent.click(button) }

describe('结果总览与单项调查', () => {
  it('默认总览不展开单项或路径，返回恢复原行焦点并提供精确 Case 回调', () => {
    const value=story();value.actions[0].execution_path={complete:true,reason_codes:[],evidence_refs:['ev1'],events:[node]}
    const change=vi.fn();render(<CurrentResultStory story={value} onError={vi.fn()} onCaseChange={change}/>)
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.queryByRole('navigation',{name:'检查项详情'})).not.toBeInTheDocument()
    expect(screen.queryByRole('button',{name:'查看任务派发的发布证据'})).not.toBeInTheDocument()
    inspect(); expect(change).toHaveBeenCalledWith('c1')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByRole('region',{name:'判断依据'})).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'← 返回 1 项结果'}))
    expect(change).toHaveBeenLastCalledWith(null)
    expect(screen.getByRole('button',{name:'查看第 1 项依据'})).toHaveFocus()
    expect(api.evidence).not.toHaveBeenCalled()
  })
  it('证据在同页读取，Esc 返回执行过程与重新挂载的原入口', async () => {
    const value=story();value.actions[0].execution_path={complete:true,reason_codes:[],evidence_refs:['ev1'],events:[node]}
    api.evidence.mockResolvedValue({...evidence(),trace:{complete:true,events:[node]}})
    render(<CurrentResultStory story={value} onError={vi.fn()}/>); inspectTrace()
    const trigger=screen.getByRole('button',{name:'查看任务派发的发布证据'});trigger.focus();fireEvent.click(trigger)
    expect(await screen.findByText('应用服务 · task-record')).toBeInTheDocument()
    const reader=screen.getByRole('region',{name:'已发布证据'})
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText('不能单独证明什么')).toBeInTheDocument()
    fireEvent.keyDown(reader,{key:'Escape'})
    expect(screen.getByRole('button',{name:'查看任务派发的发布证据'})).toHaveFocus()
  })
  it.each(['missing-node','wrong-document','wrong-case','wrong-run'])('拒绝不属于所选对象的证据：%s', async scenario => {
    const value=story();value.actions[0].execution_path={complete:true,reason_codes:[],evidence_refs:['ev1'],events:[node]}
    api.evidence.mockResolvedValue({...evidence(),run_id:scenario==='wrong-run'?'other':'r1',case:{case_id:scenario==='wrong-case'?'other':'c1'},evidence_id:scenario==='wrong-document'?'other':'ev1',trace:{complete:true,events:scenario==='missing-node'?[]:[node]}})
    const error=vi.fn();render(<CurrentResultStory story={value} onError={error}/>); inspectTrace()
    fireEvent.click(screen.getByRole('button',{name:'查看任务派发的发布证据'}))
    await waitFor(() => expect(error).toHaveBeenCalledOnce())
    expect(error.mock.calls[0][0].code).toBe('ARTIFACT_MANIFEST')
    expect(screen.queryByText('应用服务 · task-record')).not.toBeInTheDocument()
  })
  it('辅助证明只在记录页展示，保持等级及所选要求上下文', async () => {
    const value=story();value.actions[0].proof_coverage=[{effect_id:'e1',business_label:'导出文件',proof_fingerprint:'proof1',required_level:'SUPPORTING',source_label:'历史来源',observed_state:'UNKNOWN',evidence_refs:[],supporting_evidence_refs:['ev1'],limitations:['辅助材料不替代必要证明']}]
    api.evidence.mockResolvedValue(evidence())
    render(<CurrentResultStory story={value} onError={vi.fn()}/>); inspect()
    expect(screen.queryByRole('button',{name:'查看辅助观察记录'})).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'证据记录'}))
    expect(screen.getByRole('region',{name:'本轮要求与证据对应'})).toHaveTextContent('辅助材料不替代必要证明')
    fireEvent.click(screen.getByRole('button',{name:'查看辅助观察记录'}))
    expect(await screen.findByText('来自所选证明要求')).toBeInTheDocument()
    expect(api.evidence).toHaveBeenCalledWith('r1','ev1')
  })
  it('隐藏工作页后取消证据读取，迟到结果和错误都不能污染新页面', async () => {
    let reject!: (error:Error) => void
    api.evidence.mockImplementation(() => new Promise((_, fail) => {reject=fail}))
    const value=story(),error=vi.fn()
    const view=render(<WorkPageVisible.Provider value={true}><CurrentResultStory story={value} onError={error}/></WorkPageVisible.Provider>)
    inspect();openSource()
    view.rerender(<WorkPageVisible.Provider value={false}><CurrentResultStory story={value} onError={error}/></WorkPageVisible.Provider>)
    await act(async () => reject(new Error('late failed request')))
    expect(screen.queryByRole('region',{name:'已发布证据'})).not.toBeInTheDocument()
    expect(error).not.toHaveBeenCalled()
  })
  it('不存在的深链 Case 不悄悄替换为另一条；返回后可选有效项', () => {
    render(<CurrentResultStory story={story()} requestedCaseId="other" onError={vi.fn()}/>)
    expect(screen.getByText(/本轮没有指定的检查项/)).toBeInTheDocument()
    expect(screen.queryByRole('region',{name:'判断依据'})).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'← 返回 1 项结果'})); inspect()
    expect(screen.getByRole('region',{name:'判断依据'})).toBeInTheDocument()
  })
  it('切换检查项后丢弃上一项迟到证据，整轮标题保持不变', async () => {
    let resolve!: (value:unknown) => void
    api.evidence.mockImplementation(() => new Promise(done => {resolve=done}))
    const value=story();value.actions.push({...value.actions[0],case_id:'c2',display_name:'另一项操作'})
    const error=vi.fn();render(<CurrentResultStory story={value} onError={error}/>);inspect();openSource()
    fireEvent.click(screen.getByRole('button',{name:'查看第 2 项依据'}))
    await act(async () => resolve(evidence()))
    expect(error).not.toHaveBeenCalled()
    expect(screen.queryByRole('region',{name:'已发布证据'})).not.toBeInTheDocument()
    expect(screen.getByRole('heading',{name:value.judgement,level:1})).toBeInTheDocument()
    expect(screen.getByRole('heading',{name:'另一项操作',level:2})).toBeInTheDocument()
  })
  it('证明详情返回原事实入口，保持两次点击可达已发布文件', async () => {
    const value=story();value.actions[0].proof_coverage=[{effect_id:'e1',business_label:'导出文件',proof_fingerprint:'proof1',required_level:'VERDICT_REQUIRED',source_label:'资源状态',observed_state:'CONFIRMED',evidence_refs:['ev1'],supporting_evidence_refs:[],limitations:[]}]
    api.evidence.mockResolvedValue(evidence())
    render(<CurrentResultStory story={value} onError={vi.fn()}/>);inspect()
    const trigger=screen.getByRole('button',{name:'查看必要证明记录'});trigger.focus();fireEvent.click(trigger)
    await screen.findByText('来自所选证明要求')
    fireEvent.keyDown(screen.getByRole('region',{name:'已发布证据'}),{key:'Escape'})
    expect(screen.getByRole('button',{name:'查看必要证明记录'})).toHaveFocus()
  })
  it('初始和恢复保持独立核对，不把不适用阶段列成无法确认', () => {
    const value=story(),source=value.actions[0].decisive_proof_chain[0]
    value.actions[0].evidence_explanations.push({...source,source_label:'ASYNC_TASK_STATUS',observed_fact:{...source.observed_fact,phase:'BASELINE',state:'UNKNOWN',level:'SUPPORTING',reason_codes:['OBSERVER_PHASE_UNAVAILABLE']}})
    render(<CurrentResultStory story={value} onError={vi.fn()}/>);inspect()
    expect(screen.getByText('已独立核对')).toBeInTheDocument()
    expect(screen.getByText('恢复要求已满足')).toBeInTheDocument()
    expect(screen.getByText('无法独立确认')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'证据记录'}))
    expect(screen.getByRole('region',{name:'观察来源与阶段'})).toBeInTheDocument()
    expect(screen.getByRole('article',{name:'后台任务的阶段记录'})).toHaveTextContent('本阶段不采集')
  })
  it('阶段证据返回会展开原来源并恢复焦点', async () => {
    const value=story(),source=value.actions[0].decisive_proof_chain[0]
    value.actions[0].evidence_explanations.push({...source,source_label:'STRUCTURED_AUDIT_LOG',reading:{kind:'PROCESS',label:'已取得关联过程记录',detail:'只用于过程追踪。',attention:false},observed_fact:{...source.observed_fact,observer_id:'audit',level:'DIAGNOSIS_REQUIRED',phase:'EVENTUAL'}})
    api.evidence.mockResolvedValue(evidence())
    render(<CurrentResultStory story={value} onError={vi.fn()}/>);inspect()
    fireEvent.click(screen.getByRole('button',{name:'证据记录'}))
    const group=screen.getByRole('article',{name:'审计记录的阶段记录'})
    fireEvent.click(group.querySelector('summary')!)
    const trigger=screen.getByRole('button',{name:'查看审计记录最终观察记录'});trigger.focus();fireEvent.click(trigger)
    await screen.findByText('在哪里看到')
    fireEvent.keyDown(screen.getByRole('region',{name:'已发布证据'}),{key:'Escape'})
    expect(screen.getByRole('button',{name:'查看审计记录最终观察记录'})).toHaveFocus()
    expect(screen.getByRole('article',{name:'审计记录的阶段记录'}).querySelector('details')).toHaveAttribute('open')
  })
  it('历史路由回退清除选择，大列表返回仍保留原分页和焦点', () => {
    const value=story();value.actions=Array.from({length:12},(_,i)=>({...value.actions[0],case_id:`c${i+1}`,display_name:`操作 ${i+1}`}))
    const view=render(<CurrentResultStory story={value} onError={vi.fn()}/>)
    expect(screen.getAllByRole('row')).toHaveLength(11)
    fireEvent.click(screen.getByTitle('2'))
    fireEvent.click(screen.getByRole('button',{name:'查看第 11 项依据'}))
    view.rerender(<CurrentResultStory story={value} requestedCaseId="c11" onError={vi.fn()}/>)
    view.rerender(<CurrentResultStory story={value} requestedCaseId={null} onError={vi.fn()}/>)
    expect(screen.getByRole('button',{name:'查看第 11 项依据'})).toHaveFocus()
    expect(screen.getAllByRole('row')).toHaveLength(3)
  })
  it('不认识的服务端判断原样显示，不从 403 或效果替它上色', () => {
    const value=story();value.actions[0].judgement='新判断语义'
    render(<CurrentResultStory story={value} onError={vi.fn()}/>)
    expect(screen.getByText('新判断语义')).toHaveClass('is-neutral')
    expect(screen.queryByText('符合要求')).not.toBeInTheDocument()
  })
})
