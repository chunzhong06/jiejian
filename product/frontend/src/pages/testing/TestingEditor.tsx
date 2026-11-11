import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import {useWorkflow} from '../../shared/lib/workflow'
import {flowTrialsApi} from '../../entities/preparation/api/flowTrials'
import {operationFlowsApi} from '../../entities/preparation/api/operationFlows'
import {workbenchApi} from '../../entities/application/api/workbench'
import {OperationFlowEditor} from '../../entities/preparation/ui/OperationFlowEditor'
import {useRead} from '../../shared/lib/useRead'
import {go,returnDestination,returnDestinationLabel} from '../../shared/lib/navigation'
import type {PageProps} from '../../shared/model/page'
import {PageError} from '../../shared/ui/feedback'

export function TestingEditor({projectId,route,actionId}:PageProps&{actionId:string}) {
  const workflow=useWorkflow()
  const trialId=route.query.get('trial_id'),sourceId=route.query.get('source_id'),requestId=route.query.get('request_id')
  const flowId=route.query.get('flow_id'),revision=route.query.get('revision')
  const origin=returnDestination(route.query.get('return_to')),resumeDraft=route.query.get('resume_draft')==='1'
  // 编辑器持有场景上下文；此处只读取路由明确要求恢复的试运行或来源。
  const state=useRead(trialId||sourceId||flowId&&revision?'testing-seed:'+projectId+':'+route.query.toString():null,signal=>Promise.all([
    trialId?flowTrialsApi.read(projectId,trialId,signal):Promise.resolve(undefined),
    sourceId&&requestId?workbenchApi.sources(projectId,signal,sourceId):Promise.resolve(undefined),
    flowId&&revision?operationFlowsApi.read(projectId,flowId,Number(revision),signal):Promise.resolve(undefined)
  ]))
  if(state.loading)return <PageSkeleton view="/testing" title="接口流程"/>
  if(state.error)return <PageError title="接口流程" error={state.error}/>
  const [trial,sources,flow]=state.data??[]
  if(flow&&flow.business_action_id!==actionId)return <PageError title="接口流程" error={new Error('这份流程不属于当前业务操作，请返回原任务核对。')}/>
  const initial=sources?.sources.find(item=>item.source_id===sourceId)?.requests.find(item=>item.item_id===requestId)
  return <OperationFlowEditor projectId={projectId} actionId={actionId} candidateFlow={route.query.get('review')==='1'?flow:undefined} initialFlow={resumeDraft?undefined:flow&&route.query.get('review')!=='1'?flow:trial?.request.plan.flow.business_action_id===actionId?trial.request.plan.flow:undefined} initialTrialId={trialId??undefined} initialRequest={initial} initialSource={sources?.request_references.find(item=>item.source_id===sourceId&&item.item_id===requestId)} backLabel={workflow?'返回本次检查':origin?returnDestinationLabel(origin):'返回操作与材料'} onBack={()=>workflow?workflow.finish():go(origin??'/testing',projectId)}/>
}
