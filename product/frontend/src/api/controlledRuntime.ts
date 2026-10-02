// 受控启动只提交已预览的加载请求；未知响应通过原操作回读，不重复启动。
import { request } from './http'

export type RuntimePreview = {
  project_id: string; revision: number; entry: string; port: number
  source_fingerprint: string; preview_fingerprint: string
  files: Array<{relative_path: string; size: number; sha256: string}>
}
export type RuntimeOperation = {
  project_id: string; operation_id: string; instance_id: string; job_id: string
  state: 'PENDING' | 'RUNNING' | 'RETRY_WAIT' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED'
  source_fingerprint: string; receipt: null | {reference: {port: number}; started_at_us: number}
}
export type RuntimeState = {project_id: string; operation: RuntimeOperation | null; running: boolean; source_matches: boolean;
  configuration?:{entry:string;port:number;file_count:number}|null}
const prefix=(project:string)=>`/api/projects/${encodeURIComponent(project)}/controlled-runtime`
const post=<T,>(path:string,body:unknown)=>request<T>(path,{method:'POST',body:JSON.stringify(body)})
export const controlledRuntimeApi = {
  state:(project:string)=>request<RuntimeState>(prefix(project)),
  preview:(project:string,body:{entry:string;port:number;revision:number;consent_source_read:boolean})=>post<RuntimePreview>(prefix(project)+'/preview',body),
  start:(project:string,body:{entry:string;port:number;revision:number;preview_fingerprint:string;operation_id:string;consent_execute:boolean})=>post<RuntimeOperation>(prefix(project)+'/start',body),
  operation:(project:string,operation:string)=>request<RuntimeOperation|null>(prefix(project)+'/operations/'+encodeURIComponent(operation)),
  cancel:(project:string,operation:string)=>post<RuntimeOperation>(prefix(project)+'/operations/'+encodeURIComponent(operation)+'/cancel',{}),
  stop:(project:string,instance_id:string)=>post<RuntimeState>(prefix(project)+'/stop',{instance_id}),
}
