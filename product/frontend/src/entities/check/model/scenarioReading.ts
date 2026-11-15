import type {ActionResultStory} from '../api/currentChecks'
import {subject} from './checks'
import {text} from '../../../shared/lib/format'

/** 只组织封存名称；包含关系仅消除重复文字，不推断实验用途或业务结论。 */
export function scenarioReading(action:ActionResultStory){
  const role=subject(action),account=text(action.fact_comparison.planned_identity.label??'')
  const identity=!account||role.includes(account)?role:account.includes(role)?account:role+' '+account
  const operation=text(action.display_name),title=identity+' · '+operation,context=action.scenario_context
  const compact=(value:string)=>value.replace(/\s+/g,'')
  const labels=[{label:'业务实验',value:context?.experiment_label},{label:'执行安排',value:context?.invocation_label}]
    .filter((item):item is {label:string;value:string}=>Boolean(item.value?.trim())).map(item=>({...item,value:text(item.value)}))
    .filter((item,index,values)=>!compact(title).includes(compact(item.value))&&!values.some((other,otherIndex)=>otherIndex!==index&&compact(other.value).includes(compact(item.value))&&(compact(other.value)!==compact(item.value)||otherIndex<index)))
  const batch=context&&context.item_count>1?`${context.batch_strategy==='ATOMIC'?'整批原子处理':context.batch_strategy==='PER_ITEM'?'逐项处理':'批量操作'}，第 ${context.item_index} / ${context.item_count} 项资源`:null
  return {title,labels,batch}
}
