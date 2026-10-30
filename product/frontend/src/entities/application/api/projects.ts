// 应用接入 API：读取项目与连接事实，提交地址确认和源码分析授权。
import { request } from '../../../shared/api/http'
import type { DiscoveryResult } from './onboarding'

export type ProjectDto = {
  project_id: string
  name?: string
  status?: string
  // 服务端项目列表提供的持久来源，不表示示例运行状态。
  official_sample?: boolean
  governed_contract_id?: string | null
  governed_contract_version?: number | null
  created_at_us?: number
  updated_at_us?: number
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
export type ConnectionPreview = {source_root:string;snapshot:string;projects:ProjectDto[]}
export type ConnectionChoice = {mode:'RESUME'|'NEW';existing_project_id?:string;expected_snapshot:string;operation_id?:string}
export type RuntimePreview = { project_id: string; revision: number; entry: string; port: number; preview_fingerprint: string; files: Array<{ relative_path: string }> }
export type RuntimeOperation = { project_id: string; operation_id: string; instance_id: string; state: string }
export type RuntimeState = { project_id: string; running: boolean; source_matches: boolean; configuration: { entry: string; port: number } | null; operation: RuntimeOperation | null }
const runtimePath = (id: string) => `/api/projects/${encodeURIComponent(id)}/controlled-runtime`

export type CandidateSelection = { kind: 'ROLE' | 'ACTION'; candidate_id: string; decision: 'PROPOSED' | 'CONFIRMED' | 'REJECTED'; display_name: string }

export const projectsApi = {
  readiness: (id: string, signal?: AbortSignal) => request<ApplicationReadiness>(`/api/projects/${id}/readiness`, {signal}),
  activity: (id: string, signal?: AbortSignal) => request<ApplicationActivity>(`/api/projects/${id}/activity`, {signal}),
  runtime: (id: string) => request<RuntimeState>(runtimePath(id)),
  runtimePreview: (id: string, body: { entry: string; port: number; revision: number }) => request<RuntimePreview>(runtimePath(id) + '/preview', { method: 'POST', body: JSON.stringify(body) }),
  runtimeStart: (id: string, body: { entry: string; port: number; revision: number; preview_fingerprint: string; operation_id: string; consent_execute: true }) => request<RuntimeOperation>(runtimePath(id) + '/start', { method: 'POST', body: JSON.stringify(body) }),
  runtimeOperation: (id: string, operation: string) => request<RuntimeOperation | null>(runtimePath(id) + '/operations/' + operation),
  runtimeCancel: (id: string, operation: string) => request<RuntimeOperation>(runtimePath(id) + '/operations/' + operation + '/cancel', { method: 'POST' }),
  runtimeStop: (id: string, instance: string) => request<RuntimeState>(runtimePath(id) + '/stop', { method: 'POST', body: JSON.stringify({ instance_id: instance }) }),
  decideCandidates: (id: string, revision: number, decisions: CandidateSelection[]) =>
    request<ApplicationUnderstandingDto>(`/api/projects/${id}/candidate-decisions`, {
      method: 'PUT', body: JSON.stringify({ schema_version: '1', revision, decisions }),
    }),
  projects: (signal?:AbortSignal) => request<ProjectDto[]>('/api/projects',{signal}),
  archivedProjects: (signal?:AbortSignal) => request<ProjectDto[]>('/api/projects?include_archived=true',{signal}),
  connectionPreview: (sourceRoot:string) => request<ConnectionPreview>('/api/applications/connection-preview',{method:'POST',body:JSON.stringify({source_root:sourceRoot})}),
  connectApplication: (sourceRoot: string, projectName?: string, choice?:ConnectionChoice) =>
    request<ApplicationConnectionDto>('/api/applications/connect', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', source_root: sourceRoot, project_name: projectName, ...choice }),
    }),
  project: (id: string, signal?:AbortSignal) => request<ProjectDto>(`/api/projects/${id}`,{signal}),
  remove: (id: string) => request<ProjectDto>(`/api/projects/${id}`, { method: 'DELETE' }),
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

export type ApplicationActivity = {project_id: string; revision: number; items: Array<{id: string; kind: string; label: string; phase: string; destination: string; updated_at_us: number}>}
export type ApplicationReadiness = {project_id: string; revision: number; basis_fingerprint: string; endpoint: string | null; endpoint_checked_at_us: number | null; analysis_completed_at_us: number | null; items: Array<{key: string; label: string; state: string; detail: string; destination: string}>}
