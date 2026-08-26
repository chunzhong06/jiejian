/* 业务流程录制页测试：保护动作与测试身份入口、显式 TARGET/资源确认及普通用户展示。 */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RecordingPage } from './RecordingPage'

const api = vi.hoisted(() => ({
  setup: vi.fn(),
  recordings: vi.fn(),
  recording: vi.fn(),
  createRecording: vi.fn(),
  startCapture: vi.fn(),
  stopCapture: vi.fn(),
  reviewRecording: vi.fn(),
  finalizeRecording: vi.fn(),
  safetySetup: vi.fn(),
  confirmSafetySetup: vi.fn(),
  cancel: vi.fn(),
}))

vi.mock('../../api/recordings', () => ({ recordingsApi: {
  setup: api.setup,
  recordings: api.recordings,
  recording: api.recording,
  createRecording: api.createRecording,
  startCapture: api.startCapture,
  stopCapture: api.stopCapture,
  reviewRecording: api.reviewRecording,
  finalizeRecording: api.finalizeRecording,
  safetySetup: api.safetySetup,
  confirmSafetySetup: api.confirmSafetySetup,
} }))
vi.mock('../../api/runs', () => ({ runsApi: { cancel: api.cancel } }))

class EventSourceStub {
  onmessage: ((message: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  close() { return undefined }
}

const action = { action_candidate_id: 'action_0123456789abcdef0123456789abcdef', display_name: '修改资源', risk_hint: 'WRITE' }
const identity = { test_identity_id: 'test_identity_0123456789abcdef0123456789abcdef', label: '普通成员账号 A', role_display_name: '普通成员' }

describe('RecordingPage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    vi.stubGlobal('EventSource', EventSourceStub)
    api.setup.mockResolvedValue({ schema_version: '1', project_id: 'p1', action_options: [action], test_identity_options: [identity] })
    api.recordings.mockResolvedValue([])
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('以已确认动作、测试身份和明确开始停止动作驱动录制状态', async () => {
    api.createRecording.mockResolvedValue({
      recording: { recording_id: 'rec-1', project_id: 'p1', state: 'CREATED' },
      job: { job_id: 'job-1', state: 'QUEUED' },
      action,
      test_identity: identity,
    })
    api.recording.mockResolvedValue({
      recording: { recording_id: 'rec-1', project_id: 'p1', state: 'STARTING' },
      job: { job_id: 'job-1', state: 'RUNNING' },
      draft: null,
      capture_phase: 'AWAITING_CAPTURE',
    })
    api.startCapture.mockResolvedValue({
      recording: { recording_id: 'rec-1', project_id: 'p1', state: 'STARTING' },
      draft: null,
      capture_phase: 'CAPTURE_STARTING',
    })
    api.stopCapture.mockResolvedValue({
      recording: { recording_id: 'rec-1', project_id: 'p1', state: 'RECORDING' },
      draft: null,
      capture_phase: 'STOPPING',
    })

    render(<RecordingPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    const create = await screen.findByRole('button', { name: '打开浏览器并开始准备' })
    await waitFor(() => expect(create).toBeEnabled())
    fireEvent.click(create)
    await waitFor(() => expect(api.createRecording).toHaveBeenCalledWith('p1', action.action_candidate_id, identity.test_identity_id, 600))

    fireEvent.click(await screen.findByRole('button', { name: '刷新状态' }))
    expect(await screen.findByText('录制「修改资源」')).toBeInTheDocument()
    expect(await screen.findByText(/现在的浏览和登录不会写进业务流程/)).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '开始记录这个操作' }))
    await waitFor(() => expect(api.startCapture).toHaveBeenCalledWith('rec-1'))

    api.recording.mockResolvedValue({
      recording: { recording_id: 'rec-1', project_id: 'p1', state: 'RECORDING' },
      job: { job_id: 'job-1', state: 'RUNNING' },
      draft: null,
      capture_phase: 'CAPTURING',
    })
    fireEvent.click(screen.getByRole('button', { name: '刷新状态' }))
    expect(await screen.findByText(/完成后不要关闭浏览器/)).toBeInTheDocument()
    const complete = await screen.findByRole('button', { name: '我已完成这个操作' })
    expect(complete).toHaveClass('ant-btn-primary')
    expect(complete).not.toHaveClass('ant-btn-dangerous')
    fireEvent.click(complete)
    await waitFor(() => expect(api.stopCapture).toHaveBeenCalledWith('rec-1'))
    expect(await screen.findByText(/正在整理刚才的操作并寻找真正执行/)).toBeInTheDocument()
    expect(api.cancel).not.toHaveBeenCalled()
    expect(screen.getAllByText('正在整理流程')).toHaveLength(2)
  })

  it('用步骤卡片确认唯一目标和录制内资源位置，普通流程不出现 Profile 或 JSON 编辑器', async () => {
    const draft = {
      schema_version: '1',
      recording_id: 'rec-2',
      revision: 3,
      flow_id: 'recorded-flow',
      action_candidate_id: action.action_candidate_id,
      recommended_target_step_id: 'step-2',
      target_step_id: null,
      resource_candidate_id: null,
      steps: [
        { id: 'step-1', name: '读取资源', method: 'GET', path: '/resources/resource-42', resource_candidates: [] },
        { id: 'step-2', name: '修改资源', method: 'PATCH', path: '/resources/resource-42', resource_candidates: [{ candidate_id: 'resource-path-1', consumer: 'PATH', location: 'path[1]', label: '路径中的 resource-42' }] },
      ],
      variables: [],
    }
    const targetConfirmed = { ...draft, revision: 4, target_step_id: 'step-2' }
    const resourceConfirmed = { ...targetConfirmed, revision: 5, resource_candidate_id: 'resource-path-1' }
    localStorage.setItem('jiejian.resource', JSON.stringify({ recording_id: 'rec-2', project_id: 'p1', state: 'PENDING_REVIEW', capture_phase: 'FINISHED', draft, action, test_identity: identity, job: { job_id: 'job-2', state: 'SUCCEEDED' } }))
    api.reviewRecording
      .mockResolvedValueOnce({
        recording: { recording_id: 'rec-2', project_id: 'p1', state: 'PENDING_REVIEW' },
        draft: targetConfirmed,
        capture_phase: 'FINISHED',
      })
      .mockResolvedValueOnce({
        recording: { recording_id: 'rec-2', project_id: 'p1', state: 'PENDING_REVIEW' },
        draft: resourceConfirmed,
        capture_phase: 'FINISHED',
      })
    api.finalizeRecording.mockResolvedValue({
      recording: { recording_id: 'rec-2', project_id: 'p1', state: 'COMPLETED' },
      draft: resourceConfirmed,
      action,
      test_identity: identity,
      flow_path: 'var/recordings/flow.json',
    })
    const safetySetup = {
      recording_id: 'rec-2',
      action_candidate_id: action.action_candidate_id,
      action_display_name: '修改资源',
      target_method: 'PATCH',
      recording_identity: { identity_id: 'tid_0123456789abcdef0123456789abcdef', label: '普通成员账号 A', role_display_name: '普通成员', status: 'PREPARED' },
      state_changing: true,
      resource_candidates: [{ candidate_id: 'trc_0123456789abcdef0123456789abcdef', label: '录制中已确认的业务资源', suggested_resource_type: '文档', actual_resource_id: 'resource-42', consumer: 'PATH', location: 'path[1]' }],
      observation_candidates: [
        { candidate_id: 'obc_0123456789abcdef0123456789abcdef', label: '由资源所有者读取并核对', source_step_id: 'step-3', method: 'GET', path_template: '/resources/{case_resource_id}', trusted_test_identity_id: 'tid_0123456789abcdef0123456789abcdef' },
      ],
      recovery_candidates: [{ candidate_id: 'rcc_0123456789abcdef0123456789abcdef', label: '使用录制中的 PATCH 恢复同一资源', source_step_id: 'step-4', method: 'PATCH', path_template: '/resources/{case_resource_id}', json_body_template: { value: 'original' }, test_identity_id: 'tid_0123456789abcdef0123456789abcdef' }],
      security_effect_candidates: [{ candidate_id: 'sfc_0123456789abcdef0123456789abcdef', kind: 'STATE_MUTATION', label: '修改受保护资源状态', protected_fields: [] }],
      confirmed_setup: { resource: { resource_id: 'trs_0123456789abcdef0123456789abcdef', logical_name: '普通用户A 的测试资源', resource_type: '文档', actual_resource_id: 'resource-42', owner_test_identity_id: 'tid_0123456789abcdef0123456789abcdef' }, observation: null, recovery: null, effect: null },
      gaps: ['TEST_RESOURCE_UNCONFIRMED', 'OBSERVATION_UNCONFIRMED', 'RECOVERY_UNCONFIRMED', 'SECURITY_EFFECT_UNCONFIRMED'],
      automatic_execution_allowed: false,
    }
    api.recordings.mockResolvedValue([{ recording_id: 'rec-2', project_id: 'p1', state: 'PENDING_REVIEW' }])
    api.recording.mockResolvedValue({
      recording: { recording_id: 'rec-2', project_id: 'p1', state: 'PENDING_REVIEW' },
      draft,
      capture_phase: 'FINISHED',
      action,
      test_identity: identity,
      job: { job_id: 'job-2', state: 'SUCCEEDED' },
    })
    api.safetySetup.mockResolvedValue(safetySetup)
    api.confirmSafetySetup.mockResolvedValue({
      ...safetySetup,
      confirmed_setup: { resource: { resource_id: 'trs_0123456789abcdef0123456789abcdef', logical_name: '普通成员账号 A 的测试资源', resource_type: '文档', actual_resource_id: 'resource-42', owner_test_identity_id: 'tid_0123456789abcdef0123456789abcdef' }, observation: { source_step_id: 'step-3', path_template: '/resources/{case_resource_id}' }, recovery: { kind: 'RECORDED_REQUEST', source_step_id: 'step-4', path_template: '/resources/{case_resource_id}' }, effect: { kind: 'STATE_MUTATION' } },
      gaps: [],
      automatic_execution_allowed: true,
    })

    render(<RecordingPage project={{ project_id: 'p1' }} onError={vi.fn()} onNext={vi.fn()} />)
    expect(await screen.findByText('步骤 1：读取资源')).toBeInTheDocument()
    expect(await screen.findByText(/界鉴认为下面这一步真正执行了/)).toBeInTheDocument()
    expect(screen.queryByText(/^TARGET$/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '与下一步合并' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '重命名' })).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: /删除步骤/ })).toHaveLength(2)
    expect(screen.queryByText('审阅命令 JSON')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue(/RENAME_STEP/)).not.toBeInTheDocument()
    expect(screen.queryByText(/执行配置/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '将“修改资源”确认为目标请求' }))
    await waitFor(() => expect(api.reviewRecording).toHaveBeenCalledWith('rec-2', expect.objectContaining({
      schema_version: '1',
      operation: 'CONFIRM_TARGET_STEP',
      step_id: 'step-2',
    })))
    fireEvent.click(await screen.findByRole('radio', { name: '路径中的 resource-42' }))
    await waitFor(() => expect(api.reviewRecording).toHaveBeenCalledWith('rec-2', expect.objectContaining({
      schema_version: '1',
      operation: 'CONFIRM_RESOURCE_SLOT',
      candidate_id: 'resource-path-1',
    })))
    const finalize = await screen.findByRole('button', { name: '确认并保存流程' })
    expect(finalize).toBeEnabled()
    fireEvent.click(finalize)
    await waitFor(() => expect(api.finalizeRecording).toHaveBeenCalledWith('rec-2'))
    expect(await screen.findByText('流程已经保存。请继续确认测试资源、真实观察和安全恢复。')).toBeInTheDocument()
    expect(screen.getAllByText('修改资源')).toHaveLength(2)
    expect(document.body).toHaveTextContent('PATCH /resources/{测试资源}')
    expect(screen.getAllByText('普通成员账号 A（普通成员）')).toHaveLength(2)
    expect(await screen.findByText('当前动作还不能安全自动检查')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '去权限规则' })).not.toBeInTheDocument()
    fireEvent.mouseDown(screen.getByRole('combobox', { name: '选择真实观察方式' }))
    fireEvent.click(await screen.findByTitle(safetySetup.observation_candidates[0].label))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: '选择安全恢复方式' }))
    fireEvent.click(await screen.findByTitle(safetySetup.recovery_candidates[0].label))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: '选择安全影响' }))
    fireEvent.click(await screen.findByTitle(safetySetup.security_effect_candidates[0].label))
    fireEvent.click(screen.getByRole('button', { name: '确认测试资源、观察与恢复' }))
    await waitFor(() => expect(api.confirmSafetySetup).toHaveBeenCalledWith('rec-2', expect.objectContaining({
      owner_test_identity_id: 'tid_0123456789abcdef0123456789abcdef',
      observation_candidate_id: safetySetup.observation_candidates[0].candidate_id,
      recovery_candidate_id: safetySetup.recovery_candidates[0].candidate_id,
      security_effect_candidate_id: safetySetup.security_effect_candidates[0].candidate_id,
    })))
    expect(await screen.findByText('资源、独立观察、安全恢复和真实影响已经确认')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '去权限规则' })).toBeInTheDocument()
  })

  it('忽略同项目的陈旧浏览器录制定位，只恢复服务端当前 Recording', async () => {
    const onError = vi.fn()
    localStorage.setItem('jiejian.resource', JSON.stringify({
      recording_id: 'rec-stale',
      project_id: 'p1',
      state: 'COMPLETED',
    }))
    const current = {
      recording_id: 'rec-current',
      project_id: 'p1',
      state: 'COMPLETED',
    }
    api.recordings.mockResolvedValue([current])
    api.recording.mockResolvedValue({ recording: current, draft: null, capture_phase: 'FINISHED' })
    api.safetySetup.mockResolvedValue({
      recording_id: 'rec-current',
      action_candidate_id: action.action_candidate_id,
      action_display_name: action.display_name,
      target_method: 'PATCH',
      recording_identity: { identity_id: identity.test_identity_id, label: identity.label, role_display_name: identity.role_display_name, status: 'PREPARED' },
      state_changing: true,
      resource_candidates: [],
      observation_candidates: [],
      recovery_candidates: [],
      security_effect_candidates: [],
      confirmed_setup: null,
      gaps: [],
      automatic_execution_allowed: false,
    })

    render(<RecordingPage project={{ project_id: 'p1' }} onError={onError} />)

    await waitFor(() => expect(api.recording).toHaveBeenCalledWith('rec-current'))
    await waitFor(() => expect(api.safetySetup).toHaveBeenCalledWith('rec-current'))
    expect(api.recording).not.toHaveBeenCalledWith('rec-stale')
    expect(api.safetySetup).not.toHaveBeenCalledWith('rec-stale')
    expect(onError).not.toHaveBeenCalled()
  })
})
