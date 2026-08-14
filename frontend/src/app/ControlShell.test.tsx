import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ControlShell, { remembered } from './ControlShell'
import { JobProgress } from '../features/runs/JobProgress'
import { RecordingPage } from '../features/recording/RecordingPage'
import { ReportPage } from '../features/results/ReportPage'
import { VerifyPage } from '../features/verification/VerifyPage'

const mockApi = vi.hoisted(() => ({
  projects: vi.fn().mockResolvedValue([]),
  runs: vi.fn().mockResolvedValue([]),
  llmProfiles: vi.fn().mockResolvedValue([]),
  systemStatus: vi.fn().mockResolvedValue({ api: 'available', worker: 'stopped', browser: 'unknown' }),
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

vi.mock('../api/http', () => ({ ApiError: class extends Error {}, request: vi.fn().mockResolvedValue({ status: 'stopped', demo_data: true, session_id: null, project_id: null, run_id: null, job_id: null, message: '内置演示尚未启动。' }) }))
vi.mock('../api/projects', () => ({ projectsApi: mockApi }))
vi.mock('../api/recordings', () => ({ recordingsApi: mockApi }))
vi.mock('../api/results', () => ({ resultsApi: mockApi }))
vi.mock('../api/runs', () => ({ runsApi: mockApi }))
vi.mock('../api/llm', () => ({ llmApi: { profiles: mockApi.llmProfiles } }))
vi.mock('../api/system', () => ({ systemApi: { status: mockApi.systemStatus } }))

describe('应用壳', () => {
  beforeEach(() => { localStorage.clear(); window.location.hash = ''; mockApi.projects.mockReset().mockResolvedValue([]); mockApi.runs.mockReset().mockResolvedValue([]); mockApi.llmProfiles.mockReset().mockResolvedValue([]); mockApi.systemStatus.mockReset().mockResolvedValue({ api: 'available', worker: 'stopped', browser: 'unknown' }); mockApi.cancel.mockClear(); mockApi.recordings.mockReset(); mockApi.recording.mockReset(); mockApi.reviewRecording.mockReset(); mockApi.finalizeRecording.mockReset(); mockApi.run.mockReset(); mockApi.findings.mockReset(); mockApi.evidence.mockReset(); mockApi.evidenceDetail.mockReset() })

  it('显示六个用户阶段', async () => {
    render(<ControlShell />)
    expect(await screen.findByText('检查你的应用有没有权限越界')).toBeInTheDocument()
    for (const phase of ['录制', '建约', '测试', '验证', '报告']) {
      expect(screen.getAllByText(phase).length).toBeGreaterThan(0)
    }
    expect(screen.getByRole('button', { name: '模型服务' })).toBeInTheDocument()
    expect(screen.getByText('API · 可用')).toBeInTheDocument()
    expect(screen.getByText('Worker · 已停止')).toBeInTheDocument()
    expect(screen.getByText('浏览器 · 未知')).toBeInTheDocument()
    expect(document.querySelector('.topbar .status-cluster')).toBeInTheDocument()
    expect(document.querySelectorAll('.phase-steps .ant-steps-item')).toHaveLength(6)
    expect(document.querySelector('.phase-steps')?.className).toContain('phase-steps')
  })

  it('从 hash 路由恢复阶段且未选项目时保留明确提示', async () => {
    window.location.hash = '#/report'
    const first = render(<ControlShell />)
    expect(await screen.findByText('请先在接入阶段选择项目')).toBeInTheDocument()
    expect(window.location.hash).toBe('#/report')
    first.unmount()
    render(<ControlShell />)
    expect(window.location.hash).toBe('#/report')
  })

  it('只显示后端确认的系统状态，并在陈旧项目不存在时清除继续入口', async () => {
    localStorage.setItem(remembered.project, JSON.stringify({ project_id: 'stale-project', name: '陈旧项目' }))
    mockApi.systemStatus.mockResolvedValue({ api: 'unknown', worker: 'unknown', browser: 'unknown' })
    render(<ControlShell />)
    expect(await screen.findByText('检查你的应用有没有权限越界')).toBeInTheDocument()
    expect(screen.getAllByText(/API · 未知/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Worker · 未知/).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: '继续建约' })).not.toBeInTheDocument()
    expect(localStorage.getItem(remembered.project)).toBeNull()
  })

  it('错误恢复重试会重新挂载当前页面并再次读取当前运行', async () => {
    window.location.hash = '#/verify'
    localStorage.setItem(remembered.project, JSON.stringify({ project_id: 'project-retry' }))
    mockApi.projects.mockResolvedValue([{ project_id: 'project-retry', name: '重试项目' }])
    mockApi.runs.mockResolvedValue([{ run_id: 'run-retry', lifecycle: 'COMPLETED', result_integrity: 'VERIFIED' }])
    mockApi.run.mockRejectedValueOnce({ code: 'TEMPORARY_READ_FAILURE', message: '暂时无法读取检查状态' }).mockResolvedValue({ run_id: 'run-retry', lifecycle: 'COMPLETED', result_integrity: 'VERIFIED', case_progress: { status: 'PUBLISHED', completed: 1, total: 1 } })
    mockApi.findings.mockResolvedValue([])
    mockApi.evidence.mockResolvedValue([])
    render(<ControlShell />)
    await screen.findByText('这一步没有完成')
    fireEvent.click(screen.getByRole('button', { name: '刷新状态并重试' }))
    await waitFor(() => expect(mockApi.run).toHaveBeenCalledTimes(2))
  })

  it('按真实 profile 状态优先显示正在测试，不因其他 profile 可用而伪造可用', async () => {
    mockApi.llmProfiles.mockResolvedValue([
      { profile_name: 'available', enabled: true, secret_configured: true, connection_status: 'available' },
      { profile_name: 'testing', enabled: true, secret_configured: true, connection_status: 'testing' },
    ])
    render(<ControlShell />)
    expect(await screen.findByText('LLM · 正在测试')).toBeInTheDocument()
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
    expect(screen.getByText('已完成')).toBeInTheDocument()
    expect(screen.getByText('MISSING_OBSERVATION')).toBeInTheDocument()
    expect(screen.getByText('2/2')).toBeInTheDocument()
    const findingCount = screen.getByText('Finding 数量').closest('.ant-descriptions-item')
    expect(findingCount).not.toBeNull()
    expect(within(findingCount as HTMLElement).getByText('3')).toBeInTheDocument()
    expect(screen.getByText('已验证')).toBeInTheDocument()
    expect(screen.getByText('证据不足，暂时不能下结论')).toBeInTheDocument()
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
    expect(await screen.findByText('已安全停止')).toBeInTheDocument()
    expect(screen.getByText('安全边界已停止运行')).toBeInTheDocument()
    const pendingVerdict = await screen.findByText('等待结论')
    const gateVerdict = pendingVerdict.closest('.ant-descriptions-item')
    expect(gateVerdict).not.toBeNull()
    expect(within(gateVerdict as HTMLElement).getByText('安全结论')).toBeInTheDocument()
    expect(within(gateVerdict as HTMLElement).getByText('等待结论')).toBeInTheDocument()
    expect(screen.getAllByText('发布后可用').length).toBeGreaterThanOrEqual(2)
    expect(within(gateVerdict as HTMLElement).queryByText('INCONCLUSIVE')).not.toBeInTheDocument()
  })

  it('V2 Evidence 索引不伪造未知 verdict，查看详情后才展示真实 verdict', async () => {
    mockApi.run.mockResolvedValue({
      run_id: 'run-v2-evidence',
      execution_schema_version: '2',
      result_integrity: 'VERIFIED',
      lifecycle: 'COMPLETED',
      case_progress: { status: 'PUBLISHED', completed: 1, total: 1 },
      observer_health: { required_observers: ['owner_api'] },
      coverage_record_count: 1,
      coverage_gap_count: 0,
    })
    mockApi.evidence.mockResolvedValue([{ case_id: 'case-1', evidence_id: 'ev_123', byte_count: 256 }])
    mockApi.evidenceDetail.mockResolvedValue({ evidence_id: 'ev_123', verdict: 'SAFE' })
    render(<VerifyPage run={{ run_id: 'run-v2-evidence' }} onError={vi.fn()} />)
    expect(await screen.findByText('Evidence ev_123')).toBeInTheDocument()
    expect(screen.queryByText(/INCONCLUSIVE/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /高级：复杂权限证据与运行细节/ }))
    fireEvent.click(screen.getByRole('button', { name: '查看证据' }))
    expect(await screen.findByText(/"verdict": "SAFE"/)).toBeInTheDocument()
  })

  it('V2 报告仅在可信发布后提示证据已发布，未发布和无效结果不伪造', async () => {
    mockApi.run.mockResolvedValue({
      run_id: 'run-v2-report',
      execution_schema_version: '2',
      result_integrity: 'UNAVAILABLE',
      lifecycle: 'RUNNING',
    })
    const first = render(<ReportPage run={{ run_id: 'run-v2-report' }} onError={vi.fn()} />)
    expect((await screen.findAllByText('等待已发布证据。')).length).toBeGreaterThan(0)
    expect(screen.queryByText('复杂权限证据已发布')).not.toBeInTheDocument()
    first.unmount()

    mockApi.run.mockResolvedValue({
      run_id: 'run-v2-report',
      execution_schema_version: '2',
      result_integrity: 'INVALID',
      lifecycle: 'COMPLETED',
    })
    render(<ReportPage run={{ run_id: 'run-v2-report' }} onError={vi.fn()} />)
    expect((await screen.findAllByText('结果完整性无效，暂不提供报告。')).length).toBeGreaterThan(0)
    expect(screen.queryByText('复杂权限证据已发布')).not.toBeInTheDocument()
  })

  it('完成录制审阅到 revision 更新再最终化的闭环', async () => {
    mockApi.recordings.mockResolvedValue([{ recording_id: 'rec-1' }])
    mockApi.recording.mockResolvedValue({ recording: { recording_id: 'rec-1', project_id: 'project-1', state: 'PENDING_REVIEW' }, draft: { revision: 1, flow_id: 'flow-1', steps: [], variables: [] }, job: null })
    mockApi.reviewRecording.mockResolvedValue({ recording: { recording_id: 'rec-1', project_id: 'project-1', state: 'PENDING_REVIEW' }, draft: { revision: 2, flow_id: 'flow-1', steps: [], variables: [] }, job: null })
    mockApi.finalizeRecording.mockResolvedValue({ recording: { recording_id: 'rec-1', project_id: 'project-1', state: 'COMPLETED' }, flow_path: 'var/projects/project-1/recordings/rec-1/flow.json' })
    render(<RecordingPage project={{ project_id: 'project-1' }} onError={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /高级：录制与步骤调整/ }))
    expect(await screen.findByText('步骤草稿 revision 1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '提交审阅' }))
    await waitFor(() => expect(mockApi.reviewRecording).toHaveBeenCalled())
    expect(await screen.findByText('步骤草稿 revision 2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '最终化' }))
    await waitFor(() => expect(mockApi.finalizeRecording).toHaveBeenCalledWith('rec-1'))
    expect(await screen.findByText('var/projects/project-1/recordings/rec-1/flow.json')).toBeInTheDocument()
  })
})
