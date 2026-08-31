/* 官方 Sample 体验 API：只交换非秘密状态与明确用户动作，不携带源码路径或预期结论。 */

import { request } from './http'

export type OfficialExperienceMode = 'GUIDED' | 'FULL'

export type OfficialExperienceDto = {
  available: boolean
  display_name: string
  unavailable_reason: string | null
  active: boolean
  experience_id: string | null
  experience_mode: OfficialExperienceMode | null
  project_id: string | null
  origin: string | null
  identities_ready: boolean
  authorization_order: 'ENQUEUE_BEFORE_AUTHORIZE' | 'AUTHORIZE_BEFORE_ENQUEUE' | null
  blob_observation: 'AVAILABLE' | 'UNAVAILABLE' | null
  repair_change_id: string | null
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
  start: (experienceMode: OfficialExperienceMode) =>
    request<OfficialExperienceDto>('/api/experience/official-sample/start', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', experience_mode: experienceMode, consent: true }),
    }),
  prepareIdentities: () =>
    request<OfficialExperienceDto>('/api/experience/official-sample/identities', { method: 'POST' }),
  useUnavailableObservation: (authorizationOrder: 'ENQUEUE_BEFORE_AUTHORIZE' | 'AUTHORIZE_BEFORE_ENQUEUE') =>
    request<OfficialExperienceDto>('/api/experience/official-sample/behavior', {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        authorization_order: authorizationOrder,
        blob_observation: 'UNAVAILABLE',
        verification_run_id: null,
      }),
    }),
  stop: () => request<OfficialExperienceDto>('/api/experience/official-sample/stop', { method: 'POST' }),
}
