/* 延期检查链 DTO：仅供未注册旧组件继续编译，不属于 当前 Workspace API。 */

import type { ProjectDto } from './projects'
import type { SourceChangeViewDto } from './sourceChanges'

export type PreparationItemKind = 'IDENTITY' | 'FLOW' | 'RESOURCE' | 'OBSERVATION' | 'RECOVERY' | 'EFFECT' | 'PROFILE'
export type PreparationItemStatus = 'READY' | 'AUTO' | 'USER' | 'BLOCKED'
export type PreparationPath = '/application' | '/changes' | '/permissions' | '/preparation' | '/identities' | '/flows' | '/validation'
export type PreparationItemDto = {
  key: string; kind: PreparationItemKind; label: string; status: PreparationItemStatus
  description: string; next_path: PreparationPath | null; next_label: string | null
  reason_codes: string[]; auto_action: 'ENSURE_IDENTITY_RECORD' | 'BUILD_CURRENT_PROFILE' | null
  role_candidate_id: string | null; action_candidate_id: string | null; recording_id: string | null
  identity_id: string | null; owner_test_identity_id: string | null
}
export type PreparationExternalBlockerDto = {
  key: string; category: 'APPLICATION' | 'PERMISSION' | 'SOURCE_CHANGE'; label: string
  description: string; next_path: PreparationPath; next_label: string; reason_codes: string[]
}
export type ProjectPreparationDto = {
  project_id: string; ready: boolean; items: PreparationItemDto[]; next_item_key: string | null
  auto_action_count: number; user_action_count: number; blocked_count: number
  external_blockers: PreparationExternalBlockerDto[]; next_path: PreparationPath | null; next_label: string | null
}
export type ProjectRepairStatus = 'NONE' | 'REPAIR_REQUIRED' | 'CHANGE_SUBMITTED' | 'READY_TO_VERIFY' | 'VERIFIED' | 'NOT_VERIFIED' | 'INCONCLUSIVE' | 'STALE'
export type ProjectRepairPath = '/changes' | '/permissions' | '/preparation' | '/validation' | '/results'
export type RepairTaskDto = {
  source_run_id: string; source_finding_id: string; status: ProjectRepairStatus
  must_disappear: string; must_remain: string; must_not_change: string[]
  linked_change_id: string | null; verification_run_id: string | null
  verification_status: 'VERIFIED' | 'NOT_VERIFIED' | 'INCONCLUSIVE' | null
  next_path: ProjectRepairPath; next_label: string; reason_codes: string[]
}
export type ProjectRepairDto = {
  project_id: string; status: ProjectRepairStatus; tasks: RepairTaskDto[]
  next_path: ProjectRepairPath | null; next_label: string | null; reason_codes: string[]
}
export type DeliveryCheckDto = {
  project_id: string; decision: 'READY' | 'BLOCKED' | 'ERROR'; summary: string
  reason_codes: string[]; next_path: ProjectRepairPath | null; next_label: string | null
  verified_run_id: string | null
}
export type ProjectReadinessDto = {
  project_id: string; project_status: string; application_connected: boolean
  endpoint_status: 'NEEDS_CONNECTION' | 'NEEDS_CONFIRMATION' | 'CONFIRMED' | 'UNAVAILABLE'
  source_analysis_status: 'NOT_AVAILABLE' | 'NOT_AUTHORIZED' | 'PENDING' | 'COMPLETED' | 'STALE'
  discovered_role_count: number; confirmed_role_count: number
  discovered_action_count: number; confirmed_action_count: number
  execution_profile_available: boolean; completed_flow_available: boolean; active_contract_available: boolean
  permission_actions?: Array<{ action_candidate_id: string; action_display_name: string; compilable: boolean; gaps: string[]; required_intent_count: number; confirmed_intent_count: number; executable_intent_count: number; representative_gap_count: number }>
  permission_requirement_count?: number; confirmed_permission_requirement_count?: number
  executable_permission_requirement_count?: number; permission_representative_gap_count?: number
  current_scope_runnable: boolean; remaining_gap_count: number
  active_tasks: Array<{ kind: 'RUN' | 'RECORDING'; task_id: string; state: string }>
  latest_verified_run_id: string | null
  next_required_action: 'CONNECT_APPLICATION' | 'CONFIRM_TARGET' | 'AUTHORIZE_SOURCE_ANALYSIS' | 'REVIEW_DISCOVERY' | 'RECORD_FLOW' | 'REVIEW_CHANGE' | 'REVIEW_PERMISSION' | 'RUN_CHECK' | 'OPEN_RESULT'
  preparation?: ProjectPreparationDto | null
}
export type ProductStatusDto = {
  project: (ProjectDto & { target_type: 'WEB' }) | null
  readiness: ProjectReadinessDto | null
  revalidation: { project_id: string; status: 'NO_CHANGE' | 'REVIEW_REQUIRED' | 'PREPARATION_REQUIRED' | 'READY' | 'VERIFIED' | 'STALE'; change_id: string | null; summary: string; next_path: '/changes' | '/permissions' | '/preparation' | '/validation' | '/results' | null; next_label: string | null; required_intent_count: number; reason_codes: string[]; verified_run_id: string | null; verified_change_id: string | null } | null
  repair: ProjectRepairDto | null
  areas: Array<{ key: 'overview' | 'changes' | 'permissions' | 'tests'; label: string; description: string; route: '/workspace' | '/changes' | '/permissions' | '/tests'; status: 'READY' | 'NEEDS_ATTENTION' | 'RUNNING' | 'AVAILABLE' | 'BLOCKED' | 'EMPTY'; status_label: string }>
  primary_attention_key: string | null
  attention_items: Array<{ key: string; label: string; description: string; route: '/workspace' | '/application' | '/changes' | '/permissions' | '/tests' | '/preparation' | '/identities' | '/flows' | '/validation' | '/results' | '/verification' | '/history'; tone: 'ACTION' | 'WARNING' | 'INFO' }>
  latest_change: SourceChangeViewDto | null
  latest_result: { run_id: string; verdict: 'PASS' | 'BLOCK' | 'INCONCLUSIVE' | null; headline: string; scope_statement: string; verified_change_id: string | null } | null
  inconclusive_recovery: { source_run_id: string; summary: string; next_path: '/changes' | '/permissions' | '/preparation' | '/validation'; next_label: string; reason_codes: string[] } | null
}
