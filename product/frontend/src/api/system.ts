// 运行环境状态 API；仅暴露面向产品的可用性枚举。

import { request } from './http'

export type SystemStatus = {
  version?: string
  api: 'available' | 'unknown'
  worker: 'running' | 'stopped' | 'unavailable' | 'unknown'
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
    frontend?: { mode?: 'development' | 'prebuilt' | 'source-build'; dependencies?: string; dist?: string; build_state?: string }
  }
}

export type MaintenanceEntry = { path: string; bytes: number; files: number; categories?: Record<string, MaintenanceEntry> }
export type MaintenanceStatus = {
  schema_version: '1'
  entries: { assistant: MaintenanceEntry; logs: MaintenanceEntry; temporary: MaintenanceEntry }
  protected: { data: string; applications: boolean; permissions: boolean; database: boolean; evidence: boolean; reports: boolean; credentials: boolean; active_runtime: boolean; current_session_logs: boolean; development_root_included: boolean }
  last_successful_operation?: { operation?: string; completed_at?: number } | null
}
export type MaintenanceOperation = 'clear-assistant-cache' | 'clear-logs' | 'clear-temporary' | 'clear-all' | 'repair-runtime'
export type MaintenanceOperationResult = {
  schema_version: '1'
  plan_id: string
  scope: string
  operation: string
  generated_at_us: number
  expires_at_us: number
  dry_run: boolean
  confirmed?: boolean
  estimated_bytes: number
  targets: Array<{ item_id: string; label: string; relative_path: string; estimated_bytes: number }>
  removed: string[]
  results: Array<{ item_id: string; label: string; relative_path: string; status: 'DELETED' | 'ALREADY_MISSING' | 'SKIPPED_IN_USE' | 'SKIPPED_CHANGED' | 'FAILED'; reason: string }>
  counts: Record<'DELETED' | 'ALREADY_MISSING' | 'SKIPPED_IN_USE' | 'SKIPPED_CHANGED' | 'FAILED', number>
  requires_restart?: boolean
  protected: MaintenanceStatus['protected']
  status: MaintenanceStatus
}

export const systemApi = {
  status: () => request<SystemStatus>('/api/system/status'),
  maintenanceStatus: () => request<MaintenanceStatus>('/api/system/maintenance'),
  maintenanceOperation: (operation: MaintenanceOperation, body: { confirmed: boolean; dry_run: boolean; plan_id?: string }) => request<MaintenanceOperationResult>(`/api/system/maintenance/${operation}`, { method: 'POST', body: JSON.stringify({ schema_version: '1', ...body }) }),
  shutdown: () => request<{ status: 'stopping'; message: string }>('/api/system/shutdown', { method: 'POST' }),
}
