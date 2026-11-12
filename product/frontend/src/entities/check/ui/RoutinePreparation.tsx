import {TaskActions} from '../../../shared/ui/layout'
import {useRef,useState} from 'react'
import {useWorkflow} from '../../../shared/lib/workflow'
import {routinesApi,type CheckRoutine,type BindRoutine,type RoutineBinding} from '../api/routines'
import {RoutineHandoff} from './RoutineHandoff'
import {RoutineBindingRequirements} from './RoutineBindingRequirements'
import {useRead} from '../../../shared/lib/useRead'
import {operationId,readPending,savePending} from '../../../shared/lib/operations'
import {assertProject} from '../../../shared/model/page'
import {go,scopedPath,withReturnDestination} from '../../../shared/lib/navigation'
import {ApiError} from '../../../shared/api/http'
import {Button,ActionLink} from '../../../shared/ui/actions'
import {ErrorNote,InlineFeedback,Loading,Notice} from '../../../shared/ui/feedback'

export function RoutinePreparation({projectId,document,dirty,origin,initialSlot,onBound,official=false}:{projectId:string;document:CheckRoutine;dirty:boolean;origin:string;initialSlot?:string|null;onBound?:(binding:RoutineBinding)=>void;official?:boolean}){
 const workflow=useWorkflow(),[receipt,setReceipt]=useState<RoutineBinding>()
 const [assist,setAssist]=useState(false)
 const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),lock=useRef(false)
 const key='jiejian.routine-binding:'+projectId+':'+document.routine_id+':'+document.revision
 const [pending,setPending]=useState(()=>readPending<BindRoutine>(key))
 const state=useRead('routine-binding:'+projectId+':'+document.routine_id+':'+document.revision,async()=>{
  const [preparation,bindings]=await Promise.all([routinesApi.preparation(projectId,document.routine_id,document.revision),routinesApi.bindings(projectId,document.routine_id,document.revision)])
  assertProject(preparation.project_id,projectId);bindings.forEach(item=>assertProject(item.project_id,projectId));return {preparation,bindings}
 })
 const accepted=receipt?.project_id===projectId&&receipt.routine_id===document.routine_id&&receipt.routine_revision===document.revision?receipt:undefined
 const confirmation=accepted&&<InlineFeedback tone="positive">已确认这次检查使用的材料。{state.error?'当前准备详情暂未更新，确认回执已保留。':''}<ActionLink href={'#'+scopedPath('/reports?'+new URLSearchParams({view:'plan',routine_id:accepted.routine_id,routine_revision:String(accepted.routine_revision),binding_id:accepted.binding_id,return_to:origin}),projectId)}>继续检查</ActionLink></InlineFeedback>
 if(!state.data&&accepted)return confirmation
 // 子工作面读取失败仍保留方案标题、分类和准确回程，不再嵌入第二个页面骨架。
 if(!state.data)return state.error?<section className="jj-routine-preparation-intro"><h2>暂时无法读取本次检查准备</h2><p>请先核对应用连接，再读取方案所需的账号和材料。已保存的方案和本地草稿继续保留。</p><ErrorNote error={state.error}/><TaskActions separated><ActionLink href={'#'+scopedPath(withReturnDestination('/application',origin),projectId)}>核对应用连接</ActionLink><Button onClick={()=>state.reload()}>重新读取准备</Button></TaskActions></section>:<Loading/>
 const {preparation,bindings}=state.data,matched=bindings.find(item=>item.environment_fingerprint===preparation.environment_fingerprint&&item.material_fingerprint===preparation.material_fingerprint)
 const previous=bindings.find(item=>item.environment_id===preparation.environment?.environment_id),assets=preparation.assets
 const bind=async()=>{
  if(lock.current||dirty||!pending&&!preparation.can_bind)return;lock.current=true;setBusy(true);setError(undefined)
  const command=pending??{operation_id:operationId(),revision:document.revision,expected_material_fingerprint:preparation.material_fingerprint!,expected_environment_fingerprint:preparation.environment_fingerprint!}
  savePending(key,command);setPending(command)
  try{const value=await routinesApi.bind(projectId,document.routine_id,command);assertProject(value.project_id,projectId);if(value.routine_id!==document.routine_id||value.routine_revision!==document.revision)throw new Error('材料确认回执与原方案不一致');setReceipt(value);savePending(key,undefined);setPending(undefined);if(onBound)onBound(value);else state.reload()}
  catch(error){setError(error);if(error instanceof ApiError&&['INPUT_INVALID','STATE_PRECONDITION','RECORD_NOT_FOUND'].includes(error.code)){savePending(key,undefined);setPending(undefined)}}finally{lock.current=false;setBusy(false)}
 }
 const previewPath='/reports?'+new URLSearchParams({view:'plan',routine_id:document.routine_id,routine_revision:String(document.revision),...(matched?{binding_id:matched.binding_id}:{}),return_to:origin})
 const contentPath=withReturnDestination('/testing?'+new URLSearchParams({view:'plans',routine_id:document.routine_id,routine_revision:String(document.revision),section:'content'}),origin)
 return <>{confirmation}<header className="jj-routine-preparation-intro"><h2>确认这次检查的应用和材料</h2><p>核对当前连接和所需材料，补齐缺口后确认用于本次检查。</p></header>
  {dirty&&<Notice tone="caution">请先保存这份方案的修改，再准备本次检查。</Notice>}
  {pending&&!busy&&<Notice tone="caution">上次确认材料的结果还不明确，请先核对原操作。</Notice>}
  {!preparation.environment&&!pending&&<Notice title="尚未设置检查连接">先设置这次要检查的应用地址。当前材料可以先核对，连接设置完成后再确认使用。</Notice>}
  {preparation.environment&&<dl className="jj-facts"><div><dt>检查连接</dt><dd>{preparation.environment.target.base_url}</dd></div></dl>}
  <RoutineBindingRequirements projectId={projectId} document={document} assets={assets} progress={preparation.requirement_progress} onReload={()=>state.reload()} previous={previous} origin={origin} initialSlot={initialSlot} dirty={dirty}/>
  {Boolean(error)&&<ErrorNote error={error}/>}{!dirty&&<TaskActions note={<div className="jj-inline-actions">{preparation.environment&&<ActionLink href={'#'+scopedPath(withReturnDestination('/application',origin),projectId)}>核对应用连接</ActionLink>}<ActionLink navigationScope="page" href={'#'+scopedPath(contentPath,projectId)}>查看方案内容</ActionLink></div>}><Button kind="quiet" disabled={Boolean(pending)} onClick={()=>setAssist(true)}>请 Agent 协助准备</Button>{matched?<Button kind="primary" onClick={()=>onBound?onBound(matched):go(previewPath,projectId)}>预览这次检查</Button>:!preparation.environment&&!pending?<ActionLink kind="primary" href={"#"+scopedPath(withReturnDestination("/application",origin),projectId)}>设置检查连接</ActionLink>:official&&workflow&&!pending&&!preparation.can_bind?<Button kind="primary" onClick={()=>workflow.open('/preparation?prepare_example=1')}>一键准备示例材料</Button>:<Button kind="primary" busy={busy} disabled={!pending&&!preparation.can_bind} onClick={()=>void bind()}>{busy?'正在确认材料':pending?'核对上次确认结果':'确认使用这些材料'}</Button>}</TaskActions>}
  {assist&&<RoutineHandoff projectId={projectId} document={document} reference={matched?{routine_id:document.routine_id,revision:document.revision,binding_id:matched.binding_id}:undefined} origin={origin} onClose={()=>setAssist(false)}/>} 
 </>
}
