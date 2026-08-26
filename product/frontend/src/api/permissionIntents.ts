/* 普通权限矩阵 API：只传递业务期望与生成命令，不暴露 Contract/Profile 编辑面。 */

import { request } from './http'

export type PermissionIntentExpectation = 'ALLOW' | 'DENY'
export type PermissionIntentCellDto = {
  action_candidate_id: string
  subject_role_candidate_id: string
  subject_role_display_name: string
  resource_owner_role_candidate_id: string
  resource_owner_role_display_name: string
  relation: 'OWNS' | 'SAME_ROLE_OTHER_ACCOUNT' | 'OTHER_ROLE'
  expectation: PermissionIntentExpectation | null
  status: 'UNCONFIRMED' | 'CURRENT' | 'NEEDS_REVIEW'
  review_reasons: string[]
  intent_fingerprint: string | null
  representative_test_identity_id: string | null
  representative_label: string | null
  execution_gap: string | null
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
  actions: PermissionIntentActionDto[]
  confirmed_count: number
  review_required_count: number
  unconfirmed_count: number
  executable_count: number
  representative_gap_count: number
  compilable_action_count: number
}
export type SecuritySetupCompileResultDto = {
  project_id: string
  authority_fingerprint: string
  contract_id: string
  contract_version: number
  contract_fingerprint: string
  profile_id: string
  profile_path: string
  profile_sha256: string
  covered_action_ids: string[]
  reused: boolean
}

export const permissionIntentsApi = {
  matrix: (projectId: string) =>
    request<PermissionIntentMatrixDto>(`/api/projects/${projectId}/permission-intents`),
  confirm: (
    projectId: string,
    actionId: string,
    subjectRoleId: string,
    ownerRoleId: string,
    relation: PermissionIntentCellDto['relation'],
    expectation: PermissionIntentExpectation | null,
    actor: string,
  ) => request<PermissionIntentMatrixDto>(
    `/api/projects/${projectId}/permission-intents/${actionId}/${subjectRoleId}/${ownerRoleId}/${relation}`,
    {
      method: 'PUT',
      body: JSON.stringify({ schema_version: '1', expectation, actor }),
    },
  ),
  compile: (projectId: string, actor: string) =>
    request<SecuritySetupCompileResultDto>(`/api/projects/${projectId}/security-setup/compile`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', actor }),
    }),
}
