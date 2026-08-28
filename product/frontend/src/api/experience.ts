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
}

export const experienceApi = {
  status: () => request<OfficialExperienceDto>('/api/experience/official-sample'),
  start: (experienceMode: OfficialExperienceMode) =>
    request<OfficialExperienceDto>('/api/experience/official-sample/start', {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', experience_mode: experienceMode, consent: true }),
    }),
  prepareIdentities: () =>
    request<OfficialExperienceDto>('/api/experience/official-sample/identities', { method: 'POST' }),
  verifyFixedBehavior: (runId: string) =>
    request<OfficialExperienceDto>('/api/experience/official-sample/behavior', {
      method: 'POST',
      body: JSON.stringify({
        schema_version: '1',
        authorization_order: 'AUTHORIZE_BEFORE_ENQUEUE',
        blob_observation: 'AVAILABLE',
        verification_run_id: runId,
      }),
    }),
  stop: () => request<OfficialExperienceDto>('/api/experience/official-sample/stop', { method: 'POST' }),
}
