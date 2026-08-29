/* =============================================================================
 * 检查结果 API 客户端
 *
 * 定位
 *   验证、报告页面与已发布结果 HTTP 路由之间的只读适配器
 *
 * 职责
 *   读取报告、ExecutionTrace、Evidence 和 Finding｜保持后端发布视图为真源
 *
 * 调用链
 *   CheckResultsPage / EvidenceTimeline / ReportPanel → resultsApi → api/http
 * ============================================================================= */

import { request } from './http'

export type ReportDto = {
  report_id: string
  schema_version?: '1'
  title?: string
  verdict?: string
  result_integrity?: string
  summary?: string
  created_at_us?: number
  gate_decision?: string
  runtime?: {
    verdict?: string
    findings?: unknown[]
    execution_errors?: unknown[]
    observer_statuses?: Array<{ observer_id?: string; required?: boolean; status?: string }>
  }
  gate?: { decision?: string }
  artifacts?: Array<{ status?: string }>
  limitations?: unknown[]
}
export type FindingIdentityDto = {
  finding_id?: string
  permission_intent?: string | string[]
  problem_category?: string
  subject_class?: string | string[]
  action?: string
  resource_class?: string | string[]
  resource_relation?: string | string[]
}
export type FindingOccurrenceDto = {
  occurrence_id?: string
  status?: string
  severity?: string
  verdict?: string
  evidence_refs?: string[]
}
export type FindingDto = {
  finding?: { finding_id?: string; identity?: FindingIdentityDto }
  occurrence?: FindingOccurrenceDto
}
export type EvidenceCaseSnapshotDto = {
  subject_id?: string
  action_id?: string
  resource_ids?: string[]
  expectations?: string[]
  relation_paths?: string[][]
  required_observations?: string[]
}
export type ExecutionFactDto = { target_type?: string; action_id?: string; outcome?: string; reason_codes?: string[] }
export type ObservationFactDto = { requirement_id?: string; resource_id?: string; effect?: string; complete?: boolean; reliable?: boolean; reason_codes?: string[] }
export type SecurityEffectFactDto = {
  effect_id?: string
  kind?: string
  resource_id?: string
  state?: string
  complete?: boolean
  reliable?: boolean
  correlated?: boolean
  temporal_closure?: string
  baseline_integrity?: boolean
  source_requirement_ids?: string[]
  reason_codes?: string[]
}
export type EvidenceDto = {
  evidence_id: string
  evidence_type?: string
  observer?: string
  summary?: string
  observed_at_us?: number
  case_snapshot?: EvidenceCaseSnapshotDto
  execution_fact?: ExecutionFactDto
  observation_facts?: ObservationFactDto[]
  security_effect_facts?: SecurityEffectFactDto[]
  twin_snapshot?: { twin_id?: string } | null
  twin_role?: string | null
  allow_control_valid?: boolean
  baseline_integrity?: boolean
  verdict?: string
  observations?: Array<Record<string, unknown>>
  outcomes?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export type ResultEvidenceSourceDto = {
  observer_type: 'OWNER_API' | 'READ_ONLY_SQLITE' | 'STRUCTURED_AUDIT_LOG' | 'ASYNC_TASK_STATUS' | 'AZURE_QUEUE_PEEK' | 'AZURE_BLOB_OBJECT'
  label: string
  role: 'KEY' | 'SUPPORTING'
  status: 'FOUND' | 'NOT_FOUND' | 'UNAVAILABLE'
  evidence_refs: string[]
}

export type TraceEventDto = {
  event_id: string
  parent_event_ids: string[]
  case_id: string
  action_id: string
  resource_ids: string[]
  kind: string
  semantic_key: string
  subject_id: string | null
  actor_id: string | null
  credential_source: string | null
  authority_scope: string[]
  authorization_decision: 'ALLOW' | 'DENY' | null
  effect_id: string | null
  source_component: string
  source_location: string
  correlation_kind: 'EXPLICIT_PARENT' | 'CASE_MARKER' | 'RESOURCE_LINK' | 'TEMPORAL'
  evidence_refs: string[]
  recorded_at_us: number
}

export type ExecutionTraceDto = {
  schema_version: '1'
  case_id: string
  action_id: string
  planned_subject_id: string
  events: TraceEventDto[]
  complete: boolean
  reason_codes: string[]
}

export type ResultPresentationIssueDto = {
  finding_id: string
  title: string
  subject_group: string
  action: string
  resource: string
  relation: string
  expectation: string
  surface_result: string
  actual_result: string
  conclusion: string
  explanation: string
  planned_identity_id: string
  planned_identity_label: string | null
  actual_identity_status: 'UNAVAILABLE'
  actual_identity_label: null
  severity: 'unknown' | 'low' | 'medium' | 'high' | 'critical'
  evidence_refs: string[]
  evidence_sources: ResultEvidenceSourceDto[]
  verdict: 'SAFE' | 'VULNERABLE' | 'INCONCLUSIVE'
  occurrence_status: string | null
}

export type ResultPresentationDto = {
  run_id: string
  project_id: string
  project_name: string
  run_lifecycle: string
  verdict: 'PASS' | 'BLOCK' | 'INCONCLUSIVE' | null
  headline: string
  scope_statement: string
  checked_count: number
  safe_count: number
  problem_count: number
  inconclusive_count: number
  uncovered_count: number
  execution_problem: string | null
  execution_traces: ExecutionTraceDto[]
  issues: ResultPresentationIssueDto[]
  limitations: string[]
}

export type HistoryChangeDto = {
  finding_id: string
  title: string
  subject_group: string
  action: string
  resource: string
  relation: string
  status: 'NEW' | 'FIXED' | 'PERSISTENT' | 'INCONCLUSIVE' | 'NOT_COVERED'
  status_label: string
  explanation: string
  severity: string
  evidence_refs: string[]
  current_verdict: 'SAFE' | 'VULNERABLE' | 'INCONCLUSIVE' | null
  occurrence_status: string | null
}

export type HistoryComparisonDto = {
  run_id: string
  previous_run_id: string | null
  checked_at_us: number
  changes: HistoryChangeDto[]
}

export type HistoryViewDto = {
  project_id: string
  comparisons: HistoryComparisonDto[]
}

export const resultsApi = {
  reports: (runId: string) => request<ReportDto[]>(`/api/runs/${runId}/reports`),
  report: (runId: string, reportId: string) => request<ReportDto>(`/api/runs/${runId}/reports/${encodeURIComponent(reportId)}`),
  findings: (runId: string) => request<FindingDto[]>(`/api/runs/${runId}/findings`),
  evidence: (runId: string) => request<EvidenceDto[]>(`/api/runs/${runId}/evidence`),
  evidenceDetail: (runId: string, evidenceId: string) => request<EvidenceDto>(`/api/runs/${runId}/evidence/${evidenceId}`),
  reportView: (runId: string, reportId: string) => `/api/runs/${encodeURIComponent(runId)}/reports/${encodeURIComponent(reportId)}/view`,
  presentation: (runId: string) => request<ResultPresentationDto>(`/api/runs/${runId}/presentation`),
  history: (projectId: string) => request<HistoryViewDto>(`/api/projects/${projectId}/results/history`),
  reportFormat: (runId: string, reportId: string, format: 'json' | 'html' | 'sarif' | 'junit') => `/api/runs/${encodeURIComponent(runId)}/reports/${encodeURIComponent(reportId)}/formats/${format}`,
}
