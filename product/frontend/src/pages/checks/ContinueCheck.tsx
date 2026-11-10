import {useEffect,useRef} from 'react'
import {currentChecksApi,type CheckContinuation} from '../../entities/check/api/currentChecks'
import {assertProject,type PageProps} from '../../shared/model/page'
import {useRead} from '../../shared/lib/useRead'
import {replaceDestination,returnDestination,scopedPath} from '../../shared/lib/navigation'
import {operationId,savePending} from '../../shared/lib/operations'
import {Heading} from '../../shared/ui/layout'
import {ActionLink} from '../../shared/ui/actions'
import {Loading,PageError} from '../../shared/ui/feedback'

/** 原运行只提供范围引用，点击后进入新预览，不携带旧操作编号、授权或秘密。 */
export function ContinueCheck({projectId,route}:PageProps){
 const run=route.query.get('resume_run')!,origin=returnDestination(route.query.get('return_to'))??'/reports?run_id='+encodeURIComponent(run)
 const state=useRead('continue:'+projectId+':'+run,async signal=>{const value=await currentChecksApi.continuation(projectId,run,signal);assertProject(value.project_id,projectId);if(value.run_id!==run)throw new Error('检查记录引用不一致');return value})
 const restored=useRef(false)
 useEffect(()=>{if(state.data?.state==='AVAILABLE'&&!restored.current){restored.current=true;replaceDestination(continuationDestination(projectId,state.data,origin),projectId)}},[state.data,projectId,origin])
 if(state.loading&&!state.data)return <Loading page/>
 if(!state.data)return <PageError title="找回原检查范围" error={state.error}/>
 const value=state.data
 if(value.state==='AVAILABLE')return <Loading page/>
 return <><Heading eyebrow="继续已有工作" title="重新核对原检查">沿用原检查范围，重新核对当前材料。</Heading>
  <section className="jj-panel"><h2>{value.state==='WAITING'?'原运行尚未结束':'原检查范围暂时无法恢复'}</h2>
   <p>{value.state==='WAITING'?'这次检查仍沿原记录执行。查看进度或处理停止请求后，再重新核对范围。':value.message}</p>
   <footer className="jj-task-actions"><ActionLink href={'#'+scopedPath(origin)} kind="primary">{value.state==='WAITING'?'查看原检查进度':'返回原记录'}</ActionLink></footer>
  </section></>
}

/** 仅重建公开选择；新预览仍核对当前绑定，不复用旧执行指纹。 */
export function continuationDestination(projectId:string,value:CheckContinuation,origin:string){
  const query=new URLSearchParams({view:'plan',return_to:origin})
  if(value.external_recheck&&value.repair)return '/issues?'+new URLSearchParams({repair_reference:value.repair.repair_fingerprint,source_run_id:value.repair.source_run_id,source_case_id:value.repair.source_case_id,section:'repair',return_to:origin})
  if(value.routine){query.set('routine_id',value.routine.routine_id);query.set('routine_revision',String(value.routine.revision));query.set('binding_id',value.routine.binding_id)}
  if(value.change_id)query.set('change_id',value.change_id)
  if(value.scenario){query.set('scenario_id',value.scenario.scenario_id);query.set('scenario_revision',String(value.scenario.revision))}
  if(!value.routine&&!value.change_id&&!value.scenario){const scope=operationId();savePending(`jiejian.studio.scope:${projectId}:${scope}`,{refs:value.permissions});query.set('scope_id',scope)}
  if(value.repair)query.set('repair_reference',value.repair.repair_fingerprint)
  return '/reports?'+query
}
