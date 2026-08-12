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
 *   RunPage / VerifyPage / JobProgress → runsApi → api/http
 * ============================================================================= */

import { request } from './http'

export const runsApi = {
  runs: (id: string) => request<Record<string, unknown>[]>(`/api/v1/projects/${id}/runs`),
  run: (id: string) => request<Record<string, unknown>>(`/api/v1/runs/${id}`),
  createRun: (id: string) =>
    request<Record<string, unknown>>(`/api/v1/projects/${id}/runs`, {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        idempotency_key: `gui-${crypto.randomUUID()}`,
      }),
    }),
  cancel: (jobId: string) => request<Record<string, unknown>>(`/api/v1/jobs/${jobId}/cancel`, { method: 'POST' }),
}
