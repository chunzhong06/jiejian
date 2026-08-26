/* 工作台 AI 辅助 API；确定性 guidance 与模型推荐分开表达，客户端不创建新选项。 */

import { request } from './http'

export type GuidanceOption = {
  option_id: string
  kind: string
  title: string
  reason_codes: string[]
  priority_tier: 'PRIMARY' | 'BLOCKING' | 'OPTIONAL'
  route: string
}

export type GuidanceSnapshot = {
  project_id: string
  state_fingerprint: string
  phase: string
  current_scope_runnable: boolean
  remaining_gap_count: number
  options: GuidanceOption[]
}

export type AssistantRecommendation = { option_id: string; explanation: string }
export type AssistantGuidance = {
  status: 'DISABLED' | 'REFRESH_NEEDED' | 'GENERATING' | 'READY' | 'BACKOFF'
  template_id: string
  template_version: '1'
  guidance: GuidanceSnapshot
  recommendations: AssistantRecommendation[]
  retry_after_us: number | null
}

export const assistantApi = {
  guidance: (projectId: string) => request<AssistantGuidance>(`/api/projects/${encodeURIComponent(projectId)}/assistant/guidance`),
  refresh: (projectId: string, retry = false) => request<AssistantGuidance>(`/api/projects/${encodeURIComponent(projectId)}/assistant/guidance/refresh`, {
    method: 'POST',
    body: JSON.stringify({ schema_version: '1', retry }),
  }),
}
