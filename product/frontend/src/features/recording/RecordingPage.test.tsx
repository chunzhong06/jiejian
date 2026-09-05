// 业务流程页面测试：保护正式动作来源、采集控制、审阅与工作区续接。

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RecordingPage } from './RecordingPage'

const api = vi.hoisted(() => ({
  setup: vi.fn(), recordings: vi.fn(), recording: vi.fn(), createRecording: vi.fn(), startCapture: vi.fn(), stopCapture: vi.fn(),
  reviewRecording: vi.fn(), finalizeRecording: vi.fn(), cancel: vi.fn(),
}))

vi.mock('../../api/recordings', () => ({ recordingsApi: {
  setup: api.setup, recordings: api.recordings, recording: api.recording, createRecording: api.createRecording,
  startCapture: api.startCapture, stopCapture: api.stopCapture, reviewRecording: api.reviewRecording,
  finalizeRecording: api.finalizeRecording,
} }))
vi.mock('../../api/runs', () => ({ runsApi: { cancel: api.cancel } }))

const action = { business_action_id: `bac_${'1'.repeat(32)}`, display_name: '修改资源', action_revision: 3 }
const identity = { test_identity_id: `tid_${'2'.repeat(32)}`, label: '普通成员账号 A', actor_display_name: '普通成员' }
const target = { recording_id: `rec_${'3'.repeat(32)}`, project_id: 'p1', flow_id: 'flow-1', purpose: 'TARGET' as const, parent_recording_id: null, state: 'COMPLETED', action, test_identity: identity }
const originalEventSource = globalThis.EventSource

function pageProps() {
  return {
    project: { project_id: 'p1' },
    onError: vi.fn(),
    onBack: vi.fn(),
    onStateChanged: vi.fn().mockResolvedValue({ status: {}, readiness: {}, runs: [] }),
    onContinuePreparation: vi.fn(),
  }
}

describe('RecordingPage', () => {
  beforeEach(() => {
    localStorage.clear(); vi.clearAllMocks()
    ;(globalThis as unknown as { EventSource: unknown }).EventSource = class {
      onmessage: ((event: MessageEvent) => void) | null = null
      onerror: (() => void) | null = null
      close() {}
    }
    api.setup.mockResolvedValue({ action_options: [action], test_identity_options: [identity] })
    api.recordings.mockResolvedValue([])
  })
  afterEach(() => {
    cleanup()
    ;(globalThis as unknown as { EventSource: unknown }).EventSource = originalEventSource
  })

  it('用业务动作与已准备账号创建受控录制', async () => {
    api.createRecording.mockResolvedValue({ recording: { ...target, state: 'CREATED' }, job: { job_id: 'job-1', state: 'QUEUED' }, action, test_identity: identity })
    const props = pageProps()
    render(<RecordingPage {...props} />)
    expect(await screen.findByText('请使用')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '普通成员账号 A · 普通成员' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '“修改资源”' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '打开浏览器并开始准备' }))
    await waitFor(() => expect(api.createRecording).toHaveBeenCalledWith('p1', action.business_action_id, action.action_revision, identity.test_identity_id, 600))
    expect(props.onStateChanged).not.toHaveBeenCalled()
    expect(screen.queryByRole('list', { name: '业务流程准备进度' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Profile|JSONPath|TARGET|高级/)).not.toBeInTheDocument()
  })

  it('只展示业务歧义选择，不提供重命名、删除、合并或技术路径编辑', async () => {
    const draft = { schema_version: '2' as const, action_revision: action.action_revision, test_identity_id: identity.test_identity_id, recording_id: target.recording_id, flow_id: 'flow-1', business_action_id: action.business_action_id, revision: 1, recommended_target_step_id: 'step-2', target_step_id: null, resource_candidate_id: null, variables: [], steps: [
      { id: 'step-1', name: '提交修改', method: 'PATCH', path: '/projects/project-1', resource_candidates: [{ candidate_id: 'resource-1111111111111111', consumer: 'PATH', location: 'path[1]', label: 'project-1，看起来是当前项目' }] },
      { id: 'step-2', name: '确认更新', method: 'POST', path: '/projects/project-1/confirm', resource_candidates: [] },
    ] }
    api.recordings.mockResolvedValue([{ ...target, state: 'PENDING_REVIEW' }])
    api.recording.mockResolvedValue({ recording: { ...target, state: 'PENDING_REVIEW' }, draft, capture_phase: 'FINISHED', action, test_identity: identity })
    render(<RecordingPage {...pageProps()} />)
    expect(await screen.findByText(/哪一步真正完成了/)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: '提交修改' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /重命名|删除|合并/ })).not.toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('/projects/project-1')
  })

  it('已保存流程按工作区继续，不调用旧安全准备确认', async () => {
    api.recordings.mockResolvedValue([target])
    api.recording.mockResolvedValue({ recording: target, capture_phase: 'FINISHED', action, test_identity: identity })
    const props = pageProps()
    render(<RecordingPage {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: '继续准备' }))
    expect(props.onContinuePreparation).toHaveBeenCalledTimes(1)
    expect(api.createRecording).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /采用已识别|补录验证|补录恢复/ })).not.toBeInTheDocument()
    expect(props.onStateChanged).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '刷新流程状态' }))
    await waitFor(() => expect(props.onStateChanged).toHaveBeenCalledTimes(1))
  })

  it('采集使用开始和停止控制，不把完成操作当作取消', async () => {
    const active = { ...target, state: 'RECORDING' }
    api.recordings.mockResolvedValue([active])
    api.recording.mockResolvedValue({ recording: active, capture_phase: 'AWAITING_CAPTURE', action, test_identity: identity })
    api.startCapture.mockResolvedValue({ recording: active, capture_phase: 'CAPTURING' })
    api.stopCapture.mockResolvedValue({ recording: { ...active, state: 'PROCESSING' }, capture_phase: 'STOPPING' })
    render(<RecordingPage {...pageProps()} />)
    fireEvent.click(await screen.findByRole('button', { name: '开始记录这个操作' }))
    fireEvent.click(await screen.findByRole('button', { name: '我已完成这个操作' }))
    await waitFor(() => expect(api.stopCapture).toHaveBeenCalledWith(target.recording_id))
    expect(api.startCapture).toHaveBeenCalledWith(target.recording_id)
    expect(api.cancel).not.toHaveBeenCalled()
  })
})