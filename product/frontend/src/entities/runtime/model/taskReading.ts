import {purposeLabels,type CollaborationTask,type CollaborationPurpose,type CollaborationBrief,type CollaborationQuestion} from '../api/collaboration'

type TaskName={goal:string;purpose?:CollaborationPurpose;brief?:CollaborationBrief|null}
/** 旧长目标不截句猜含义；短名称来自明确说明、原短目标或任务用途。 */
export const collaborationTitle=(task:TaskName)=>task.brief?.title||(task.goal.length<=80?task.goal:task.purpose?purposeLabels[task.purpose]:'协作任务')
export const questionTitle=(question:CollaborationQuestion)=>question.presentation?.title||(question.question.length<=80?question.question:'补充任务信息')

const products={FLOW:{capability:'flows.save',label:'操作流程'},PROOF:{capability:'proofs.save',label:'结果判断方式'},SCENARIO:{capability:'scenarios.save',label:'业务实验'}} as const
export function collaborationOutputs(task:CollaborationTask){
 const operations=task.operations.slice(task.goal_operation_baseline??0)
 const outputs=task.brief?.outputs.length?task.brief.outputs:Object.entries(products).filter(([,type])=>operations.some(item=>item.capability===type.capability&&item.state==='SUCCEEDED')).map(([kind,type])=>({kind:kind as keyof typeof products,label:type.label}))
 return outputs.map(output=>{
  const type=products[output.kind],ids=new Set<string>()
  for(const operation of operations){
   if(operation.capability!==type.capability||operation.state!=='SUCCEEDED'||!operation.result||typeof operation.result!=='object')continue
   const result=operation.result as Record<string,unknown>,id=output.kind==='PROOF'?result.source_id:result.id
   if(typeof id==='string'&&typeof result.revision==='number')ids.add(id)
  }
  return {...output,saved:ids.size}
 })
}
