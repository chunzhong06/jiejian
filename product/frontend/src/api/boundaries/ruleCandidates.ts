// 对话候选API只提交或审阅建议；正式批准继续复用businessBoundariesApi。
import { request } from '../http'
import type { ProposedActorDto, ProposedActionDto, ProposedPermissionDto } from './businessBoundaries'

export type RuleScenario = {
  scenario_id: string; scenario_fingerprint: string; original_excerpt: string; question: string
  options: Array<{option_id: string; label: string; explanation: string; replacements: ProposedPermissionDto[]}>
}
export type MeaningChoice = {scenario_id: string; scenario_fingerprint: string; action: 'SELECT'|'CORRECT'|'DEFER'|'DISMISS'; option_id?: string; correction?: string}
export type ScenarioDecision = {scenario_id: string; status: MeaningChoice['action']|'NEEDS_DECISION'; decision: null|{decision_id: string; option_id: string|null; correction: string|null}}
export type ReviewDependencies = {requirement_ids:string[];permission_item_ids:string[]}
export type BoundaryChoice = {issue_id: string; issue_fingerprint: string; outcome: 'NOT_SEPARATE_ACTION'|'AGENT_OVERINTERPRETATION'|'REPRESENTED_BY_RULES'|'BUSINESS_RULE'|'PREPARATION_DEPENDENCY'|'EVIDENCE_GAP'|'COVERAGE_GAP'|'DEFER'; reason: string; retained_requirement: string; permission_item_ids?: string[];dependencies?:ReviewDependencies|null}
export type BoundaryReview = {issue_id: string; issue_fingerprint: string; source: 'unresolved_questions'|'unsupported_constraints'; text: string; status: 'NEEDS_DECISION'|'STALE'|'OPEN'|'RESOLVED'; blocking: boolean; decision: (BoundaryChoice & {output_revision:number})|null;suggestion?:BoundaryChoice|null;dependencies?:ReviewDependencies|null;invalidation_reason?:string|null}
export type BoundaryReviewGap = {candidate_id:string; revision:number; issue_id:string; message:string; status:string; review_url:string;next_url?:string|null;next_label?:string|null}
export type RequirementSource = {requirement_id:string;title:string;origin:'USER'|'SOURCE'|'AGENT';source_excerpt:string;interpretation:string;permission_item_ids:string[]}
export type ScopeChoice = {requirement_id:string;requirement_fingerprint:string;disposition:'IN_SCOPE'|'PREPARATION'|'OUT_OF_SCOPE'|'DEFER'|'SUPPORTING';requirement:string;reason:string;time_scope:'CHECK_WINDOW'|'HISTORY'|'NOT_APPLICABLE';related_requirement_ids?:string[]}
export type ScopeReview = {source:RequirementSource;fingerprint:string;status:'NEEDS_DECISION'|'STALE'|'DEFER'|'CONFIRMED';decision:(ScopeChoice&{output_revision:number})|null}
export type CoverageChoice = {issue_id:string;issue_fingerprint:string;review_revision:number;time_scope:'CHECK_WINDOW'|'HISTORY';reason:string;complete:boolean;targets:Array<{permission_item_id:string;method:'GET'|'POST'|'PUT'|'PATCH'|'DELETE'|'HEAD'|'OPTIONS';path:string;proof:'EFFECT'|'PROCESS_RECORD'}>}
export type CandidateTask = {code:string;message:string;handler:'USER'|'AGENT'|'CAPABILITY';stage:string;next_step:string;path?:string;permission_item_ids?:string[]}

export type RuleCandidateView = {
  scope_only?:boolean
  visibility?: {archived: boolean; version: number}
  candidate: {
    candidate_id: string; project_id: string; revision: number; basis_id: string
    submitted_via: 'MCP' | 'LOCAL_GUI'; created_at_us: number
    supporting_notes?:Array<{note_id:string;kind:'SOURCE_CLUE'|'TECHNICAL_PRECONDITION'|'CAPABILITY_INFORMATION';text:string;state:'ACTIVE'|'WITHDRAWN';withdrawal_reason?:string|null;related_requirement_ids:string[]}>
    content: { original_text: string; actors: ProposedActorDto[]; actions: ProposedActionDto[]
      permissions: ProposedPermissionDto[]; examples: Array<{description: string; permission_item_id: string | null; uncovered_reason: string | null}>
      unresolved_questions: string[]; unsupported_constraints: string[]; scenarios?: RuleScenario[];requirement_sources?:RequirementSource[];coverage_suggestions?:Array<{issue_id:string;targets:CoverageChoice['targets'];time_scope:CoverageChoice['time_scope'];explanation:string}> }
  }
  assessment: 'REVIEWABLE' | 'NEEDS_CHANGES' | 'DECIDED' | 'ALREADY_CONFIRMED'
  issues: Array<{code: string; message: string; scenario_id?: string; path?: string; permission_item_ids?: string[]}>
  revision_guidance?: string[]
  scenario_decisions?: ScenarioDecision[]
  boundary_reviews?: BoundaryReview[]
  scope_review?: ScopeReview[]
  coverage_review?: Array<{issue_id:string;status:'STALE'|'UNSUPPORTED_HISTORY'|'DRAFT'|'PLANNED';message:string;link:CoverageChoice}>
  next_tasks?: CandidateTask[]
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
  scope: (project:string,candidate:string,revision:number,basis:string,operation:string,choice:ScopeChoice) => request<RuleCandidateView>(`${prefix(project)}/rule-candidates/${encodeURIComponent(candidate)}/scope-decisions`,{method:'POST',body:JSON.stringify({...choice,expected_revision:revision,expected_basis_id:basis,operation_id:operation})}),
  scopeBatch: (project:string,candidate:string,revision:number,basis:string,operation:string,choices:ScopeChoice[]) => request<RuleCandidateView>(`${prefix(project)}/rule-candidates/${encodeURIComponent(candidate)}/scope-batch`,{method:'POST',body:JSON.stringify({choices,expected_revision:revision,expected_basis_id:basis,operation_id:operation})}),
  coverage: (project:string,candidate:string,revision:number,basis:string,operation:string,choice:CoverageChoice) => request<RuleCandidateView>(`${prefix(project)}/rule-candidates/${encodeURIComponent(candidate)}/coverage-links`,{method:'POST',body:JSON.stringify({...choice,expected_revision:revision,expected_basis_id:basis,operation_id:operation})}),
  receipt: (project: string, operation: string, kind: 'PROPOSE'|'DECIDE' = 'PROPOSE') => request<{status: 'FOUND' | 'UNKNOWN'; candidate?: RuleCandidateView}>(`${prefix(project)}/rule-operations/${kind}/${operation}`),
}
