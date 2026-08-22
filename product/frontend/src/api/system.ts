// 运行环境状态 API；仅暴露面向产品的可用性枚举。

import { request } from './http'

export type SystemStatus = {
  api: 'available' | 'unknown'
  worker: 'running' | 'stopped' | 'unknown'
  browser: 'available' | 'unavailable' | 'unknown'
  recovered_jobs?: number
  environment?: {
    python?: { ok?: boolean; executable?: string; version?: string; prefix?: string; environment_type?: string; user_site_on_sys_path?: boolean; package_origins?: Record<string, string | null>; issues?: string[] }
    node?: { version?: string; executable?: string }
    pnpm?: { version?: string; executable?: string }
    playwright?: { package_version?: string; chromium_executable?: string }
    frontend_dependencies?: string
  }
}

export const systemApi = {
  status: () => request<SystemStatus>('/api/system/status'),
  shutdown: () => request<{ status: 'stopping'; message: string }>('/api/system/shutdown', { method: 'POST', headers: { 'X-Jiejian-Control': 'shutdown' } }),
}
