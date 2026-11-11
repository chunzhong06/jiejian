import {TaskActions} from '../../shared/ui/layout'
import {Progress} from '../../shared/ui/Progress'
import {taskDestination} from '../../entities/workspace/taskDestination'
import type {WorkspaceViewDto} from '../../entities/workspace/api/workspace'
import type {OfficialExperienceDto} from '../../entities/application/api/experience'
import {repairsApi} from '../../entities/check/api/repairs'
import {currentChecksApi} from '../../entities/check/api/currentChecks'
import {ActionLink} from '../../shared/ui/actions'
import {Heading} from '../../shared/ui/layout'
import {Badge,Loading,ErrorNote,Status} from '../../shared/ui/feedback'
import type {PageProps} from '../../shared/model/page'
import {scopedPath,withReturnDestination} from '../../shared/lib/navigation'
import {useRead} from '../../shared/lib/useRead'
import './workbench.css'

export function Home({projectId,workspace,experience}:PageProps&{workspace:WorkspaceViewDto|null;experience:OfficialExperienceDto|null}){
  const task=workspace?.primary_task,active=workspace?.active_check
  const history=useRead('home-history:'+projectId,signal=>currentChecksApi.history(projectId,{},signal))
  const repair=useRead(task?.repair?'home-repair:'+projectId:null,()=>repairsApi.project(projectId))
  const problem=repair.data?.tasks.find(item=>task?.repair?.repair_fingerprint===item.contract.repair_fingerprint)?.comparison?.find(item=>item.role==='DENY')
  const taskTitle=problem&&['PREPARE_AGENT_REPAIR','VERIFY_REPAIR'].includes(task?.task_kind??'')?`${task?.task_kind==='VERIFY_REPAIR'?'复验':'处理'}${problem.subject_label??''}${problem.action_label}的问题`:task?.title
  const action=workspace?.actions?.find(item=>item.action_id===task?.business_action_id)
  const actor=workspace?.actors?.find(item=>item.actor_id===task?.business_actor_id)
  const taskObject=[action?.display_name,actor?.display_name].filter(Boolean).join(' · ')
  const running=active&&['QUEUED','RUNNING'].includes(active.run.lifecycle)
  const stopped=experience?.project_id===projectId&&!experience.active
  const destination=running?'/reports?run_id='+active.run.run_id:task?taskDestination(task):'/permissions'
  const result=!running&&task?.task_kind==='VIEW_CURRENT_RESULT'&&workspace&&workspace.latest_result?.run_id===task.run_id?workspace.latest_result:null
  const recent=history.data?.items.filter(item=>item.status.result_integrity==='VALID'&&item.status.run.run_id!==result?.run_id).slice(0,4)
  const detail=running?'检查在后台执行，可以离开此页，稍后查看结果。':stopped?'重启后可沿用已保存的权限、场景和报告。':task?task.why_now:'先确认角色、操作和数据范围，再准备检查材料。'
  const href=(path:string)=>'#'+scopedPath(withReturnDestination(path,'/workspace'),projectId)
  return <div className="jj-home-layout" data-page-pending={!workspace||history.loading||undefined}>
    <Heading title="工作台"/>
    <section className="jj-home-current-task" aria-labelledby="home-current-task">
      <div className="jj-home-task-copy"><p className="jj-eyebrow">{running?'正在检查':stopped?'示例已停止':taskObject||'当前工作'}</p>
      <h2 id="home-current-task">{running?'正在检查访问权限':stopped?'继续'+experience.display_name:taskTitle??(workspace?'设置应用的访问权限要求':'正在读取应用状态')}</h2>
      <p className="jj-home-task-description">{detail}</p>
      {task?.unavailable_reason&&<p className="jj-small jj-muted">{task.user_responsibility}</p>}
      {result&&<div className="jj-home-task-result"><Badge tone={result.verdict==='PASS'?'positive':result.verdict==='BLOCK'?'negative':'caution'}>{result.verdict==='PASS'?'本轮符合规则':result.verdict==='BLOCK'?'本轮不符合规则':'本轮证据不足'}</Badge><p>{result.summary}</p></div>}
      {running&&active.progress&&<div className="jj-home-task-progress"><span>{active.progress.planned_cases>0?`已完成 ${active.progress.completed_cases} / ${active.progress.planned_cases} 项`:'正在整理检查事项'}</span><Progress label="检查进度" value={active.progress.planned_cases>0?active.progress.completed_cases:undefined} max={active.progress.planned_cases} active/></div>}
      </div>
      <TaskActions><ActionLink kind="primary" href={href(stopped?'/environment':destination)}>{running?'查看进度':stopped?'打开示例环境':task?.action_label??'查看权限规则'}</ActionLink></TaskActions>
    </section>
    <section className="jj-home-check-history" aria-labelledby="home-recent-checks"><header><h2 id="home-recent-checks" className="jj-title-group">{result?'更早的检查':'最近检查'}</h2>{Boolean(recent?.length)&&<ActionLink href={href('/reports')}>全部检查记录</ActionLink>}</header>
      {history.error?<ErrorNote error={history.error}/>:history.loading?<Loading/>:recent?.length?<div className="jj-home-check-list">{recent.map(item=><a className="jj-home-check-row" key={item.status.run.run_id} href={href('/reports?run_id='+item.status.run.run_id)}><Status className="jj-home-check-outcome" tone={item.status.run.verdict==='PASS'?'positive':item.status.run.verdict==='BLOCK'?'negative':'caution'}>{item.status.run.verdict==='PASS'?'符合规则':item.status.run.verdict==='BLOCK'?'不符合规则':'证据不足'}</Status><div><strong>{item.action_labels.join('、')||'权限检查'}</strong><p><time>{new Date(item.status.run.created_at_us/1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})}</time><span>{item.change_id?'修改后检查':'常规检查'}</span></p></div></a>)}</div>:<p className="jj-small jj-muted">{result?'后续检查会持续保留各轮范围和依据。':'尚无检查记录。完成准备后的结果会保留在这里。'}</p>}
    </section>
    {repair.error&&<ErrorNote error={repair.error}/>}
  </div>
}
