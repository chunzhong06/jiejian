import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { StartCheckPage } from './StartCheckPage'

const permissionApi = vi.hoisted(() => ({ profiles: vi.fn().mockResolvedValue([]), submit: vi.fn() }))
const runsApi = vi.hoisted(() => ({ run: vi.fn(), cancel: vi.fn() }))
vi.mock('../../api/executionProfiles', () => ({ executionProfilesApi: permissionApi }))
vi.mock('../../api/runs', () => ({ runsApi }))

describe('StartCheckPage', () => {
  afterEach(() => { vi.clearAllMocks(); delete (globalThis as any).EventSource; localStorage.clear() })
  it('只在真实 completed/total 存在时显示数量与对应百分比', async () => {
    runsApi.run.mockResolvedValue({ run_id: 'run-1', lifecycle: 'RUNNING', result_integrity: 'UNAVAILABLE', case_progress: { completed: 2, total: 5 } })
    render(<StartCheckPage project={{ project_id: 'p1' }} runs={[{ run_id: 'run-1', lifecycle: 'RUNNING' }]} onRefresh={vi.fn()} onError={vi.fn()} />)
    expect(await screen.findByText('已完成 2/5 个用例')).toBeInTheDocument()
    expect(screen.getByText('40%')).toBeInTheDocument()
  })

  it('缺少真实总量时明确降级', async () => {
    runsApi.run.mockResolvedValue({ run_id: 'run-2', lifecycle: 'RUNNING', result_integrity: 'UNAVAILABLE', case_progress: { completed: null, total: null } })
    render(<StartCheckPage project={{ project_id: 'p1' }} runs={[{ run_id: 'run-2', lifecycle: 'RUNNING' }]} onRefresh={vi.fn()} onError={vi.fn()} />)
    expect(await screen.findByText('正在执行，暂时没有可确认的用例总量')).toBeInTheDocument()
  })

  it('同一运行进入失败状态后重新读取并展示可复制的诊断信息', async () => {
    runsApi.run
      .mockResolvedValueOnce({ run_id: 'run-failed', lifecycle: 'RUNNING', updated_at_us: 1, job: { job_id: 'job-failed', state: 'RUNNING' } })
      .mockResolvedValueOnce({
        run_id: 'run-failed',
        lifecycle: 'FAILED',
        updated_at_us: 2,
        job: { job_id: 'job-failed', state: 'FAILED' },
        execution_errors: [{ stage: '后台执行', message: 'Worker 在任务完成前异常退出', log_path: 'var/logs/workers/job-failed.log', recovery: '重新启动后再次检查。', copy_text: '请分析任务 job-failed 的失败原因。' }],
      })
    const onError = vi.fn()
    const { rerender } = render(<StartCheckPage project={{ project_id: 'p1' }} runs={[{ run_id: 'run-failed', lifecycle: 'RUNNING', updated_at_us: 1, job: { job_id: 'job-failed', state: 'RUNNING' } }]} onRefresh={vi.fn()} onError={onError} />)
    await waitFor(() => expect(runsApi.run).toHaveBeenCalledTimes(1))

    rerender(<StartCheckPage project={{ project_id: 'p1' }} runs={[{ run_id: 'run-failed', lifecycle: 'FAILED', updated_at_us: 2, job: { job_id: 'job-failed', state: 'FAILED' } }]} onRefresh={vi.fn()} onError={onError} />)

    expect(await screen.findByText('后台执行失败')).toBeInTheDocument()
    expect(screen.getByText('Worker 在任务完成前异常退出')).toBeInTheDocument()
    expect(screen.getByText(/var\/logs\/workers\/job-failed\.log/)).toBeInTheDocument()
    expect(screen.getByText('下一步：重新启动后再次检查。')).toBeInTheDocument()
    expect(screen.getByText('复制这段信息后可直接询问 AI')).toBeInTheDocument()
    expect(runsApi.run).toHaveBeenCalledTimes(2)
    expect(onError).not.toHaveBeenCalled()
  })

  it('从已保存游标续读事件并用真实 sequence 刷新状态', async () => {
    let source: any
    class FakeEventSource {
      onmessage?: (event: MessageEvent) => void
      onerror?: () => void
      close = vi.fn()
      constructor(public url: string) { source = this }
    }
    ;(globalThis as any).EventSource = FakeEventSource
    localStorage.setItem('jiejian.cursor.job-1', JSON.stringify(4))
    const refresh = vi.fn()
    runsApi.run.mockResolvedValue({ run_id: 'run-3', lifecycle: 'RUNNING', job: { job_id: 'job-1', state: 'RUNNING' } })
    render(<StartCheckPage project={{ project_id: 'p1' }} runs={[{ run_id: 'run-3', lifecycle: 'RUNNING', job: { job_id: 'job-1', state: 'RUNNING' } }]} onRefresh={refresh} onError={vi.fn()} />)
    await waitFor(() => expect(source?.url).toBe('/api/jobs/job-1/events?after=4'))
    source.onmessage?.({ data: JSON.stringify({ sequence: 5, event_type: 'JOB_RUNNING' }), lastEventId: '' } as MessageEvent)
    expect(localStorage.getItem('jiejian.cursor.job-1')).toBe('5')
    expect(refresh).toHaveBeenCalled()
  })
})
