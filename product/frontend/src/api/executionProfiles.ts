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

export const executionProfilesApi = {
  register: (path: string) =>
    request<ExecutionProfileDto>('/api/execution-profiles', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', profile_path: path }),
    }),
  profiles: (projectId: string) =>
    request<ExecutionProfileDto[]>(`/api/projects/${encodeURIComponent(projectId)}/execution-profiles`),
  contract: (projectId: string, profileId: string) =>
    request<PermissionContractDto>(`/api/projects/${encodeURIComponent(projectId)}/execution-profiles/${encodeURIComponent(profileId)}/contract`),
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
