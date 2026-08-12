/* =============================================================================
 * Recording API Client
 *
 * 定位
 *   录制页面与 Recording、Job HTTP 路由之间的前端能力适配器
 *
 * 职责
 *   创建和读取 Recording｜提交审阅命令｜取消关联 Job
 *
 * 调用链
 *   RecordingPage / JobProgress → recordingsApi → api/http
 * ============================================================================= */

import { request } from './http'

export const recordingsApi = {
  createRecording: (id: string, identities: string[], durationSeconds: number) =>
    request<Record<string, unknown>>(`/api/v1/projects/${id}/recordings`, {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        identities,
        duration_seconds: durationSeconds,
        headless: true,
        idempotency_key: `gui-recording-${crypto.randomUUID()}`,
      }),
    }),
  recordings: (id: string) => request<Record<string, unknown>[]>(`/api/v1/projects/${id}/recordings`),
  recording: (id: string) => request<Record<string, unknown>>(`/api/v1/recordings/${id}`),
  reviewRecording: (
    id: string,
    command: Record<string, unknown>,
    bindings?: Record<string, Record<string, string>>,
  ) =>
    request<Record<string, unknown>>(`/api/v1/recordings/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', command, bindings }),
    }),
  finalizeRecording: (id: string) => request<Record<string, unknown>>(`/api/v1/recordings/${id}/finalize`, { method: 'POST' }),
}
