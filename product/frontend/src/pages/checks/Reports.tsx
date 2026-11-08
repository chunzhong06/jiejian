import './styles.css'
import './workspace.css'
import type {ReportsProps} from './types'
import {History} from './History'
import {Plan} from './CheckPlan'
import {Run} from './CheckRun'
import {RoutinePlan} from './RoutinePlan'
import {Comparison} from './Comparison'

export function Reports(props:ReportsProps){
  if(props.route.query.get('view')==='compare')return <Comparison {...props}/>
  const runId=props.route.query.get('run_id'),plan=props.route.query.get('view')==='plan'
  // 同页深链接也可能换检查对象；只重建范围身份，局部分类切换不重建任务。
  const planKey=JSON.stringify([props.projectId,...['scope_id','rule_id','change_id','scenario_id','scenario_revision','routine_id','routine_revision','binding_id'].map(key=>props.route.query.get(key))])
  const routine=['routine_id','routine_revision','binding_id'].some(key=>props.route.query.has(key))
  return runId?<Run key={runId} {...props} runId={runId}/>:plan&&!props.archive?routine?<RoutinePlan key={planKey} {...props}/>:<Plan key={planKey} {...props}/>:<History key={props.projectId+':'+props.route.query.get('intent_id')} {...props}/>
}
