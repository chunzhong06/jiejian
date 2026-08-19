/* 执行配置 API 客户端
 *
 * 定位：测试页执行配置的独立控制面适配器。
 * 不保存执行配置路径或凭据。
 */

import { request } from './http'

type Item = Record<string, any>

export const executionProfilesApi = {
  register: (path: string) =>
    request<Item>('/api/execution-profiles', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', profile_path: path }),
    }),
  profiles: (projectId: string) =>
    request<Item[]>(`/api/projects/${encodeURIComponent(projectId)}/execution-profiles`),
  contract: (projectId: string, profileId: string) =>
    request<Item>(`/api/projects/${encodeURIComponent(projectId)}/execution-profiles/${encodeURIComponent(profileId)}/contract`),
  submit: (projectId: string, profileId: string) =>
    request<Item>(`/api/projects/${encodeURIComponent(projectId)}/runs`, {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        profile_id: profileId,
        idempotency_key: `gui-permission-${crypto.randomUUID()}`,
      }),
    }),
}
