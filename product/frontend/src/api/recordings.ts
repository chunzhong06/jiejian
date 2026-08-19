/* =============================================================================
 * Recording API Client
 *
 * 定位
 *   录制页面与 Recording、Job HTTP 路由之间的前端能力适配器
 *
 * 职责
 *   读取录制准备信息｜控制采集开始和停止｜提交图形化审阅结果
 *
 * 调用链
 *   RecordingPage / recording status → recordingsApi → api/http
 * ============================================================================= */

import { request } from './http'

export const recordingsApi = {
  setup: (projectId: string, profileId: string) =>
    request<Record<string, unknown>>(`/api/projects/${encodeURIComponent(projectId)}/recordings/setup?profile_id=${encodeURIComponent(profileId)}`),
  createRecording: (projectId: string, profileId: string, identityId: string, durationSeconds: number) =>
    request<Record<string, unknown>>(`/api/projects/${encodeURIComponent(projectId)}/recordings`, {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        profile_id: profileId,
        identity_id: identityId,
        duration_seconds: durationSeconds,
        idempotency_key: `gui-recording-${crypto.randomUUID()}`,
      }),
    }),
  recordings: (id: string) => request<Record<string, unknown>[]>(`/api/projects/${encodeURIComponent(id)}/recordings`),
  recording: (id: string) => request<Record<string, unknown>>(`/api/recordings/${encodeURIComponent(id)}`),
  startCapture: (id: string) => request<Record<string, unknown>>(`/api/recordings/${encodeURIComponent(id)}/capture/start`, { method: 'POST' }),
  stopCapture: (id: string) => request<Record<string, unknown>>(`/api/recordings/${encodeURIComponent(id)}/capture/stop`, { method: 'POST' }),
  reviewRecording: (
    id: string,
    command: Record<string, unknown>,
    bindings?: Record<string, Record<string, string>>,
  ) =>
    request<Record<string, unknown>>(`/api/recordings/${encodeURIComponent(id)}/review`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', command, bindings }),
    }),
  finalizeRecording: (id: string, bindings: Record<string, Record<string, string>>) =>
    request<Record<string, unknown>>(`/api/recordings/${encodeURIComponent(id)}/finalize`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', bindings }),
    }),
}
