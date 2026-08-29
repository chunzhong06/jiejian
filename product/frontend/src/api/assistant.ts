/* 九类 AI surface API；客户端只能选择封闭 surface，不能提交任意 prompt 或 facts。 */

import { request } from './http'

export type ProjectAssistantSurface =
  | 'next-step'
  | 'candidate-review'
  | 'identity-preparation'
  | 'recording-review'
  | 'permission-review'
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
}

const generateBody = (retry: boolean) => JSON.stringify({ schema_version: '1', retry })

export const assistantApi = {
  project: (projectId: string, surface: ProjectAssistantSurface) =>
    request<AssistantSurfaceView>(`/api/projects/${encodeURIComponent(projectId)}/assistant/${surface}`),
  generateProject: (projectId: string, surface: ProjectAssistantSurface, retry = false) =>
    request<AssistantSurfaceView>(`/api/projects/${encodeURIComponent(projectId)}/assistant/${surface}`, {
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
