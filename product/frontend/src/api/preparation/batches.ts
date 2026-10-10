// 材料批次只提交人的固定确认并读取后台回执；浏览器不逐项授权或执行准备步骤。
import {request} from '../http'

export type PreparationBatchPlan={schema_version:'1';project_id:string;mode:'OFFICIAL'|'REVIEWED';basis_id:string;runtime_origin:string;guard:string;sources:Array<{source_id:string;revision:number;config_hash:string;label:string}>}
export type PreparationBatch={schema_version:'1';project_id:string;operation_id:string;state:'RUNNING'|'CANCELLING'|'SUCCEEDED'|'CANCELLED'|'BLOCKED';cancel_requested:boolean;message:string;completed:number;total:number;preflight_id:string|null;updated_at_us:number}
const base=(project:string)=>`/api/projects/${encodeURIComponent(project)}/proof-preparation/batches`
export const preparationBatchesApi={
  preview:(project:string,mode:PreparationBatchPlan['mode'])=>request<PreparationBatchPlan>(`${base(project)}/preview?mode=${mode}`,{method:'POST'}),
  start:(project:string,operation:string,plan:PreparationBatchPlan)=>request<PreparationBatch>(base(project),{method:'POST',body:JSON.stringify({operation_id:operation,plan,confirmed:true})}),
  latest:(project:string)=>request<PreparationBatch|null>(`${base(project)}/latest`),
  status:(project:string,operation:string)=>request<PreparationBatch>(`${base(project)}/${encodeURIComponent(operation)}`),
  cancel:(project:string,operation:string)=>request<PreparationBatch>(`${base(project)}/${encodeURIComponent(operation)}/cancel`,{method:'POST'}),
}
