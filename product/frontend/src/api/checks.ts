/* 普通检查 API：只读取当前检查预览，并无 Profile 参数地提交 Generated Profile。 */

import { request } from './http'
import type { RunDto } from './runs'

export type CheckPreviewGapDto = {
  code: string
  message: string
  next_path: '/application' | '/identities' | '/flows' | '/check'
  next_label: string
}

export type CheckPreviewItemDto = {
  subject_label: string
  subject_role_display_name: string
  relation: string
  expectation: 'ALLOW' | 'DENY' | null
  ready: boolean
  gaps: CheckPreviewGapDto[]
}

export type CheckPreviewActionDto = {
  action_candidate_id: string
  action_display_name: string
  resource_logical_name: string | null
  ready: boolean
  checks: CheckPreviewItemDto[]
  gaps: CheckPreviewGapDto[]
}

export type CheckPreviewDto = {
  project_id: string
  ready: boolean
  actions: CheckPreviewActionDto[]
  gaps: CheckPreviewGapDto[]
  next_path: CheckPreviewGapDto['next_path'] | null
  next_label: string | null
  case_count: number
  differential_pair_count: number
  change_id: string | null
  required_intent_count: number
}

export type CheckSubmissionDto = {
  schema_version: '1'
  run: RunDto
  job: { job_id: string; state: string }
}

export const checksApi = {
  preview: (projectId: string, changeId?: string) => request<CheckPreviewDto>(`/api/projects/${projectId}/check-preview${changeId ? `?change_id=${encodeURIComponent(changeId)}` : ''}`),
  submit: (projectId: string, changeId?: string) => request<CheckSubmissionDto>(`/api/projects/${projectId}/checks`, {
    method: 'POST',
    body: JSON.stringify({ schema_version: '1', idempotency_key: createIdempotencyKey(), change_id: changeId ?? null }),
  }),
}

function createIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() ?? `check-${Date.now()}-${Math.random().toString(16).slice(2)}`
}
