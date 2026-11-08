import {request} from '../../../shared/api/http'
import type {CheckPreview,CheckStatus} from './currentChecks'
import type {PermissionReference} from '../../preparation/api/preparation'
import type {ScenarioReference} from '../../preparation/api/businessScenarios'

export type RoutineReference={routine_id:string;revision:number;binding_id:string}
export type RunEnvironment={environment_id:string;revision:number;name:string;deployment_label:string|null;deployment_verification:'UNVERIFIED'}
export type RoutineScope={permissions:PermissionReference[];scenario:ScenarioReference|null}
export type RoutineLimits={max_duration_us:number;max_cases:number}
export type RoutineRequirement={kind:RoutineAsset['kind'];slot:string;label:string;minimum_count:number;actor?:{actor_id:string;revision:number};action?:{action_id:string;revision:number};effect_id?:string;normal_control_required:boolean;recovery_required:boolean}
export type CheckRoutine={document_type:'jiejian.check-routine';schema_version:'2';routine_id:string;project_id:string;revision:number;name:string;scope:RoutineScope;limits:RoutineLimits;requirements?:RoutineRequirement[]|null;created_at_us:number}
export type RoutineSummary={routine_id:string;revision:number;name:string;scope_kind:'PERMISSIONS'|'SCENARIO';permission_count:number;created_at_us:number}
export type LegacySelection={routine_id:string;name:string;selected_permissions:PermissionReference[]|null;created_at_us:number}
export type RoutineCatalog={project_id:string;routines:RoutineSummary[];legacy_selections:LegacySelection[];next_cursor?:string|null}
export type RoutineAsset={kind:'ACCOUNT'|'RESOURCE'|'FLOW'|'PROOF';slot:string;label:string;reference:string;fingerprint:string;requirement_slot?:string|null;owner_reference?:string|null}
export type RoutineBinding={document_type:'jiejian.check-routine-binding';schema_version:'1';binding_id:string;project_id:string;routine_id:string;routine_revision:number;routine_fingerprint:string;environment_id:string;environment_revision:number;environment_fingerprint:string;material_fingerprint:string;assets:RoutineAsset[];created_at_us:number}
export type RoutineBindingPreview={project_id:string;routine:CheckRoutine;preview:CheckPreview;environment:{environment_id:string;revision:number;name:string;deployment_label:string|null;target:{base_url:string}}|null;environment_fingerprint:string|null;material_fingerprint:string|null;assets:RoutineAsset[];can_bind:boolean}
export type SaveRoutine={operation_id:string;routine_id?:string;expected_revision:number;name:string;scope:RoutineScope;limits:RoutineLimits}
export type BindRoutine={operation_id:string;revision:number;expected_material_fingerprint:string;expected_environment_fingerprint:string}
const root=(project:string)=>'/api/projects/'+encodeURIComponent(project)+'/check-routines'
const path=(project:string,id:string)=>root(project)+'/'+encodeURIComponent(id)
export const routinesApi={
 catalog:(project:string,signal?:AbortSignal,after?:string)=>request<RoutineCatalog>(root(project)+'/catalog'+(after?'?after='+encodeURIComponent(after):''),{signal}),
 read:(project:string,id:string,revision:number)=>request<CheckRoutine>(path(project,id)+'/revisions/'+revision),
 save:(project:string,body:SaveRoutine)=>request<CheckRoutine>(root(project)+'/revisions',{method:'POST',body:JSON.stringify(body)}),
 history:(project:string,id:string,before?:number)=>request<Array<{revision:number;name:string;created_at_us:number}>>(path(project,id)+'/revisions'+(before?'?before='+before:'')),
 preparation:(project:string,id:string,revision:number)=>request<RoutineBindingPreview>(path(project,id)+'/binding-preview?revision='+revision),
 bindings:(project:string,id:string,revision:number)=>request<RoutineBinding[]>(path(project,id)+'/bindings?revision='+revision),
 bind:(project:string,id:string,body:BindRoutine)=>request<RoutineBinding>(path(project,id)+'/bindings',{method:'POST',body:JSON.stringify(body)}),
 receipt:(project:string,reference:RoutineReference,fingerprint:string,operation:string)=>request<CheckStatus|null>(path(project,reference.routine_id)+'/requests/'+encodeURIComponent(operation)+'?'+new URLSearchParams({revision:String(reference.revision),binding_id:reference.binding_id,fingerprint})),
}
