// 证明准备API只交换有限配置、报告和回执；目标读取由后端独立预检查Job执行。
import { request } from '../../../shared/api/http'
import type { PreparationGuidance } from './preparationGuidance'
import type { PreparationSuggestionContext } from './preparationSuggestions'
import type {RelationshipRequirement,FieldMutationRequirement} from '../../permission/api/businessBoundaries'
import type {DatabaseCapture} from '../../application/api/projects'
export type RelationshipSourceMapping = {
  subject_groups_path?:string[]|null
  scope_complete_path:string[]|null;source_time_path:string[]|null
  application_action:string;subject_organizations_path:string[]|null;resource_organization_path:string[]|null
  organization_parents_path:string[]|null;subject_roles_path:string[]|null;role_inheritance_path:string[]|null;grants_path:string[]|null;clock_uncertainty_us:number
}
export type ProofConfig = {
  action_id: string; action_revision: number; effect_id: string; observation_identity_id: string
  resource_binding_id: string; read_scope_id: string | null; relative_path_template: string
  mappings: Record<string, string[]>; target_operation_path: string[]; source_contract_id: string
  identity_claims: Array<{identity_id: string; application_subject_id: string; request_path?: string; subject_path?: string[]; role_path?: string[]; tenant_path?: string[] | null; application_role?: string}>; source_files: string[]
  collection?: string; protected_projection?: string[]
  relationship_mapping?:RelationshipSourceMapping|null
  state_field_optional?:boolean
  max_response_bytes: number; timeout_us: number; source_kind: 'JSON_HTTP_RESOURCE' | 'MANAGED_TRANSACTION_RECORDS' | 'REFERENCE_FILE' | 'CREATED_OBJECT_RECORDS'|'SQLITE_AUDIT'|'SQLITE_OBJECTS'|'DATABASE_AUDIT'
  database_capture?:DatabaseCapture
  database_path?:string;table?:string;resource_column?:string;owner_column?:string;protected_column?:string;observed_columns?:string[]
  reference_artifact?: ArtifactManifest | null; reference_origin?: 'UPLOAD' | 'REFERENCE_CAPTURE' | null
  reference_resource_id?: string; reference_owner_identity_id?: string
  async_export?:AsyncExportMapping|null
}
export type AsyncExportMapping={dispatch_task_path:string[];status_path_template:string;file_path_template:string;task_path:string[];state_path:string[];resource_path:string[];owner_path:string[];subject_path:string[];request_nonce_path:string[];states:Record<string,'QUEUED'|'RUNNING'|'SUCCESS'|'FAILED'|'TIMED_OUT'|'CANCELLED'>;max_polls:number;poll_interval_us:number;timeout_us:number;max_response_bytes:number}
export type ArtifactManifest = {asset_id: string; size: number; sha256: string}
export type ReferenceInput = {asset_id: string; action_id: string; action_revision: number; resource_binding_id: string; resource_id: string; owner_identity_id: string
  origin: 'UPLOAD' | 'REFERENCE_CAPTURE'; reference_capture_id: string | null; state: 'PENDING' | 'COMPLETE' | 'INCOMPLETE' | 'CANCELLED'; manifest: ArtifactManifest | null; created_at_us: number}
export type CaptureSelection = {basis_id: string; action_id: string; action_revision: number; allow_intent_id: string; resource_binding_id: string; collection: string; identity_claims: ProofConfig['identity_claims']; restore_capture_id?: string}
export type CapturePlan = {schema_version: '1'; project_id: string; basis_id: string; plan_hash: string; created_at_us: number
  restore: null | {capture_id:string;resource_id:string;generation:string}
  case: {subject_test_identity_id: string; resource_owner_test_identity_id: string; resource_id: string; resource_binding_id: string}
  runtime: {source_fingerprint: string; target: {base_url: string; max_response_bytes: number}; actions: Array<{display_name: string; state_changing: boolean; recovery: unknown}>}}
export type CaptureStatus = {capture_id: string; action_id:string;resource_binding_id:string;asset_id: string | null; state: string; target_may_have_run: boolean; operation_may_have_run:boolean; plan_hash: string
  report: null | {state: 'CANDIDATE' | 'INCOMPLETE' | 'RECOVERED'; recovery_verified: boolean; reason_codes: string[]; manifest: ArtifactManifest | null}}
export type ProofReport = { assessment: 'USABLE' | 'NEEDS_CHANGES' | 'UNSUPPORTED'|'COMPLETED'; checks: Array<{code: string; status: 'CONFIRMED' | 'MISSING' | 'UNAVAILABLE' | 'UNSUPPORTED'; mapping_key: string | null}> }
export type ProofSource = { source_id: string; revision: number; config: ProofConfig; submitted_via: string; client_name: string; adopted: boolean; usable?: boolean
  database_installation?:{installed:boolean;state:'NOT_INSTALLED'|'INCOMPLETE'|'INSTALLED'|'REMOVING'|'REMOVED';generation:string|null}
  read_scope_confirmed?: boolean; matching_read_scope_id?: string | null
  preflight: null | {preflight_id: string; state: string; current_basis: boolean; report: ProofReport | null} }
export type ProofContext = { project_id: string; basis_id: string; runtime_available: boolean; runtime_origin: string | null
  databases?:DatabaseCapture[]
  sqlite?:Array<{database_path:string;table:string;resource_column:string;owner_column:string;fields:string[]}>
  guidance?: PreparationGuidance
  suggestion_context?: PreparationSuggestionContext
  actions: Array<{action_id: string; revision: number; label: string; execution_identity_id?: string | null; recovery_identity_id?: string | null; condition_requirements?: {tenant:boolean;resource_state:boolean;relationships?:RelationshipRequirement[]}; effects: Array<{effect_id: string; label: string; kind: string}>}>
  identities: Array<{identity_id: string; label: string; actor_id: string; prepared: boolean}>
  resources: Array<{resource_binding_id: string; binding_fingerprint?:string; case_specific?:boolean; action_id: string; action_revision: number; resource_id: string; owner_identity_id: string}>
  sources: ProofSource[]; read_scopes: Array<{scope_id: string; origin: string; identity_ids: string[]; resource_binding_ids: string[]; path_templates: string[]; max_response_bytes: number; timeout_us: number}>
  reference_inputs?: ReferenceInput[]
  reference_recovery_gaps?: Array<{capture_id:string;action_id:string;resource_id:string;owner_identity_id:string;reason:string}>
  allow_permissions?: Array<{intent_id: string; action_id: string; action_revision: number; subject_actor_id: string; owner_actor_id: string; relation: string}>
}
export type ProofReceipt = { project_id: string; operation_id: string; operation_kind: string; result: {source_id?: string; state: string; preflight_id?: string; asset_id?: string; capture_id?: string} }
export type AdoptionPreview = {project_id: string; basis_id: string; source_id: string; revision: number; preflight_id: string; action_label: string; effect_label: string; replaces_existing: boolean; resource_id: string; retained: string[]; recheck: string[]; collection: string; mappings: Record<string,string>; expected_state: string | null; protected_projection: string[]; field_mutation:FieldMutationRequirement|null; identity_claims:ProofConfig['identity_claims']; source_path:string; read_paths:string[]; gui_url:string}
export type ProofOperationKind = 'SAVE_SOURCE' | 'GRANT_SCOPE' | 'START_PREFLIGHT' | 'CANCEL_PREFLIGHT' | 'ADOPT_SOURCE' | 'REVOKE_SCOPE' | 'UPLOAD_REFERENCE' | 'CANCEL_REFERENCE' | 'START_REFERENCE_CAPTURE' | 'CANCEL_REFERENCE_CAPTURE'
const paths: Record<ProofOperationKind, string> = {SAVE_SOURCE: '/sources', GRANT_SCOPE: '/read-scopes', START_PREFLIGHT: '/preflights', CANCEL_PREFLIGHT: '/preflights/cancel', ADOPT_SOURCE: '/adoptions', REVOKE_SCOPE: '/read-scopes/revoke',UPLOAD_REFERENCE:'/reference-inputs',CANCEL_REFERENCE:'/reference-inputs/cancel',START_REFERENCE_CAPTURE:'/reference-captures',CANCEL_REFERENCE_CAPTURE:'/reference-captures/cancel'}
const prefix = (project: string) => `/api/projects/${encodeURIComponent(project)}/proof-preparation`
export const proofSourcesApi = {
  databaseCandidate:(project:string,body:object)=>request<ProofConfig>(prefix(project)+'/database-candidate',{method:'POST',body:JSON.stringify(body)}),
  databaseMaintenancePreview:(project:string,source:ProofSource,purpose:'INSTALL_DATABASE'|'REMOVE_DATABASE')=>request<{fingerprint:string;objects:string[];transactional_ddl:boolean;config:DatabaseCapture}>(prefix(project)+`/sources/${source.source_id}/database-maintenance-preview?revision=${source.revision}&purpose=${purpose}`),
  sqliteCandidate:(project:string,body:object)=>request<ProofConfig>(prefix(project)+'/sqlite-candidate',{method:'POST',body:JSON.stringify({schema_version:'1',...body})}),
  fileCandidate:(project:string,body:object)=>request<ProofConfig>(prefix(project)+'/file-candidate',{method:'POST',body:JSON.stringify(body)}),
  context: (project: string, view: 'full' | 'sources' = 'full', signal?:AbortSignal) => request<ProofContext>(prefix(project) + (view === 'sources' ? '?view=sources' : ''),{signal}),
  write: (project: string, kind: ProofOperationKind, body: object, content?: ArrayBuffer) => request<ProofReceipt>(prefix(project) + (kind==='START_PREFLIGHT'&&'purpose' in body?'/database-maintenance':paths[kind]), content
    ? {method:'POST',headers:{'Content-Type':'application/octet-stream','X-Jiejian-Reference':JSON.stringify(body)},body:content}
    : {method:'POST',body:JSON.stringify(body)}),
  receipt: (project: string, kind: ProofOperationKind, operation: string) => request<ProofReceipt>(`${prefix(project)}/receipts/${kind}/${operation}`),
  adoptionPreview: (project: string, source: string, preflight: string) => request<AdoptionPreview>(`${prefix(project)}/sources/${encodeURIComponent(source)}/adoption-preview?preflight_id=${encodeURIComponent(preflight)}`),
  capturePreview: (project: string, body: CaptureSelection) => request<CapturePlan>(`${prefix(project)}/reference-captures/preview`,{method:'POST',body:JSON.stringify(body)}),
  captureStatus: (project: string, id: string) => request<CaptureStatus>(`${prefix(project)}/reference-captures/${encodeURIComponent(id)}`),
  referenceDownload: (project: string, id: string) => `${prefix(project)}/reference-inputs/${encodeURIComponent(id)}/file`,
}
