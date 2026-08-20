/* =============================================================================
 * Results API Client
 *
 * 定位
 *   验证、报告页面与已发布结果 HTTP 路由之间的只读适配器
 *
 * 职责
 *   读取报告｜读取 Evidence 和 Finding｜保持后端发布视图为真源
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
  permission_intent?: string
  problem_category?: string
  subject_class?: string
  action?: string
  resource_class?: string
  resource_relation?: string
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
export type EvidenceDto = {
  evidence_id: string
  evidence_type?: string
  observer?: string
  summary?: string
  observed_at_us?: number
  case_snapshot?: EvidenceCaseSnapshotDto
  execution_fact?: ExecutionFactDto
  observation_facts?: ObservationFactDto[]
  verdict?: string
  observations?: Array<Record<string, unknown>>
  outcomes?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export const resultsApi = {
  reports: (runId: string) => request<ReportDto[]>(`/api/runs/${runId}/reports`),
  report: (runId: string, reportId: string) => request<ReportDto>(`/api/runs/${runId}/reports/${encodeURIComponent(reportId)}`),
  findings: (runId: string) => request<FindingDto[]>(`/api/runs/${runId}/findings`),
  evidence: (runId: string) => request<EvidenceDto[]>(`/api/runs/${runId}/evidence`),
  evidenceDetail: (runId: string, evidenceId: string) => request<EvidenceDto>(`/api/runs/${runId}/evidence/${evidenceId}`),
  reportFormat: (runId: string, reportId: string, format: 'json' | 'html' | 'sarif' | 'junit') => `/api/runs/${runId}/reports/${encodeURIComponent(reportId)}/formats/${format}`,
}
