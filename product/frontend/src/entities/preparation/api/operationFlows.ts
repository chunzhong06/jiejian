import {request} from '../../../shared/api/http'
export type ApiSourceReference={source_id:string;revision:number;item_id:string;request_fingerprint:string}
export type EntityEvidence = {effect_id:string;query:{request:Record<string,unknown>;resource_path:string;owner_path:string;data_path:string}}
export type FlowStep={failure_policy?:'INCONCLUSIVE'|'STOP';id:string;purpose:'SETUP'|'TARGET';identity_id:string;request_template:{method:string;path:string;body:{kind:'EMPTY'|'JSON';value?:unknown};query?:Array<Record<string,unknown>>;headers?:Array<Record<string,unknown>>;input_slots?:Array<Record<string,unknown>>;response_extractors?:Array<Record<string,unknown>>};classifier:{accepted:Array<Record<string,unknown>>;denied:Array<Record<string,unknown>>};depends_on_step_ids:string[]}
export type OperationFlow={source_request?:ApiSourceReference;entity_evidence?:EntityEvidence[];id:string;revision:number;business_action_id:string;action_revision:number;subject_test_identity_id:string;resource_owner_test_identity_id:string;provenance:'MANUAL'|'OPENAPI'|'RECORDING';source_recording_id:string|null;source_fingerprint:string|null;actual_resource_id:string;workflow:{steps:FlowStep[];target_step_id:string};recovery:{method:string;relative_path:string;json_body:Record<string,unknown>}|null}
export type OperationContext={project_id:string;source_fingerprint:string|null;endpoint:string|null;recordings:Array<{recording_id:string;action_id:string;label:string;created_at_us:number}>;actions:Array<{action_id:string;revision:number;label:string;state_changing:boolean;effects:Array<{effect_id:string;label:string;kind:string;protected_projection:string[]}>}>;flows:Array<{document:OperationFlow;adopted:boolean;in_use:boolean;configuration_current:boolean}>}
export type ApiCandidate={method:string;path:string;label:string;fields:string[]}
const prefix=(project:string)=>`/api/projects/${project}/operation-flows`
export const operationFlowsApi={
    read:(project:string,flow:string,revision:number,signal?:AbortSignal)=>request<OperationFlow>(`${prefix(project)}/${encodeURIComponent(flow)}/${revision}`,{signal}),
    context:(project:string,signal?:AbortSignal)=>request<OperationContext>(prefix(project),{signal}),
    candidate:(project:string,document:object)=>request<OperationFlow>(prefix(project)+'/candidate',{method:'POST',body:JSON.stringify(document)}),
    save:(project:string,document:OperationFlow)=>request<OperationFlow>(prefix(project),{method:'PUT',body:JSON.stringify(document)}),
    adopt:(project:string,flow:OperationFlow)=>request<{adopted:boolean}>(`${prefix(project)}/${flow.id}/${flow.revision}/adopt`,{method:'POST',body:'{}'}),
    openapi:(project:string,document:string)=>request<ApiCandidate[]>(prefix(project)+'/openapi',{method:'POST',body:document}),
    recording:(project:string,id:string)=>request<{steps:FlowStep[];target_step_id:string;actual_resource_id:string}>(prefix(project)+'/recording/'+id)
}
