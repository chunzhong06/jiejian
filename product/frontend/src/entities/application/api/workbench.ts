import {request} from '../../../shared/api/http'
import type {ApplicationUnderstandingDto, ProjectDto} from './projects'

export type TargetScope = {base_url:string;allowed_origins:string[];allowed_hosts:string[];allowed_ports:number[];allow_private_network:boolean;follow_redirects?:boolean;timeout_seconds?:number;max_requests?:number;max_response_bytes?:number}
export type ApplicationEnvironment = {environment_id:string;revision:number;name:string;target:TargetScope;deployment_label:string|null;deployment_verification:'UNVERIFIED'}
export type EnvironmentImpact={project_id:string;expected_revision:number;impact_fingerprint:string;previous:ApplicationEnvironment|null;previous_endpoint:string|null;chosen:ApplicationEnvironment;changed:boolean;materials:{state:'RECHECK_REQUIRED'|'UNKNOWN';items:Array<{action_id:string;action_label:string;action_revision:number;kind:string;status:string;reason_codes:string[]}>|null};retained:string[];can_activate:boolean}
export type EnvironmentContext = {project_id:string;revision:number;active_environment:ApplicationEnvironment|null;environments:Array<{configuration:ApplicationEnvironment;created_at_us:number}>;source_available:boolean;confirmed_endpoint:string|null;endpoint_reachable:boolean|null;endpoint_checked_at_us:number|null}
export type SourceRequest = {item_id:string;method:string;path:string;label:string;pointer:string;parameters:Array<{name:string;location:'PATH'|'QUERY'|'HEADER'|'BODY';required:boolean;sensitive:boolean}>}
export type ApiSource = {source_id:string;revision:number;kind:'OPENAPI'|'HAR'|'POSTMAN';name:string;requests:SourceRequest[];warnings:string[];created_at_us:number}
export type SourceAnnotation = {source_id:string;item_id:string;label:string;action_id:string|null;revision:number}
export type SourcesContext = {project_id:string;sources:ApiSource[];annotations:SourceAnnotation[];request_references:import('../../preparation/api/operationFlows').ApiSourceReference[]}
export type SourcesSummary = {project_id:string;source_count:number;request_count:number}
export type ImportPreview = {candidate_id:string;requests:SourceRequest[];warnings:string[];fingerprint:string;previous_revision:number;added:string[];removed:string[];changed:string[]}
const root = (project:string) => `/api/projects/${encodeURIComponent(project)}`
export const workbenchApi = {
  sourceSummary:(project:string,signal?:AbortSignal)=>request<SourcesSummary>(root(project)+'/api-sources/summary',{signal}),
  create:(operation_id:string,name:string)=>request<ProjectDto>('/api/applications',{method:'POST',body:JSON.stringify({operation_id,name})}),
  environments:(project:string,signal?:AbortSignal)=>request<EnvironmentContext>(root(project)+'/environments',{signal}),
  attachSource:(project:string,source_root:string,expected_revision:number)=>request<ApplicationUnderstandingDto>(root(project)+'/source-directory',{method:'PUT',body:JSON.stringify({source_root,expected_revision})}),
  saveEnvironment:(project:string,configuration:ApplicationEnvironment,expected_revision:number)=>request(root(project)+'/environments',{method:'POST',body:JSON.stringify({configuration,expected_revision})}),
  previewActivation:(project:string,environment_id:string,revision:number)=>request<EnvironmentImpact>(root(project)+`/environments/${environment_id}/activation-preview?revision=${revision}`),
  activateEnvironment:(project:string,environment_id:string,revision:number,expected_revision:number,impact_fingerprint:string)=>request<ApplicationUnderstandingDto>(root(project)+`/environments/${environment_id}/activate`,{method:'POST',body:JSON.stringify({revision,expected_revision,impact_fingerprint})}),
  sources:(project:string,signal?:AbortSignal,sourceId?:string)=>request<SourcesContext>(root(project)+'/api-sources'+(sourceId?'?source_id='+encodeURIComponent(sourceId):''),{signal}),
  sourceRevision:(project:string,source:string,revision:number)=>request<ApiSource|null>(root(project)+`/api-sources/${source}/revisions/${revision}`),
  preview:(project:string,raw:string,kind:ApiSource['kind'],source_id?:string)=>request<ImportPreview>(root(project)+'/api-sources/preview',{method:'POST',body:JSON.stringify({raw,kind,source_id})}),
  accept:(project:string,source_id:string,name:string,preview:ImportPreview)=>request<ApiSource>(root(project)+'/api-sources/accept',{method:'POST',body:JSON.stringify({candidate_id:preview.candidate_id,source_id,name,expected_revision:preview.previous_revision,expected_fingerprint:preview.fingerprint})}),
  annotate:(project:string,source:string,item:string,label:string,action_id:string|null,expected_revision:number)=>request<SourceAnnotation>(root(project)+`/api-sources/${source}/requests/${item}`,{method:'PUT',body:JSON.stringify({label,action_id,expected_revision})}),
  candidate:(project:string,source:string,item:string,expected_revision:number)=>request<ApplicationUnderstandingDto>(root(project)+`/api-sources/${source}/requests/${item}/candidate`,{method:'POST',body:JSON.stringify({expected_revision})}),
}
