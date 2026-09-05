/* 八类 AI surface API；客户端只能选择封闭 surface，不能提交任意 prompt 或 facts。 */

import { request } from './http'

export type ProjectAssistantSurface =
  | 'implementation-mapping'
  | 'preparation-explanation'
  | 'next-step'
  | 'candidate-review'
  | 'identity-preparation'
  | 'recording-review'
  | 'observation-recovery'
  | 'check-preview-explanation'

export type AssistantEntity = {
  entity_id: string
  entity_type: string
  display_name: string
  facts: Array<{ field: string; value: string | boolean | number | string[] }>
}

export type AssistantSuggestion = {
  kind: string
  entity_ids: string[]
  explanation: string
}

export type AssistantSurfaceView = {
  status: 'DISABLED' | 'REFRESH_NEEDED' | 'GENERATING' | 'READY' | 'BACKOFF'
  template_id: string
  template_version: '1'
  subject_id: string
  state_fingerprint: string
  entities: AssistantEntity[]
  suggestions: AssistantSuggestion[]
  retry_after_us: number | null
  can_generate?: boolean
}

export type AssistantFocus = { business_actor_id?: string; business_action_id?: string; recording_id?: string }
const focusQuery = (focus?: AssistantFocus) => {
  const query = new URLSearchParams(Object.entries(focus ?? {}).filter((entry): entry is [string, string] => Boolean(entry[1])))
  return query.size ? `?${query}` : ''
}

const generateBody = (retry: boolean) => JSON.stringify({ schema_version: '1', retry })

export const assistantApi = {
  project: (projectId: string, surface: ProjectAssistantSurface, focus?: AssistantFocus) =>
    request<AssistantSurfaceView>(`/api/projects/${encodeURIComponent(projectId)}/assistant/${surface}${focusQuery(focus)}`),
  generateProject: (projectId: string, surface: ProjectAssistantSurface, retry = false, focus?: AssistantFocus) =>
    request<AssistantSurfaceView>(`/api/projects/${encodeURIComponent(projectId)}/assistant/${surface}${focusQuery(focus)}`, {
      method: 'POST',
      body: generateBody(retry),
    }),
  result: (runId: string) => request<AssistantSurfaceView>(`/api/runs/${encodeURIComponent(runId)}/assistant/result`),
  generateResult: (runId: string, retry = false) => request<AssistantSurfaceView>(`/api/runs/${encodeURIComponent(runId)}/assistant/result`, {
    method: 'POST',
    body: generateBody(retry),
  }),
  generateError: (errorCode: string, retry = false) => request<AssistantSurfaceView>('/api/assistant/error', {
    method: 'POST',
    body: JSON.stringify({ schema_version: '1', error_code: errorCode, retry }),
  }),
}
