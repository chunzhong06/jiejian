/* =============================================================================
 * Project API Client
 *
 * 定位
 *   接入页面与 Project HTTP 路由之间的前端能力适配器
 *
 * 职责
 *   注册 Project｜激活显式 Contract｜保持请求路径集中
 *
 * 调用链
 *   Access / ControlShell → projectsApi → api/http
 * ============================================================================= */

import { request } from './http'

export const projectsApi = {
  projects: () => request<Record<string, unknown>[]>('/api/projects'),
  registerProject: (path: string) =>
    request<Record<string, unknown>>('/api/projects', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', profile_path: path }),
    }),
  project: (id: string) => request<Record<string, unknown>>(`/api/projects/${id}`),
}
