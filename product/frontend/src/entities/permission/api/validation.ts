import {request} from '../../../shared/api/http'
import type {RuleCandidateView} from './ruleCandidates'
import type {BoundaryMaintenanceCommandDto} from './businessBoundaries'

export type ValidationQuestion={requirement_id:string;fingerprint:string;action_item_id:string;dimension:string;question:string;basis:string;source_excerpt:string;status:'NEEDS_DECISION'|'DEFERRED'|'EXCLUDED'|'IN_REVIEW'|'RECHECK';review_url:string|null;decision_reason:string|null}
export type ValidationRequirement={definition_changes?:string[];environment_summary?:string;preparation_summary?:string;item_id:string;intent_id:string|null;revision:number|null;action_id:string|null;action_item_id:string;action_label:string;sentence:string;expectation:'ALLOW'|'DENY';relation:string;conditions:unknown;normal_control:string;preparation_requirements:string[];preparation_url:string;current_materials:Array<{kind:string;status:string;member_label:string;reason_codes:string[];explanation?:string;next_step?:string;compatible_with_definition?:boolean}>;effects:Array<{configured_path?:string|null;configuration_present?:boolean;capability_status?:'CONFIGURED'|'NEEDS_CONFIGURATION'|'NEEDS_RECHECK'|'UNSUPPORTED';item_id:string;label:string;kind:string;requirement:string;supported_paths:string[];protected_fields:string[];material_status:string;reason_codes:string[]}>}
export type ValidationPlan={project_id:string;basis_id:string;fingerprint:string;candidate_id:string|null;candidate_revision:number|null;state:'CURRENT'|'STALE';requirements:ValidationRequirement[];questions:ValidationQuestion[];scope:string}
export type ValidationReference={candidate_id?:string;revision?:number;intent_id?:string}
export type OpenQuestionRequest={operation_id:string;expected_fingerprint:string;question_fingerprint:string;candidate_id?:string;revision?:number}
const prefix=(project:string)=>'/api/projects/'+encodeURIComponent(project)+'/business-boundaries'
export const validationApi={
  read:(project:string,reference:ValidationReference={},signal?:AbortSignal)=>request<ValidationPlan>(prefix(project)+'/validation-plan?'+new URLSearchParams(Object.entries(reference).map(([key,value])=>[key,String(value)])),{signal}),
  open:(project:string,question:string,command:OpenQuestionRequest)=>request<RuleCandidateView>(prefix(project)+'/validation-questions/'+encodeURIComponent(question),{method:'POST',body:JSON.stringify(command)}),
  preview:(project:string,command:BoundaryMaintenanceCommandDto,signal?:AbortSignal)=>request<ValidationPlan>(prefix(project)+'/validation-plan/preview',{method:'POST',body:JSON.stringify({schema_version:'1',...command}),signal}),
}
