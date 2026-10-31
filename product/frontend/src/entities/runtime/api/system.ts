// 运行环境状态 API；仅暴露面向产品的可用性枚举。

import { request } from '../../../shared/api/http'

export type SystemStatus = {
  frontend_identity?: {status: 'CONFIRMED' | 'UNCONFIRMED'; build_id: string | null; reason: string}
  version?: string
  api: 'available' | 'unknown'
  worker: 'running' | 'stopped' | 'unavailable' | 'unknown'
  browser: 'available' | 'unavailable' | 'unknown'
  recovered_jobs?: number
  checked_at?: string | null
  diagnostics_stale?: boolean
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
export type ExitReceipt = {state:'STOPPED'|'NEEDS_REVIEW';finished_at:number;exit_code:number}
export type RuntimeDiagnostics = SystemStatus & {checked_at:string;runtime_mode:string;components:Array<{key:string;label:string;ready:boolean}>;summary_text:string;last_exit?:ExitReceipt|null}
export type UpdateOperation = {operation_id:string;phase:'PREVIEWED'|'WAITING_FOR_EXIT'|'STARTING'|'READY'|'FAILED';target_version:string;target_release:string;workspace:string;reason:string;return_path:string;workspace_upgrade?:boolean}
export type UpdateInfo = {version:string;portable:boolean;release_root:string|null;workspace:string;operation:UpdateOperation|null;last_exit?:ExitReceipt|null}
export type MaintenanceStatus = {
  schema_version: '1'
  entries: { assistant: MaintenanceEntry; logs: MaintenanceEntry; temporary: MaintenanceEntry }
  protected: { data: string; applications: boolean; permissions: boolean; database: boolean; evidence: boolean; reports: boolean; credentials: boolean; active_runtime: boolean; current_session_logs: boolean; development_root_included: boolean }
  last_successful_operation?: { operation?: string; completed_at?: number } | null
  unresolved_plans?: string[]
  inventory?: Array<{category:string;label:string;relative_path:string;state:'CLEANABLE'|'PROTECTED'|'UNKNOWN';reason:string;bytes:number|null;files:number|null}>
  ownership_policy?: string
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
  targets: Array<{ item_id: string; label: string; relative_path: string; estimated_bytes: number; category?:string }>
  removed: string[]
  results: Array<{ item_id: string; label: string; relative_path: string; status: 'DELETED' | 'ALREADY_MISSING' | 'SKIPPED_IN_USE' | 'SKIPPED_CHANGED' | 'FAILED'; reason: string }>
  counts: Record<'DELETED' | 'ALREADY_MISSING' | 'SKIPPED_IN_USE' | 'SKIPPED_CHANGED' | 'FAILED', number>
  requires_restart?: boolean
  interrupted?: boolean
  unconfirmed?: number
  protected: MaintenanceStatus['protected']
  status: MaintenanceStatus
}

export const systemApi = {
  status: (signal?:AbortSignal) => request<SystemStatus>('/api/system/summary',{signal}),
  diagnostics: (signal?:AbortSignal) => request<RuntimeDiagnostics>('/api/system/diagnostics',{signal}),
  refreshDiagnostics: () => request<RuntimeDiagnostics>('/api/system/diagnostics',{method:'POST'}),
  updateInfo: (signal?:AbortSignal) => request<UpdateInfo>('/api/system/updates',{signal}),
  previewUpdate: (directory:string,returnPath:string) => request<UpdateOperation>('/api/system/updates/preview',{method:'POST',body:JSON.stringify({directory,return_path:returnPath})}),
  confirmUpdate: (id:string) => request<UpdateOperation>(`/api/system/updates/${encodeURIComponent(id)}/confirm`,{method:'POST'}),
  updateOutcome: (id:string) => request<UpdateOperation>(`/api/system/updates/${encodeURIComponent(id)}`),
  maintenanceStatus: (signal?:AbortSignal) => request<MaintenanceStatus>('/api/system/maintenance',{signal}),
  maintenanceOperation: (operation: MaintenanceOperation, body: { confirmed: boolean; dry_run: boolean; plan_id?: string; item_ids?:string[] }) => request<MaintenanceOperationResult>(`/api/system/maintenance/${operation}`, { method: 'POST', body: JSON.stringify({ schema_version: '1', ...body }) }),
  maintenanceOutcome: (planId:string) => request<{state:'COMPLETED'|'PENDING'|'INTERRUPTED'|'UNKNOWN';result:MaintenanceOperationResult|null}>(`/api/system/maintenance/plans/${encodeURIComponent(planId)}`),
  reviewMaintenance: (planId:string) => request<{reviewed:boolean}>(`/api/system/maintenance/plans/${encodeURIComponent(planId)}/review`,{method:'POST'}),
  shutdown: () => request<{ status: 'stopping'; message: string }>('/api/system/shutdown', { method: 'POST' }),
}
