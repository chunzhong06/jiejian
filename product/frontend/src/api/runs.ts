/* =============================================================================
 * Run API Client
 *
 * 定位
 *   测试、验证页面与 Run、Job HTTP 路由之间的前端能力适配器
 *
 * 职责
 *   提交和读取 Run｜列出项目运行｜取消关联 Job
 *
 * 调用链
 *   PermissionCheckPage / CheckResultsPage → runsApi → api/http
 * ============================================================================= */

import { request, type ErrorDiagnosis } from './http'

export type RunDto = {
  schema_version?: '1'
  execution_schema_version?: string
  run_id?: string
  project_id?: string
  job_id?: string
  lifecycle?: string
  state?: string
  verdict?: string | null
  result_integrity?: string
  created_at?: string | number
  created_at_us?: number
  updated_at_us?: number
  job?: { job_id: string; state: string; event_sequence?: number; job_type?: string }
  case_progress?: { completed?: number; total?: number }
  execution_errors?: Array<{ stage?: string; message?: string; code?: string; job_id?: string; log_path?: string; recovery?: string; copy_text?: string; diagnosis?: ErrorDiagnosis } | string>
  event_sequence?: number
  coverage_record_count?: number
  coverage_gap_count?: number
  observer_health?: Record<string, unknown>
  reason_codes?: string[]
}

export type JobEventDto = {
  schema_version?: '1'
  sequence: number
  event_type?: string
  state?: string
}

export type RunnerProgressEventDto = {
  schema_version: '1'
  sequence: number
  case_id: string
  action_id: string
  twin_role: 'ALLOW_CONTROL' | 'DENY_VARIANT' | null
  phase: 'PREPARE' | 'BASELINE' | 'TARGET' | 'OBSERVE' | 'VERIFY' | 'RECOVERY'
  state: 'STARTED' | 'COMPLETED'
  recorded_at_us: number
}

export type JobProgressDto = {
  job_id: string
  attempt: number
  events: RunnerProgressEventDto[]
}

export type CancelJobDto = { schema_version?: '1'; job_id: string; state: string }

export const runsApi = {
  runs: (id: string) => request<RunDto[]>(`/api/projects/${id}/runs`),
  run: (id: string) => request<RunDto>(`/api/runs/${id}`),
  progress: (jobId: string) => request<JobProgressDto>(`/api/jobs/${encodeURIComponent(jobId)}/progress`),
  cancel: (jobId: string) => request<CancelJobDto>(`/api/jobs/${jobId}/cancel`, { method: 'POST' }),
}
