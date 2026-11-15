import type {FlowDraftDto} from '../api/recordings'
import {Badge} from '../../../shared/ui/feedback'
import {ObjectIdentity,SectionHeading} from '../../../shared/ui/layout'

/** 按真实采集顺序解释草稿；只展示已确认来源，不把候选或请求成功当作业务结论。 */
export function RecordingSteps({draft,action}:{draft:FlowDraftDto;action:string}){
 return <section className="jj-recording-reading" aria-label="采集到的操作顺序">
  <SectionHeading title="采集到的操作顺序" appearance="group"/>
  <ol className="jj-recording-steps">{draft.steps.map(step=>{
   const target=step.id===draft.target_step_id
   const sources=(draft.variables??[]).filter(variable=>variable.status==='CONFIRMED'&&variable.confirmed_source?.source_step_id===step.id)
   return <li key={step.id}><ObjectIdentity name={<strong>{target?action:step.name}</strong>} status={target?<Badge tone="accent">本次操作</Badge>:undefined}/>
    {sources.length>0&&<p className="jj-small jj-muted">后续操作会沿用这一步读取的内容，已确认 {sources.length} 项来源。</p>}
    {(step.method||step.path)&&<details className="jj-recording-request"><summary>核对请求</summary><code>{step.method} {step.path}</code></details>}
   </li>
  })}</ol>
 </section>
}
