// 当前代码变化事实；声明仅作线索，服务端重新扫描并决定可执行状态。
import { request } from './http'
import type { RepairReference } from './repairs'
import type { DeliverySubmission, DevelopmentReceipt } from './development'
export type SourceChangeViewDto = {
  manifest: { change_id: string; project_id: string; reason: string; submitted_by: string; created_at_us: number; claimed_paths: string[]; repair_reference: RepairReference | null }
  change_set: { status: 'COMPARABLE' | 'NO_BASELINE'; added_paths: string[]; modified_paths: string[]; removed_paths: string[] }
  assessment: { payload: { action_impacts: Array<{ action_id: string; action_revision: number; classification: 'DIRECTLY_AFFECTED' | 'MAPPING_REVIEW_REQUIRED' | 'NO_DIRECT_EVIDENCE'; relevant_paths: string[]; permission_refs: Array<{ intent_id: string }> }> } }
  revalidation: { status: 'READY' | 'NO_BASELINE' | 'SOURCE_STALE' | 'POLICY_STALE' | 'MAPPING_REVIEW_REQUIRED'; can_execute: boolean; preparation_gaps: Array<{ reason: string }> }
}
const base = (id: string) => `/api/projects/${encodeURIComponent(id)}/source-changes`
export type RegistrationPreview = { project_id: string; fingerprint: string; policy_epoch: number; permission_count: number }
export const sourceChangesApi = {
  registrationPreview: (id: string) => request<RegistrationPreview>(`${base(id)}/registration-preview`),
  register: (id: string, body: { operation_id: string; expected_registration_fingerprint: string; reason: string; claimed_paths: string[]; repair_reference: RepairReference | null }) => request<DevelopmentReceipt>(`${base(id)}/register`, { method: 'POST', body: JSON.stringify({ schema_version: '1', ...body }) }),
  list: (id: string, limit = 50) => request<SourceChangeViewDto[]>(`${base(id)}?limit=${limit}`),
  latest: (id: string) => request<SourceChangeViewDto | null>(`${base(id)}/latest`),
  show: (id: string, changeId: string) => request<SourceChangeViewDto>(`${base(id)}/${encodeURIComponent(changeId)}`),
  submit: (id: string, reason: string, paths: string[], reference: RepairReference | null, submission: DeliverySubmission) => request<DevelopmentReceipt>(base(id), { method: 'POST', body: JSON.stringify({ schema_version: '2', ...submission, reason, claimed_paths: paths, repair_reference: reference }) }),
}
