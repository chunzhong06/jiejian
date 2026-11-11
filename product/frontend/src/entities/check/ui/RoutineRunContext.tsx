import type {RoutineReference,RunEnvironment} from '../api/routines'
import {routinesApi} from '../api/routines'
import {useRead} from '../../../shared/lib/useRead'
import {scopedPath,withReturnDestination} from '../../../shared/lib/navigation'
import {ActionLink} from '../../../shared/ui/actions'
import {assertProject} from '../../../shared/model/page'

export function RoutineRunContext({projectId,routine,environment,origin,readOnly=false}:{projectId:string;routine?:RoutineReference|null;environment?:RunEnvironment|null;origin:string;readOnly?:boolean}){
 const state=useRead('run-plan:'+projectId+':'+routine?.routine_id+':'+routine?.revision,async()=>{if(!routine||readOnly)return null;const value=await routinesApi.read(projectId,routine.routine_id,routine.revision);assertProject(value.project_id,projectId);return value})
 if(!routine&&!environment)return null
 const destination=routine&&withReturnDestination('/testing?'+new URLSearchParams({view:'plans',routine_id:routine.routine_id,routine_revision:String(routine.revision),section:'binding'}),origin)
 return <div className="jj-run-context">
  {routine&&<span>{destination&&!readOnly?<ActionLink href={'#'+scopedPath(destination,projectId)}>{state.data?.name??'检查方案'} · 第 {routine.revision} 次保存的内容</ActionLink>:<>检查方案 · 第 {routine.revision} 次保存的内容</>}</span>}
  {environment&&<span>检查连接：{environment.name}{environment.deployment_label?' · 部署声明 '+environment.deployment_label:''}</span>}
 </div>
}
