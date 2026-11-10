import type {CheckPreview} from '../check/api/currentChecks'
import {workspaceApi} from './api/workspace'
import {taskDestination} from './taskDestination'
import {useRead} from '../../shared/lib/useRead'
import {assertProject} from '../../shared/model/page'
import {useWorkflow} from '../../shared/lib/workflow'
import {Button} from '../../shared/ui/actions'
import {ErrorNote} from '../../shared/ui/feedback'

export function PreparationNext({preview,onReview,official=false}:{preview:CheckPreview;onReview:()=>void;official?:boolean}){
 const workflow=useWorkflow()
 const ids=[...new Set([...preview.actions.map(item=>item.action_id),...preview.gaps.map(item=>item.action_id)])].sort()
 const state=useRead(ids.length?'work-preparation:'+preview.project_id+':'+ids.join(','):null,async signal=>{
  const value=await workspaceApi.preparation(preview.project_id,ids,signal);assertProject(value.project_id,preview.project_id);return value
 })
 const task=state.data?.primary_task
 return <footer className="jj-plan-review-confirm"><div><strong>{official?'为示例备齐检查材料':task?task.title:state.loading?'正在核对本次准备':'继续核对待准备事项'}</strong><p className="jj-small jj-muted">{official?'准备本次所需的示例账号、操作和结果证明。':task?.user_responsibility??'只准备当前检查范围内的材料。'}</p>{state.error&&<ErrorNote error={state.error}/>}</div><Button kind="primary" disabled={state.loading} onClick={()=>official&&workflow?workflow.open('/preparation?prepare_example=1'):task?workflow?.open(taskDestination(task)):onReview()}>{official?'一键准备示例材料':task?.action_label??'核对待准备事项'}</Button></footer>
}
