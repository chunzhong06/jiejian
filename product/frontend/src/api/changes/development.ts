// 开发任务和稳定回执的唯一 HTTP 入口；不把任务关闭推断成检查通过。
import { request } from '../http'
import type { SourceChangeViewDto } from './sourceChanges'

export type DevelopmentTask = { task_id: string; project_id: string; status: 'ACTIVE' | 'CLOSED' | 'CANCELLED'; version: number; revision: number; context_id: string; created_at_us: number; updated_at_us: number }
export type DevelopmentContext = { context_id: string; task_id: string; project_id: string; revision: number; title: string; goal: string; permission_refs: Array<{ intent_id: string; revision: number; intent_hash: string }> }
export type DevelopmentDelivery = { delivery_id: string; context_id: string; task_id: string; project_id: string; ordinal: number; change_id: string; created_at_us: number }
export type DevelopmentView = { task: DevelopmentTask; context: DevelopmentContext; acceptance: { client_name: string; accepted_at_us: number } | null; deliveries: DevelopmentDelivery[]; has_more: boolean; runtime_state: 'MATCHED' | 'NOT_LOADED' | 'UNCONFIRMED' | 'UNSUPPORTED'; latest_verification: { run_id: string | null; lifecycle: string | null; verdict: string | null; runtime_status: string; repair_status: string | null } | null }
export type OperationKind = 'CREATE' | 'REVISE' | 'ACCEPT' | 'DELIVER' | 'CLOSE' | 'CANCEL'
export type DevelopmentReceipt = { project_id: string; kind: OperationKind; operation_id: string; status: 'SUCCEEDED'; task_id: string; task_version: number; context_id: string; delivery_id: string | null; change_id: string | null }
export type DeliverySubmission = { operation_id: string; task_id: string; context_id: string; expected_version: number }
export type RuntimeActivationReceipt = { project_id: string; operation_id: string; delivery_id: string; status: 'PENDING' | 'SUCCEEDED' | 'FAILED' | 'UNKNOWN'; error_code: string | null }
export type TaskHistoryItem = { task_id: string; title: string; status: DevelopmentTask['status']; revision: number; updated_at_us: number }
export type TaskHistoryPage = { project_id: string; items: TaskHistoryItem[]; next_task_id: string | null }
export type DeliveryPage = { project_id: string; task_id: string; items: Array<{ delivery: DevelopmentDelivery; reason: string; submitted_by: string }>; next_ordinal: number | null }
export type DeliveryDetails = { project_id: string; delivery: DevelopmentDelivery; context: DevelopmentContext; relative_change: SourceChangeViewDto['change_set']; cumulative_change: SourceChangeViewDto['change_set']; verification: NonNullable<DevelopmentView['latest_verification']> }
const base = (project: string) => `/api/projects/${encodeURIComponent(project)}/development`
const post = <T,>(url: string, body: object) => request<T>(url, { method: 'POST', body: JSON.stringify({ schema_version: '1', ...body }) })
export const newOperationId = () => crypto.randomUUID().replaceAll('-', '')
export const developmentApi = {
  history: (project: string, before?: string | null) => request<TaskHistoryPage>(`${base(project)}/history${before ? '?before_task_id=' + encodeURIComponent(before) : ''}`),
  deliveries: (project: string, task: string, before?: number | null) => request<DeliveryPage>(`${base(project)}/tasks/${encodeURIComponent(task)}/deliveries${before ? '?before_ordinal=' + before : ''}`),
  details: (project: string, change: string) => request<DeliveryDetails | null>(`${base(project)}/changes/${encodeURIComponent(change)}`),
  current: (project: string) => request<DevelopmentView | null>(`${base(project)}/current`),
  show: (project: string, task: string) => request<DevelopmentView>(`${base(project)}/tasks/${encodeURIComponent(task)}`),
  list: (project: string) => request<DevelopmentTask[]>(`${base(project)}/tasks`),
  create: (project: string, body: { operation_id: string; title: string; goal: string }) => post<DevelopmentReceipt>(`${base(project)}/tasks`, { ...body, expected_version: 0 }),
  revise: (project: string, task: string, body: { operation_id: string; expected_version: number; title: string; goal: string }) => post<DevelopmentReceipt>(`${base(project)}/tasks/${encodeURIComponent(task)}/revisions`, body),
  finish: (project: string, task: string, body: { operation_id: string; expected_version: number; action: 'CLOSE' | 'CANCEL' }) => post<DevelopmentReceipt>(`${base(project)}/tasks/${encodeURIComponent(task)}/finish`, body),
  receipt: (project: string, kind: OperationKind, operation: string) => request<DevelopmentReceipt | null>(`${base(project)}/receipts/${kind}/${encodeURIComponent(operation)}`),
  loadRuntime: (project: string, delivery: string, body: { operation_id: string; expected_version: number }) => post<RuntimeActivationReceipt>(`${base(project)}/deliveries/${encodeURIComponent(delivery)}/runtime`, body),
  runtimeReceipt: (project: string, operation: string) => request<RuntimeActivationReceipt | null>(`${base(project)}/runtime-operations/${encodeURIComponent(operation)}`),
}
