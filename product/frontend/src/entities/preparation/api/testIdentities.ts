// 账号与登录准备的非秘密控制接口；密码和会话正文只经独立准备进程处理。
import { request } from '../../../shared/api/http'

export type TestIdentityStatus = 'NOT_PREPARED' | 'PREPARED' | 'NEEDS_REVIEW'
export type TestIdentityAuthMethod = 'COOKIE_SESSION' | 'BEARER'
export type AuthenticationProfile = {
  method:'BROWSER_SESSION'|'BEARER'|'API_LOGIN'; login_path:string; username_field:string; password_field:string; token_path:string[];
  verification:{path:string;subject_path:string[];role_path:string[];expected_subject:string;expected_role:string}
}
export type IdentityVerification = {status:'VERIFIED'|'AUTH_EXPIRED'|'SUBJECT_MISMATCH'|'ROLE_MISMATCH'|'FIELD_MISSING'|'UNAVAILABLE';checked_at_us:number;subject:string|null;role:string|null}
export type AuthenticationOptions = {identity_id:string;templates:Array<{identity_id:string;label:string;profile:Omit<AuthenticationProfile,'verification'>&{verification:Omit<AuthenticationProfile['verification'],'expected_subject'|'expected_role'>};expected_role:string|null}>}

export type TestIdentityDto = {
  identity_id: string
  project_id: string
  actor_id: string
  actor_revision: number
  actor_display_name: string
  label: string
  auth_method: TestIdentityAuthMethod | null
  status: TestIdentityStatus
  review_reasons: string[]
  cookie_count: number
  prepared_at_us: number | null
  refreshed_at_us: number | null
  created_at_us: number
  updated_at_us: number
  authentication:AuthenticationProfile|null
  verification:IdentityVerification|null
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
  project_id: string | null
  job_id: string | null
  cleanup_required: boolean
  purpose:'LOGIN'|'VERIFY'
}

const command = { schema_version: '1' as const }

export const testIdentitiesApi = {
  authenticationOptions:(identity:string,signal?:AbortSignal)=>request<AuthenticationOptions>(`/api/test-identities/${identity}/authentication-options`,{signal}),
  configureAuthentication:(identity:TestIdentityDto,profile:AuthenticationProfile)=>request<TestIdentityDto>(`/api/test-identities/${identity.identity_id}/authentication`,{method:'PUT',body:JSON.stringify({schema_version:'1',profile,expected_updated_at_us:identity.updated_at_us})}),
  cleanupPreparation: (id:string) => request<IdentityPreparationDto>(`/api/identity-preparations/${id}/cleanup`, {method:'POST',body:JSON.stringify(command)}),
  preparations: (projectId: string, signal?: AbortSignal) => request<IdentityPreparationDto[]>(`/api/projects/${projectId}/identity-preparations`, {signal}),
  requestedPreparation: (identity: string, operation: string) => request<IdentityPreparationDto | null>(`/api/test-identities/${identity}/preparation-requests/${operation}`),
  list: (projectId: string, signal?:AbortSignal) => request<TestIdentityDto[]>(`/api/projects/${projectId}/test-identities`,{signal}),
  create: (projectId: string, actorId: string, actorRevision: number, label: string, operationId?: string) =>
    request<TestIdentityDto>(`/api/projects/${projectId}/test-identities`, {
      method: 'POST',
      body: JSON.stringify({ schema_version: '1', actor_id: actorId, actor_revision: actorRevision, label, operation_id: operationId }),
    }),
  created: (projectId: string, operationId: string) => request<TestIdentityDto | null>(`/api/projects/${projectId}/test-identity-requests/${operationId}`),
  latestPreparation: (identityId: string) => request<IdentityPreparationDto | null>(`/api/test-identities/${identityId}/preparations/latest`),
  reset: (identityId: string) => request<TestIdentityDto>(`/api/test-identities/${identityId}/reset`, {
    method: 'POST', body: JSON.stringify(command),
  }),
  delete: (identityId: string) => request<{ deleted: true; identity_id: string }>(`/api/test-identities/${identityId}`, { method: 'DELETE' }),
  startPreparation: (identityId: string, operationId?: string,verifyOnly=false) => request<IdentityPreparationDto>(`/api/test-identities/${identityId}/preparations`, {
    method: 'POST', body: JSON.stringify({ ...command, operation_id: operationId,verify_only:verifyOnly }),
  }),
  preparation: (preparationId: string) => request<IdentityPreparationDto>(`/api/identity-preparations/${preparationId}`),
  confirmPreparation: (preparationId: string) => request<IdentityPreparationDto>(`/api/identity-preparations/${preparationId}/confirm`, {
    method: 'POST', body: JSON.stringify(command),
  }),
  cancelPreparation: (preparationId: string) => request<IdentityPreparationDto>(`/api/identity-preparations/${preparationId}/cancel`, {
    method: 'POST', body: JSON.stringify(command),
  }),
}
