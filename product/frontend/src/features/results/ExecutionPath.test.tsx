// 显式分支必须原样显示；缺图、partial 与降级定位不得被视觉升级。
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { StoryTraceEvent } from '../../api/currentChecks'
import { story } from './testing.fixtures'
import { ExecutionPath } from './ExecutionPath'

const event = (event_id: string, kind: StoryTraceEvent['kind'], parents: string[] = []): StoryTraceEvent => ({ event_id, kind, parent_event_ids: parents, authorization_decision: kind === 'AUTHORIZATION' ? 'DENY' : null, effect_id: null, dispatch_effect_ids: [], source_component: '应用服务', source_location: '/export', })
describe('执行路径', () => {
  it('保留派发的两个分支，不把拒绝响应接到 Worker 前', () => {
    const action = story().actions[0], select = vi.fn()
    action.execution_path = { complete: true, reason_codes: [], evidence_refs: ['ev-graph'], events: [event('entry','ENTRY'), event('dispatch','MESSAGE',['entry']), event('denied','AUTHORIZATION',['dispatch']), event('worker','DELEGATION',['dispatch'])] }
    const { container } = render(<ExecutionPath action={action} onSelect={select}/>)
    expect(container.querySelectorAll('path[data-parent]')).toHaveLength(3)
    expect(container.querySelector('[data-parent="dispatch"][data-child="worker"]')).not.toBeNull()
    expect(container.querySelector('[data-parent="denied"][data-child="worker"]')).toBeNull()
    fireEvent.click(screen.getByRole('button', {name:'查看权限判断 · 拒绝的发布证据'}))
    expect(select).toHaveBeenCalledWith(action.execution_path.events[2], ['ev-graph'])
    expect(screen.queryByText('首个可证明断裂')).not.toBeInTheDocument()
  })
  it('部分路径说明缺口，范围定位不显示成精确节点', () => {
    const action=story().actions[0]
    action.breakpoint={...action.breakpoint!,precision:'RANGE',first_violation_event_id:'a'}
    action.execution_path={complete:false,reason_codes:['MISSING_SOURCE'],evidence_refs:['ev'],events:[event('a','ENTRY')]}
    render(<ExecutionPath action={action} onSelect={vi.fn()}/>)
    expect(screen.getByText('路径不完整 · 只展示已知关系')).toBeInTheDocument()
    expect(screen.queryByText('首个可证明断裂')).not.toBeInTheDocument()
  })
  it('没有发布路径时不从 HTTP 与效果事实画图', () => {
    const {container}=render(<ExecutionPath action={story().actions[0]} onSelect={vi.fn()}/>)
    expect(screen.getByText(/不从页面回应推断后台路径/)).toBeInTheDocument()
    expect(container.querySelector('.path-canvas svg')).toBeNull()
  })
  it('范围只使用服务端端点，不在缺失区间补连线', () => {
    const action=story().actions[0], select=vi.fn()
    action.breakpoint={...action.breakpoint!,precision:'RANGE',first_violation_event_id:null,range_start_event_id:'a',range_end_event_id:'b'}
    action.execution_path={complete:false,reason_codes:['TRACE_PARENT_MISSING'],evidence_refs:['ev'],events:[event('a','MESSAGE'),event('b','PERSISTENT_EFFECT',['missing'])]}
    const {container}=render(<ExecutionPath action={action} onSelect={select}/>)
    const range=screen.getByRole('region',{name:'已发布的定位区间'})
    expect(screen.getByRole('button',{name:'查看定位区间'})).toHaveAttribute('aria-pressed','true')
    fireEvent.click(screen.getByRole('button',{name:'图形查看执行路径'}))
    expect(container.querySelector('.path-canvas svg')).not.toBeNull()
    expect(container.querySelectorAll('path[data-parent]')).toHaveLength(0)
    expect(screen.getByText('仅标示诊断区间，不补画内部步骤')).toBeInTheDocument()
    fireEvent.click(within(range).getByRole('button',{name:/持久业务变化/}))
    expect(select).toHaveBeenCalledWith(action.execution_path.events[1],['ev'])
    expect(screen.queryByText('首个可证明断裂')).not.toBeInTheDocument()
  })
  it('未知端点不按首尾节点猜测；只有精确定位能标记单点', () => {
    const action=story().actions[0]
    action.execution_path={complete:false,reason_codes:[],evidence_refs:['ev'],events:[event('a','ENTRY')]}
    action.breakpoint={...action.breakpoint!,precision:'RANGE',range_start_event_id:'other',range_end_event_id:'missing'}
    const view=render(<ExecutionPath action={action} onSelect={vi.fn()}/>)
    expect(screen.getByText('当前路径未提供起点记录')).toBeInTheDocument()
    expect(screen.getByText('当前路径未提供终点记录')).toBeInTheDocument()
    view.rerender(<ExecutionPath action={{...action,breakpoint:{...action.breakpoint!,precision:'EXACT',first_violation_event_id:'a',range_start_event_id:null,range_end_event_id:null}}} onSelect={vi.fn()}/>)
    expect(screen.getByText('首个可证明断裂')).toBeInTheDocument()
    expect(screen.queryByRole('region',{name:'已发布的定位区间'})).not.toBeInTheDocument()
  })
  it('分支合流和不同业务结果保持显式关联', () => {
    const action=story().actions[0]
    action.fact_comparison.effects[0]={...action.fact_comparison.effects[0],effect_id:'record',business_label:'项目记录修改'}
    action.execution_path={complete:true,reason_codes:[],evidence_refs:['ev'],events:[event('a','ENTRY'),event('b','MESSAGE',['a']),event('c','DELEGATION',['a']),{...event('d','FINAL_EFFECT',['b','c']),effect_id:'record'},event('separate','ENTRY')]}
    const {container}=render(<ExecutionPath action={action} onSelect={vi.fn()}/>)
    expect(container.querySelectorAll('path[data-parent]')).toHaveLength(4)
    expect(container.querySelector('[data-parent="b"][data-child="d"]')).not.toBeNull()
    expect(container.querySelector('[data-parent="c"][data-child="d"]')).not.toBeNull()
    expect(screen.getByText('项目记录修改')).toBeInTheDocument()
    expect(container.querySelector('[data-child="separate"]')).toBeNull()
  })
  it('长路径可列表阅读全部事件，缺失前序保持具名缺口', () => {
    const action=story().actions[0]
    action.execution_path={complete:false,reason_codes:[],evidence_refs:['ev'],events:Array.from({length:40},(_,i)=>event(`e${i}`,'MESSAGE',[i ? `e${i-1}`:'absent']))}
    render(<ExecutionPath action={action} onSelect={vi.fn()}/>)
    expect(screen.getByRole('button',{name:'展开完整执行路径'})).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'列表查看执行路径'}))
    expect(within(screen.getByRole('list',{name:'已发布事件列表'})).getAllByRole('listitem')).toHaveLength(40)
    expect(screen.getByText('已记录的前序：前序记录缺失')).toBeInTheDocument()
  })
})
