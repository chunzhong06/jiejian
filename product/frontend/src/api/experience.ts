/* 官方 Sample 体验 API：只交换非秘密状态与明确用户动作，不携带源码路径或预期结论。 */

import { request } from './http'
import type { RepairReference } from './repairs'
import type { BoundaryProposalViewDto } from './businessBoundaries'

export type OfficialScenarioVersion = 'VULNERABLE' | 'EVIDENCE_LIMITED' | 'FIXED'

export type OfficialExperienceDto = {
  available: boolean
  display_name: string
  unavailable_reason: string | null
  active: boolean
  experience_id: string | null
  project_id: string | null
  origin: string | null
  scenario_prepared: boolean
  scenario_version: OfficialScenarioVersion | null
  scenario_changed_at_us?: number | null
  vulnerable_change_id: string | null
  repair_change_id: string | null
  pending_tasks?: string[]
  lifecycle?: 'NOT_STARTED' | 'STARTING' | 'RUNNING' | 'STOPPING' | 'STOPPED' | 'FAILED' | 'UNKNOWN'
  history_project_id?: string | null
  last_error_code?: string | null
  operation_id?: string | null
  operation_state?: 'PENDING' | 'SUCCEEDED' | 'FAILED' | 'UNKNOWN' | null
}

export type CompetitionValidationSummaryDto = {
  schema_version: '1'
  generated_at_us: number
  suite: 'validation' | 'competition'
  status: 'accepted'
  repetitions: 1 | 3
  case_count: number
  case_run_count: number
  application_count: number
  mode_count: number
  state_count: number
  full_exact_match_count: number
  full_wrong_pass_vulnerable: number
  full_wrong_pass_evidence_gap: number
  http_exact_match_count: number
  http_wrong_pass_vulnerable: number
  http_wrong_pass_evidence_gap: number
  http_wrong_pass_per_matrix: number
  source_revision: string | null
  source_dirty: boolean | null
}

export type CompetitionValidationSummaryViewDto = {
  available: boolean
  unavailable_reason: string | null
  summary: CompetitionValidationSummaryDto | null
}

export const experienceApi = {
  status: () => request<OfficialExperienceDto>('/api/experience/official-sample'),
  validationSummary: () => request<CompetitionValidationSummaryViewDto>('/api/experience/official-sample/validation-summary'),
  start: (operationId?: string) =>
    request<OfficialExperienceDto>('/api/experience/official-sample/start', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', consent: true, ...(operationId ? { operation_id: operationId } : {}) }),
    }),
  prepare: () =>
    request<OfficialExperienceDto>('/api/experience/official-sample/prepare', { method: 'POST' }),
  boundaryProposal: () => request<BoundaryProposalViewDto>('/api/experience/official-sample/boundary-proposal', { method: 'POST' }),
  switchVersion: (version: OfficialScenarioVersion, reference?: RepairReference) =>
    request<OfficialExperienceDto>('/api/experience/official-sample/version', {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        version,
        repair_reference: reference ?? null,
      }),
    }),
  stop: (operationId?: string) => request<OfficialExperienceDto>('/api/experience/official-sample/stop', { method: 'POST', ...(operationId ? { body: JSON.stringify({ operation_id: operationId }) } : {}) }),
  history: () => request<{items:Array<{operation_id:string;operation:string;state:string;project_id:string|null;experience_id:string|null;started_at_us:number;finished_at_us:number|null;error_code:string|null}>;has_more:boolean}>('/api/experience/official-sample/history'),
}
