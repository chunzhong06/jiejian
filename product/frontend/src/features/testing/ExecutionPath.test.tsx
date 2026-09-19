// 显式分支必须原样显示；缺图、partial 与降级定位不得被视觉升级。
import { fireEvent, render, screen } from '@testing-library/react'
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
    expect(container.querySelector('svg')).toBeNull()
  })
})
