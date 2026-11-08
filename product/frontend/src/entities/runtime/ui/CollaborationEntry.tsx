import {lazy,Suspense,useEffect,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import CommentOutlined from '@ant-design/icons/CommentOutlined'
import {collaborationApi,collaborationLabels,type CollaborationPurpose,type CollaborationEditor} from '../api/collaboration'
import {routeReferences,useCurrentHandoff} from '../model/handoff'
import {useRead} from '../../../shared/lib/useRead'
import {go} from '../../../shared/lib/navigation'
import {ApiError} from '../../../shared/api/http'
import {Button} from '../../../shared/ui/actions'
import {Dialog} from '../../../shared/ui/Dialog'
import {Loading} from '../../../shared/ui/feedback'

// 表单按意图加载；网络未知时的原请求与输入仍由常驻入口持有。
const Composer=lazy(()=>import('./CollaborationComposer').then(module=>({default:module.CollaborationComposer})))
type Submission={goal:string;purpose:CollaborationPurpose;references:Record<string,string>;editor?:CollaborationEditor;target:string}

export function CollaborationEntry({projectId,route,viewedTaskId,selected,portalHost,onNavigate}:{projectId:string;route:string;viewedTaskId?:string|null;selected?:boolean;portalHost?:HTMLElement|null;onNavigate?:()=>void}){
  const state=useRead('collaboration:'+projectId,signal=>collaborationApi.current(projectId,signal),4000)
  const context=useCurrentHandoff(projectId)
  const [open,setOpen]=useState(false),[goal,setGoal]=useState(''),[purpose,setPurpose]=useState<CollaborationPurpose>('CHECK')
  const [target,setTarget]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),[uncertain,setUncertain]=useState(false)
  const operation=useRef(crypto.randomUUID().replaceAll('-','')),pending=useRef<Submission|undefined>(undefined)
  const current=state.data
  useEffect(()=>{
    const compose=(event:Event)=>{
      const detail=(event as CustomEvent<{projectId:string;purpose:CollaborationPurpose;goal:string;newTask?:boolean}>).detail
      if(detail.projectId!==projectId)return
      if(!pending.current){setGoal(detail.goal);setPurpose(detail.purpose);setTarget(detail.newTask?'':current?.task_id??'');setError(undefined)}
      setOpen(true)
    }
    window.addEventListener('jiejian:collaboration-compose',compose)
    return()=>window.removeEventListener('jiejian:collaboration-compose',compose)
  },[projectId,current?.task_id])
  const status=state.error?'读取失败':current?({WAITING_AGENT:'待接续',RUNNING:'进行中',WAITING_USER:'待你确认',BLOCKED:'需处理',PAUSED:'已暂停',UNKNOWN:'待核对'} as Record<string,string>)[current.state]??collaborationLabels[current.state]:null
  const visit=(id:string)=>{go('/workspace?view=collaboration&task_id='+encodeURIComponent(id),projectId);onNavigate?.()}
  const create=async()=>{
    setBusy(true);setError(undefined)
    const input=pending.current??{goal:goal.trim(),purpose,target,references:{...routeReferences(route),...context?.references},editor:context?.editor}
    pending.current=input
    try{
      const task=input.target?await collaborationApi.followup(projectId,input.target,input.goal,input.purpose,input.references,operation.current,input.editor):await collaborationApi.create(projectId,input.goal,input.purpose,input.references,operation.current,input.editor)
      pending.current=undefined;operation.current=crypto.randomUUID().replaceAll('-','');setUncertain(false);setOpen(false);state.reload();visit(task.task_id)
    }catch(value){
      setError(value)
      // 明确拒绝可以调整输入；未知写入冻结原请求，重试只查同一幂等回执。
      if(value instanceof ApiError&&['INPUT_INVALID','STATE_PRECONDITION','MCP_PERMISSION_REQUIRED','RECORD_NOT_FOUND'].includes(value.code)){pending.current=undefined;setUncertain(false)}else setUncertain(true)
    }finally{setBusy(false)}
  }
  const trigger=<Button kind="quiet" className="jj-nav-item jj-collaboration-entry" icon={<CommentOutlined aria-hidden="true"/>} aria-label={state.error?'Agent 协作，状态读取失败':current?'Agent 协作，继续任务':'Agent 协作，开始任务'} aria-description={current?`${current.goal}，${collaborationLabels[current.state]}`:'让 Agent 整理权限要求、准备场景并协助检查与复验'} tip={current?`${current.goal}，${collaborationLabels[current.state]}`:'交代目标，让 Agent 接续当前应用的准备与验证'} aria-current={selected||viewedTaskId?'page':undefined} disabled={state.loading} onClick={()=>current?visit(current.task_id):setOpen(true)}><span className="jj-collaboration-entry-copy"><span className="jj-collaboration-entry-label jj-nav-label">Agent 协作</span>{status&&<span className="jj-collaboration-entry-status">{status}</span>}</span></Button>
  return <>
    {portalHost===undefined?trigger:portalHost?createPortal(trigger,portalHost):null}
    {open&&createPortal(<Suspense fallback={<Dialog title="与 Agent 协作" onClose={()=>setOpen(false)}><Loading/></Dialog>}><Composer goal={goal} setGoal={setGoal} purpose={purpose} setPurpose={setPurpose} target={target} setTarget={setTarget} current={current??undefined} context={context} busy={busy} uncertain={uncertain} error={error} onClose={()=>setOpen(false)} onSubmit={()=>void create()}/></Suspense>,document.body)}
  </>
}
