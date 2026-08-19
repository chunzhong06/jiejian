import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { StartCheckPage } from './StartCheckPage'

const permissionApi = vi.hoisted(() => ({ profiles: vi.fn().mockResolvedValue([]), submit: vi.fn() }))
const runsApi = vi.hoisted(() => ({ run: vi.fn(), cancel: vi.fn() }))
vi.mock('../../api/executionProfiles', () => ({ executionProfilesApi: permissionApi }))
vi.mock('../../api/runs', () => ({ runsApi }))

describe('StartCheckPage', () => {
  afterEach(() => { delete (globalThis as any).EventSource; localStorage.clear() })
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
