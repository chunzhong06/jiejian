import {useWorkflow} from '../../shared/lib/workflow'
import {RoutinePreparation} from '../../entities/check/ui/RoutinePreparation'
import '../testing/routines.css'
import {useRef,useState} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import {currentChecksApi as checks} from '../../entities/check/api/currentChecks'
import {routinesApi,type RoutineReference} from '../../entities/check/api/routines'
import {preparationApi} from '../../entities/preparation/api/preparation'
import {testIdentitiesApi} from '../../entities/preparation/api/testIdentities'
import {useRead} from '../../shared/lib/useRead'
import {operationId,readPending,savePending} from '../../shared/lib/operations'
import {go,returnDestination,returnDestinationLabel,scopedPath} from '../../shared/lib/navigation'
import {ApiError} from '../../shared/api/http'
import {assertProject,type PageProps} from '../../shared/model/page'
import {Heading} from '../../shared/ui/layout'
import {Button,ActionLink} from '../../shared/ui/actions'
import {ErrorNote,Loading,Notice,PageError} from '../../shared/ui/feedback'
import {PlanWorkspace} from './CheckPlan'

type Pending={operation:string;fingerprint:string;reference:RoutineReference}

/** 方案只采用准确修订和绑定；未确认绑定的准备视图不能直接提交运行。 */
export function RoutinePlan({projectId,route,refresh,onError}:PageProps){
 const workflow=useWorkflow()
 const routineId=route.query.get('routine_id'),revision=Number(route.query.get('routine_revision')),bindingId=route.query.get('binding_id')
 const valid=Boolean(routineId&&/^csp_[0-9a-f]{32}$/.test(routineId)&&Number.isInteger(revision)&&revision>0&&(!bindingId||/^crb_[0-9a-f]{32}$/.test(bindingId)))
 const reference:RoutineReference|undefined=valid&&bindingId?{routine_id:routineId!,revision,binding_id:bindingId}:undefined
 const identity=JSON.stringify([projectId,routineId,revision,bindingId]),key='jiejian.routine-run:'+identity
 const scheme='/testing?'+new URLSearchParams({view:'plans',routine_id:routineId??'',routine_revision:String(revision)})
 const origin=returnDestination(route.query.get('return_to'))??scheme
 const [pending,setPending]=useState(()=>readPending<Pending>(key)),[busy,setBusy]=useState(false),[notFound,setNotFound]=useState(false),lock=useRef(false)
 const state=useRead(valid?'routine-plan:'+identity:null,async()=>{
  const [document,materials,identities,preview]=await Promise.all([routinesApi.read(projectId,routineId!,revision),preparationApi.get(projectId),testIdentitiesApi.list(projectId),reference?checks.preview(projectId,null,null,undefined,reference):routinesApi.preparation(projectId,routineId!,revision).then(value=>value.preview)])
  for(const value of [document,materials,preview])assertProject(value.project_id,projectId)
  identities.forEach(value=>assertProject(value.project_id,projectId))
  if(document.routine_id!==routineId||document.revision!==revision)throw new Error('方案修订与本次范围不一致。')
  return {document,materials,identities,preview}
 })
 const open=(runId:string)=>{savePending(key,undefined);setPending(undefined);refresh();go('/reports?'+new URLSearchParams({run_id:runId,routine_id:routineId!,routine_revision:String(revision),...(bindingId?{binding_id:bindingId}:{}),return_to:origin}),projectId)}
 const act=async(callback:()=>Promise<void>)=>{if(lock.current)return;lock.current=true;setBusy(true);try{await callback()}catch(error){onError(error)}finally{lock.current=false;setBusy(false)}}
 const recover=async()=>{
  if(!pending)return
  const result=await routinesApi.receipt(projectId,pending.reference,pending.fingerprint,pending.operation)
  if(result){assertProject(result.run.project_id,projectId);open(result.run.run_id)}else setNotFound(true)
 }
 const submit=async()=>{
  if(!reference||!state.data?.preview.can_execute)return
  const preview=await checks.preview(projectId,null,null,undefined,reference)
  if(!preview.can_execute||preview.plan_fingerprint!==state.data.preview.plan_fingerprint||pending&&pending.fingerprint!==preview.plan_fingerprint){state.reload();throw new ApiError('STATE_PRECONDITION','方案、应用连接或检查材料已变化，请重新核对。')}
  const request=pending??{operation:operationId(),fingerprint:preview.plan_fingerprint,reference}
  savePending(key,request);setPending(request)
  const result=await checks.submit(projectId,request.fingerprint,request.operation,null,null,undefined,undefined,request.reference)
  assertProject(result.run.project_id,projectId);open(result.run.run_id)
 }
 if(!valid)return <><div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath('/testing?view=plans',projectId)} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}返回检查方案</ActionLink></div><PageError title="核对检查方案" error={new Error('这次检查的方案版本或材料确认信息不完整，请返回方案重新核对。')}/></>
 if(state.loading)return <Loading page/>
 if(!state.data||state.error)return <><div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(scheme,projectId)} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}返回方案继续准备</ActionLink></div><PageError title="核对检查方案" error={state.error}/></>
 const {document,materials,identities,preview}=state.data
 const returnTo='/reports?'+new URLSearchParams({view:'plan',routine_id:routineId!,routine_revision:String(revision),...(bindingId?{binding_id:bindingId}:{}),return_to:origin})
 return <><div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin,projectId)} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}{returnDestinationLabel(origin)}</ActionLink></div><Heading eyebrow={'第 '+document.revision+' 修订'} title={document.name}>开始前，确认要检查的内容和本次所需的材料。</Heading>
  {!reference&&workflow?<RoutinePreparation projectId={projectId} document={document} dirty={false} origin={returnTo} initialSlot={route.query.get('binding_slot')} onBound={binding=>{refresh();go('/reports?'+new URLSearchParams({view:'plan',routine_id:routineId!,routine_revision:String(revision),binding_id:binding.binding_id,return_to:origin}),projectId)}}/>:<>
  {!reference&&<Notice>这次检查还没有确认使用哪些材料。准备完成后，再回到这里预览和运行。</Notice>}
  {pending&&!busy&&<Notice tone="caution">上次提交的结果还未确认。<Button busy={busy} onClick={()=>void act(recover)}>查看上次提交结果</Button>{notFound&&<span>尚未查到原记录；再次提交沿用同一请求。</span>}</Notice>}
  {Boolean(state.error)&&<ErrorNote error={state.error}/>}<PlanWorkspace preview={preview} actions={materials.actions} identities={identities} returnTo={returnTo} changeId={null} initialView={route.query.get('plan_tab')} initialItem={route.query.get('plan_item')}
   scope={<p>使用“{document.name}”第 {document.revision} 次保存的检查内容。需要修改时，请返回方案保存新的版本。</p>} loading={state.loading} busy={busy} pending={Boolean(pending)&&!notFound} error={false} onSubmit={()=>void act(submit)}
   executionAction={!reference?<ActionLink navigationScope="page" href={'#'+scopedPath(origin,projectId)} kind="primary">返回方案继续准备</ActionLink>:undefined} executionExplanation={!reference?'这里只核对准备，不创建运行任务。':undefined}/>
 </>}</>
}
