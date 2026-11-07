import {request} from '../../../shared/api/http'
import type {PermissionReference} from './preparation'
import type {CheckPreview} from '../../check/api/currentChecks'

export type ScenarioReference={scenario_id:string;revision:number}
export type ScenarioItem={id:string;permission:PermissionReference;subject_identity_id:string|null;resource_id:string;resource_from?:string}
export type ScenarioInvocation={id:string;label:string;items:ScenarioItem[];depends_on:string[];batch:{strategy:'ATOMIC'|'PER_ITEM';array_path:Array<string|number>;response_items_path:string|null;response_resource_field:string|null}|null}
export type ScenarioExperiment={id:string;label:string;kind:'NORMAL'|'OMIT'|'REORDER'|'REPEAT'|'CHANGE_SUBJECT'|'REVOKE';control_experiment_id:string|null;invocations:ScenarioInvocation[]}
export type BusinessScenario={document_type:'jiejian.business-scenario';schema_version:'1';id:string;project_id:string;revision:number;label:string;description:string;experiments:ScenarioExperiment[]}
export type FrozenBusinessScenario={document:BusinessScenario;fingerprint:string;invocations:Array<{experiment_id:string;invocation_id:string;case_ids:string[]}>}
export type AvailableScenarioCase={case_id:string;subject_test_identity_id:string|null;resource_owner_test_identity_id:string;resource_id:string;permission:PermissionReference&{expectation:'ALLOW'|'DENY'}}
export type ScenarioSummary={id:string;revision:number;label:string;description:string;experiment_count:number}
export type ScenarioListing={project_id:string;documents:ScenarioSummary[]}
export type ScenarioContext=ScenarioListing&{actions:Array<{action_id:string;action_revision:number;label:string;cases:AvailableScenarioCase[];trial_flow?:{flow_id:string;revision:number}|null;creates_resource?:boolean}>;identities:Array<{identity_id:string;label:string}>;gaps:CheckPreview['gaps']}
const path=(project:string)=>'/api/projects/'+encodeURIComponent(project)+'/business-scenarios'
export const businessScenariosApi={
  list:(project:string,signal?:AbortSignal)=>request<ScenarioListing>(path(project),{signal}),
  context:(project:string,signal?:AbortSignal)=>request<ScenarioContext>(path(project)+'/context',{signal}),
  read:(project:string,id:string,revision:number)=>request<BusinessScenario>(path(project)+'/'+encodeURIComponent(id)+'/'+revision),
  save:(project:string,document:BusinessScenario)=>request<BusinessScenario>(path(project),{method:'PUT',body:JSON.stringify(document)}),
}
