import {request} from '../../../shared/api/http'
export type CollaborationPurpose='RULES'|'SETUP'|'CHECK'|'CHECK_AND_REPAIR'|'REPAIR'|'UNDERSTAND'|'MAINTENANCE'
export const purposeLabels:Record<CollaborationPurpose,string>={RULES:'整理权限要求',SETUP:'补齐检查准备',CHECK:'调查权限问题',CHECK_AND_REPAIR:'检查并修复',REPAIR:'修复指定问题',UNDERSTAND:'理解应用或报告',MAINTENANCE:'处理运行与维护'}
export type FlowHandoff={kind:'FLOW';flow_id:string;revision:number;action_id:string;action_revision:number;subject_identity_id:string|null;owner_identity_id:string|null;target_step_id:string;steps:{id:string;method:string;path:string|null;parameters:{location:string;name:string;source:string;secret:boolean}[]}[];recovery_path:string|null;evidence_effect_ids:string[];evidence_queries?:{effect_id:string;request_path:string|null;resource_path:string;owner_path:string;data_path:string}[]}
export type ProofHandoff={kind:'PROOF';basis_id:string;action_id:string;effect_id:string;resource_binding_id:string|null;table:string|null;protected_column:string|null;tenant_column:string|null;state_column:string|null}
export type CollaborationEditor=FlowHandoff|ProofHandoff

export type CollaborationOperation = {operation_id:string;capability:string;title:string;state:string;arguments:Record<string,unknown>;summary?:{label:string;value:string}[];result:unknown;error_code?:string}
export type CollaborationCheck = {run_id:string;lifecycle:string;verdict:'PASS'|'BLOCK'|'INCONCLUSIVE'|null;revalidation:boolean;selected_scope?:boolean}
export type CollaborationTask = {task_id:string;project_id:string;goal:string;purpose:CollaborationPurpose;state:string;revision:number;updated_at_us:number;references:Record<string,string>;editor?:CollaborationEditor|null;operations:CollaborationOperation[];reviews?:{id:string;title:string;destination:string;action_label:string}[];questions:{question_id:string;question:string;options:string[];answer:string|null}[];events:{id:string;actor:string;title:string;at_us:number}[];latest_check?:CollaborationCheck|null;outcome?:{fulfilled:boolean;title:string;destination:string};execution:null|{state:string;session_id?:string;message?:string;restricted?:boolean;failed_tools?:boolean;continuous?:boolean;turn_count?:number;max_turns?:number;max_seconds?:number}}
export type CollaborationCapability = {key:string;title:string;domain:string;level:string;requires_review:boolean}
export type CollaborationExecutor = {available:boolean;provider:string;read_only?:boolean}&({ready:true}|{ready:false;setup_label:string;setup_path:string})
const base=(project:string)=>'/api/projects/'+encodeURIComponent(project)+'/collaboration'
const post=<T>(path:string,body:unknown)=>request<T>(path,{method:'POST',body:JSON.stringify(body)})
export const collaborationApi={
  current:(project:string,signal?:AbortSignal)=>request<Pick<CollaborationTask,'task_id'|'goal'|'state'|'revision'|'updated_at_us'>|null>('/api/projects/'+encodeURIComponent(project)+'/collaboration-active',{signal}),
  list:(project:string,signal?:AbortSignal)=>request<CollaborationTask[]>(base(project),{signal}),
  show:(project:string,task:string)=>request<CollaborationTask>(base(project)+'/'+task),
  context:(project:string,task:string)=>request<{task:CollaborationTask;capabilities:CollaborationCapability[]}>(base(project)+'/'+task+'/context'),
  activity:(project:string,task:string)=>request<{id:string;label:string;phase:string;destination:string}[]>(base(project)+'/'+task+'/activity'),
  create:(project:string,goal:string,purpose:CollaborationPurpose,references:Record<string,string>={},operationId=crypto.randomUUID().replaceAll('-',''),editor?:CollaborationEditor)=>post<CollaborationTask>(base(project),{operation_id:operationId,goal,purpose,references,...(editor?{editor}:{})}),
  followup:(project:string,task:string,goal:string,purpose:CollaborationPurpose,references:Record<string,string>,operationId:string,editor?:CollaborationEditor|null)=>post<CollaborationTask>('/api/projects/'+encodeURIComponent(project)+'/collaboration-followup',{task_id:task,operation_id:operationId,goal,purpose,references,...(editor?{editor}:{})}),
  decide:(project:string,task:string,operation:string,accept:boolean)=>post(base(project)+'/'+task+'/actions/'+operation+'/decision',{accept}),
  reconcile:(project:string,task:string,operation:string)=>post(base(project)+'/'+task+'/actions/'+operation+'/reconcile',{}),
  answer:(project:string,task:string,question:string,answer:string)=>post(base(project)+'/'+task+'/questions/'+question,{answer}),
  control:(project:string,task:string,action:string)=>post(base(project)+'/'+task+'/control',{action}),
  executor:(project:string)=>request<CollaborationExecutor>('/api/collaboration/executor?project_id='+encodeURIComponent(project)),
  execute:(project:string,task:string,allowChanges:boolean,operationId:string,continuous=true)=>post(base(project)+'/'+task+'/execute',{operation_id:operationId,allow_changes:allowChanges,continuous,max_turns:8,max_seconds:1800}),
}
export const collaborationLabels:Record<string,string>={WAITING_AGENT:'等待 Agent 接续',RUNNING:'正在处理',WAITING_USER:'需要你确认',BLOCKED:'需要处理',PAUSED:'已暂停',COMPLETED:'协作已结束',CANCELLED:'已停止',UNKNOWN:'结果待核对',FAILED:'未完成',SUCCEEDED:'已取得回执',DECLINED:'已取消这项操作'}

// 生命周期只表达协作进展；业务检查结论继续由各自的 Verdict 呈现。
export const collaborationTone=(state:string):'neutral'|'accent'|'positive'|'caution'|'negative'=>
  ['SUCCEEDED','COMPLETED'].includes(state)?'positive':state==='FAILED'?'negative':['BLOCKED','UNKNOWN'].includes(state)?'caution':['RUNNING','PENDING','WAITING_USER'].includes(state)?'accent':'neutral'
