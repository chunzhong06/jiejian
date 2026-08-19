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

export const contractsApi = {
  contracts: (id: string) => request<Record<string, unknown>[]>(`/api/projects/${id}/contracts`),
  contractGovernance: (id: string) => request<Record<string, unknown>>(`/api/projects/${id}/contract-governance`),
  createRequirement: (id: string, text: string, securityTags: string[], actor: string) =>
    request<Record<string, unknown>>(`/api/projects/${id}/contract-governance/requirements`, {
      method: 'POST', body: JSON.stringify({ schema_version: '1', text, security_tags: securityTags, actor }),
    }),
  deriveCandidates: (id: string, requirementIds: string[], actor: string) =>
    request<Record<string, unknown>>(`/api/projects/${id}/contract-governance/candidates/derive`, {
      method: 'POST', body: JSON.stringify({ schema_version: '1', requirement_ids: requirementIds, actor }),
    }),
  createGovernanceContract: (id: string, snapshot: Record<string, unknown>, candidateIds: string[], actor: string) =>
    request<Record<string, unknown>>(`/api/projects/${id}/contract-governance/contracts`, {
      method: 'POST', body: JSON.stringify({ schema_version: '1', contract_id: snapshot.contract_id, snapshot, candidate_ids: candidateIds, actor }),
    }),
  reviseGovernanceContract: (id: string, snapshot: Record<string, unknown>, candidateIds: string[], actor: string) =>
    request<Record<string, unknown>>(`/api/projects/${id}/contract-governance/contracts/${snapshot.contract_id}/revisions`, {
      method: 'POST', body: JSON.stringify({ schema_version: '1', snapshot, candidate_ids: candidateIds, actor }),
    }),
  transitionGovernanceVersion: (id: string, contractId: string, version: number, action: 'submit' | 'reject' | 'activate', actor: string) =>
    request<Record<string, unknown>>(`/api/projects/${id}/contract-governance/contracts/${contractId}/versions/${version}/${action}`, {
      method: 'POST', body: JSON.stringify({ schema_version: '1', actor }),
    }),
  contractVersions: (id: string, contractId: string) => request<Record<string, unknown>[]>(`/api/projects/${id}/contract-governance/contracts/${contractId}/versions`),
  assessment: (id: string, contractId: string, version: number) => request<Record<string, unknown>>(`/api/projects/${id}/contract-governance/contracts/${contractId}/versions/${version}/assessment`),
  diff: (id: string, contractId: string, version: number, fromVersion: number) => request<Record<string, unknown>>(`/api/projects/${id}/contract-governance/contracts/${contractId}/versions/${version}/diff?from_version=${fromVersion}`),
  drift: (id: string, contractId: string, version: number) => request<Record<string, unknown>>(`/api/projects/${id}/contract-governance/contracts/${contractId}/versions/${version}/drift`),
  llmCandidates: (id: string, requirementIds: string[], actor: string, profileName: string) =>
    request<Record<string, unknown>>(`/api/projects/${id}/contract-governance/candidates/llm`, {
      method: 'POST', body: JSON.stringify({ schema_version: '1', requirement_ids: requirementIds, actor, profile_name: profileName }),
    }),
  runContract: (runId: string) => request<Record<string, unknown>>(`/api/runs/${runId}/contract`),
}
