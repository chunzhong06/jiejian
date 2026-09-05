// 动作准备的只读投影；主任务继续由 Workspace 提供，客户端不推导准备顺序。
import { request } from './http'

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
  identity_requirements: PreparationItem & { allocation_mode: string; slots: IdentitySlot[] }
  execution: PreparationItem
  resources: Array<PreparationItem & { owner_slot_id: string; owner_test_identity_id: string | null }>
  effect_evidence: Array<PreparationItem & { effect_id: string }>
  recovery: PreparationItem
  reason_codes: string[]
}
export type PreparationView = { project_id: string; actions: ActionPreparation[]; preparation_complete: boolean }
export const preparationApi = {
  get: (projectId: string) => request<PreparationView>(`/api/projects/${projectId}/preparation`),
}
