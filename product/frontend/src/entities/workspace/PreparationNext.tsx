import {TaskActions} from '../../shared/ui/layout'
import type {CheckPreview} from '../check/api/currentChecks'
import {taskDestination} from './taskDestination'
import {useWorkflow} from '../../shared/lib/workflow'
import {Button} from '../../shared/ui/actions'

export function PreparationNext({preview,onReview,official=false}:{preview:CheckPreview;onReview:()=>void;official?:boolean}){
 const workflow=useWorkflow()
 // 建议与范围来自同一次预览；旧建议不能配给同ID的新修订，也不另读全动作的缺口。
 const work=preview.preparation_work?.project_id===preview.project_id&&preview.preparation_work.plan_fingerprint===preview.plan_fingerprint?preview.preparation_work:undefined
 const task=work?.primary_task
 const member=work?.impacts.find(item=>item.action_id===task?.business_action_id&&item.kind==='evidence'&&item.member_id===task?.effect_id)
 const title=task?.task_kind==='COMPLETE_EFFECT_EVIDENCE'&&member?.member_label?`设置“${member.member_label}”的判断依据`:task?.title
 const kept=[...new Set(work?.impacts.filter(item=>item.status==='SATISFIED').map(item=>item.member_label||({identity:'测试账号',execution:'操作步骤',resource:'测试数据',evidence:'结果证明',recovery:'恢复方式'}[item.kind]))??[])]
 return <TaskActions separated note={<div><strong>{official?'为示例备齐检查材料':title??'继续核对待准备事项'}</strong><p className="jj-small jj-muted">{official?'准备本次所需的示例账号、操作和结果证明。':task?.user_responsibility??'只准备当前检查范围内的材料。'}{!official&&kept.length>0?' 可沿用：'+kept.slice(0,3).join('、')+(kept.length>3?'等。':'。'):''}</p></div>}><Button kind="primary" onClick={()=>official&&workflow?workflow.open('/preparation?prepare_example=1'):task&&workflow?workflow.open(taskDestination(task)):onReview()}>{official?'一键准备示例材料':task?.action_label??'核对待准备事项'}</Button></TaskActions>
}
