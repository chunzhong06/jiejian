/* 执行配置 API 客户端
 *
 * 定位：测试页执行配置的独立控制面适配器。
 * 不保存执行配置路径或凭据。
 */

import { request } from './http'
import type { PermissionContractDto } from './contracts'

export type ExecutionProfileDto = {
  schema_version?: '1'
  profile_id: string
  project_id: string
  name?: string
  profile_path?: string
  created_at_us?: number
  updated_at_us?: number
}

export type SubmittedRunDto = {
  schema_version: '1'
  run: import('./runs').RunDto
  job: { job_id: string; state: string }
}

export type ExecutionProfileSummaryDto = {
  schema_version: '1'
  workflows: Array<{
    action_id: string
    workflow_id: string
    target_step: { step_id: string; method: string; path: string }
    setup_step_count: number
    cleanup_step_count: number
    baseline_modes: string[]
  }>
  effect_bindings: Array<{
    effect_id: string
    required_channels: string[]
    corroborating_channels: string[]
    closure_policy: string
  }>
}

export const executionProfilesApi = {
  profiles: (projectId: string) =>
    request<ExecutionProfileDto[]>(`/api/projects/${encodeURIComponent(projectId)}/execution-profiles`),
  contract: (projectId: string, profileId: string) =>
    request<PermissionContractDto>(`/api/projects/${encodeURIComponent(projectId)}/execution-profiles/${encodeURIComponent(profileId)}/contract`),
  summary: (projectId: string, profileId: string) =>
    request<ExecutionProfileSummaryDto>(`/api/projects/${encodeURIComponent(projectId)}/execution-profiles/${encodeURIComponent(profileId)}/summary`),
  submit: (projectId: string, profileId: string) =>
    request<SubmittedRunDto>(`/api/projects/${encodeURIComponent(projectId)}/runs`, {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        profile_id: profileId,
        idempotency_key: `gui-permission-${crypto.randomUUID()}`,
      }),
    }),
}
