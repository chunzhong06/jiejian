// 验证评委导览完全由 ProductStatus 与活跃 Experience 推导，不保存独立步骤。

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { JudgeGuideBar } from './JudgeGuideBar'

const experience = {
  available: true,
  display_name: '协作空间',
  unavailable_reason: null,
  active: true,
  experience_id: `exp_${'a'.repeat(32)}`,
  experience_mode: 'GUIDED' as const,
  project_id: 'p1',
  origin: 'http://127.0.0.1:12345',
  identities_ready: false,
  authorization_order: 'ENQUEUE_BEFORE_AUTHORIZE' as const,
  blob_observation: 'AVAILABLE' as const,
}

function status(action: string, route: string) {
  return {
    project: { project_id: 'p1', name: '协作空间', status: 'DRAFT', target_type: 'WEB' as const },
    readiness: null,
    steps: [],
    next_action: { action, label: '继续', description: '继续当前任务', route, cli_command: 'jiejian status' },
    latest_result: null,
  }
}

describe('JudgeGuideBar', () => {
  it('候选待确认时显示七步中的第二个用户决定', () => {
    render(<JudgeGuideBar status={status('REVIEW_DISCOVERY', '/application') as never} experience={experience} preparingIdentities={false} onPrepareIdentities={vi.fn()} />)
    expect(screen.getByText('评委导览 · 2/7')).toBeInTheDocument()
    expect(screen.getByText(/确认三个权限组/)).toBeInTheDocument()
  })

  it('身份步骤提供明确准备动作，完成后由新的产品状态推进', () => {
    const prepare = vi.fn()
    render(<JudgeGuideBar status={status('RECORD_FLOW', '/identities') as never} experience={experience} preparingIdentities={false} onPrepareIdentities={prepare} />)
    expect(screen.getByText(/Eve 只用于确认外部访客边界，主演示比较 Alice 与 Bob/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '准备官方测试账号' }))
    expect(prepare).toHaveBeenCalledOnce()
  })

  it('录制步骤解释 Alice 的控制组与结果恢复职责', () => {
    render(<JudgeGuideBar status={status('RECORD_FLOW', '/flows') as never} experience={{ ...experience, identities_ready: true }} preparingIdentities={false} onPrepareIdentities={vi.fn()} />)
    expect(screen.getByText(/正常有权限的 Alice 作为控制组/)).toBeInTheDocument()
    expect(screen.getByText(/怎样确认结果和恢复现场/)).toBeInTheDocument()
  })

  it('完整体验或其他项目不显示导览条', () => {
    const { rerender } = render(<JudgeGuideBar status={status('RECORD_FLOW', '/identities') as never} experience={{ ...experience, experience_mode: 'FULL' }} preparingIdentities={false} onPrepareIdentities={vi.fn()} />)
    expect(screen.queryByLabelText('评委导览')).not.toBeInTheDocument()
    rerender(<JudgeGuideBar status={{ ...status('RECORD_FLOW', '/identities'), project: { project_id: 'p2', name: '其他应用', status: 'DRAFT', target_type: 'WEB' } } as never} experience={experience} preparingIdentities={false} onPrepareIdentities={vi.fn()} />)
    expect(screen.queryByLabelText('评委导览')).not.toBeInTheDocument()
  })
})
