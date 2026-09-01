/* 官方 Sample 体验 API：只交换非秘密状态与明确用户动作，不携带源码路径或预期结论。 */

import { request } from './http'

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
  start: () =>
    request<OfficialExperienceDto>('/api/experience/official-sample/start', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', consent: true }),
    }),
  prepare: () =>
    request<OfficialExperienceDto>('/api/experience/official-sample/prepare', { method: 'POST' }),
  switchVersion: (version: OfficialScenarioVersion, sourceRunId?: string) =>
    request<OfficialExperienceDto>('/api/experience/official-sample/version', {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        version,
        source_run_id: sourceRunId ?? null,
      }),
    }),
  stop: () => request<OfficialExperienceDto>('/api/experience/official-sample/stop', { method: 'POST' }),
}
