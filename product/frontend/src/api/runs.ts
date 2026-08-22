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
 *   StartCheckPage / CheckResultsPage → runsApi → api/http
 * ============================================================================= */

import { request } from './http'

export type RunDto = {
  schema_version?: '1'
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
  execution_errors?: Array<{ stage?: string; message?: string; code?: string; job_id?: string; log_path?: string; recovery?: string; copy_text?: string } | string>
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

export type CancelJobDto = { schema_version?: '1'; job_id: string; state: string }

export const runsApi = {
  runs: (id: string) => request<RunDto[]>(`/api/projects/${id}/runs`),
  run: (id: string) => request<RunDto>(`/api/runs/${id}`),
  cancel: (jobId: string) => request<CancelJobDto>(`/api/jobs/${jobId}/cancel`, { method: 'POST' }),
}
