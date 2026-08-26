/* =============================================================================
 * 测试账号 API Client
 *
 * 定位
 *   普通测试账号页面与本地身份准备控制面之间的前端适配器
 *
 * 职责
 *   管理账号元数据｜启动和确认独立登录浏览器｜轮询非秘密准备状态
 *
 * 边界
 *   不接收或展示密码、Cookie、Token 与 secret_ref
 * ============================================================================= */

import { request } from './http'

export type TestIdentityStatus = 'NOT_PREPARED' | 'PREPARED' | 'NEEDS_REVIEW'
export type TestIdentityAuthMethod = 'COOKIE_SESSION' | 'BEARER'

export type TestIdentityDto = {
  identity_id: string
  project_id: string
  role_candidate_id: string
  role_canonical_key: string
  role_display_name: string
  label: string
  confirmed_endpoint: string
  auth_method: TestIdentityAuthMethod | null
  status: TestIdentityStatus
  review_reasons: string[]
  cookie_count: number
  prepared_at_us: number | null
  refreshed_at_us: number | null
  created_at_us: number
  updated_at_us: number
}

export type IdentityPreparationStatus =
  | 'STARTING'
  | 'WAITING_FOR_LOGIN'
  | 'SAVING'
  | 'CANCELLING'
  | 'PREPARED'
  | 'UNSUPPORTED'
  | 'CANCELLED'
  | 'FAILED'

export type IdentityPreparationDto = {
  preparation_id: string
  identity_id: string
  status: IdentityPreparationStatus
  message: string
  error_code: string | null
  log_path: string
}

const command = { schema_version: '1' as const }

export const testIdentitiesApi = {
  list: (projectId: string) => request<TestIdentityDto[]>(`/api/projects/${projectId}/test-identities`),
  create: (projectId: string, roleCandidateId: string, label: string) =>
    request<TestIdentityDto>(`/api/projects/${projectId}/test-identities`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', role_candidate_id: roleCandidateId, label }),
    }),
  reset: (identityId: string) => request<TestIdentityDto>(`/api/test-identities/${identityId}/reset`, {
    method: 'POST', body: JSON.stringify(command),
  }),
  delete: (identityId: string) => request<{ deleted: true; identity_id: string }>(`/api/test-identities/${identityId}`, { method: 'DELETE' }),
  startPreparation: (identityId: string) => request<IdentityPreparationDto>(`/api/test-identities/${identityId}/preparations`, {
    method: 'POST', body: JSON.stringify(command),
  }),
  preparation: (preparationId: string) => request<IdentityPreparationDto>(`/api/identity-preparations/${preparationId}`),
  confirmPreparation: (preparationId: string) => request<IdentityPreparationDto>(`/api/identity-preparations/${preparationId}/confirm`, {
    method: 'POST', body: JSON.stringify(command),
  }),
  cancelPreparation: (preparationId: string) => request<IdentityPreparationDto>(`/api/identity-preparations/${preparationId}/cancel`, {
    method: 'POST', body: JSON.stringify(command),
  }),
}
