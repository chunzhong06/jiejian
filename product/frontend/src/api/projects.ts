/* =============================================================================
 * 应用与项目 API 客户端
 *
 * 定位
 *   接入页面与 Project HTTP 路由之间的前端能力适配器
 *
 * 职责
 *   建立应用连接｜确认 endpoint｜授权源码分析｜读取候选与 ProjectReadiness
 *
 * 调用链
 *   Access / ControlShell → projectsApi → api/http
 * ============================================================================= */

import { request } from './http'
import type { DiscoveryResult } from './onboarding'
import type { SourceChangeViewDto } from './sourceChanges'

export type ProjectDto = {
  project_id: string
  name?: string
  status?: string
  governed_contract_id?: string | null
  governed_contract_version?: number | null
  created_at_us?: number
  updated_at_us?: number
}

export type ProjectReadinessDto = {
  project_id: string
  project_status: string
  application_connected: boolean
  endpoint_status: 'NEEDS_CONNECTION' | 'NEEDS_CONFIRMATION' | 'CONFIRMED' | 'UNAVAILABLE'
  source_analysis_status: 'NOT_AVAILABLE' | 'NOT_AUTHORIZED' | 'PENDING' | 'COMPLETED' | 'STALE'
  discovered_role_count: number
  confirmed_role_count: number
  discovered_action_count: number
  confirmed_action_count: number
  execution_profile_available: boolean
  completed_flow_available: boolean
  active_contract_available: boolean
  permission_actions?: Array<{ action_candidate_id: string; action_display_name: string; compilable: boolean; gaps: string[]; required_intent_count: number; confirmed_intent_count: number; executable_intent_count: number; representative_gap_count: number }>
  permission_requirement_count?: number
  confirmed_permission_requirement_count?: number
  executable_permission_requirement_count?: number
  permission_representative_gap_count?: number
  current_scope_runnable: boolean
  remaining_gap_count: number
  active_tasks: Array<{ kind: 'RUN' | 'RECORDING'; task_id: string; state: string }>
  latest_verified_run_id: string | null
  next_required_action: 'CONNECT_APPLICATION' | 'CONFIRM_TARGET' | 'AUTHORIZE_SOURCE_ANALYSIS' | 'REVIEW_DISCOVERY' | 'RECORD_FLOW' | 'REVIEW_PERMISSION' | 'RUN_CHECK' | 'OPEN_RESULT'
}

export type ProductStatusDto = {
  project: (ProjectDto & { target_type: 'WEB' }) | null
  readiness: ProjectReadinessDto | null
  areas: Array<{
    key: 'overview' | 'changes' | 'permissions' | 'preparation' | 'validation' | 'results'
    label: string
    description: string
    route: '/workspace' | '/changes' | '/permissions' | '/preparation' | '/validation' | '/results'
    status: 'READY' | 'NEEDS_ATTENTION' | 'RUNNING' | 'AVAILABLE' | 'BLOCKED' | 'EMPTY'
    status_label: string
  }>
  attention_items: Array<{
    key: string
    label: string
    description: string
    route: '/workspace' | '/application' | '/changes' | '/permissions' | '/preparation' | '/identities' | '/flows' | '/validation' | '/results' | '/verification' | '/history'
    tone: 'ACTION' | 'WARNING' | 'INFO'
  }>
  latest_change: SourceChangeViewDto | null
  latest_result: {
    run_id: string
    verdict: 'PASS' | 'BLOCK' | 'INCONCLUSIVE' | null
    headline: string
    scope_statement: string
    verified_change_id: string | null
  } | null
}

export type ApplicationUnderstandingDto = {
  project_id: string
  source_root: string
  confirmed_endpoint: string | null
  endpoint_source_fingerprint: string | null
  endpoint_confirmed_at_us: number | null
  endpoint_last_checked_at_us: number | null
  endpoint_reachable: boolean | null
  source_analysis_authorized: boolean
  source_analysis_authorized_at_us: number | null
  source_fingerprint: string | null
  analysis_completed_at_us: number | null
  role_candidates: RoleCandidateDto[]
  action_candidates: ActionCandidateDto[]
  revision: number
  created_at_us: number
  updated_at_us: number
}

export type CandidateEvidenceDto = {
  relative_path: string
  line_start: number
  line_end: number
  symbol: string | null
  detector: string
  content_sha256: string
}

export type RoleCandidateDto = {
  candidate_id: string
  canonical_key: string
  display_name: string
  confidence: 'HIGH' | 'MEDIUM' | 'LOW'
  decision: 'PROPOSED' | 'CONFIRMED' | 'REJECTED' | 'REVIEW_REQUIRED'
  origin: 'DETECTED' | 'MANUAL'
  stale: boolean
  evidence: CandidateEvidenceDto[]
}

export type ActionCandidateDto = RoleCandidateDto & {
  risk_hint: 'READ' | 'WRITE' | 'DELETE' | 'ADMIN' | 'UNKNOWN'
}

export type EndpointCandidateDto = {
  endpoint: string
  source_type: 'CONFIG' | 'OPENAPI' | 'STARTUP' | 'FRAMEWORK_DEFAULT'
  source: string
  rank: number
  reachable: boolean
  status_code: number | null
  probe_detail: string
  confirmation_required: true
}

export type EndpointDiscoveryDto = {
  source_fingerprint: string
  candidates: EndpointCandidateDto[]
  request_count: number
  default_endpoint: string | null
  manual_entry_required: boolean
}

export type ApplicationConnectionDto = {
  project: ProjectDto
  understanding: ApplicationUnderstandingDto
  discovery: DiscoveryResult
}

export const projectsApi = {
  projects: () => request<ProjectDto[]>('/api/projects'),
  archivedProjects: () => request<ProjectDto[]>('/api/projects?include_archived=true'),
  connectApplication: (sourceRoot: string, projectName?: string) =>
    request<ApplicationConnectionDto>('/api/applications/connect', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', source_root: sourceRoot, project_name: projectName }),
    }),
  project: (id: string) => request<ProjectDto>(`/api/projects/${id}`),
  remove: (id: string) => request<ProjectDto>(`/api/projects/${id}`, { method: 'DELETE' }),
  status: (id: string) => request<ProductStatusDto>(`/api/projects/${id}/status`),
  understanding: (id: string) => request<ApplicationUnderstandingDto>(`/api/projects/${id}/application-understanding`),
  discoverEndpoints: (id: string) => request<EndpointDiscoveryDto>(`/api/projects/${id}/endpoint-candidates`, { method: 'POST' }),
  confirmEndpoint: (id: string, endpoint: string, revision: number) =>
    request<ApplicationUnderstandingDto>(`/api/projects/${id}/endpoint`, {
      method: 'PUT',
      body: JSON.stringify({ schema_version: '1', endpoint, revision }),
    }),
  authorizeSourceAnalysis: (id: string, revision: number) =>
    request<ApplicationUnderstandingDto>(`/api/projects/${id}/source-analysis-authorization`, {
      method: 'PUT',
      body: JSON.stringify({ schema_version: '1', authorized: true, revision }),
    }),
  analyzeSource: (id: string, revision: number) =>
    request<ApplicationUnderstandingDto>(`/api/projects/${id}/source-analysis`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', revision }),
    }),
  decideRole: (id: string, candidateId: string, decision: 'PROPOSED' | 'CONFIRMED' | 'REJECTED', displayName: string, revision: number) =>
    request<ApplicationUnderstandingDto>(`/api/projects/${id}/roles/${candidateId}`, {
      method: 'PUT',
      body: JSON.stringify({ schema_version: '1', decision, display_name: displayName, revision }),
    }),
  addRole: (id: string, displayName: string, revision: number) =>
    request<ApplicationUnderstandingDto>(`/api/projects/${id}/roles`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', display_name: displayName, revision }),
    }),
  decideAction: (id: string, candidateId: string, decision: 'PROPOSED' | 'CONFIRMED' | 'REJECTED', displayName: string, revision: number) =>
    request<ApplicationUnderstandingDto>(`/api/projects/${id}/actions/${candidateId}`, {
      method: 'PUT',
      body: JSON.stringify({ schema_version: '1', decision, display_name: displayName, revision }),
    }),
  addAction: (id: string, displayName: string, riskHint: ActionCandidateDto['risk_hint'], revision: number) =>
    request<ApplicationUnderstandingDto>(`/api/projects/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', display_name: displayName, risk_hint: riskHint, revision }),
    }),
}
