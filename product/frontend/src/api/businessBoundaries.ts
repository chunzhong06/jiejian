/* Business Boundary API：前端只编辑本地草稿，服务端 Proposal 与 Decision 均不可变。 */

import { request } from './http'

export type BoundaryConfidence = 'HIGH' | 'MEDIUM' | 'LOW'
export type BoundaryCandidateDto = {
  candidate_kind: 'ROLE' | 'ACTION'
  candidate_id: string
  display_name: string
  confidence: BoundaryConfidence
}
export type BoundaryDraftViewDto = {
  project_id: string
  application_understanding_revision: number
  candidates: BoundaryCandidateDto[]
}

export type BusinessEffectKind = 'STATE_MUTATION' | 'DATA_DISCLOSURE' | 'OBJECT_CREATION' | 'EXTERNAL_DISPATCH' | 'RESTRICTED_FUNCTION_INVOCATION' | 'CREDENTIAL_ACCESS'
export type ProposedEffectDto = {
  item_id: string
  effect_id?: string | null
  business_label: string
  effect_kind: BusinessEffectKind
  resource_concept: string
  expected_state?: string | null
  protected_projection?: string[]
  description: string
}
export type ProposedActorDto = {
  item_id: string
  write_mode: 'CREATE' | 'REFERENCE' | 'APPEND_REVISION'
  actor_id?: string | null
  expected_current_revision?: number | null
  source_candidate_ids?: string[]
  display_name: string
  description: string
  effective_state: 'ACTIVE' | 'SUPERSEDED' | 'RETIRED'
}
export type ProposedActionDto = {
  item_id: string
  write_mode: 'CREATE' | 'REFERENCE' | 'APPEND_REVISION'
  action_id?: string | null
  expected_current_revision?: number | null
  source_candidate_ids?: string[]
  display_name: string
  description: string
  primary_resource_concept: string
  operation_kind: 'READ' | 'CHANGE' | 'DELETE' | 'EXPORT' | 'ADMIN' | 'CUSTOM'
  state_changing: boolean
  effect_catalog: ProposedEffectDto[]
  effective_state: 'ACTIVE' | 'SUPERSEDED' | 'RETIRED'
}
export type ProposedPermissionDto = {
  item_id: string
  write_mode: 'CREATE' | 'REFERENCE' | 'APPEND_REVISION'
  intent_id?: string | null
  expected_current_revision?: number | null
  effective_state: 'ACTIVE' | 'RETIRED'
  subject_actor_item_id: string
  business_action_item_id: string
  resource_owner_actor_item_id: string
  relation: 'OWNS' | 'SAME_ROLE_OTHER_ACCOUNT' | 'OTHER_ROLE'
  expectation: 'ALLOW' | 'DENY'
  protected_effect_item_ids: string[]
}
export type BoundaryProposalCommandDto = {
  proposed_actors: ProposedActorDto[]
  proposed_actions: ProposedActionDto[]
  proposed_permissions: ProposedPermissionDto[]
  unresolved_questions?: string[]
  provenance: string
}
export type BoundaryProposalDto = BoundaryProposalCommandDto & {
  proposal_id: string
  project_id: string
  source_snapshot: object
  proposal_fingerprint: string
  created_at_us: number
}
export type BoundaryDecisionDto = {
  decision: 'APPROVED' | 'REJECTED'
  decided_by: string
  decided_at_us: number
  reason: string
}
export type BoundaryProposalViewDto = {
  proposal: BoundaryProposalDto
  decision: BoundaryDecisionDto | null
}
export type BoundaryProposalListDto = {
  project_id: string
  proposals: BoundaryProposalViewDto[]
}

export type BusinessActorRevisionDto = {
  actor_id: string
  revision: number
  display_name: string
  description: string
  effective_state: 'ACTIVE' | 'SUPERSEDED' | 'RETIRED'
}
export type BusinessActionRevisionDto = {
  action_id: string
  revision: number
  display_name: string
  description: string
  primary_resource_concept: string
  operation_kind: ProposedActionDto['operation_kind']
  state_changing: boolean
  effect_catalog: Array<ProposedEffectDto & { effect_id: string }>
  effective_state: 'ACTIVE' | 'SUPERSEDED' | 'RETIRED'
}
export type PermissionIntentRevisionDto = {
  subject_actor_id: string
  subject_actor_revision: number
  business_action_id: string
  action_revision: number
  resource_owner_actor_id: string
  resource_owner_actor_revision: number
  relation: ProposedPermissionDto['relation']
  expectation: ProposedPermissionDto['expectation']
  protected_effect_ids: string[]
  effective_state: 'ACTIVE' | 'RETIRED'
}
export type BusinessBoundaryViewDto = {
  project_id: string
  policy_epoch: number
  actors: BusinessActorRevisionDto[]
  actions: BusinessActionRevisionDto[]
  actor_bindings: Array<{ actor_id: string; actor_revision: number; status: 'CURRENT' | 'STALE' | 'MISSING' | 'AMBIGUOUS' }>
  action_bindings: Array<{ action_id: string; action_revision: number; status: 'CURRENT' | 'STALE' | 'MISSING' | 'AMBIGUOUS' }>
  permission_intents: PermissionIntentRevisionDto[]
  permission_statuses: Array<{
    action_id: string
    action_revision: number
    permission_semantics_confirmed: boolean
    active_permission_count: number
    stale_permission_count: number
    allow_control_available: boolean
    validation_contract_complete: boolean
    reason_codes: string[]
  }>
}

const prefix = (projectId: string) => `/api/projects/${projectId}/business-boundaries`

export const businessBoundariesApi = {
  current: (projectId: string) => request<BusinessBoundaryViewDto>(prefix(projectId)),
  preview: (projectId: string) => request<BoundaryDraftViewDto>(`${prefix(projectId)}/preview`),
  proposals: (projectId: string, pendingOnly = false) => request<BoundaryProposalListDto>(`${prefix(projectId)}/proposals${pendingOnly ? '?pending_only=true' : ''}`),
  createProposal: (projectId: string, command: BoundaryProposalCommandDto) => request<BoundaryProposalViewDto>(`${prefix(projectId)}/proposals`, {
    method: 'POST',
    body: JSON.stringify({ schema_version: '1', ...command }),
  }),
  approve: (projectId: string, proposal: BoundaryProposalDto, reason: string) => request<BusinessBoundaryViewDto>(`${prefix(projectId)}/proposals/${encodeURIComponent(proposal.proposal_id)}/approve`, {
    method: 'POST',
    body: JSON.stringify({ schema_version: '1', expected_fingerprint: proposal.proposal_fingerprint, reason }),
  }),
  reject: (projectId: string, proposal: BoundaryProposalDto, reason: string) => request<BoundaryProposalViewDto>(`${prefix(projectId)}/proposals/${encodeURIComponent(proposal.proposal_id)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ schema_version: '1', expected_fingerprint: proposal.proposal_fingerprint, reason }),
  }),
}
