// 运行环境状态 API；仅暴露面向产品的可用性枚举。

import { request } from './http'

export type SystemStatus = {
  api: 'available' | 'unknown'
  worker: 'running' | 'stopped' | 'unknown'
  browser: 'available' | 'unavailable' | 'unknown'
  recovered_jobs?: number
  environment?: {
    runtime_mode?: string
    runtime_fingerprint?: string
    python?: { ok?: boolean; executable?: string; version?: string; prefix?: string; environment_type?: string; user_site_on_sys_path?: boolean; package_origins?: Record<string, string | null>; issues?: string[] }
    uv?: { version?: string; executable?: string }
    node?: { version?: string; executable?: string; required?: boolean }
    pnpm?: { version?: string; executable?: string; required?: boolean }
    playwright?: { package_version?: string; chromium_executable?: string }
    frontend?: { mode?: 'development' | 'prebuilt'; dependencies?: string; dist?: string }
  }
}

export type CacheEntry = { path: string; bytes: number; files: number; budget: number | null; over_budget: boolean }
export type CacheStatus = {
  schema_version: '1'
  entries: Record<string, CacheEntry>
  protected: { data: string; data_unchanged: boolean; current_runtime_unchanged_by_cache: boolean }
  last_successful_operation?: { operation?: string; completed_at?: number } | null
}
export type CacheOperation = 'prune' | 'clean' | 'runtime-repair'
export type CacheOperationResult = {
  schema_version: '1'
  operation: string
  dry_run: boolean
  confirmed?: boolean
  estimated_bytes: number
  targets: Array<{ path: string; estimated_bytes: number }>
  removed: string[]
  requires_restart?: boolean
  protected: CacheStatus['protected']
  status: CacheStatus
}

export const systemApi = {
  status: () => request<SystemStatus>('/api/system/status'),
  cacheStatus: () => request<CacheStatus>('/api/system/cache'),
  cacheOperation: (operation: CacheOperation, body: { confirmed: boolean; dry_run: boolean }) => request<CacheOperationResult>(`/api/system/cache/${operation}`, { method: 'POST', body: JSON.stringify(body) }),
  shutdown: () => request<{ status: 'stopping'; message: string }>('/api/system/shutdown', { method: 'POST', headers: { 'X-Jiejian-Control': 'shutdown' } }),
}
