// 验证检查进度只投影权威业务状态，不自行计算结论，也不向普通页面暴露内部运行标识。

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CheckProgress } from './CheckProgress'

const runsApi = vi.hoisted(() => ({ progress: vi.fn() }))
vi.mock('../../api/runs', () => ({ runsApi }))
const originalEventSource = globalThis.EventSource

describe('CheckProgress', () => {
  afterEach(() => { cleanup(); (globalThis as any).EventSource = originalEventSource })
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); runsApi.progress.mockResolvedValue({ job_id: 'job-1', attempt: 1, events: [] }) })

  it('把真实旁路阶段翻译成用户任务，并隐藏未知业务动作 ID', async () => {
    runsApi.progress.mockResolvedValue({ job_id: 'job-1', attempt: 1, events: [
      { schema_version: '1', sequence: 1, case_id: 'case-a', action_id: 'action-known', twin_role: 'ALLOW_CONTROL', phase: 'RECOVERY', state: 'COMPLETED', recorded_at_us: 1 },
      { schema_version: '1', sequence: 2, case_id: 'case-b', action_id: 'action-unknown', twin_role: 'DENY_VARIANT', phase: 'TARGET', state: 'STARTED', recorded_at_us: 2 },
    ] })
    render(<CheckProgress
      run={{ run_id: 'run-1', lifecycle: 'RUNNING', job: { job_id: 'job-1', state: 'RUNNING' } } as any}
      actions={[{ action_candidate_id: 'action-known', action_display_name: '修改资源', resource_logical_name: '测试资源', ready: true, gaps: [], checks: [{ subject_label: '账号', subject_role_display_name: '成员', relation: 'OWNS', expectation: 'ALLOW', ready: true, gaps: [] }] }]}
      onRefresh={vi.fn()} onError={vi.fn()}
    />)

    expect(await screen.findByText('修改资源 · 恢复测试数据')).toBeInTheDocument()
    expect(screen.getByText('当前业务动作 · 尝试不应允许的操作')).toBeInTheDocument()
    expect(screen.queryByText('action-unknown')).not.toBeInTheDocument()
  })

  it('失败只展示生命周期与确定性诊断，不渲染成权限问题', async () => {
    const onNavigate = vi.fn()
    render(<CheckProgress run={{
      run_id: 'run-failed', lifecycle: 'FAILED', job: { job_id: 'job-failed', state: 'FAILED' },
      execution_errors: [{ stage: '后台执行', message: 'Worker 在任务完成前异常退出', log_path: 'var/logs/workers/job-failed.log', recovery: '重新启动后再次检查。', copy_text: '诊断 run-failed', diagnosis: { route: '/check', headline: '隔离执行没有正常完成', short_message: '检查没有形成安全结论，请确认运行环境后重试。', cleanup_warnings: [] } }],
    } as any} onRefresh={vi.fn()} onError={vi.fn()} onNavigate={onNavigate} />)

    expect(screen.getByText('隔离执行没有正常完成')).toBeInTheDocument()
    expect(screen.getByText('检查没有形成安全结论，请确认运行环境后重试。')).toBeInTheDocument()
    screen.getByRole('button', { name: '前往处理页面' }).click()
    expect(onNavigate).toHaveBeenCalledWith('/check')
    expect(screen.queryByText('发现权限问题')).not.toBeInTheDocument()
    expect(screen.queryByText(/job-failed|workers\/job-failed|事件序列|任务标识|高级/)).not.toBeInTheDocument()
  })

  it('从保存游标续读事件，并只请求父页面刷新权威状态', async () => {
    let source: { url: string; onmessage?: (event: MessageEvent) => void } | undefined
    class FakeEventSource {
      onmessage?: (event: MessageEvent) => void
      onerror?: () => void
      close = vi.fn()
      constructor(public url: string) { source = this }
    }
    ;(globalThis as any).EventSource = FakeEventSource
    localStorage.setItem('jiejian.cursor.job-1', JSON.stringify(4))
    const onRefresh = vi.fn()
    render(<CheckProgress run={{ run_id: 'run-1', lifecycle: 'RUNNING', job: { job_id: 'job-1', state: 'RUNNING' } } as any} onRefresh={onRefresh} onError={vi.fn()} />)

    await waitFor(() => expect(source?.url).toBe('/api/jobs/job-1/events?after=4'))
    source?.onmessage?.({ data: JSON.stringify({ sequence: 5, event_type: 'JOB_RUNNING' }), lastEventId: '' } as MessageEvent)
    expect(localStorage.getItem('jiejian.cursor.job-1')).toBe('5')
    expect(onRefresh).toHaveBeenCalledOnce()
  })

  it('事件流断开时明确保留后台运行语义', async () => {
    let source: { onerror?: () => void } | undefined
    class FakeEventSource {
      onmessage?: (event: MessageEvent) => void
      onerror?: () => void
      close = vi.fn()
      constructor() { source = this }
    }
    ;(globalThis as any).EventSource = FakeEventSource
    render(<CheckProgress run={{ run_id: 'run-1', lifecycle: 'RUNNING', job: { job_id: 'job-1', state: 'RUNNING' } } as any} onRefresh={vi.fn()} onError={vi.fn()} />)

    await waitFor(() => expect(source).toBeDefined())
    source?.onerror?.()

    expect(await screen.findByText('实时视图暂时断开，正式检查仍在后台运行')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: '真实检查阶段' })).toBeInTheDocument()
  })
})
