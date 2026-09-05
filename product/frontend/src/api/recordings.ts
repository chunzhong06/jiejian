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

export type RecordingTestIdentityDto = { test_identity_id: string; label: string; actor_display_name: string }
export type RecordingActionDto = { business_action_id: string; action_revision: number; display_name: string }
export type RecordingSetupDto = {
  schema_version?: '1'
  project_id?: string
  action_options: RecordingActionDto[]
  test_identity_options: RecordingTestIdentityDto[]
}
export type RecordingJobDto = { job_id: string; state: string }
export type FlowDraftStepDto = {
  id: string
  name: string
  method?: string | null
  path?: string | null
  resource_candidates: Array<{ candidate_id: string; consumer: 'PATH' | 'QUERY' | 'JSON_BODY'; location: string; label: string }>
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
  schema_version: '2'
  recording_id: string
  flow_id: string
  business_action_id: string
  action_revision: number
  test_identity_id: string
  revision: number
  recommended_target_step_id?: string | null
  target_step_id?: string | null
  resource_candidate_id?: string | null
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
  action?: RecordingActionDto
  test_identity?: RecordingTestIdentityDto
  purpose?: 'TARGET' | 'OBSERVATION' | 'RECOVERY'
  parent_recording_id?: string | null
}
export type RecordingViewDto = {
  schema_version?: '1'
  recording?: RecordingDto
  draft?: FlowDraftDto | null
  job?: RecordingJobDto | null
  capture_phase?: string
  flow_path?: string
  action?: RecordingActionDto
  test_identity?: RecordingTestIdentityDto
}
export type RecordingReviewCommand = Record<string, unknown>

export const recordingsApi = {
  setup: (projectId: string) =>
    request<RecordingSetupDto>(`/api/projects/${encodeURIComponent(projectId)}/recordings/setup`),
  createRecording: (
    projectId: string,
    businessActionId: string,
    actionRevision: number,
    testIdentityId: string,
    durationSeconds: number,
    purpose: 'TARGET' | 'OBSERVATION' | 'RECOVERY' = 'TARGET',
    parentRecordingId?: string,
    effectId?: string,
  ) =>
    request<RecordingViewDto>(`/api/projects/${encodeURIComponent(projectId)}/recordings`, {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '2',
        business_action_id: businessActionId,
        action_revision: actionRevision,
        test_identity_id: testIdentityId,
        duration_seconds: durationSeconds,
        purpose,
        parent_recording_id: parentRecordingId ?? null,
        effect_id: effectId ?? null,
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
  ) =>
    request<RecordingViewDto>(`/api/recordings/${encodeURIComponent(id)}/review`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', command }),
    }),
  finalizeRecording: (id: string) =>
    request<RecordingViewDto>(`/api/recordings/${encodeURIComponent(id)}/finalize`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1' }),
    }),
}
