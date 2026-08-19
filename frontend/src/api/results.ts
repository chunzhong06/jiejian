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
 *   VerifyPage / ReportPage → resultsApi → api/http
 * ============================================================================= */

import { request } from './http'

export const resultsApi = {
  report: (runId: string) => request<Record<string, unknown>>(`/api/v1/runs/${runId}/report`),
  reports: (runId: string) => request<Record<string, unknown>[]>(`/api/v2/runs/${runId}/reports`),
  reportV2: (runId: string, reportId: string) => request<Record<string, any>>(`/api/v2/runs/${runId}/reports/${encodeURIComponent(reportId)}`),
  findings: (runId: string) => request<Record<string, unknown>[]>(`/api/v1/runs/${runId}/findings`),
  evidence: (runId: string) => request<Record<string, unknown>[]>(`/api/v1/runs/${runId}/evidence`),
  evidenceDetail: (runId: string, evidenceId: string) => request<Record<string, unknown>>(`/api/v1/runs/${runId}/evidence/${evidenceId}`),
}
