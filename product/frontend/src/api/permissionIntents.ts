/* 权限意图 API：承接 Human Approval 与待审 Agent proposal，不暴露 Contract/Profile 编辑面。 */

import { request } from './http'

export type PermissionIntentExpectation = 'ALLOW' | 'DENY'
export type ProtectedEffectDto = {
  kind: 'STATE_MUTATION' | 'DATA_DISCLOSURE' | 'OBJECT_CREATION' | 'EXTERNAL_DISPATCH' | 'RESTRICTED_FUNCTION_INVOCATION' | 'CREDENTIAL_ACCESS'
  resource_type: string
  business_label: string
  protected_fields: string[]
}
export type PermissionIntentCellDto = {
  action_candidate_id: string
  subject_role_candidate_id: string
  subject_role_display_name: string
  resource_owner_role_candidate_id: string
  resource_owner_role_display_name: string
  relation: 'OWNS' | 'SAME_ROLE_OTHER_ACCOUNT' | 'OTHER_ROLE'
  expectation: PermissionIntentExpectation | null
  protected_effects: ProtectedEffectDto[]
  status: 'UNCONFIRMED' | 'CURRENT' | 'NEEDS_REVIEW' | 'UNRESOLVED'
  review_reasons: string[]
  intent_id: string | null
  intent_revision: number | null
  intent_hash: string | null
  policy_epoch: number | null
  binding_fingerprint: string | null
  representative_test_identity_id: string | null
  representative_label: string | null
  execution_gap: string | null
}
export type PermissionIntentSemanticChangeDto = {
  effective_state: 'ACTIVE' | 'RETIRED'
  subject_display_name: string
  action_display_name: string
  resource_owner_display_name: string
  relation: PermissionIntentCellDto['relation']
  expectation: PermissionIntentExpectation
  protected_effects: ProtectedEffectDto[]
}
export type PermissionIntentImplementationRebindDto = {
  action_candidate_id: string
  subject_role_candidate_id: string
  resource_owner_role_candidate_id: string
  understanding_revision: number
  action_safety_setup_fingerprint: string
}
export type PermissionIntentProposalDto = {
  proposal_id: string
  project_id: string
  kind: 'SEMANTIC_CHANGE' | 'IMPLEMENTATION_REBIND'
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  intent_id: string | null
  semantic_change: PermissionIntentSemanticChangeDto | null
  implementation_rebind: PermissionIntentImplementationRebindDto | null
  proposed_by: string
  reason: string
  created_at_us: number
  decided_at_us: number | null
}
export type PermissionIntentProposalListDto = {
  project_id: string
  proposals: PermissionIntentProposalDto[]
}
export type PermissionIntentActionDto = {
  action_candidate_id: string
  action_display_name: string
  resource_logical_name: string | null
  cells: PermissionIntentCellDto[]
  gaps: string[]
  required_intent_count: number
  confirmed_intent_count: number
  executable_intent_count: number
  representative_gap_count: number
  compilable: boolean
}
export type PermissionIntentMatrixDto = {
  project_id: string
  policy_epoch: number
  actions: PermissionIntentActionDto[]
  confirmed_count: number
  review_required_count: number
  unconfirmed_count: number
  executable_count: number
  representative_gap_count: number
  compilable_action_count: number
}
export const permissionIntentsApi = {
  matrix: (projectId: string) =>
    request<PermissionIntentMatrixDto>(`/api/projects/${projectId}/permission-intents`),
  approve: (
    projectId: string,
    target: {
      action_candidate_id: string
      subject_role_candidate_id: string
      resource_owner_role_candidate_id: string
      relation: PermissionIntentCellDto['relation']
    },
    expectation: PermissionIntentExpectation | null,
    reason?: string,
  ) => request<PermissionIntentMatrixDto>(
    `/api/projects/${projectId}/permission-intents/approvals`,
    {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', target, expectation, ...(reason ? { reason } : {}) }),
    },
  ),
  proposals: (projectId: string) =>
    request<PermissionIntentProposalListDto>(`/api/projects/${projectId}/permission-intent-proposals`),
  approveProposal: (projectId: string, proposalId: string, reason?: string) =>
    request<PermissionIntentProposalDto>(`/api/projects/${projectId}/permission-intent-proposals/${encodeURIComponent(proposalId)}/approve`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', ...(reason ? { reason } : {}) }),
    }),
  rejectProposal: (projectId: string, proposalId: string) =>
    request<PermissionIntentProposalDto>(`/api/projects/${projectId}/permission-intent-proposals/${encodeURIComponent(proposalId)}/reject`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1' }),
    }),
}
