import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ErrorRecovery } from './ErrorRecovery'
import { StageGuide } from './StageGuide'

describe('共享指导与错误恢复', () => {
  it('StageGuide 展示四项指导并只在提供回调时显示下一步', () => {
    render(<StageGuide stage="测试" what="执行检查" why="确认权限" missing="尚未开始检查" next="查看验证" onNext={vi.fn()} nextLabel="查看验证" />)
    expect(screen.getByText('正在做什么')).toBeInTheDocument()
    expect(screen.getByText('为什么需要')).toBeInTheDocument()
    expect(screen.getByText('还缺什么')).toBeInTheDocument()
    expect(screen.getByText('下一步')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看验证' })).toBeInTheDocument()
  })

  it('ErrorRecovery 默认不把错误码放在主层，诊断展开后保留脱敏标识', () => {
    render(<ErrorRecovery error={{ code: 'ONBOARDING_SESSION_CONFLICT', message: '会话需要刷新', traceId: 'trace-1' } as any} onRetry={vi.fn()} onBackAccess={vi.fn()} />)
    expect(screen.getByText('这一步没有完成')).toBeInTheDocument()
    expect(screen.getByText('会话内容已在其他页面更新。')).toBeInTheDocument()
    expect(screen.queryByText('ONBOARDING_SESSION_CONFLICT')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('诊断信息'))
    expect(screen.getByText(/错误码：ONBOARDING_SESSION_CONFLICT/)).toBeInTheDocument()
    expect(screen.getByText(/trace_id：trace-1/)).toBeInTheDocument()
  })
})
