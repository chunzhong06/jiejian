// 代码变化产品摘要 API；只接收授权源码根下的相对路径，不接收正文或内部指纹。

import { request } from './http'

export type SourceChangeViewDto = {
  change_id: string
  project_id: string
  reason: string
  created_at_us: number
  status: 'COMPARABLE' | 'NO_BASELINE'
  complete: boolean
  actual_changed_path_count: number
  added_count: number
  modified_count: number
  removed_count: number
  claimed_paths: string[]
  added_paths: string[]
  modified_paths: string[]
  removed_paths: string[]
  directly_affected_count: number
  mapping_review_required_count: number
  no_direct_evidence_count: number
  review_intent_ids: string[]
  summary: string
  next_path: '/check' | null
}

export const sourceChangesApi = {
  latest: (projectId: string) => request<SourceChangeViewDto | null>(`/api/projects/${encodeURIComponent(projectId)}/source-changes/latest`),
  show: (projectId: string, changeId: string) => request<SourceChangeViewDto>(`/api/projects/${encodeURIComponent(projectId)}/source-changes/${encodeURIComponent(changeId)}`),
}
