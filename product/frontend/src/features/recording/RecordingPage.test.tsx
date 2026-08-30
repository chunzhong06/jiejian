// 业务流程页面测试：保护业务选择、自动事实采用与同动作补录边界。

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RecordingPage } from './RecordingPage'

const api = vi.hoisted(() => ({
  setup: vi.fn(), recordings: vi.fn(), recording: vi.fn(), createRecording: vi.fn(), startCapture: vi.fn(), stopCapture: vi.fn(),
  reviewRecording: vi.fn(), finalizeRecording: vi.fn(), safetySetup: vi.fn(), confirmSafetySetup: vi.fn(), cancel: vi.fn(),
}))

vi.mock('../../api/recordings', () => ({ recordingsApi: {
  setup: api.setup, recordings: api.recordings, recording: api.recording, createRecording: api.createRecording,
  startCapture: api.startCapture, stopCapture: api.stopCapture, reviewRecording: api.reviewRecording,
  finalizeRecording: api.finalizeRecording, safetySetup: api.safetySetup, confirmSafetySetup: api.confirmSafetySetup,
} }))
vi.mock('../../api/runs', () => ({ runsApi: { cancel: api.cancel } }))

const action = { action_candidate_id: `action_${'1'.repeat(32)}`, display_name: '修改资源', risk_hint: 'WRITE' }
const identity = { test_identity_id: `tid_${'2'.repeat(32)}`, label: '普通成员账号 A', role_display_name: '普通成员' }
const target = { recording_id: `rec_${'3'.repeat(32)}`, project_id: 'p1', flow_id: 'flow-1', purpose: 'TARGET' as const, parent_recording_id: null, state: 'COMPLETED', action, test_identity: identity }
const originalEventSource = globalThis.EventSource

function safety(overrides: Record<string, unknown> = {}) {
  return {
    recording_id: target.recording_id, action_candidate_id: action.action_candidate_id, action_display_name: action.display_name,
    target_method: 'PATCH', recording_identity: { identity_id: identity.test_identity_id, label: identity.label, role_display_name: identity.role_display_name, status: 'PREPARED' },
    state_changing: true,
    resource_candidates: [{ candidate_id: `trc_${'4'.repeat(32)}`, label: '当前项目', suggested_resource_type: '项目', actual_resource_id: 'project-1', consumer: 'PATH', location: 'path[1]' }],
    observation_candidates: [], recovery_candidates: [], security_effect_candidates: [{ candidate_id: `sfc_${'5'.repeat(32)}`, kind: 'STATE_MUTATION', label: '更新项目内容', protected_fields: [] }],
    business_result: '更新项目内容', observation_status: 'MISSING', recovery_status: 'MISSING', ready: false,
    confirmed_setup: null, gaps: ['OBSERVATION_UNCONFIRMED', 'RECOVERY_UNCONFIRMED'], automatic_execution_allowed: false,
    ...overrides,
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
    render(<RecordingPage project={{ project_id: 'p1' }} onError={vi.fn()} onBack={vi.fn()} />)
    expect(await screen.findByText('请使用')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '普通成员账号 A · 普通成员' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '“修改资源”' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '打开浏览器并开始准备' }))
    await waitFor(() => expect(api.createRecording).toHaveBeenCalledWith('p1', action.action_candidate_id, identity.test_identity_id, 600))
    expect(screen.queryByRole('list', { name: '业务流程准备进度' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Profile|JSONPath|TARGET|高级/)).not.toBeInTheDocument()
  })

  it('只展示业务歧义选择，不提供重命名、删除、合并或技术路径编辑', async () => {
    const draft = { recording_id: target.recording_id, flow_id: 'flow-1', action_candidate_id: action.action_candidate_id, revision: 1, recommended_target_step_id: 'step-2', target_step_id: null, resource_candidate_id: null, variables: [], steps: [
      { id: 'step-1', name: '提交修改', method: 'PATCH', path: '/projects/project-1', resource_candidates: [{ candidate_id: 'resource-1111111111111111', consumer: 'PATH', location: 'path[1]', label: 'project-1，看起来是当前项目' }] },
      { id: 'step-2', name: '确认更新', method: 'POST', path: '/projects/project-1/confirm', resource_candidates: [] },
    ] }
    api.recordings.mockResolvedValue([{ ...target, state: 'PENDING_REVIEW' }])
    api.recording.mockResolvedValue({ recording: { ...target, state: 'PENDING_REVIEW' }, draft, capture_phase: 'FINISHED', action, test_identity: identity })
    render(<RecordingPage project={{ project_id: 'p1' }} onError={vi.fn()} onBack={vi.fn()} />)
    expect(await screen.findByText(/哪一步真正完成了/)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: '提交修改' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /重命名|删除|合并/ })).not.toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('/projects/project-1')
  })

  it('缺少观察和恢复时创建同动作、同账号的补录', async () => {
    const draft = { recording_id: target.recording_id, flow_id: 'flow-1', action_candidate_id: action.action_candidate_id, revision: 1, target_step_id: 'step-1', resource_candidate_id: 'resource-1111111111111111', steps: [], variables: [] }
    api.recordings.mockResolvedValue([target])
    api.recording.mockResolvedValue({ recording: target, draft, capture_phase: 'FINISHED', action, test_identity: identity })
    api.safetySetup.mockResolvedValue(safety())
    api.createRecording.mockResolvedValue({ recording: { ...target, recording_id: `rec_${'6'.repeat(32)}`, purpose: 'OBSERVATION', parent_recording_id: target.recording_id, state: 'CREATED' }, action, test_identity: identity, job: { job_id: 'job-2', state: 'QUEUED' } })
    render(<RecordingPage project={{ project_id: 'p1' }} onError={vi.fn()} onBack={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '补录验证操作' }))
    await waitFor(() => expect(api.createRecording).toHaveBeenCalledWith('p1', action.action_candidate_id, identity.test_identity_id, 600, 'OBSERVATION', target.recording_id))
  })

  it('唯一业务事实由后端自动采用', async () => {
    const draft = { recording_id: target.recording_id, flow_id: 'flow-1', action_candidate_id: action.action_candidate_id, revision: 1, target_step_id: 'step-1', resource_candidate_id: 'resource-1111111111111111', steps: [], variables: [] }
    const complete = safety({
      observation_candidates: [{ candidate_id: `obc_${'7'.repeat(32)}`, label: '独立读取并核对业务结果' }],
      recovery_candidates: [{ candidate_id: `rcc_${'8'.repeat(32)}`, label: '恢复测试现场' }],
    })
    api.recordings.mockResolvedValue([target]); api.recording.mockResolvedValue({ recording: target, draft, action, test_identity: identity }); api.safetySetup.mockResolvedValue(complete)
    api.confirmSafetySetup.mockResolvedValue({ ...complete, ready: true, automatic_execution_allowed: true, confirmed_setup: { resource: { resource_id: 'r', logical_name: '项目', resource_type: '项目', actual_resource_id: 'project-1', owner_test_identity_id: identity.test_identity_id } } })
    render(<RecordingPage project={{ project_id: 'p1' }} onError={vi.fn()} onBack={vi.fn()} />)
    await waitFor(() => expect(api.confirmSafetySetup).toHaveBeenCalledWith(target.recording_id, {}))
  })
})
