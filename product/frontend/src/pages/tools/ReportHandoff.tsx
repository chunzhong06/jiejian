import {currentChecksApi} from '../../entities/check/api/currentChecks'
import {actual,judgement,judgementLabels,owner,requirement,subject,resultTitle} from '../../entities/check/model/checks'
import {assertProject} from '../../shared/model/page'
import {useRead} from '../../shared/lib/useRead'
import {text} from '../../shared/lib/format'
import {ObjectHeading,TaskActions} from '../../shared/ui/layout'
import {Badge,ErrorNote,Loading} from '../../shared/ui/feedback'
import {ActionLink,Button} from '../../shared/ui/actions'

/** 交接引用读取冻结报告来解释具体对象；缺失原事项时不改用其他结果。 */
export function ReportHandoff({projectId,runId,caseId,repairPath,href}:{projectId:string;runId:string;caseId?:string;repairPath?:string;href:(path:string)=>string}){
 const state=useRead('collaboration-report:'+projectId+':'+runId+':'+caseId,async signal=>{
  const story=await currentChecksApi.story(runId,signal);assertProject(story.project_id,projectId)
  if(caseId&&!story.actions.some(item=>item.case_id===caseId))throw new Error('交接的检查事项不在这份报告中，请核对原交接位置。')
  return story
 })
 if(state.loading)return <Loading>正在读取交接的检查事项</Loading>
 if(!state.data)return <div><ErrorNote error={state.error}/><Button onClick={state.reload}>重新读取交接报告</Button></div>
 const story=state.data,action=caseId?story.actions.find(item=>item.case_id===caseId):undefined
 const path='/reports?'+new URLSearchParams({run_id:runId,...(caseId?{case_id:caseId}:{})})
 return <article className="jj-handoff-report" aria-label="交接的检查依据">
  {state.error&&<ErrorNote error={state.error} onRetry={state.reload} retryLabel="重新读取交接报告"/>}
  <ObjectHeading level={3} title={action?subject(action)+' · '+text(action.display_name):resultTitle(story)} status={action&&<Badge tone={judgement(action)}>{judgementLabels[judgement(action)]}</Badge>} description={action&&<span>{owner(action)}的资源 · {text(action.fact_comparison.resource_id??'资源尚未确认')}</span>}/>
  {action?<div className="jj-handoff-comparison"><section><h4 className="jj-title-caption">当时的访问要求</h4><p>{requirement(action)}</p></section><section><h4 className="jj-title-caption">实际观察到的结果</h4><ul>{action.fact_comparison.effects.map(effect=><li key={effect.effect_id}>{actual(effect)}</li>)}</ul></section></div>:<p className="jj-muted">{[...new Set(story.actions.map(item=>text(item.display_name)))].join('、')||'报告未保留可读的业务事项'}</p>}
  <TaskActions>{repairPath&&<ActionLink href={href(repairPath)}>继续处理这项问题</ActionLink>}<ActionLink kind="primary" href={href(path)}>阅读这项检查与证据</ActionLink></TaskActions>
 </article>
}
