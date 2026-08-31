/* 持续验证 API：按当前权限基线或指定 Agent 变化准备、预览并提交检查。 */

import { request } from './http'
import type { RunDto } from './runs'

export type CheckPreviewGapDto = {
  code: string
  message: string
  next_path: '/application' | '/permissions' | '/preparation' | '/validation'
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
  prepare: (projectId: string, changeId?: string) => request<CheckPreviewDto>(`/api/projects/${projectId}/check-preparation`, {
    method: 'POST',
    body: JSON.stringify({ schema_version: '1', change_id: changeId ?? null }),
  }),
  submit: (projectId: string, changeId?: string) => request<CheckSubmissionDto>(`/api/projects/${projectId}/checks`, {
    method: 'POST',
    body: JSON.stringify({ schema_version: '1', idempotency_key: createIdempotencyKey(), change_id: changeId ?? null }),
  }),
}

function createIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() ?? `check-${Date.now()}-${Math.random().toString(16).slice(2)}`
}
