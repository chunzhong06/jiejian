import {request} from '../../../shared/api/http'
import type {OperationFlow} from './operationFlows'

export type TrialSelection={flow_id:string;revision:number;subject_identity_id?:string;resource_owner_identity_id?:string;resource_id?:string;restore_trial_id?:string}
export type TrialPlan={flow:OperationFlow;case:{subject_test_identity_id:string;resource_owner_test_identity_id:string;resource_id:string};state_changing:boolean;mode:'TRIAL'|'RESTORE';runtime:{target:{base_url:string};budget:{max_requests:number;max_duration_us:number}}}
export type TrialPreview={plan:TrialPlan;plan_hash:string}
export type TrialReport={steps:Array<{step_id:string;purpose:'SETUP'|'TARGET'|'RESTORE';status_code:number|null;response_bytes:number|null;classification:'ACCEPTED'|'DENIED'|'UNKNOWN';error_code:string|null}>;identity_status:'MATCH'|'MISMATCH'|'UNKNOWN';target_attempted:boolean;flow_attempted:boolean;recovery:'NOT_REQUIRED'|'NOT_ATTEMPTED'|'REQUEST_ACCEPTED'|'REQUEST_DENIED'|'UNCONFIRMED';error_code:string|null}
export type FlowTrial={request:{trial_id:string;operation_id:string;created_at_us:number;plan:TrialPlan};job_id:string;state:'PENDING'|'RUNNING'|'RETRY_WAIT'|'SUCCEEDED'|'FAILED'|'CANCELLED';report:TrialReport|null;operation_may_have_run:boolean;recovery_pending:boolean}
const prefix=(project:string)=>`/api/projects/${project}/flow-trials`
export const flowTrialsApi={
  preview:(project:string,selection:TrialSelection)=>request<TrialPreview>(prefix(project)+'/preview',{method:'POST',body:JSON.stringify(selection)}),
  start:(project:string,selection:TrialSelection,preview:TrialPreview,operation:string)=>request<FlowTrial>(prefix(project),{method:'POST',body:JSON.stringify({selection,plan_hash:preview.plan_hash,operation_id:operation,confirmed:true})}),
  read:(project:string,id:string,signal?:AbortSignal)=>request<FlowTrial>(prefix(project)+'/'+id,{signal}),
  history:(project:string,signal?:AbortSignal)=>request<FlowTrial[]>(prefix(project),{signal}),
  cancel:(project:string,id:string)=>request<FlowTrial>(prefix(project)+'/'+id+'/cancel',{method:'POST',body:'{}'})
}
