// 业务流程页面测试：保护正式动作来源、采集控制、审阅与工作区续接。

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PrimaryTaskDto } from '../../api/workspace'
import { RecordingPage } from './RecordingPage'

const api = vi.hoisted(() => ({
  setup: vi.fn(), recordings: vi.fn(), recording: vi.fn(), createRecording: vi.fn(), startCapture: vi.fn(), stopCapture: vi.fn(),
  reviewRecording: vi.fn(), finalizeRecording: vi.fn(), cancel: vi.fn(), discard: vi.fn(),
}))

vi.mock('../../api/recordings', () => ({ recordingsApi: {
  setup: api.setup, recordings: api.recordings, recording: api.recording, createRecording: api.createRecording,
  startCapture: api.startCapture, stopCapture: api.stopCapture, reviewRecording: api.reviewRecording,
  finalizeRecording: api.finalizeRecording, discard: api.discard,
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
    api.recording.mockResolvedValue({ recording: { ...target, state: 'CREATED' }, capture_phase: 'PREPARING_BROWSER', action, test_identity: identity })
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
    await waitFor(() => expect(api.createRecording).toHaveBeenCalledWith('p1', action.business_action_id, action.action_revision, identity.test_identity_id, 600, 'TARGET', undefined, undefined))
    await waitFor(() => expect(props.onStateChanged).toHaveBeenCalledTimes(1))
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
    await waitFor(() => expect(props.onStateChanged).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: '刷新流程状态' }))
    await waitFor(() => expect(props.onStateChanged).toHaveBeenCalledTimes(2))
  })

  it('采集使用开始和停止控制，不把完成操作当作取消', async () => {
    const active = { ...target, state: 'RECORDING' }
    api.recordings.mockResolvedValue([active])
    api.recording.mockResolvedValue({ recording: active, capture_phase: 'AWAITING_CAPTURE', action, test_identity: identity })
    api.startCapture.mockImplementation(async () => { const view = { recording: active, capture_phase: 'CAPTURING' }; api.recording.mockResolvedValue(view); return view })
    api.stopCapture.mockImplementation(async () => { const view = { recording: { ...active, state: 'PROCESSING' }, capture_phase: 'STOPPING' }; api.recording.mockResolvedValue(view); return view })
    render(<RecordingPage {...pageProps()} />)
    fireEvent.click(await screen.findByRole('button', { name: '开始记录这个操作' }))
    fireEvent.click(await screen.findByRole('button', { name: '我已完成这个操作' }))
    await waitFor(() => expect(api.stopCapture).toHaveBeenCalledWith(target.recording_id))
    expect(api.startCapture).toHaveBeenCalledWith(target.recording_id)
    expect(api.cancel).not.toHaveBeenCalled()
  })
  it('有待审主任务时只恢复指定录制，不采用项目最新记录', async () => {
    const task: PrimaryTaskDto = { task_id: 'task-review', task_kind: 'REVIEW_RECORDING', business_action_id: action.business_action_id, business_actor_id: null, title: '审阅当前演示', why_now: '当前有待审内容', user_responsibility: '核对这次演示', system_will_do: '只保存确认的材料', route: '/tests', can_execute: true, stale_fingerprint: 'f', recording_id: target.recording_id, test_identity_id: identity.test_identity_id, action_revision: 3 }
    api.recordings.mockResolvedValue([{ ...target, recording_id: 'unrelated-latest' }])
    api.recording.mockResolvedValue({ recording: target })
    render(<RecordingPage {...pageProps()} task={task} />)
    await waitFor(() => expect(api.recording).toHaveBeenCalledWith(target.recording_id))
    expect(api.recording).not.toHaveBeenCalledWith('unrelated-latest')
    expect(api.createRecording).not.toHaveBeenCalled()
  })
  it('观察补录先说明具体业务结果，并固定 effect、来源录制与账号', async () => {
    const task: PrimaryTaskDto = { task_id: 'task-observation', task_kind: 'COMPLETE_EFFECT_EVIDENCE', business_action_id: action.business_action_id, business_actor_id: null, title: '演示如何确认业务结果', why_now: '缺少证明', user_responsibility: '演示在哪里确认结果', system_will_do: '关联已有结果', route: '/tests', can_execute: true, stale_fingerprint: 'f', recording_purpose: 'OBSERVATION', parent_recording_id: target.recording_id, effect_id: 'effect-package', test_identity_id: identity.test_identity_id, action_revision: 3 }
    api.recordings.mockResolvedValue([target])
    api.createRecording.mockResolvedValue({ recording: { ...target, recording_id: 'new-observation', purpose: 'OBSERVATION', state: 'CREATED' } })
    const props = pageProps(); props.onStateChanged.mockResolvedValue({ primary_task: task })
    render(<RecordingPage {...props} task={task} effectName="完整交付包已经形成" />)
    expect(await screen.findByText(/通常在哪里确认“完整交付包已经形成”/)).toBeInTheDocument()
    const button = await screen.findByRole('button', { name: '打开浏览器并开始准备' })
    await waitFor(() => expect(button).toBeEnabled())
    expect(api.recording).not.toHaveBeenCalled()
    fireEvent.click(button)
    await waitFor(() => expect(api.createRecording).toHaveBeenCalledWith('p1', action.business_action_id, 3, identity.test_identity_id, 600, 'OBSERVATION', target.recording_id, 'effect-package'))
  })

  it('补录歧义只展示服务端候选，选择后刷新事实才能保存', async () => {
    const draft = { schema_version: '2' as const, recording_id: target.recording_id, flow_id: 'f', business_action_id: action.business_action_id, action_revision: 3, test_identity_id: identity.test_identity_id, revision: 1, target_step_id: null, steps: [] }
    const view = { recording: { ...target, state: 'PENDING_REVIEW', purpose: 'OBSERVATION' as const }, draft,
      supplement_choices: [{ step_id: 'step-good1', label: '查看交付包列表' }, { step_id: 'step-good2', label: '查看交付详情' }] }
    api.recordings.mockResolvedValue([view.recording]); api.recording.mockResolvedValue(view)
    api.reviewRecording.mockImplementation(async () => {
      const next = { ...view, draft: { ...draft, revision: 2, target_step_id: 'step-good2' } }
      api.recording.mockResolvedValue(next); return next
    })
    render(<RecordingPage {...pageProps()} />)
    expect(await screen.findByRole('button', { name: '完成业务选择后保存' })).toBeDisabled()
    fireEvent.click(screen.getByRole('radio', { name: '查看交付详情' }))
    await waitFor(() => expect(api.reviewRecording).toHaveBeenCalledWith(target.recording_id, { schema_version: '1', operation: 'CONFIRM_TARGET_STEP', step_id: 'step-good2' }))
    await waitFor(() => expect(screen.getByRole('button', { name: '保存本次补录' })).toBeEnabled())
    expect(api.finalizeRecording).not.toHaveBeenCalled()
  })
  it('没有补录候选时禁止保存，但可以明确放弃并刷新主任务', async () => {
    const draft = { schema_version: '2' as const, recording_id: target.recording_id, flow_id: 'f', business_action_id: action.business_action_id, action_revision: 3, test_identity_id: identity.test_identity_id, revision: 1, target_step_id: null, steps: [] }
    const view = { recording: { ...target, state: 'PENDING_REVIEW', purpose: 'RECOVERY' as const }, draft, supplement_choices: [] }
    api.recordings.mockResolvedValue([view.recording]); api.recording.mockResolvedValue(view)
    api.discard.mockImplementation(async () => { const next = { ...view, recording: { ...view.recording, state: 'CANCELLED' } }; api.recording.mockResolvedValue(next); return next })
    const props = pageProps(); render(<RecordingPage {...props} />)
    expect(await screen.findByRole('button', { name: '完成业务选择后保存' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '放弃这次录制' }))
    expect(api.discard).not.toHaveBeenCalled()
    fireEvent.click(await screen.findByRole('button', { name: '放弃录制' }))
    await waitFor(() => expect(api.discard).toHaveBeenCalledWith(target.recording_id))
    expect(api.finalizeRecording).not.toHaveBeenCalled()
    await waitFor(() => expect(props.onStateChanged.mock.calls.length).toBeGreaterThan(1))
  })

})