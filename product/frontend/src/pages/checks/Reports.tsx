import './styles.css'
import './workspace.css'
import type {ReportsProps} from './types'
import {History} from './History'
import {Plan} from './CheckPlan'
import {Run} from './CheckRun'

export function Reports(props:ReportsProps){
  const runId=props.route.query.get('run_id'),plan=props.route.query.get('view')==='plan'
  return runId?<Run key={runId} {...props} runId={runId}/>:plan&&!props.archive?<Plan {...props}/>:<History key={props.projectId+':'+props.route.query.get('intent_id')} {...props}/>
}
