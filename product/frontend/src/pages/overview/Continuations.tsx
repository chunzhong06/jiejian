import {useState} from 'react'
import {routinesApi} from '../../entities/check/api/routines'
import {repairLabels,type ProjectRepair} from '../../entities/check/api/repairs'
import {useRead} from '../../shared/lib/useRead'
import {scopedPath,withReturnDestination} from '../../shared/lib/navigation'
import {assertProject} from '../../shared/model/page'
import {ErrorNote,Loading} from '../../shared/ui/feedback'
import {ActionLink} from '../../shared/ui/actions'
import {Choice} from '../../shared/ui/Choice'
import {Field} from '../../shared/ui/layout'
import {readPending,savePending} from '../../shared/lib/operations'

export function Continuations({projectId,issues:allIssues,excludeDestination}:{projectId:string;issues?:ProjectRepair['tasks'];excludeDestination?:string}){
 const plans=useRead('home-routines:'+projectId,async signal=>{const value=await routinesApi.catalog(projectId,signal);assertProject(value.project_id,projectId);return value})
 const issues=allIssues?.filter(item=>excludeDestination!=='/issues?issue='+encodeURIComponent(item.task_reference))
 const key='jiejian.home-plan:'+projectId
 const [selected,setSelected]=useState(()=>readPending<string>(key,(value):value is string=>typeof value==='string'))
 // 工作台只选择可复用内容；准确修订进入准备，浏览和选择都不创建运行。
 const choices=plans.data?.routines??[],plan=choices.find(item=>item.routine_id===selected)??choices[0]
 const destination=(path:string)=>'#'+scopedPath(withReturnDestination(path,'/workspace'),projectId)
 return <div className="jj-home-continuations">
  {Boolean(issues?.length)&&<section aria-labelledby="home-issues"><h2 id="home-issues" className="jj-title-group">继续处理已发现的问题</h2><p>有 {issues!.length} 项权限问题需要跟进。沿用原问题和正常访问对照，核对修改是否有效。</p><div className="jj-home-object-list">{issues!.slice(0,2).map(item=>{const problem=item.comparison?.find(row=>row.role==='DENY');return <a className="jj-home-object-link" key={item.task_reference} href={destination('/issues?issue='+encodeURIComponent(item.task_reference))}><div><strong>{problem?.subject_label&&problem.subject_label+' · '}{problem?.action_label??'权限问题'}</strong><small>{repairLabels[item.status]}</small></div></a>})}</div>{issues!.length>2&&<ActionLink href={destination('/issues')}>查看其余 {issues!.length-2} 项问题</ActionLink>}</section>}
  <section aria-labelledby="home-plans"><h2 id="home-plans" className="jj-title-group">再次检查相同内容</h2>{plans.loading?<Loading/>:plans.error?<ErrorNote error={plans.error}/>:plan?<>
   <p>沿用这份方案的检查内容，核对本次应用连接、账号和材料后，再开始检查。</p>
   {choices.length>1?<Field label="沿用哪份检查内容"><Choice aria-label="沿用哪份检查内容" value={plan.routine_id} onValueChange={value=>{setSelected(value);savePending(key,value)}}>{choices.map(item=><option key={item.routine_id} value={item.routine_id}>{item.name}</option>)}</Choice></Field>:<h3 className="jj-home-plan-name">{plan.name}</h3>}
   <p className="jj-home-plan-scope">{plan.scope_kind==='SCENARIO'?'这份方案会检查已保存的完整业务场景。':'将检查 '+plan.permission_count+' 条权限要求。'}</p>
   <footer><ActionLink kind="default" aria-label={'准备这次检查：'+plan.name} href={destination('/reports?'+new URLSearchParams({view:'plan',routine_id:plan.routine_id,routine_revision:String(plan.revision)}))}>准备这次检查</ActionLink></footer>
  </>:<><p>把常用的权限要求保存为检查方案，下次就能沿用这些内容，再准备本次的账号和材料。</p><ActionLink href={destination('/testing?view=plans')}>设置检查方案</ActionLink></>}</section>
 </div>
}
