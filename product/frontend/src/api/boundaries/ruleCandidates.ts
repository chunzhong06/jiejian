// 对话候选API只提交或审阅建议；正式批准继续复用businessBoundariesApi。
import { request } from '../http'
import type { ProposedActorDto, ProposedActionDto, ProposedPermissionDto } from './businessBoundaries'

export type RuleScenario = {
  scenario_id: string; scenario_fingerprint: string; original_excerpt: string; question: string
  options: Array<{option_id: string; label: string; explanation: string; replacements: ProposedPermissionDto[]}>
}
export type MeaningChoice = {scenario_id: string; scenario_fingerprint: string; action: 'SELECT'|'CORRECT'|'DEFER'|'DISMISS'; option_id?: string; correction?: string}
export type ScenarioDecision = {scenario_id: string; status: MeaningChoice['action']|'NEEDS_DECISION'; decision: null|{decision_id: string; option_id: string|null; correction: string|null}}
export type BoundaryChoice = {issue_id: string; issue_fingerprint: string; outcome: 'NOT_SEPARATE_ACTION'|'AGENT_OVERINTERPRETATION'|'REPRESENTED_BY_RULES'|'BUSINESS_RULE'|'PREPARATION_DEPENDENCY'|'EVIDENCE_GAP'|'COVERAGE_GAP'|'DEFER'; reason: string; retained_requirement: string; permission_item_ids?: string[]}
export type BoundaryReview = {issue_id: string; issue_fingerprint: string; source: 'unresolved_questions'|'unsupported_constraints'; text: string; status: 'NEEDS_DECISION'|'STALE'|'OPEN'|'RESOLVED'; blocking: boolean; decision: (BoundaryChoice & {output_revision:number})|null}
export type BoundaryReviewGap = {candidate_id:string; revision:number; issue_id:string; message:string; status:string; review_url:string}

export type RuleCandidateView = {
  visibility?: {archived: boolean; version: number}
  candidate: {
    candidate_id: string; project_id: string; revision: number; basis_id: string
    submitted_via: 'MCP' | 'LOCAL_GUI'; created_at_us: number
    content: { original_text: string; actors: ProposedActorDto[]; actions: ProposedActionDto[]
      permissions: ProposedPermissionDto[]; examples: Array<{description: string; permission_item_id: string | null; uncovered_reason: string | null}>
      unresolved_questions: string[]; unsupported_constraints: string[]; scenarios?: RuleScenario[] }
  }
  assessment: 'REVIEWABLE' | 'NEEDS_CHANGES' | 'DECIDED' | 'ALREADY_CONFIRMED'
  issues: Array<{code: string; message: string; scenario_id?: string; path?: string; permission_item_ids?: string[]}>
  revision_guidance?: string[]
  scenario_decisions?: ScenarioDecision[]
  boundary_reviews?: BoundaryReview[]
  meaning_context?: {actors:Array<{item_id:string;display_name:string}>;actions:Array<{item_id:string;display_name:string;effect_catalog:Array<{item_id:string;business_label:string}>}>}
  approval_mappings?: Array<{permission_item_id: string; intent_id: string; revision: number; scenario_decision_ids: string[]}>
  proposal_id: string | null
  decision: {decision: 'APPROVED' | 'REJECTED'; reason: string} | null
  reuse: {status: string; message: string; actions?: Array<{item_id: string; display_name: string; status: string; materials: string[]; message: string}>}
  review_url: string
}
export type RuleCandidateContext = {
  project_id: string; basis_id: string
  source_summary?: {roles: number; actions: number; pending: number; analyzed: boolean} | null
  formal_permission_count?: number
  boundary_review_gaps?: BoundaryReviewGap[]
  candidates: Array<{candidate_id: string; revision: number; original_text: string; submitted_via: string; created_at_us: number
    assessment?: RuleCandidateView['assessment']; counts?: {actors: number; actions: number; permissions: number; examples: number}
    issue_count?: number; proposal_id?: string | null; decision?: 'APPROVED' | 'REJECTED' | null
    visibility?: {archived: boolean; version: number}}>
  next_offset: number | null
}
const prefix = (project: string) => `/api/projects/${encodeURIComponent(project)}/business-boundaries`
export const ruleCandidatesApi = {
  context: (project: string, offset = 0, archived = false) => request<RuleCandidateContext>(`${prefix(project)}/rule-context?offset=${offset}&archived=${archived}&include_preparation=false`),
  visibility: (project: string, candidate: string, revision: number, expected_version: number, archived: boolean) => request<{archived: boolean; version: number}>(`${prefix(project)}/rule-candidates/${encodeURIComponent(candidate)}/visibility`, {method:'PUT', body:JSON.stringify({revision,expected_version,archived})}),
  show: (project: string, candidate: string, revision?: number) => request<RuleCandidateView>(`${prefix(project)}/rule-candidates/${encodeURIComponent(candidate)}${revision ? `?revision=${revision}` : ''}`),
  propose: (project: string, candidate: string, revision: number, operation: string) => request<RuleCandidateView>(`${prefix(project)}/rule-candidates/${encodeURIComponent(candidate)}/proposals`, {method: 'POST', body: JSON.stringify({revision, operation_id: operation})}),
  decide: (project: string, candidate: string, revision: number, basis: string, operation: string, choice: MeaningChoice) => request<RuleCandidateView>(`${prefix(project)}/rule-candidates/${encodeURIComponent(candidate)}/decisions`, {method:'POST', body:JSON.stringify({...choice, expected_revision:revision, expected_basis_id:basis, operation_id:operation})}),
  reviewBoundary: (project: string, candidate: string, revision: number, basis: string, operation: string, choice: BoundaryChoice) => request<RuleCandidateView>(`${prefix(project)}/rule-candidates/${encodeURIComponent(candidate)}/boundary-decisions`, {method:'POST', body:JSON.stringify({...choice, expected_revision:revision, expected_basis_id:basis, operation_id:operation})}),
  receipt: (project: string, operation: string, kind: 'PROPOSE'|'DECIDE' = 'PROPOSE') => request<{status: 'FOUND' | 'UNKNOWN'; candidate?: RuleCandidateView}>(`${prefix(project)}/rule-operations/${kind}/${operation}`),
}
