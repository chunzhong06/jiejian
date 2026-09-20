// 证据调查必须维持 Run/Case 归属，切换后的陈旧读取不能污染当前事实。
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Grid } from 'antd'
import type { StoryTraceEvent } from '../../api/currentChecks'
import { CurrentResultStory } from './CurrentResultStory'
import { story, outcome } from './testing.fixtures'
import { WorkPageVisible } from '../../app/RetainedWorkPages'
const api=vi.hoisted(()=>({evidence:vi.fn()}))
vi.mock('../../api/currentChecks',()=>({currentChecksApi:api}))
vi.mock('../../components/AssistantPanel',()=>({AssistantPanel:()=>null}))
beforeEach(()=>vi.clearAllMocks())
afterEach(()=>vi.restoreAllMocks())
const node:StoryTraceEvent={event_id:'task',parent_event_ids:[],kind:'MESSAGE',authorization_decision:null,effect_id:null,dispatch_effect_ids:[],source_component:'应用服务',source_location:'task-record'}
describe('结果调查',()=>{
  it('桌面证据独立占列，核验节点后展示四问并返回原焦点',async()=>{
    vi.spyOn(Grid,'useBreakpoint').mockReturnValue({lg:true})
    const value=story();value.actions[0].execution_path={complete:true,reason_codes:[],evidence_refs:['ev1'],events:[node]}
    api.evidence.mockResolvedValue({schema_version:'1',run_id:'r1',action_id:'a1',case:{case_id:'c1'},evidence_id:'ev1',outcome,observations:[],trace:{complete:true,events:[node]}})
    render(<CurrentResultStory story={value} onError={vi.fn()}/>)
    const trigger=screen.getByRole('button',{name:'查看任务派发的发布证据'});trigger.focus();fireEvent.click(trigger)
    expect(await screen.findByText('应用服务的已发布记录')).toBeInTheDocument()
    expect(screen.getByRole('complementary',{name:'已发布证据'})).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText('不能单独证明什么')).toBeInTheDocument()
    fireEvent.keyDown(screen.getByRole('complementary'),{key:'Escape'})
    expect(trigger).toHaveFocus()
  })
  it.each(['missing-node','wrong-document'])('拒绝未对应当前选择的证据：%s',async scenario=>{
    const value=story();value.actions[0].execution_path={complete:true,reason_codes:[],evidence_refs:['ev1'],events:[node]}
    api.evidence.mockResolvedValue({schema_version:'1',run_id:'r1',action_id:'a1',case:{case_id:'c1'},evidence_id:scenario==='wrong-document'?'other':'ev1',outcome,observations:[],trace:{complete:true,events:[]}})
    const error=vi.fn();render(<CurrentResultStory story={value} onError={error}/>)
    fireEvent.click(screen.getByRole('button',{name:'查看任务派发的发布证据'}))
    await waitFor(()=>expect(error).toHaveBeenCalledOnce())
    expect(screen.queryByText('应用服务的已发布记录')).not.toBeInTheDocument()
  })
  it('要求对应入口读取同轮证据，辅助材料保留等级和所选要求上下文',async()=>{
    const value=story()
    value.actions[0].proof_coverage=[{effect_id:'e1',business_label:'导出文件',proof_fingerprint:'proof1',required_level:'SUPPORTING',source_label:'历史来源',observed_state:'UNKNOWN',evidence_refs:[],supporting_evidence_refs:['ev1'],limitations:['辅助材料不替代必要证明']}]
    api.evidence.mockResolvedValue({schema_version:'1',run_id:'r1',action_id:'a1',case:{case_id:'c1'},evidence_id:'ev1',outcome,observations:[],trace:null})
    render(<CurrentResultStory story={value} onError={vi.fn()}/>)
    expect(screen.getByRole('region',{name:'本轮要求与证据对应'})).toHaveTextContent('辅助材料不替代必要证明')
    expect(screen.queryByRole('button',{name:'查看必要证明记录'})).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'查看辅助观察记录'}))
    expect(await screen.findByText('来自所选证明要求')).toBeInTheDocument()
    expect(api.evidence).toHaveBeenCalledWith('r1','ev1')
  })
  it('页面进入保留状态时关闭 Portal，证据不能遮盖新页面',async()=>{
    api.evidence.mockResolvedValue({schema_version:'1',run_id:'r1',action_id:'a1',case:{case_id:'c1'},evidence_id:'ev1',outcome,observations:[],trace:null})
    const value=story(),error=vi.fn()
    const view=render(<WorkPageVisible.Provider value={true}><CurrentResultStory story={value} onError={error}/></WorkPageVisible.Provider>)
    fireEvent.click(screen.getAllByRole('button',{name:'为什么这样判断？查看资源状态证据'})[0])
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    view.rerender(<WorkPageVisible.Provider value={false}><CurrentResultStory story={value} onError={error}/></WorkPageVisible.Provider>)
    await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
  it('查询不存在的 Case 不悄悄展示另一条原题',()=>{
    render(<CurrentResultStory story={story()} requestedCaseId="other" onError={vi.fn()}/>)
    expect(screen.getByText(/本轮没有指定的检查项/)).toBeInTheDocument()
    expect(screen.queryByText('本项已确认越权后果')).not.toBeInTheDocument()
  })
  it('拒绝另一 Case 的证据并撤销当前调查可信性',async()=>{
    const error=vi.fn()
    api.evidence.mockResolvedValue({schema_version:'1',run_id:'r1',action_id:'a1',case:{case_id:'other'},evidence_id:'ev1',outcome,observations:[],trace:null})
    render(<CurrentResultStory story={story()} onError={error}/>)
    fireEvent.click(screen.getAllByRole('button',{name:'为什么这样判断？查看资源状态证据'})[0])
    await waitFor(()=>expect(error).toHaveBeenCalledOnce())
    expect(error.mock.calls[0][0].code).toBe('ARTIFACT_MANIFEST')
  })
  it('切换本轮检查项后丢弃上一项迟到证据',async()=>{
    let resolve!: (value:unknown)=>void
    api.evidence.mockImplementation(()=>new Promise(done=>{resolve=done}))
    const value=story(); value.actions.push({...value.actions[0],case_id:'c2',display_name:'另一项操作'})
    const error=vi.fn();render(<CurrentResultStory story={value} onError={error}/>)
    fireEvent.click(screen.getAllByRole('button',{name:'为什么这样判断？查看资源状态证据'})[0])
    fireEvent.click(screen.getByRole('button',{name:/另一项操作 · 计划成员/}))
    await act(async()=>resolve({schema_version:'1',run_id:'r1',action_id:'a1',case:{case_id:'c1'},evidence_id:'ev1',outcome,observations:[],trace:null}))
    expect(error).not.toHaveBeenCalled()
    await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})
