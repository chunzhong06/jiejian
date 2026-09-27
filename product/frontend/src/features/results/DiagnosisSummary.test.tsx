// 定位精度只翻译发布结果；没有断裂定位时不虚构证据缺口。
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DiagnosisSummary } from './DiagnosisSummary'
import { story } from './testing.fixtures'

describe('定位依据', () => {
  it('范围定位解释真实原因，不提供精确节点结论', () => {
    const action=story().actions[0]
    action.breakpoint={...action.breakpoint!,precision:'RANGE',reason_codes:['TRACE_EVIDENCE_INCOMPLETE','TRACE_PARENT_MISSING']}
    render(<DiagnosisSummary action={action} onEvidence={vi.fn()}/>)
    expect(screen.getByText('定位所需的执行证据不完整。')).toBeInTheDocument()
    expect(screen.getByText('部分事件缺少前序记录，无法还原完整关联。')).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'查看区间的定位证据'})).toBeInTheDocument()
    expect(screen.queryByText('精确定位')).not.toBeInTheDocument()
  })
  it('只有后果时不因诊断不足撤销后果说明', () => {
    render(<DiagnosisSummary action={story().actions[0]} onEvidence={vi.fn()}/>)
    expect(screen.getByText('业务后果已确认，现有路径证据不足以进一步定位。')).toBeInTheDocument()
    expect(screen.getByText('定位解释已有事实，不改变本轮结论。')).toBeInTheDocument()
  })
  it('没有断裂定位不自动归因于缺少证据', () => {
    render(<DiagnosisSummary action={{...story().actions[0],breakpoint:null}} onEvidence={vi.fn()}/>)
    expect(screen.queryByText('为什么不能进一步定位')).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
