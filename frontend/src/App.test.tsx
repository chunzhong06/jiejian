import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App, { JobProgress, RecordingPage, VerifyPage } from './App'

const mockApi = vi.hoisted(() => ({
  projects: vi.fn().mockResolvedValue([]),
  cancel: vi.fn().mockResolvedValue({}),
  recordings: vi.fn().mockResolvedValue([]),
  recording: vi.fn(),
  reviewRecording: vi.fn(),
  finalizeRecording: vi.fn(),
  run: vi.fn(),
  findings: vi.fn(),
  evidence: vi.fn(),
  evidenceDetail: vi.fn(),
}))

vi.mock('./api/client', () => ({
  api: mockApi,
  ApiError: class extends Error {},
}))

describe('应用壳', () => {
  beforeEach(() => { localStorage.clear(); window.location.hash = ''; mockApi.cancel.mockClear(); mockApi.recordings.mockReset(); mockApi.recording.mockReset(); mockApi.reviewRecording.mockReset(); mockApi.finalizeRecording.mockReset(); mockApi.run.mockReset(); mockApi.findings.mockReset(); mockApi.evidence.mockReset(); mockApi.evidenceDetail.mockReset() })

  it('显示六个用户阶段', async () => {
    render(<App />)
    expect(await screen.findByText('接入项目')).toBeInTheDocument()
    for (const phase of ['录制', '建约', '测试', '验证', '报告']) {
      expect(screen.getAllByText(phase).length).toBeGreaterThan(0)
    }
  })

  it('从 hash 路由恢复阶段且未选项目时保留明确提示', async () => {
    window.location.hash = '#/report'
    const first = render(<App />)
    expect(await screen.findByText('请先在接入阶段选择项目')).toBeInTheDocument()
    expect(window.location.hash).toBe('#/report')
    first.unmount()
    render(<App />)
    expect(window.location.hash).toBe('#/report')
  })

  it('恢复任务事件时保留原生重连，卸载才关闭，取消必须由用户按钮触发', async () => {
    const sources: Array<{ url: string; onmessage: ((event: MessageEvent) => void) | null; onerror: (() => void) | null; close: ReturnType<typeof vi.fn> }> = []
    vi.stubGlobal('EventSource', class {
      url: string
      onmessage: ((event: MessageEvent) => void) | null = null
      onerror: (() => void) | null = null
      close = vi.fn()
      constructor(url: string) { this.url = url; sources.push(this) }
    })
    localStorage.setItem('jiejian.cursor.job_progress_test', '4')
    const refresh = vi.fn()
    const rendered = render(<JobProgress job={{ job_id: 'job_progress_test', state: 'RUNNING' }} onRefresh={refresh} onError={vi.fn()} />)
    expect(sources[0].url).toBe('/api/v1/jobs/job_progress_test/events?after=4')
    sources[0].onmessage?.({ data: JSON.stringify({ sequence: 7, event_type: 'JOB_RUNNING' }) } as MessageEvent)
    expect(localStorage.getItem('jiejian.cursor.job_progress_test')).toBe('7')
    sources[0].onerror?.()
    expect(sources[0].close).not.toHaveBeenCalled()
    expect(mockApi.cancel).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '主动取消' }))
    await waitFor(() => expect(mockApi.cancel).toHaveBeenCalledWith('job_progress_test'))
    rendered.unmount()
    expect(sources[0].close).toHaveBeenCalledTimes(1)
  })

  it('展示已完成运行的可信概览与 INCONCLUSIVE 原因码', async () => {
    mockApi.run.mockResolvedValue({
      run_id: 'run-overview',
      lifecycle: 'COMPLETED',
      verdict: 'INCONCLUSIVE',
      result_integrity: 'VERIFIED',
      target_scope: { base_url: 'http://127.0.0.1:18080', allowed_hosts: ['127.0.0.1'], allowed_ports: [18080] },
      budget: { max_requests: 64, max_response_bytes: 262144, request_timeout_us: 30000000 },
      observer_health: { http: { configured: true, required: true }, owner_api: { configured: true, required: true } },
      case_progress: { status: 'PUBLISHED', completed: 2, total: 2 },
      finding_count: 3,
      reason_codes: ['MISSING_OBSERVATION'],
      safety_context: null,
    })
    mockApi.findings.mockResolvedValue([])
    mockApi.evidence.mockResolvedValue([])
    render(<VerifyPage run={{ run_id: 'run-overview' }} onError={vi.fn()} />)
    expect((await screen.findAllByText('http://127.0.0.1:18080')).length).toBeGreaterThan(0)
    expect(screen.getByText('COMPLETED')).toBeInTheDocument()
    expect(screen.getByText('MISSING_OBSERVATION')).toBeInTheDocument()
    expect(screen.getByText('2/2')).toBeInTheDocument()
    const findingCount = screen.getByText('Finding 数量').closest('.ant-descriptions-item')
    expect(findingCount).not.toBeNull()
    expect(within(findingCount as HTMLElement).getByText('3')).toBeInTheDocument()
    expect(screen.getByText('结果完整性：VERIFIED')).toBeInTheDocument()
    expect(screen.getByText('Gate verdict')).toBeInTheDocument()
    expect(screen.getByText('INCONCLUSIVE')).toBeInTheDocument()
    expect(screen.queryByText('SAFETY_STOPPED · 安全边界已停止运行')).not.toBeInTheDocument()
  })

  it('展示安全停止上下文且不伪造 INCONCLUSIVE verdict', async () => {
    mockApi.run.mockResolvedValue({
      run_id: 'run-stopped',
      lifecycle: 'SAFETY_STOPPED',
      verdict: null,
      result_integrity: 'VERIFIED',
      target_scope: { base_url: 'http://127.0.0.1:18081', allowed_hosts: ['127.0.0.1'], allowed_ports: [18081] },
      budget: { max_requests: 64, max_response_bytes: 262144, request_timeout_us: 30000000 },
      observer_health: { http: { configured: true, required: true }, owner_api: { configured: true, required: true } },
      case_progress: { status: 'UNAVAILABLE', completed: null, total: null },
      finding_count: null,
      reason_codes: ['REQUEST_BUDGET_EXCEEDED'],
      safety_context: { reason_codes: ['REQUEST_BUDGET_EXCEEDED'], target_scope: { base_url: 'http://127.0.0.1:18081' }, budget: { max_requests: 64 } },
    })
    mockApi.findings.mockResolvedValue([])
    mockApi.evidence.mockResolvedValue([])
    render(<VerifyPage run={{ run_id: 'run-stopped' }} onError={vi.fn()} />)
    expect(await screen.findByText('SAFETY_STOPPED')).toBeInTheDocument()
    expect(screen.getByText('SAFETY_STOPPED · 安全边界已停止运行')).toBeInTheDocument()
    expect(screen.getByText('REQUEST_BUDGET_EXCEEDED')).toBeInTheDocument()
    const pendingVerdict = await screen.findByText('等待结论')
    const gateVerdict = pendingVerdict.closest('.ant-descriptions-item')
    expect(gateVerdict).not.toBeNull()
    expect(within(gateVerdict as HTMLElement).getByText('Gate verdict')).toBeInTheDocument()
    expect(within(gateVerdict as HTMLElement).getByText('等待结论')).toBeInTheDocument()
    expect(screen.getAllByText('发布后可用').length).toBeGreaterThanOrEqual(2)
    expect(within(gateVerdict as HTMLElement).queryByText('INCONCLUSIVE')).not.toBeInTheDocument()
  })

  it('完成录制审阅到 revision 更新再最终化的闭环', async () => {
    mockApi.recordings.mockResolvedValue([{ recording_id: 'rec-1' }])
    mockApi.recording.mockResolvedValue({ recording: { recording_id: 'rec-1', project_id: 'project-1', state: 'PENDING_REVIEW' }, draft: { revision: 1, flow_id: 'flow-1', steps: [], variables: [] }, job: null })
    mockApi.reviewRecording.mockResolvedValue({ recording: { recording_id: 'rec-1', project_id: 'project-1', state: 'PENDING_REVIEW' }, draft: { revision: 2, flow_id: 'flow-1', steps: [], variables: [] }, job: null })
    mockApi.finalizeRecording.mockResolvedValue({ recording: { recording_id: 'rec-1', project_id: 'project-1', state: 'COMPLETED' }, flow_path: 'var/projects/project-1/recordings/rec-1/flow.json' })
    render(<RecordingPage project={{ project_id: 'project-1' }} onError={vi.fn()} />)
    expect(await screen.findByText('FlowDraft revision 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '提交审阅' }))
    await waitFor(() => expect(mockApi.reviewRecording).toHaveBeenCalled())
    expect(await screen.findByText('FlowDraft revision 2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '最终化' }))
    await waitFor(() => expect(mockApi.finalizeRecording).toHaveBeenCalledWith('rec-1'))
    expect(await screen.findByText('var/projects/project-1/recordings/rec-1/flow.json')).toBeInTheDocument()
  })
})
