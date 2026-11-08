import type {CheckPreview} from '../check/api/currentChecks'
import {workspaceApi} from './api/workspace'
import {taskDestination} from './taskDestination'
import {useRead} from '../../shared/lib/useRead'
import {assertProject} from '../../shared/model/page'
import {useWorkflow} from '../../shared/lib/workflow'
import {Button} from '../../shared/ui/actions'
import {ErrorNote} from '../../shared/ui/feedback'

export function PreparationNext({preview,onReview}:{preview:CheckPreview;onReview:()=>void}){
 const workflow=useWorkflow()
 const ids=[...new Set([...preview.actions.map(item=>item.action_id),...preview.gaps.map(item=>item.action_id)])].sort()
 const state=useRead(ids.length?'work-preparation:'+preview.project_id+':'+ids.join(','):null,async signal=>{
  const value=await workspaceApi.preparation(preview.project_id,ids,signal);assertProject(value.project_id,preview.project_id);return value
 })
 const task=state.data?.primary_task
 return <footer className="jj-plan-review-confirm"><div><strong>{task?task.title:state.loading?'正在核对本次准备':'继续核对待准备事项'}</strong><p className="jj-small jj-muted">{task?.user_responsibility??'只处理本次检查范围中的材料，已有内容继续保留。'}</p>{state.error&&<ErrorNote error={state.error}/>}</div><Button kind="primary" disabled={state.loading} onClick={()=>task?workflow?.open(taskDestination(task)):onReview()}>{task?.action_label??'核对待准备事项'}</Button></footer>
}
