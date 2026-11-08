import {useRef,useState} from 'react'
import {collaborationApi} from '../../runtime/api/collaboration'
import type {CheckRoutine,RoutineReference} from '../api/routines'
import {operationId,readPending,savePending} from '../../../shared/lib/operations'
import {go} from '../../../shared/lib/navigation'
import {Button} from '../../../shared/ui/actions'
import {Dialog} from '../../../shared/ui/Dialog'
import {ErrorNote,Notice} from '../../../shared/ui/feedback'
import {assertProject} from '../../../shared/model/page'
import {ApiError} from '../../../shared/api/http'

type PendingHandoff={operation:string;goal:string;purpose:'CHECK'|'SETUP';references:Record<string,string>}

export function RoutineHandoff({projectId,document,reference,origin,onClose}:{projectId:string;document:CheckRoutine;reference?:RoutineReference;origin:string;onClose:()=>void}){
 const key='jiejian.routine-handoff:'+projectId+':'+document.routine_id+':'+document.revision+':'+(reference?.binding_id??'review')
 const [pending,setPending]=useState(()=>readPending<PendingHandoff>(key)),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),lock=useRef(false)
 const start=async()=>{
  if(lock.current)return;lock.current=true;setBusy(true);setError(undefined)
  const command:PendingHandoff=pending??{operation:operationId(),goal:'核对“'+document.name+'”第 '+document.revision+' 修订的检查范围、当前材料和下一步',purpose:reference?'CHECK':'SETUP',
   references:{routine_id:document.routine_id,routine_revision:String(document.revision),...(reference?{binding_id:reference.binding_id}:{}),return_to:origin}}
  savePending(key,command);setPending(command)
  try{
   const task=await collaborationApi.create(projectId,command.goal,command.purpose,command.references,command.operation)
   assertProject(task.project_id,projectId);savePending(key,undefined);setPending(undefined);onClose();go('/workspace?view=collaboration&task_id='+task.task_id,projectId)
  }catch(error){setError(error);if(error instanceof ApiError&&['INPUT_INVALID','RECORD_NOT_FOUND','STATE_PRECONDITION'].includes(error.code)){savePending(key,undefined);setPending(undefined)}}finally{lock.current=false;setBusy(false)}
 }
 return <Dialog title="交接当前检查方案" onClose={()=>{if(!busy)onClose()}} actions={<><Button disabled={busy} onClick={onClose}>返回方案</Button><Button kind="primary" busy={busy} onClick={()=>void start()}>{busy?'正在交接':pending?'核对原交接请求':'建立协作任务'}</Button></>}>
  <p>会把“{document.name}”的检查内容{reference?'和本次已确认的材料':''}交给 Agent，接着准备和检查。</p><p className="jj-small jj-muted">需要授权的操作会留在任务中供你确认，最终结论仍以正式检查结果为准。</p>
  {pending&&!busy&&<Notice>原交接结果待确认；再次核对沿用同一请求。</Notice>}{Boolean(error)&&<ErrorNote error={error}/>}
 </Dialog>
}
