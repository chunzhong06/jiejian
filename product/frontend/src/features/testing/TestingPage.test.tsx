// 验证测试模块并列组织条件、运行和结果，不把三项工作重新包装成线性向导。

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TestingPage } from './TestingPage'

const status = {
  areas: [{ key: 'tests', status_label: '已有可信结果' }],
  latest_result: { verdict: 'BLOCK', headline: '发现权限问题' },
}

const readiness = {
  current_scope_runnable: true,
  remaining_gap_count: 0,
  active_tasks: [],
  preparation: { ready: true },
}

describe('TestingPage', () => {
  it('把测试条件、运行检查和结果历史作为可自由进入的三个区域', () => {
    const onNavigate = vi.fn()
    render(<TestingPage status={status as never} readiness={readiness as never} runs={[]} onNavigate={onNavigate} />)

    expect(screen.getByRole('heading', { name: '测试', level: 2 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '身份、流程与观察条件已准备' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '核对范围并发起独立检查' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '发现权限问题' })).toBeInTheDocument()
    expect(document.querySelector('.phase-steps')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '管理测试条件' }))
    fireEvent.click(screen.getByRole('button', { name: '进入运行检查' }))
    fireEvent.click(screen.getByRole('button', { name: '查看结果与历史' }))
    expect(onNavigate.mock.calls).toEqual([["/preparation"], ["/validation"], ["/results"]])
  })

  it('运行中只改变当前判断和运行入口，不锁住另外两个区域', () => {
    const onNavigate = vi.fn()
    const running = { ...readiness, active_tasks: [{ kind: 'RUN' }] }
    render(<TestingPage status={status as never} readiness={running as never} runs={[]} onNavigate={onNavigate} />)

    expect(screen.getByText('界鉴正在检查当前代码版本的真实业务结果。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '查看检查进度' }))
    expect(onNavigate).toHaveBeenCalledWith('/validation')
    expect(screen.getByRole('button', { name: '管理测试条件' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '查看结果与历史' })).toBeEnabled()
  })
})
