/* Permission Execution V2 API Client
 *
 * 定位：测试页高级权限执行配置的独立控制面适配器。
 * 不进入 V1 runsApi，也不保存 Profile 路径或凭据。
 */

import { request } from './http'

type Item = Record<string, any>

export const permissionExecutionApi = {
  register: (path: string, revalidate = false) =>
    request<Item>('/api/v2/permission-execution-profiles', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '2', path, revalidate }),
    }),
  profiles: (projectId: string) =>
    request<Item[]>(`/api/v2/projects/${encodeURIComponent(projectId)}/permission-execution-profiles`),
  submit: (projectId: string, profileId: string) =>
    request<Item>(`/api/v2/projects/${encodeURIComponent(projectId)}/runs`, {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '2',
        profile_id: profileId,
        idempotency_key: `gui-v2-${crypto.randomUUID()}`,
        max_attempts: 3,
      }),
    }),
}
