/* 模型服务 API；秘密只作为单次写入字段，不存在于响应类型。 */

import { request } from './http'

export type LLMProvider = 'openai' | 'deepseek' | 'gemini' | 'openai_compatible'
export type LLMConnectionStatus = 'testing' | 'configured' | 'available' | 'unavailable' | 'unknown'

export type LLMProfile = {
  schema_version: '1'
  profile_name: string
  provider: LLMProvider
  model: string
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
  profiles: () => request<LLMProfile[]>('/api/v1/llm/profiles'),
  profile: (name: string) => request<LLMProfile>(`/api/v1/llm/profiles/${encodeURIComponent(name)}`),
  create: (body: LLMProfileWrite) => request<LLMProfile>('/api/v1/llm/profiles', {
    method: 'POST',
    body: JSON.stringify({ schema_version: '1', ...body }),
  }),
  update: (name: string, body: LLMProfileWrite) => request<LLMProfile>(`/api/v1/llm/profiles/${encodeURIComponent(name)}`, {
    method: 'PATCH',
    body: JSON.stringify({ schema_version: '1', ...body }),
  }),
  test: (name: string) => request<LLMProfile>(`/api/v1/llm/profiles/${encodeURIComponent(name)}/test`, {
    method: 'POST',
  }),
}
