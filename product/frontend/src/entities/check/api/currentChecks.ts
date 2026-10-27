// 当前权限实验与只读结果合同；浏览器只提交计划指纹，不创建考题或计算安全结论。
import { ApiError, request } from '../../../shared/api/http'
import type { RepairContract, RepairVerification, RepairComparisonRow } from './repairs'
import type { BoundaryReviewGap } from '../../permission/api/ruleCandidates'

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
  boundary_review_gaps?: BoundaryReviewGap[]
  requirement_scope?: RequirementScope[]
  actions: Array<{ action_id: string; action_revision: number; cases: Array<{ case_id: string }> }>
}
export type RequirementScope={candidate_id:string;revision:number;requirements:Array<{requirement_id:string;requirement:string;disposition:'IN_SCOPE'|'PREPARATION'|'OUT_OF_SCOPE';time_scope:'CHECK_WINDOW'|'HISTORY'|'NOT_APPLICABLE';permissions:Array<{intent_id:string;revision:number;intent_hash:string}>}>}
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
  reading?: ObservationReading | null
}
export type ObservationReading = {
  kind: 'REFERENCE' | 'PROCESS' | 'OBSERVED' | 'WAITING' | 'UNSUPPORTED' | 'UNAVAILABLE' | 'INCOMPLETE' | 'NOT_COLLECTED'
  label: string; detail: string; attention: boolean
}
export type StoryIdentity = { identity_id: string | null; label: string | null; actor_id: string | null; actor_label: string | null; verification_status: 'PLANNED' | 'MATCH' | 'MISMATCH' | 'UNKNOWN'; namespace: string | null; application_subject_id: string | null }
export type CheckOutcome = { execution_outcome: string; http_status: number | null; actual_identity_status: 'MATCH' | 'MISMATCH' | 'UNKNOWN'; baseline_trusted: boolean; recovery_verified: boolean; run_correlated: boolean; resource_correlated: boolean }
export type CheckBreakpoint = {
  breakpoint_type: 'AUTHORIZATION_MISSING' | 'AUTHORIZATION_LATE' | 'AUTHORIZATION_BYPASS' | 'IDENTITY_SUBSTITUTION' | 'AUTHORITY_EXPANSION' | 'COMPENSATION_MASKING' | null
  precision: 'EXACT' | 'RANGE' | 'VIOLATION_ONLY'; first_violation_event_id: string | null
  range_start_event_id: string | null; range_end_event_id: string | null; evidence_refs: string[]
  reason_codes?: string[]
}
export type StoryTraceEvent = {
  semantic_key?: string | null
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
  permission: { intent_id?: string; revision?: number; intent_hash?: string; expectation: 'ALLOW' | 'DENY'; relation: string }
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
export type ResultStory = { run_id: string; project_id: string; verdict: CheckVerdict; judgement: string; policy_epoch: number; actions: ActionResultStory[]; claim_boundary: string[]; technical_references: string[]; change_context?: { change_id: string } | null; repair_verification?: RepairVerification | null; repair_comparison?: RepairComparisonRow[]; runtime_status?: 'MATCHED' | 'UNCONFIRMED' | 'UNSUPPORTED'; runtime_instance_id?: string | null;requirement_scope?:RequirementScope[] }
export type CheckEvidence = {
  schema_version: '1' | '2' | '3'; evidence_id: string; run_id: string; action_id: string; case: { case_id: string; resource_id: string }
  outcome: CheckOutcome; observations: CheckObservation[]
  trace: { complete: boolean; events: Array<{ event_id: string; parent_event_ids: string[]; kind: string; source_component: string; source_location: string }> } | null
}
export type EvidenceRecordLink = {record_id:string;kind:'FACT'|'OUTCOME'|'OBSERVATION'|'TRACE';label:string;proof_fingerprint:string|null;observer_id:string|null;phase:string|null;event_id:string|null}
export type EvidenceRecordIndex = {project_id:string;run_id:string;case_id:string;action_id:string;evidence_id:string;records:EvidenceRecordLink[]}
export type EvidenceRecordView = Omit<EvidenceRecordIndex,'records'> & {record:EvidenceRecordLink;summary:string;published_judgement:string;role:'PROOF'|'SUPPORTING';
  verification:Array<{key:string;title:string;status:'CONFIRMED'|'LIMITED'|'UNKNOWN';text:string;record_refs:string[];source:Record<string,string>;fragment:Record<string,unknown>}>;
  values:Array<{label:string;before?:unknown;after?:unknown;before_label?:string;after_label?:string;value?:unknown}>;location:Record<string,string>;fragment:Record<string,unknown>;related_records:EvidenceRecordLink[];limitations:string[]}
const projectPath = (id: string) => `/api/projects/${encodeURIComponent(id)}`
const runPath = (id: string) => `/api/runs/${encodeURIComponent(id)}`
export type CheckHistoryCursor = { created_at_us: number; run_id: string }
export type RuleHistoryReference={intent_id:string;revision:number;intent_hash:string}
export type HistoryCoverage={project_id:string;checkpoint:number;generation:number;processed:number;failed:number;missing:number;status:'COMPLETE'|'INCOMPLETE'|'IN_PROGRESS'|'NEEDS_SCAN'}
export type RuleHistoryItem=RuleHistoryReference & {expectation:'ALLOW'|'DENY';effective_state:string;relation:string;action_label:string;subject_label:string;owner_label:string;latest_run_id:string|null;case_results:Array<{case_id:string;verdict:'SAFE'|'VULNERABLE'|'INCONCLUSIVE'}>;result_integrity:string;index_matches:boolean}
export type RuleHistoryPage={project_id:string;items:RuleHistoryItem[];next_cursor:string|null;coverage:HistoryCoverage}
export type HistoryMaintenanceReceipt={project_id:string;operation_id:string;checkpoint:number;processed:number;failed:number;complete:boolean}
export type CheckHistoryItem = { status: CheckStatus; action_labels: string[]; change_id: string | null; source_run_id: string | null;matching_cases?:string[];matching_verdicts?:string[] }
export type CheckHistoryPage = { project_id: string; items: CheckHistoryItem[]; next_cursor: CheckHistoryCursor | null }
export type CheckHistoryQuery = { query?: string; verdict?: CheckVerdict; lifecycle?: CheckStatus['run']['lifecycle']; cursor?: CheckHistoryCursor | null;rule?:RuleHistoryReference }
const statusReads = new Map<string, Promise<CheckStatus>>()
function readStatus(id: string, signal?:AbortSignal) {
  if(signal)return request<CheckStatus>(runPath(id),{signal})
  const existing = statusReads.get(id)
  if (existing) return existing
  const pending = request<CheckStatus>(runPath(id)).finally(() => { if (statusReads.get(id) === pending) statusReads.delete(id) })
  statusReads.set(id, pending)
  return pending
}
export const currentChecksApi = {
  history: (id: string, options: CheckHistoryQuery = {}, signal?:AbortSignal) => {
    const query = new URLSearchParams({ limit: '25' })
    if (options.query?.trim()) query.set('query', options.query.trim())
    if (options.verdict) query.set('verdict', options.verdict)
    if (options.lifecycle) query.set('lifecycle', options.lifecycle)
    if (options.cursor) { query.set('before_created_at_us', String(options.cursor.created_at_us)); query.set('before_run_id', options.cursor.run_id) }
    if(options.rule){query.set('intent_id',options.rule.intent_id);query.set('revision',String(options.rule.revision));query.set('intent_hash',options.rule.intent_hash)}
    return request<CheckHistoryPage>(`${projectPath(id)}/check-history?${query}`,{signal})
  },
  historyRules:(projectId:string,after?:string|null,archived=false)=>request<RuleHistoryPage>(`${projectPath(projectId)}/check-history/rules?${new URLSearchParams({limit:'25',include_archived:String(archived),...(after?{after}:{})})}`),
  historyCoverage:(projectId:string)=>request<HistoryCoverage>(`${projectPath(projectId)}/check-history/index-status`),
  maintainHistory:(projectId:string,body:{operation_id:string;expected_checkpoint:number;limit:number})=>request<HistoryMaintenanceReceipt>(`${projectPath(projectId)}/check-history/index-maintenance`,{method:'POST',body:JSON.stringify(body)}),
  historyReceipt:(projectId:string,operationId:string)=>request<{status:'FOUND'|'NOT_FOUND';receipt?:HistoryMaintenanceReceipt}>(`${projectPath(projectId)}/check-history/index-maintenance/${encodeURIComponent(operationId)}`),
  preview: (id: string, changeId?: string | null) => request<CheckPreview>(`${projectPath(id)}/check-preview${changeId ? `?change_id=${encodeURIComponent(changeId)}` : ''}`),
  list: (id: string, activeOnly = false) => request<CheckStatus[]>(`${projectPath(id)}/runs${activeOnly ? '?active_only=true' : ''}`),
  submit: (id: string, fingerprint: string, key: string, changeId?: string | null) => request<Pick<CheckStatus, 'run' | 'job'>>(`${projectPath(id)}/runs`, {
    method: 'POST', body: JSON.stringify({ schema_version: '2', expected_plan_fingerprint: fingerprint, idempotency_key: key, ...(changeId ? { change_id: changeId } : {}) }),
  }),
  cancel: (jobId: string) => request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' }),
  status: readStatus,
  story: (id: string, signal?:AbortSignal) => request<ResultStory>(`${runPath(id)}/result-story`,{signal}),
  evidenceBundle:(projectId:string,runId:string,caseId:string,ids:string[])=>{
    const query=new URLSearchParams({project_id:projectId,case_id:caseId});ids.forEach(id=>query.append('evidence_id',id))
    return request<{project_id:string;run_id:string;case_id:string;items:Array<{document:CheckEvidence;index:EvidenceRecordIndex}>}>(`${runPath(runId)}/evidence-bundle?${query}`)
  },
  evidence: async (runId: string, evidenceId: string) => {
    const value = await request<CheckEvidence>(`${runPath(runId)}/evidence/${encodeURIComponent(evidenceId)}`)
    if (!['1','2'].includes(value.schema_version) || value.run_id !== runId || value.evidence_id !== evidenceId) throw new ApiError('ARTIFACT_MANIFEST', '证据版本或所属检查不一致。')
    return value
  },
  evidenceRecords:(projectId:string,runId:string,evidenceId:string,caseId:string)=>request<EvidenceRecordIndex>(`${runPath(runId)}/evidence/${encodeURIComponent(evidenceId)}/records?${new URLSearchParams({project_id:projectId,case_id:caseId})}`),
  evidenceRecord:(projectId:string,runId:string,evidenceId:string,caseId:string,recordId:string)=>request<EvidenceRecordView>(`${runPath(runId)}/evidence/${encodeURIComponent(evidenceId)}/records/${encodeURIComponent(recordId)}?${new URLSearchParams({project_id:projectId,case_id:caseId})}`),
}
