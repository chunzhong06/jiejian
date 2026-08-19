import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RecordingPage } from './RecordingPage'

const api = vi.hoisted(() => ({
  profiles: vi.fn(),
  setup: vi.fn(),
  recordings: vi.fn(),
  recording: vi.fn(),
  createRecording: vi.fn(),
  startCapture: vi.fn(),
  stopCapture: vi.fn(),
  reviewRecording: vi.fn(),
  finalizeRecording: vi.fn(),
  cancel: vi.fn(),
}))

vi.mock('../../api/executionProfiles', () => ({ executionProfilesApi: { profiles: api.profiles } }))
vi.mock('../../api/recordings', () => ({ recordingsApi: {
  setup: api.setup,
  recordings: api.recordings,
  recording: api.recording,
  createRecording: api.createRecording,
  startCapture: api.startCapture,
  stopCapture: api.stopCapture,
  reviewRecording: api.reviewRecording,
  finalizeRecording: api.finalizeRecording,
} }))
vi.mock('../../api/runs', () => ({ runsApi: { cancel: api.cancel } }))

class EventSourceStub {
  onmessage: ((message: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  close() { return undefined }
}

const identities = [
  { identity_id: 'owner', role: '项目负责人' },
  { identity_id: 'member', role: '普通成员' },
]

describe('RecordingPage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    vi.stubGlobal('EventSource', EventSourceStub)
    api.profiles.mockResolvedValue([{ profile_id: 'profile-1', project_id: 'p1' }])
    api.setup.mockResolvedValue({ profile_id: 'profile-1', project_id: 'p1', identity_options: identities })
    api.recordings.mockResolvedValue([])
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('以单身份和明确开始停止动作驱动录制状态', async () => {
    api.createRecording.mockResolvedValue({
      recording: { recording_id: 'rec-1', project_id: 'p1', state: 'CREATED' },
      job: { job_id: 'job-1', state: 'QUEUED' },
      identity_options: identities,
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
    const create = await screen.findByRole('button', { name: '打开浏览器并准备登录' })
    await waitFor(() => expect(create).toBeEnabled())
    fireEvent.click(create)
    await waitFor(() => expect(api.createRecording).toHaveBeenCalledWith('p1', 'profile-1', 'owner', 600))

    fireEvent.click(await screen.findByRole('button', { name: '刷新状态' }))
    fireEvent.click(await screen.findByRole('button', { name: '开始录制' }))
    await waitFor(() => expect(api.startCapture).toHaveBeenCalledWith('rec-1'))

    api.recording.mockResolvedValue({
      recording: { recording_id: 'rec-1', project_id: 'p1', state: 'RECORDING' },
      job: { job_id: 'job-1', state: 'RUNNING' },
      draft: null,
      capture_phase: 'CAPTURING',
    })
    fireEvent.click(screen.getByRole('button', { name: '刷新状态' }))
    fireEvent.click(await screen.findByRole('button', { name: '停止录制并生成流程' }))
    await waitFor(() => expect(api.stopCapture).toHaveBeenCalledWith('rec-1'))
    expect(screen.getAllByText('正在生成流程')).toHaveLength(2)
  })

  it('用步骤卡片和变量来源完成保存，普通流程不出现 JSON 编辑器', async () => {
    const draft = {
      revision: 3,
      flow_id: 'recorded-flow',
      steps: [
        { id: 'step-1', name: '创建项目', identity_id: 'owner', alternate_identity_id: 'member', resource_id: 'owner-project', alternate_resource_id: 'member-project', bindings_confirmed: true, method: 'POST', path: '/projects' },
        { id: 'step-2', name: '打开项目', identity_id: 'owner', alternate_identity_id: 'member', resource_id: 'owner-project', alternate_resource_id: 'member-project', bindings_confirmed: true, method: 'GET', path: '/projects/{project_id}' },
      ],
      variables: [{
        name: 'project_id',
        status: 'UNCONFIRMED',
        candidate_sources: [{ source_step_id: 'step-1', source_event_sequence: 5, json_path: '$.project_id' }],
        consumer_step_ids: ['step-2'],
      }],
    }
    localStorage.setItem('jiejian.resource', JSON.stringify({ recording_id: 'rec-2', project_id: 'p1', state: 'PENDING_REVIEW', capture_phase: 'FINISHED', draft, job: { job_id: 'job-2', state: 'SUCCEEDED' } }))
    api.reviewRecording.mockResolvedValue({
      recording: { recording_id: 'rec-2', project_id: 'p1', state: 'PENDING_REVIEW' },
      draft: { ...draft, revision: 4, variables: [{ ...draft.variables[0], status: 'CONFIRMED', confirmed_source: draft.variables[0].candidate_sources[0] }] },
      capture_phase: 'FINISHED',
    })
    api.finalizeRecording.mockResolvedValue({ recording: { recording_id: 'rec-2', project_id: 'p1', state: 'COMPLETED' }, flow_path: 'var/recordings/flow.json' })

    render(<RecordingPage project={{ project_id: 'p1' }} onError={vi.fn()} />)
    expect(await screen.findByText('步骤 1：创建项目')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '与下一步合并' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '重命名' })).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: /删除步骤/ })).toHaveLength(2)
    expect(screen.getByText(/来自“创建项目”响应中的 project_id/)).toBeInTheDocument()
    expect(screen.queryByText('审阅命令 JSON')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue(/RENAME_STEP/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '确认并保存流程' }))
    await waitFor(() => expect(api.reviewRecording).toHaveBeenCalledWith('rec-2', expect.objectContaining({
      operation: 'CONFIRM_VARIABLE_SOURCE',
      variable_name: 'project_id',
      source_event_sequence: 5,
      source_json_path: '$.project_id',
    })))
    await waitFor(() => expect(api.finalizeRecording).toHaveBeenCalledWith('rec-2', {
      'step-1': { alternate_identity_id: 'member', resource_id: 'owner-project', alternate_resource_id: 'member-project' },
      'step-2': { alternate_identity_id: 'member', resource_id: 'owner-project', alternate_resource_id: 'member-project' },
    }))
    expect(await screen.findByText('流程已经保存，可以用于后续检查。')).toBeInTheDocument()
  })
})
