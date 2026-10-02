// 证明准备API只交换有限配置、报告和回执；目标读取由后端独立预检查Job执行。
import { request } from './http'
import type { PreparationGuidance } from './preparationGuidance'
export type ProofConfig = {
  action_id: string; action_revision: number; effect_id: string; observation_identity_id: string
  resource_binding_id: string; read_scope_id: string | null; relative_path_template: string
  mappings: Record<string, string[]>; target_operation_path: string[]; source_contract_id: string
  identity_claims: Array<{identity_id: string; application_subject_id: string; request_path?: string; subject_path?: string[]; role_path?: string[]; application_role?: string}>; source_files: string[]
  collection?: string; protected_projection?: string[]
  max_response_bytes: number; timeout_us: number; source_kind: 'JSON_HTTP_RESOURCE' | 'MANAGED_TRANSACTION_RECORDS'
}
export type ProofReport = { assessment: 'USABLE' | 'NEEDS_CHANGES' | 'UNSUPPORTED'; checks: Array<{code: string; status: 'CONFIRMED' | 'MISSING' | 'UNAVAILABLE' | 'UNSUPPORTED'; mapping_key: string | null}> }
export type ProofSource = { source_id: string; revision: number; config: ProofConfig; submitted_via: string; client_name: string; adopted: boolean
  read_scope_confirmed?: boolean; matching_read_scope_id?: string | null
  preflight: null | {preflight_id: string; state: string; current_basis: boolean; report: ProofReport | null} }
export type ProofContext = { project_id: string; basis_id: string; runtime_available: boolean; runtime_origin: string | null
  guidance?: PreparationGuidance
  actions: Array<{action_id: string; revision: number; label: string; effects: Array<{effect_id: string; label: string; kind: string}>}>
  identities: Array<{identity_id: string; label: string; actor_id: string; prepared: boolean}>
  resources: Array<{resource_binding_id: string; action_id: string; action_revision: number; resource_id: string; owner_identity_id: string}>
  sources: ProofSource[]; read_scopes: Array<{scope_id: string; origin: string; identity_ids: string[]; resource_binding_ids: string[]; path_templates: string[]; max_response_bytes: number; timeout_us: number}>
}
export type ProofReceipt = { project_id: string; operation_id: string; operation_kind: string; result: {source_id?: string; state: string; preflight_id?: string} }
export type AdoptionPreview = {project_id: string; basis_id: string; source_id: string; revision: number; preflight_id: string; action_label: string; effect_label: string; replaces_existing: boolean; resource_id: string; retained: string[]; recheck: string[]; collection?: string; mappings?: Record<string,string>; expected_state?: string | null; protected_projection?: string[]}
export type ProofOperationKind = 'SAVE_SOURCE' | 'GRANT_SCOPE' | 'START_PREFLIGHT' | 'CANCEL_PREFLIGHT' | 'ADOPT_SOURCE' | 'REVOKE_SCOPE'
const paths: Record<ProofOperationKind, string> = {SAVE_SOURCE: '/sources', GRANT_SCOPE: '/read-scopes', START_PREFLIGHT: '/preflights', CANCEL_PREFLIGHT: '/preflights/cancel', ADOPT_SOURCE: '/adoptions', REVOKE_SCOPE: '/read-scopes/revoke'}
const prefix = (project: string) => `/api/projects/${encodeURIComponent(project)}/proof-preparation`
export const proofSourcesApi = {
  context: (project: string) => request<ProofContext>(prefix(project)),
  write: (project: string, kind: ProofOperationKind, body: object) => request<ProofReceipt>(prefix(project) + paths[kind], {method: 'POST', body: JSON.stringify(body)}),
  receipt: (project: string, kind: ProofOperationKind, operation: string) => request<ProofReceipt>(`${prefix(project)}/receipts/${kind}/${operation}`),
  adoptionPreview: (project: string, source: string, preflight: string) => request<AdoptionPreview>(`${prefix(project)}/sources/${encodeURIComponent(source)}/adoption-preview?preflight_id=${encodeURIComponent(preflight)}`),
}
