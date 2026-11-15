import type {RoutineRequirement} from '../api/routines'

export const routineMaterialNames={ACCOUNT:'测试账号',RESOURCE:'测试资源',FLOW:'业务操作步骤',PROOF:'业务结果证明'} as const

/** 相同名称的资源仍按准确操作修订区分，不因展示名称相同合并材料槽位。 */
export function routineRequirementLabel(item:RoutineRequirement,requirements:RoutineRequirement[]){
 if(item.kind==='ACCOUNT')return item.label.endsWith('账号')?item.label:item.label+'的测试账号'
 if(item.kind!=='RESOURCE')return item.label
 const action=requirements.find(value=>value.kind==='FLOW'&&value.action?.action_id===item.action?.action_id&&value.action?.revision===item.action?.revision)
 return action?item.label+' · '+action.label:item.label
}
