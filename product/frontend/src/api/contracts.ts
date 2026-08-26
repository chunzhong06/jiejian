/* =============================================================================
 * Contract API Client
 *
 * 定位
 *   建约页面与 Contract 治理、Diff、Drift HTTP 路由之间的适配器
 *
 * 职责
 *   提交治理动作｜读取工作台快照｜请求确定性分析视图
 *
 * 调用链
 *   PermissionRulesPage → contractsApi → api/http
 * ============================================================================= */

import { request } from './http'

export type PermissionSubjectDto = { subject_id: string; roles?: string[] }
export type PermissionActionDto = { action_id: string; effect_ids?: string[] }
export type SecurityEffectDto = {
  effect_id: string
  kind: string
  resource_type: string
  expected_state?: string | null
  protected_fields?: string[]
}
export type PermissionResourceDto = { resource_id: string; resource_type?: string }
export type PermissionEndpointDto = { endpoint_type: string; endpoint_id: string }
export type PermissionRelationDto = {
  relation_id?: string
  relation: string
  source: PermissionEndpointDto
  target: PermissionEndpointDto
}
export type PermissionRuleDto = {
  rule_id?: string
  id?: string
  subject_id: string
  action_id: string
  resource_id: string
  expectation: string
  severity?: string
  relation_path?: string[]
  context?: Record<string, unknown>
  required_observations?: string[]
}
export type PermissionBatchExpectationDto = {
  resource_id: string
  expectation: string
  relation_path?: string[]
}
export type PermissionBatchRuleDto = Omit<PermissionRuleDto, 'resource_id' | 'expectation'> & {
  atomic?: boolean
  resource_expectations?: PermissionBatchExpectationDto[]
}
export type PermissionContractDto = {
  schema_version?: '1'
  contract_id: string
  version: number
  status?: string
  subjects?: PermissionSubjectDto[]
  role_ids?: string[]
  effects?: SecurityEffectDto[]
  actions?: PermissionActionDto[]
  resources?: PermissionResourceDto[]
  relations?: PermissionRelationDto[]
  rules?: PermissionRuleDto[]
  batch_rules?: PermissionBatchRuleDto[]
}

export type ContractSummaryDto = {
  schema_version: '1'
  status: string
  id: string
  version: number
  rules: PermissionRuleDto[]
}

export type GovernanceRequirementDto = { requirement_id: string; text: string; security_tags?: string[] }
export type GovernanceCandidateDto = { candidate_id: string; rule?: { id?: string; rule_id?: string } }
export type GovernanceIssueDto = { severity?: string; code?: string; reason_code?: string; detail?: string }
export type GovernanceVersionDto = {
  contract_id: string
  version: number
  status: string
  snapshot?: PermissionContractDto
}
export type GovernanceWorkspaceDto = {
  project?: { governed_contract_id?: string | null; governed_contract_version?: number | null }
  requirements?: GovernanceRequirementDto[]
  candidates?: GovernanceCandidateDto[]
  versions?: GovernanceVersionDto[]
}
export type CandidateDerivationDto = {
  batches?: Array<{ issues?: GovernanceIssueDto[] }>
  merge?: { issues?: GovernanceIssueDto[] }
  persisted_candidates?: GovernanceCandidateDto[]
}
export type GovernanceAnalysisDto = Record<string, unknown>

export const contractsApi = {
  contracts: (id: string) => request<ContractSummaryDto[]>(`/api/projects/${id}/contracts`),
  contractGovernance: (id: string) => request<GovernanceWorkspaceDto>(`/api/projects/${id}/contract-governance`),
  createRequirement: (id: string, text: string, securityTags: string[], actor: string) =>
    request<GovernanceRequirementDto>(`/api/projects/${id}/contract-governance/requirements`, {
      method: 'POST', body: JSON.stringify({ schema_version: '1', text, security_tags: securityTags, actor }),
    }),
  deriveCandidates: (id: string, requirementIds: string[], actor: string) =>
    request<CandidateDerivationDto>(`/api/projects/${id}/contract-governance/candidates/derive`, {
      method: 'POST', body: JSON.stringify({ schema_version: '1', requirement_ids: requirementIds, actor }),
    }),
  createGovernanceContract: (id: string, snapshot: PermissionContractDto, candidateIds: string[], actor: string) =>
    request<GovernanceVersionDto>(`/api/projects/${id}/contract-governance/contracts`, {
      method: 'POST', body: JSON.stringify({ schema_version: '1', contract_id: snapshot.contract_id, snapshot, candidate_ids: candidateIds, actor }),
    }),
  reviseGovernanceContract: (id: string, snapshot: PermissionContractDto, candidateIds: string[], actor: string) =>
    request<GovernanceVersionDto>(`/api/projects/${id}/contract-governance/contracts/${snapshot.contract_id}/revisions`, {
      method: 'POST', body: JSON.stringify({ schema_version: '1', snapshot, candidate_ids: candidateIds, actor }),
    }),
  transitionGovernanceVersion: (id: string, contractId: string, version: number, action: 'submit' | 'reject' | 'activate', actor: string) =>
    request<GovernanceVersionDto>(`/api/projects/${id}/contract-governance/contracts/${contractId}/versions/${version}/${action}`, {
      method: 'POST', body: JSON.stringify({ schema_version: '1', actor }),
    }),
  contractVersions: (id: string, contractId: string) => request<GovernanceVersionDto[]>(`/api/projects/${id}/contract-governance/contracts/${contractId}/versions`),
  assessment: (id: string, contractId: string, version: number) => request<GovernanceAnalysisDto>(`/api/projects/${id}/contract-governance/contracts/${contractId}/versions/${version}/assessment`),
  diff: (id: string, contractId: string, version: number, fromVersion: number) => request<GovernanceAnalysisDto>(`/api/projects/${id}/contract-governance/contracts/${contractId}/versions/${version}/diff?from_version=${fromVersion}`),
  drift: (id: string, contractId: string, version: number) => request<GovernanceAnalysisDto>(`/api/projects/${id}/contract-governance/contracts/${contractId}/versions/${version}/drift`),
  runContract: (runId: string) => request<PermissionContractDto>(`/api/runs/${runId}/contract`),
}
