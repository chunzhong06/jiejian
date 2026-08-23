/* 首次使用 API 客户端：只保存会话标识，凭据请求不定义响应秘密字段。 */

import { request } from './http'

export type DiscoveryCandidate = {
  label: string
  command: string
  source: string
  confirmation_required: true
  executed: false
  safety_note: string
}

export type DiscoveryHint = {
  detail: string
  source: string
  confirmation_required: true
}

export type DiscoveryResult = {
  schema_version: '1'
  detected_types: string[]
  start_candidates: DiscoveryCandidate[]
  config_hints: DiscoveryHint[]
  interface_hints: DiscoveryHint[]
  auth_hints: DiscoveryHint[]
  missing_items: Array<{ key: string; label: string; state: string; reason: string; confirmation_required: true }>
  warnings: Array<{ code: string; message: string }>
}

export type OnboardingSession = {
  schema_version: '1'
  session_id: string
  revision: number
  status: 'DRAFT' | 'READY' | 'SUBMITTED'
  source_path: string
  project_name: string
  mode: 'quick'
  target_address: string | null
  primary_display_name: string | null
  comparison_display_name: string | null
  primary_resource_id: string | null
  comparison_resource_id: string | null
  read_only_path_template: string | null
  recovery_path: string | null
  startup_candidate_source: string | null
  confirmations: {
    app_started: boolean
    target_authorized: boolean
    recovery_confirmed: boolean
    dangerous_inference_confirmed: boolean
  }
  primary_configured: boolean
  comparison_configured: boolean
  missing_items: string[]
}

export type QuickCheckResult = {
  schema_version: '1'
  session: OnboardingSession
  project_id: string
  run_id: string
  job_id: string
  created: boolean
}

type SessionPatch = {
  project_name?: string
  target_address?: string
  primary_display_name?: string
  comparison_display_name?: string
  primary_resource_id?: string
  comparison_resource_id?: string
  read_only_path_template?: string
  recovery_path?: string
  startup_candidate_source?: string
  confirmations: Partial<OnboardingSession['confirmations']>
}

export const onboardingApi = {
  selectFolder: (signal?: AbortSignal) => request<{ status: 'selected' | 'cancelled' | 'unavailable'; path?: string; message?: string }>('/api/onboarding/select-folder', { method: 'POST', signal }),
  inspect: (path: string) => request<DiscoveryResult>('/api/onboarding/inspect', { method: 'POST', body: JSON.stringify({ schema_version: '1', path }) }),
  createSession: (path: string, projectName: string) => request<OnboardingSession>('/api/onboarding/sessions', { method: 'POST', body: JSON.stringify({ schema_version: '1', path, project_name: projectName }) }),
  getSession: (sessionId: string) => request<OnboardingSession>(`/api/onboarding/sessions/${encodeURIComponent(sessionId)}`),
  updateSession: (sessionId: string, revision: number, patch: SessionPatch) => request<OnboardingSession>(`/api/onboarding/sessions/${encodeURIComponent(sessionId)}`, { method: 'PATCH', body: JSON.stringify({ schema_version: '1', revision, ...patch }) }),
  putCredentials: (sessionId: string, primary: string, comparison: string) => request<{ primary_configured: boolean; comparison_configured: boolean }>(`/api/onboarding/sessions/${encodeURIComponent(sessionId)}/credentials`, { method: 'POST', body: JSON.stringify({ schema_version: '1', primary, comparison }) }),
  quickCheck: (sessionId: string) => request<QuickCheckResult>(`/api/onboarding/sessions/${encodeURIComponent(sessionId)}/quick-check`, { method: 'POST', body: JSON.stringify({ schema_version: '1' }) }),
}
