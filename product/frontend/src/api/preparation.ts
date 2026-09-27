// 动作准备的只读投影；主任务继续由 Workspace 提供，客户端不推导准备顺序。
import { request } from './http'
import type { PermissionIntentRevisionDto } from './businessBoundaries'

export type PermissionReference = { intent_id: string; revision: number; intent_hash: string }
export type AllowControlRequirement = {
  deny_permission: PermissionReference
  protected_effect_ids: string[]
  candidate_allow_permissions: PermissionReference[]
  resolved_allow_permission: PermissionReference | null
  selection_fingerprint: string
}

export type PreparationStatus = 'SATISFIED' | 'NEEDS_USER' | 'STALE' | 'BLOCKED' | 'NOT_REQUIRED'
export type PreparationItem = { status: PreparationStatus; reason_codes: string[]; binding_fingerprint?: string | null }
export type IdentitySlot = PreparationItem & {
  requirement: { slot_id: string; actor_id: string; actor_revision: number; ordinal: number }
  actor_display_name: string
  test_identity_id: string | null
}
export type ActionPreparation = {
  action_id: string
  action_revision: number
  display_name: string
  preparation_complete: boolean
  permissions: PermissionIntentRevisionDto[]
  assurance_contract: { allow_controls: AllowControlRequirement[] }
  identity_requirements: PreparationItem & { allocation_mode: string; slots: IdentitySlot[] }
  execution: PreparationItem
  resources: Array<PreparationItem & { owner_slot_id: string; owner_test_identity_id: string | null }>
  effect_evidence: Array<PreparationItem & { effect_id: string }>
  recovery: PreparationItem
  reason_codes: string[]
}
export type PreparationView = { project_id: string; actions: ActionPreparation[]; preparation_complete: boolean }
export type EffectMaterialSummary = {
  effect_id: string; business_label: string; resource_concept: string
  material_status: PreparationStatus; binding_fingerprint: string | null
  source_kind: 'RECORDED_OBSERVATION' | 'REGISTERED_OBSERVER' | null; source_label: string
  registered_source_available: boolean | null; closure_supported: boolean | null
  resource_correlation_supported: boolean | null; reason_codes: string[]
}
export type EvidenceMaterialDetail = {
  project_id: string; action_id: string; action_revision: number; action_label: string
  effects: EffectMaterialSummary[]
}
export type MaterialReference = { action_id: string; action_revision: number; kind: 'execution' | 'resource' | 'evidence' | 'recovery'; member_id: string | null }
export type MaterialDetails = {
  material: MaterialReference; status: PreparationStatus; reason_codes: string[]; retained: boolean
  source_recording_id: string | null; confirmed_at_us: number | null; expected_fingerprint: string; observed_at_us: number
  candidates: Array<{ recording_id: string; captured_at_us: number | null; current: boolean; updates: MaterialReference[] }>
  recording_context: MaterialRecordingContext | null
}
export type MaterialRecordingContext = {
  context_id: string; material: MaterialReference; expected_fingerprint: string; can_execute: boolean
  business_action_id: string; action_revision: number; subject_test_identity_id: string; resource_owner_test_identity_id: string
  subject_slot_id: string; resource_owner_slot_id: string; recording_purpose: 'TARGET' | 'OBSERVATION' | 'RECOVERY'
  parent_recording_id: string | null; effect_id: string | null; recording_id: string | null
  title: string; why_now: string; user_responsibility: string; system_will_do: string
}
export type MaterialChange = { schema_version: '1'; operation_id: string; material: MaterialReference; expected_fingerprint: string; candidate_recording_id: string | null }
export type MaterialPreview = { updates: MaterialReference[]; retained: MaterialReference[]; recheck: MaterialReference[] }
export type MaterialReceipt = MaterialPreview & { operation_id: string; created_at_us: number; result: 'SAVED' | 'RECHECKED' }
export type PreparationDraft = {
  schema_version: '1'; revision: number; action_id: string | null; action_revision: number | null
  material: MaterialReference | null; candidate_recording_id: string | null; base_fingerprint: string | null; pending_operation_id: string | null
}
export const preparationApi = {
  material: (projectId: string, ref: MaterialReference) => request<MaterialDetails>(`/api/projects/${projectId}/preparation/materials/${ref.action_id}/${ref.kind}?action_revision=${ref.action_revision}${ref.member_id ? `&member_id=${encodeURIComponent(ref.member_id)}` : ''}`),
  previewMaterial: (projectId: string, value: MaterialChange) => request<MaterialPreview>(`/api/projects/${projectId}/preparation/changes/preview`, { method: 'POST', body: JSON.stringify(value) }),
  saveMaterial: (projectId: string, value: MaterialChange) => request<MaterialReceipt>(`/api/projects/${projectId}/preparation/changes`, { method: 'POST', body: JSON.stringify(value) }),
  materialReceipt: (projectId: string, operationId: string) => request<MaterialReceipt>(`/api/projects/${projectId}/preparation/changes/${operationId}`),
  draft: (projectId: string) => request<PreparationDraft>(`/api/projects/${projectId}/preparation/draft`),
  saveDraft: (projectId: string, value: PreparationDraft) => request<PreparationDraft>(`/api/projects/${projectId}/preparation/draft`, { method: 'PUT', body: JSON.stringify(value) }),
  evidence: (projectId: string, actionId: string) => request<EvidenceMaterialDetail>(`/api/projects/${encodeURIComponent(projectId)}/preparation/evidence/${encodeURIComponent(actionId)}`),
  get: (projectId: string) => request<PreparationView>(`/api/projects/${projectId}/preparation`),
  selectAllowControl: (projectId: string, control: AllowControlRequirement, selected: PermissionReference) =>
    request(`/api/projects/${projectId}/preparation/allow-control`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', deny_permission: control.deny_permission,
        selected_allow_permission: selected, expected_selection_fingerprint: control.selection_fingerprint }),
    }),
}
