import {request} from '../../../shared/api/http'

export type CollaborationOperation = {operation_id:string;capability:string;title:string;state:string;arguments:Record<string,unknown>;summary?:{label:string;value:string}[];result:unknown;error_code?:string}
export type CollaborationCheck = {run_id:string;lifecycle:string;verdict:'PASS'|'BLOCK'|'INCONCLUSIVE'|null;revalidation:boolean;selected_scope?:boolean}
export type CollaborationTask = {task_id:string;project_id:string;goal:string;purpose:string;state:string;revision:number;updated_at_us:number;references:Record<string,string>;operations:CollaborationOperation[];reviews?:{id:string;title:string;destination:string;action_label:string}[];questions:{question_id:string;question:string;options:string[];answer:string|null}[];events:{id:string;actor:string;title:string;at_us:number}[];latest_check?:CollaborationCheck|null;outcome?:{fulfilled:boolean;title:string;destination:string};execution:null|{state:string;session_id?:string;message?:string;restricted?:boolean;failed_tools?:boolean;continuous?:boolean;turn_count?:number;max_turns?:number;max_seconds?:number}}
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
  create:(project:string,goal:string,purpose:string,references:Record<string,string>={},operationId=crypto.randomUUID().replaceAll('-',''))=>post<CollaborationTask>(base(project),{operation_id:operationId,goal,purpose,references}),
  followup:(project:string,task:string,goal:string,purpose:string,references:Record<string,string>,operationId:string)=>post<CollaborationTask>('/api/projects/'+encodeURIComponent(project)+'/collaboration-followup',{task_id:task,operation_id:operationId,goal,purpose,references}),
  decide:(project:string,task:string,operation:string,accept:boolean)=>post(base(project)+'/'+task+'/actions/'+operation+'/decision',{accept}),
  reconcile:(project:string,task:string,operation:string)=>post(base(project)+'/'+task+'/actions/'+operation+'/reconcile',{}),
  answer:(project:string,task:string,question:string,answer:string)=>post(base(project)+'/'+task+'/questions/'+question,{answer}),
  control:(project:string,task:string,action:string)=>post(base(project)+'/'+task+'/control',{action}),
  executor:(project:string)=>request<CollaborationExecutor>('/api/collaboration/executor?project_id='+encodeURIComponent(project)),
  execute:(project:string,task:string,allowChanges:boolean,operationId:string,continuous=true)=>post(base(project)+'/'+task+'/execute',{operation_id:operationId,allow_changes:allowChanges,continuous,max_turns:8,max_seconds:1800}),
}
export const collaborationLabels:Record<string,string>={WAITING_AGENT:'等待 Agent 接续',RUNNING:'正在处理',WAITING_USER:'需要你确认',BLOCKED:'需要处理',PAUSED:'已暂停',COMPLETED:'协作已结束',CANCELLED:'已停止',UNKNOWN:'结果待核对',FAILED:'未完成',SUCCEEDED:'已取得回执',DECLINED:'已取消这项操作'}
