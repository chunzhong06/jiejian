import { request } from '../../../shared/api/http'
import type { ProjectRepair } from '../../check/api/repairs'
import type { RuleChangeTarget } from '../../source-change/api/sourceChanges'

export type RuleState = 'UNCONFIRMED' | 'UNTESTED' | 'STALE' | 'SAFE' | 'VULNERABLE' | 'INCONCLUSIVE' | 'REPAIR_PENDING'
export type RuleHistory = { run_id: string; created_at_us: number; case_ids: string[]; verdict: 'SAFE'|'VULNERABLE'|'INCONCLUSIVE'; case_count: number; current: boolean; change_id: string|null }
export type RuleItem = {
  permission: {intent_id: string; revision: number; intent_hash: string}
  title: string; expectation: 'ALLOW'|'DENY'; subject: string; action: string; resource_scope: string
  state: RuleState; latest: RuleHistory|null; issues: ProjectRepair['tasks']
  changes: Array<{change_id: string; reason: string; created_at_us: number; file_count: number; targets: RuleChangeTarget[]}>
  history: RuleHistory[]; history_has_more: boolean
}
export type RuleWorkspace = {schema_version: '1'; project_id: string; policy_epoch: number; rules: RuleItem[]; change_history_limited: boolean}
export const ruleWorkspaceApi = { read: (id: string) => request<RuleWorkspace>(`/api/projects/${encodeURIComponent(id)}/rule-workspace`) }
