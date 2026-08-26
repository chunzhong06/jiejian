/* 首次使用 API：只提供目录选择与受限只读识别，不保存快速检查会话。 */

import { request } from './http'

export type DiscoveryCandidate = {
  label: string
  command: string
  source: string
  confirmation_required: true
  executed: false
  safety_note: string
}

export type DiscoveryHint = {
  detail: string
  source: string
  confirmation_required: true
}

export type DiscoveryResult = {
  detected_types: string[]
  start_candidates: DiscoveryCandidate[]
  config_hints: DiscoveryHint[]
  interface_hints: DiscoveryHint[]
  auth_hints: DiscoveryHint[]
  missing_items: Array<{ key: string; label: string; state: string; reason: string; confirmation_required: true }>
  warnings: Array<{ code: string; message: string }>
}

export const onboardingApi = {
  selectFolder: (signal?: AbortSignal) => request<{ status: 'selected' | 'cancelled' | 'unavailable'; path?: string; message?: string }>('/api/onboarding/select-folder', { method: 'POST', signal }),
  inspect: (path: string) => request<DiscoveryResult>('/api/onboarding/inspect', { method: 'POST', body: JSON.stringify({ schema_version: '1', path }) }),
}
