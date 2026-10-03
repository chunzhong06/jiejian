// 对话候选API只提交或审阅建议；正式批准继续复用businessBoundariesApi。
import { request } from '../http'
import type { ProposedActorDto, ProposedActionDto, ProposedPermissionDto } from './businessBoundaries'

export type RuleCandidateView = {
  candidate: {
    candidate_id: string; project_id: string; revision: number; basis_id: string
    submitted_via: 'MCP' | 'LOCAL_GUI'; created_at_us: number
    content: { original_text: string; actors: ProposedActorDto[]; actions: ProposedActionDto[]
      permissions: ProposedPermissionDto[]; examples: Array<{description: string; permission_item_id: string | null; uncovered_reason: string | null}>
      unresolved_questions: string[]; unsupported_constraints: string[] }
  }
  assessment: 'REVIEWABLE' | 'NEEDS_CHANGES' | 'DECIDED' | 'ALREADY_CONFIRMED'
  issues: Array<{code: string; message: string}>
  proposal_id: string | null
  decision: {decision: 'APPROVED' | 'REJECTED'; reason: string} | null
  reuse: {status: string; message: string; actions?: Array<{item_id: string; display_name: string; status: string; materials: string[]; message: string}>}
  review_url: string
}
export type RuleCandidateContext = {
  candidates: Array<{candidate_id: string; revision: number; original_text: string; submitted_via: string; created_at_us: number}>
  next_offset: number | null
}
const prefix = (project: string) => `/api/projects/${encodeURIComponent(project)}/business-boundaries`
export const ruleCandidatesApi = {
  context: (project: string, offset = 0) => request<RuleCandidateContext>(`${prefix(project)}/rule-context?offset=${offset}`),
  show: (project: string, candidate: string, revision?: number) => request<RuleCandidateView>(`${prefix(project)}/rule-candidates/${encodeURIComponent(candidate)}${revision ? `?revision=${revision}` : ''}`),
  propose: (project: string, candidate: string, revision: number, operation: string) => request<RuleCandidateView>(`${prefix(project)}/rule-candidates/${encodeURIComponent(candidate)}/proposals`, {method: 'POST', body: JSON.stringify({revision, operation_id: operation})}),
  receipt: (project: string, operation: string) => request<{status: 'FOUND' | 'UNKNOWN'; candidate?: RuleCandidateView}>(`${prefix(project)}/rule-operations/PROPOSE/${operation}`),
}
