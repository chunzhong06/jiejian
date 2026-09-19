// 当前权限实验与只读结果合同；浏览器只提交计划指纹，不创建考题或计算安全结论。
import { ApiError, request } from './http'
import type { RepairContract, RepairVerification, RepairComparisonRow } from './repairs'

export type CheckVerdict = 'PASS' | 'BLOCK' | 'INCONCLUSIVE'
export type CheckProgressCase = {
  case_id: string; action_label: string; expectation: 'ALLOW' | 'DENY'
  planned_subject_label: string; planned_resource_owner_label: string; resource_id: string; effect_labels: string[]
}
export type CheckStatus = {
  run: { run_id: string; project_id: string; lifecycle: string; verdict: CheckVerdict | null; plan_fingerprint: string; policy_epoch: number; created_at_us: number; finished_at_us: number | null }
  job: { job_id: string; state: string; attempt: number; cancel_requested: boolean } | null
  progress: { phase: 'PREPARING' | 'EXECUTING' | 'FINALIZING'; completed_cases: number; planned_cases: number; current_case?: CheckProgressCase | null } | null
  result_integrity: 'VALID' | 'INVALID' | 'NOT_PUBLISHED'
}
export type CheckPreview = {
  project_id: string; can_execute: boolean; plan_fingerprint: string; action_count: number; case_count: number
  gaps: Array<{ action_id: string; action_revision: number; reason: string }>
  actions: Array<{ action_id: string; action_revision: number; cases: Array<{ case_id: string }> }>
}
export type CheckObservation = {
  effect_id: string; proof_fingerprint: string; observer_id: string
  level: 'VERDICT_REQUIRED' | 'DIAGNOSIS_REQUIRED' | 'SUPPORTING'
  phase: 'BASELINE' | 'BEFORE' | 'AFTER' | 'EVENTUAL' | 'RECOVERY'
  state: 'CONFIRMED' | 'ABSENT' | 'UNKNOWN'; closure: 'CLOSED' | 'OPEN' | 'UNKNOWN'
  complete: boolean; reliable: boolean; correlated: boolean; authoritative: boolean
  window_start_us: number; window_end_us: number; correlation_refs: string[]; reason_codes: string[]
}
export type EvidenceExplanation = {
  source_label: string; source_location: string; observed_fact: CheckObservation
  supports_claim: string; does_not_prove: string; evidence_refs: string[]
}
export type StoryIdentity = { identity_id: string | null; label: string | null; actor_id: string | null; actor_label: string | null; verification_status: 'PLANNED' | 'MATCH' | 'MISMATCH' | 'UNKNOWN'; namespace: string | null; application_subject_id: string | null }
export type CheckOutcome = { execution_outcome: string; http_status: number | null; actual_identity_status: 'MATCH' | 'MISMATCH' | 'UNKNOWN'; baseline_trusted: boolean; recovery_verified: boolean; run_correlated: boolean; resource_correlated: boolean }
export type CheckBreakpoint = {
  breakpoint_type: 'AUTHORIZATION_MISSING' | 'AUTHORIZATION_LATE' | 'AUTHORIZATION_BYPASS' | 'IDENTITY_SUBSTITUTION' | 'AUTHORITY_EXPANSION' | 'COMPENSATION_MASKING' | null
  precision: 'EXACT' | 'RANGE' | 'VIOLATION_ONLY'; first_violation_event_id: string | null
  range_start_event_id: string | null; range_end_event_id: string | null; evidence_refs: string[]
}
export type StoryTraceEvent = {
  event_id: string; parent_event_ids: string[]
  kind: 'ENTRY' | 'IDENTITY' | 'AUTHORIZATION' | 'PERSISTENT_EFFECT' | 'MESSAGE' | 'DELEGATION' | 'FINAL_EFFECT' | 'RECOVERY'
  authorization_decision: 'ALLOW' | 'DENY' | null; effect_id: string | null; dispatch_effect_ids: string[]
  source_component: string; source_location: string
}
export type StoryExecutionPath = { complete: boolean; reason_codes: string[]; events: StoryTraceEvent[]; evidence_refs: string[] }
export type StoryProofCoverage = {
  effect_id: string; business_label: string; proof_fingerprint: string
  required_level: 'VERDICT_REQUIRED' | 'SUPPORTING'; source_label: string
  observed_state: 'CONFIRMED' | 'ABSENT' | 'UNKNOWN'
  evidence_refs: string[]; supporting_evidence_refs: string[]; limitations: string[]
}
export type ActionResultStory = {
  action_id: string; action_revision: number; display_name: string; case_id: string
  permission: { expectation: 'ALLOW' | 'DENY'; relation: string }
  judgement: string
  fact_comparison: {
    planned_identity: StoryIdentity; planned_resource_owner?: StoryIdentity | null; resource_id?: string | null; verified_actual_identity: StoryIdentity; http_surface: CheckOutcome; http_explanation: string
    effects: Array<{ effect_id: string; business_label: string; resource_concept: string; observed_state: 'CONFIRMED' | 'ABSENT' | 'UNKNOWN'; judgement: string; evidence_refs: string[] }>
    allow_control: { case_id: string; verdict: 'SAFE' | 'VULNERABLE' | 'INCONCLUSIVE'; evidence_refs: string[] } | null
  }
  breakpoint: CheckBreakpoint | null; decisive_proof_chain: EvidenceExplanation[]; evidence_explanations: EvidenceExplanation[]
  claim_boundary: string[]; repair_requirement: RepairContract | null; repair_comparison?: RepairComparisonRow[]; technical_references: string[]
  execution_path?: StoryExecutionPath | null
  proof_coverage?: StoryProofCoverage[]
}
export type ResultStory = { run_id: string; project_id: string; verdict: CheckVerdict; judgement: string; policy_epoch: number; actions: ActionResultStory[]; claim_boundary: string[]; technical_references: string[]; change_context?: { change_id: string } | null; repair_verification?: RepairVerification | null }
export type CheckEvidence = {
  schema_version: '1'; evidence_id: string; run_id: string; action_id: string; case: { case_id: string; resource_id: string }
  outcome: CheckOutcome; observations: CheckObservation[]
  trace: { complete: boolean; events: Array<{ event_id: string; parent_event_ids: string[]; kind: string; source_component: string; source_location: string }> } | null
}
const projectPath = (id: string) => `/api/projects/${encodeURIComponent(id)}`
const runPath = (id: string) => `/api/runs/${encodeURIComponent(id)}`
export type CheckHistoryCursor = { created_at_us: number; run_id: string }
export type CheckHistoryItem = { status: CheckStatus; action_labels: string[]; change_id: string | null; source_run_id: string | null }
export type CheckHistoryPage = { project_id: string; items: CheckHistoryItem[]; next_cursor: CheckHistoryCursor | null }
export type CheckHistoryQuery = { query?: string; verdict?: CheckVerdict; lifecycle?: CheckStatus['run']['lifecycle']; cursor?: CheckHistoryCursor | null }
export const currentChecksApi = {
  history: (id: string, options: CheckHistoryQuery = {}) => {
    const query = new URLSearchParams({ limit: '25' })
    if (options.query?.trim()) query.set('query', options.query.trim())
    if (options.verdict) query.set('verdict', options.verdict)
    if (options.lifecycle) query.set('lifecycle', options.lifecycle)
    if (options.cursor) { query.set('before_created_at_us', String(options.cursor.created_at_us)); query.set('before_run_id', options.cursor.run_id) }
    return request<CheckHistoryPage>(`${projectPath(id)}/check-history?${query}`)
  },
  preview: (id: string, changeId?: string | null) => request<CheckPreview>(`${projectPath(id)}/check-preview${changeId ? `?change_id=${encodeURIComponent(changeId)}` : ''}`),
  list: (id: string) => request<CheckStatus[]>(`${projectPath(id)}/runs`),
  submit: (id: string, fingerprint: string, key: string, changeId?: string | null) => request<Pick<CheckStatus, 'run' | 'job'>>(`${projectPath(id)}/runs`, {
    method: 'POST', body: JSON.stringify({ schema_version: '2', expected_plan_fingerprint: fingerprint, idempotency_key: key, ...(changeId ? { change_id: changeId } : {}) }),
  }),
  cancel: (jobId: string) => request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' }),
  status: (id: string) => request<CheckStatus>(runPath(id)),
  story: (id: string) => request<ResultStory>(`${runPath(id)}/result-story`),
  evidence: async (runId: string, evidenceId: string) => {
    const value = await request<CheckEvidence>(`${runPath(runId)}/evidence/${encodeURIComponent(evidenceId)}`)
    if (value.schema_version !== '1' || value.run_id !== runId || value.evidence_id !== evidenceId) throw new ApiError('ARTIFACT_MANIFEST', '证据版本或所属检查不一致。')
    return value
  },
}
