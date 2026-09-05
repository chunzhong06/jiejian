// 自然语言权限建议只返回待审数据；客户端没有应用或批准权限的快捷入口。
import { request } from './http'
import type { ProposedPermissionDto } from './businessBoundaries'

export type PermissionDraftSuggestion = {
  option_ids: string[]
  subject_actor_id: string
  subject_actor_revision: number
  business_action_id: string
  action_revision: number
  resource_owner_actor_id: string
  resource_owner_actor_revision: number
  relation: ProposedPermissionDto['relation']
  protected_effect_ids: string[]
  subject_display_name: string
  action_display_name: string
  resource_owner_display_name: string
  effect_display_names: string[]
  current_expectation: 'ALLOW' | 'DENY' | null
  suggested_expectation: 'ALLOW' | 'DENY'
  source_quotes: string[]
}
export type PermissionDraftView = {
  project_id: string
  boundary_fingerprint: string
  status: 'READY_FOR_REVIEW' | 'PARTIAL' | 'UNAVAILABLE'
  suggestions: PermissionDraftSuggestion[]
  issues: Array<{ code: string; message: string; source_quote: string | null }>
}
export const permissionDraftsApi = {
  generate: (projectId: string, text: string) => request<PermissionDraftView>(`/api/projects/${encodeURIComponent(projectId)}/permission-drafts`, {
    method: 'POST', body: JSON.stringify({ schema_version: '1', text }),
  }),
}
