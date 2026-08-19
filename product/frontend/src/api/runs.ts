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

export const runsApi = {
  runs: (id: string) => request<Record<string, unknown>[]>(`/api/projects/${id}/runs`),
  run: (id: string) => request<Record<string, unknown>>(`/api/runs/${id}`),
  cancel: (jobId: string) => request<Record<string, unknown>>(`/api/jobs/${jobId}/cancel`, { method: 'POST' }),
}
