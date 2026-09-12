// 原题与项目修复只读投影；修复状态由服务端发布事实决定。
import { request } from './http'

export type RepairReference = { source_run_id: string; source_case_id: string; repair_fingerprint: string }
export type RepairStatus = 'REPAIR_REQUIRED' | 'CHANGE_SUBMITTED' | 'READY_TO_VERIFY' | 'VERIFIED' | 'NOT_VERIFIED' | 'INCONCLUSIVE' | 'STALE'
export type RepairContract = {
  project_id: string; source_run_id: string; source_case_id: string; repair_fingerprint: string; original_policy_epoch: number
  deny: { identity: { action_id: string; resource_id: string; subject_test_identity_id: string; resource_owner_test_identity_id: string; protected_effect_ids: string[] }; evidence_refs: string[] }
  regressions: Array<{ source_case_id: string }>
}
export type RepairComparisonRow = {
  role: 'DENY' | 'SELECTED_ALLOW' | 'REGRESSION'; source_case_id: string; action_label: string
  subject_label: string | null; resource_owner_label: string | null; resource_id: string; effect_labels: string[]
  before_verdict: 'SAFE' | 'VULNERABLE' | 'INCONCLUSIVE'; before_evidence_refs: string[]
  after_run_id?: string | null; after_case_id?: string | null; after_verdict?: 'SAFE' | 'VULNERABLE' | 'INCONCLUSIVE' | null
  after_evidence_refs?: string[]; match_status: 'NOT_AVAILABLE' | 'MATCHED' | 'NOT_FOUND' | 'AMBIGUOUS'
}
export type RepairVerification = { repair_reference: string; source_run_id: string; run_id: string; status: 'VERIFIED' | 'NOT_VERIFIED' | 'INCONCLUSIVE' | 'STALE'; reason_codes: string[] }
export type ProjectRepair = { project_id: string; status: RepairStatus | null; primary_task_reference: string | null; tasks: Array<{ task_reference: string; contract: RepairContract; status: RepairStatus; change_id: string | null; run_id: string | null; verification: RepairVerification | null; comparison?: RepairComparisonRow[] }> }
export const repairLabels: Record<RepairStatus, string> = { REPAIR_REQUIRED: '需要修复', CHANGE_SUBMITTED: '修改已登记，准备待完成', READY_TO_VERIFY: '可以复验原题', VERIFIED: '原题复验通过', NOT_VERIFIED: '原问题仍然存在', INCONCLUSIVE: '尚不能确认修复', STALE: '权限已变化，原题已失效' }
export const repairReference = (contract: RepairContract): RepairReference => ({ source_run_id: contract.source_run_id, source_case_id: contract.source_case_id, repair_fingerprint: contract.repair_fingerprint })
export const repairsApi = {
  project: (id: string) => request<ProjectRepair>(`/api/projects/${encodeURIComponent(id)}/repair`),
  contracts: (id: string) => request<RepairContract[]>(`/api/runs/${encodeURIComponent(id)}/repair-contracts`),
}
