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

export type RecordingTestIdentityDto = { test_identity_id: string; label: string; role_display_name: string }
export type RecordingActionDto = { action_candidate_id: string; display_name: string; risk_hint: string }
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
  schema_version?: '1'
  recording_id: string
  flow_id: string
  action_candidate_id: string
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

export type TestResourceCandidateDto = {
  candidate_id: string
  label: string
  suggested_resource_type: string
  actual_resource_id: string
  consumer: 'PATH' | 'QUERY' | 'JSON_BODY'
  location: string
}
export type ObservationCandidateDto = {
  candidate_id: string
  label: string
  source_recording_id: string
  source_step_id: string
  method: 'GET'
  path_template: string
  trusted_test_identity_id: string
}
export type RecoveryCandidateDto = {
  candidate_id: string
  label: string
  source_recording_id: string
  source_step_id: string
  method: 'PATCH' | 'POST' | 'PUT' | 'DELETE'
  path_template: string
  json_body_template: Record<string, unknown>
  test_identity_id: string
}
export type SecurityEffectCandidateDto = {
  candidate_id: string
  kind: string
  label: string
  protected_fields: string[]
}
export type ActionSafetySetupDto = {
  resource: {
    resource_id: string
    logical_name: string
    resource_type: string
    actual_resource_id: string
    owner_test_identity_id: string
  }
  observation?: { source_step_id: string; path_template: string } | null
  recovery?: { kind: 'RECORDED_REQUEST' | 'NOT_REQUIRED'; source_step_id?: string | null; path_template?: string | null } | null
  effect?: { kind: string } | null
}
export type ActionSafetySetupViewDto = {
  recording_id: string
  action_candidate_id: string
  action_display_name: string
  target_method: string
  recording_identity: { identity_id: string; label: string; role_display_name: string; status: string }
  state_changing: boolean
  resource_candidates: TestResourceCandidateDto[]
  observation_candidates: ObservationCandidateDto[]
  recovery_candidates: RecoveryCandidateDto[]
  security_effect_candidates: SecurityEffectCandidateDto[]
  business_result?: string | null
  observation_status: 'READY' | 'MISSING'
  recovery_status: 'READY' | 'MISSING' | 'NOT_REQUIRED'
  ready: boolean
  confirmed_setup?: ActionSafetySetupDto | null
  gaps: string[]
  automatic_execution_allowed: boolean
}
export type ConfirmActionSafetySetupInput = {
  resource_candidate_id?: string | null
  logical_name?: string | null
  resource_type?: string | null
  observation_candidate_id?: string | null
  recovery_candidate_id?: string | null
}

export const recordingsApi = {
  setup: (projectId: string) =>
    request<RecordingSetupDto>(`/api/projects/${encodeURIComponent(projectId)}/recordings/setup`),
  createRecording: (
    projectId: string,
    actionCandidateId: string,
    testIdentityId: string,
    durationSeconds: number,
    purpose: 'TARGET' | 'OBSERVATION' | 'RECOVERY' = 'TARGET',
    parentRecordingId?: string,
  ) =>
    request<RecordingViewDto>(`/api/projects/${encodeURIComponent(projectId)}/recordings`, {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        action_candidate_id: actionCandidateId,
        test_identity_id: testIdentityId,
        duration_seconds: durationSeconds,
        purpose,
        parent_recording_id: parentRecordingId ?? null,
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
  safetySetup: (id: string) =>
    request<ActionSafetySetupViewDto>(`/api/recordings/${encodeURIComponent(id)}/safety-setup`),
  confirmSafetySetup: (id: string, input: ConfirmActionSafetySetupInput) =>
    request<ActionSafetySetupViewDto>(`/api/recordings/${encodeURIComponent(id)}/safety-setup`, {
      method: 'PUT',
      body: JSON.stringify({ schema_version: '1', ...input }),
    }),
}
