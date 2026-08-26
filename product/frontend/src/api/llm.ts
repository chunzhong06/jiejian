/* 模型服务 API；秘密只作为单次写入字段，不存在于响应类型。 */

import { request } from './http'

export type LLMProvider = 'openai' | 'deepseek' | 'gemini' | 'openai_compatible'
export type LLMConnectionStatus = 'testing' | 'configured' | 'available' | 'unavailable' | 'unknown'
export type LLMModelOption = {
  model: string
  display_name: string | null
  reasoning_options: string[]
  reasoning_default_label: string
  structured_output_mode: string
}
export type LLMModelCatalog = {
  schema_version: '1'
  provider: LLMProvider
  models: LLMModelOption[]
  manual_model_allowed: boolean
  truncated: boolean
}
export type AIAssistanceSettings = {
  enabled: boolean
  default_profile_name: string | null
  updated_at_us: number
}

export type LLMProfile = {
  schema_version: '1'
  profile_name: string
  provider: LLMProvider
  model: string
  reasoning_effort: string | null
  base_url: string | null
  timeout_ms: number
  max_input_bytes: number
  max_output_bytes: number
  max_budget_microusd: number
  enabled: boolean
  secret_ref: string | null
  allow_local_http: boolean
  created_at_us: number
  updated_at_us: number
  secret_configured: boolean
  connection_status: LLMConnectionStatus
  tested_at_us: number | null
  duration_ms: number | null
  error_code: string | null
  error_message: string | null
}

export type LLMProfileWrite = {
  profile_name?: string
  provider?: LLMProvider
  model?: string
  reasoning_effort?: string | null
  base_url?: string | null
  timeout_ms?: number
  max_input_bytes?: number
  max_output_bytes?: number
  max_budget_microusd?: number
  enabled?: boolean
  secret_ref?: string | null
  allow_local_http?: boolean
  secret?: string
}

export const llmApi = {
  settings: () => request<AIAssistanceSettings>('/api/llm/settings'),
  patchSettings: (body: Pick<AIAssistanceSettings, 'enabled' | 'default_profile_name'>) => request<AIAssistanceSettings>('/api/llm/settings', {
    method: 'PATCH', body: JSON.stringify({ schema_version: '1', ...body }),
  }),
  discoverModels: (body: { provider: LLMProvider; secret: string; base_url?: string; allow_local_http?: boolean }) => request<LLMModelCatalog>('/api/llm/models/discover', {
    method: 'POST', body: JSON.stringify({ schema_version: '1', ...body }),
  }),
  refreshModels: (name: string) => request<LLMModelCatalog>(`/api/llm/profiles/${encodeURIComponent(name)}/models/refresh`, { method: 'POST' }),
  saveDefault: (body: LLMProfileWrite) => request<LLMProfile>('/api/llm/default-profile', {
    method: 'PUT', body: JSON.stringify({ schema_version: '1', ...body }),
  }),
  profiles: () => request<LLMProfile[]>('/api/llm/profiles'),
  profile: (name: string) => request<LLMProfile>(`/api/llm/profiles/${encodeURIComponent(name)}`),
  create: (body: LLMProfileWrite) => request<LLMProfile>('/api/llm/profiles', {
    method: 'POST',
    body: JSON.stringify({ schema_version: '1', ...body }),
  }),
  update: (name: string, body: LLMProfileWrite) => request<LLMProfile>(`/api/llm/profiles/${encodeURIComponent(name)}`, {
    method: 'PATCH',
    body: JSON.stringify({ schema_version: '1', ...body }),
  }),
  test: (name: string) => request<LLMProfile>(`/api/llm/profiles/${encodeURIComponent(name)}/test`, {
    method: 'POST',
  }),
}
