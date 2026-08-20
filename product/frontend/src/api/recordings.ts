/* =============================================================================
 * Recording API Client
 *
 * 定位
 *   录制页面与 Recording、Job HTTP 路由之间的前端能力适配器
 *
 * 职责
 *   读取录制准备信息｜控制采集开始和停止｜提交图形化审阅结果
 *
 * 调用链
 *   RecordingPage / recording status → recordingsApi → api/http
 * ============================================================================= */

import { request } from './http'

export type RecordingIdentityDto = { identity_id: string; role: string }
export type RecordingProfileDto = { profile_id: string; name?: string }
export type RecordingSetupDto = {
  schema_version?: '1'
  project_id?: string
  profiles?: RecordingProfileDto[]
  identity_options: RecordingIdentityDto[]
}
export type RecordingJobDto = { job_id: string; state: string }
export type FlowDraftStepDto = {
  id: string
  name: string
  identity_id: string
  alternate_identity_id?: string | null
  resource_id?: string | null
  alternate_resource_id?: string | null
  method?: string | null
  path?: string | null
}
export type FlowDraftVariableSourceDto = {
  source_step_id: string
  source_event_sequence: number
  json_path: string
}
export type FlowDraftVariableDto = {
  name: string
  status: 'INFERRED' | 'UNCONFIRMED' | 'CONFIRMED'
  candidate_sources: FlowDraftVariableSourceDto[]
  confirmed_source?: FlowDraftVariableSourceDto | null
}
export type FlowDraftDto = {
  schema_version?: '1'
  recording_id: string
  flow_id: string
  revision: number
  steps: FlowDraftStepDto[]
  variables?: FlowDraftVariableDto[]
}
export type RecordingDto = {
  schema_version?: '1'
  recording_id: string
  project_id: string
  flow_id?: string
  state: string
  capture_phase?: string
  duration_seconds?: number
  draft?: FlowDraftDto | null
  job?: RecordingJobDto | null
  created_at_us?: number
  updated_at_us?: number
  flow_path?: string
  identity_options?: RecordingIdentityDto[]
}
export type RecordingViewDto = {
  schema_version?: '1'
  recording?: RecordingDto
  draft?: FlowDraftDto | null
  job?: RecordingJobDto | null
  capture_phase?: string
  flow_path?: string
  identity_options?: RecordingIdentityDto[]
}
export type RecordingReviewCommand = Record<string, unknown>

export const recordingsApi = {
  setup: (projectId: string, profileId: string) =>
    request<RecordingSetupDto>(`/api/projects/${encodeURIComponent(projectId)}/recordings/setup?profile_id=${encodeURIComponent(profileId)}`),
  createRecording: (projectId: string, profileId: string, identityId: string, durationSeconds: number) =>
    request<RecordingViewDto>(`/api/projects/${encodeURIComponent(projectId)}/recordings`, {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        profile_id: profileId,
        identity_id: identityId,
        duration_seconds: durationSeconds,
        idempotency_key: `gui-recording-${crypto.randomUUID()}`,
      }),
    }),
  recordings: (id: string) => request<RecordingDto[]>(`/api/projects/${encodeURIComponent(id)}/recordings`),
  recording: (id: string) => request<RecordingViewDto>(`/api/recordings/${encodeURIComponent(id)}`),
  startCapture: (id: string) => request<RecordingViewDto>(`/api/recordings/${encodeURIComponent(id)}/capture/start`, { method: 'POST' }),
  stopCapture: (id: string) => request<RecordingViewDto>(`/api/recordings/${encodeURIComponent(id)}/capture/stop`, { method: 'POST' }),
  reviewRecording: (
    id: string,
    command: RecordingReviewCommand,
    bindings?: Record<string, Record<string, string>>,
  ) =>
    request<RecordingViewDto>(`/api/recordings/${encodeURIComponent(id)}/review`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', command, bindings }),
    }),
  finalizeRecording: (id: string, bindings: Record<string, Record<string, string>>) =>
    request<RecordingViewDto>(`/api/recordings/${encodeURIComponent(id)}/finalize`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', bindings }),
    }),
}
