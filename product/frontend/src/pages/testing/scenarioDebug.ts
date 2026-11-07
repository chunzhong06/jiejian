import type {BusinessScenario,ScenarioExperiment} from '../../entities/preparation/api/businessScenarios'

// 调试范围另存为准确修订；保留完整正常对照，不修改原场景或偷偷提交目标请求。
export function scenarioDebugSnapshot(document:BusinessScenario,experiment:ScenarioExperiment,id:string,through?:string):BusinessScenario{
  if(through&&experiment.kind!=='NORMAL')throw new Error('变体需要保留完整结构和正常对照，请预览整个实验。')
  const index=through?experiment.invocations.findIndex(node=>node.id===through):-1
  if(through&&index<0)throw new Error('所选步骤已变化，请重新选择。')
  const selected={...experiment,invocations:through?experiment.invocations.slice(0,index+1):experiment.invocations}
  const control=experiment.control_experiment_id?document.experiments.find(item=>item.id===experiment.control_experiment_id):undefined
  if(experiment.kind!=='NORMAL'&&!control)throw new Error('缺少完整正常对照，不能单独检查这个变体。')
  return {...structuredClone(document),id,revision:1,label:(document.label+' · '+experiment.label+(through?' · 到第 '+(index+1)+' 步':'')).slice(0,128),
    description:'独立调试范围；从原场景草稿整理。执行前仍须预览并确认账号、资源、预算和恢复安排。',experiments:structuredClone(control?[control,selected]:[selected])}
}
