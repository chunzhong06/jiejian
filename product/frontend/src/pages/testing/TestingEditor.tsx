import {flowTrialsApi} from '../../entities/preparation/api/flowTrials'
import {operationFlowsApi} from '../../entities/preparation/api/operationFlows'
import {workbenchApi} from '../../entities/application/api/workbench'
import {OperationFlowEditor} from '../../entities/preparation/ui/OperationFlowEditor'
import {useRead} from '../../shared/lib/useRead'
import {go} from '../../shared/lib/navigation'
import type {PageProps} from '../../shared/model/page'
import {PageError, Loading} from '../../shared/ui/feedback'

export function TestingEditor({projectId,route,actionId}:PageProps&{actionId:string}) {
  const trialId=route.query.get('trial_id'),sourceId=route.query.get('source_id'),requestId=route.query.get('request_id')
  const flowId=route.query.get('flow_id'),revision=route.query.get('revision')
  // 编辑器持有场景上下文；此处只读取路由明确要求恢复的试运行或来源。
  const state=useRead(trialId||sourceId||flowId&&revision?'testing-seed:'+projectId+':'+route.query.toString():null,signal=>Promise.all([
    trialId?flowTrialsApi.read(projectId,trialId,signal):Promise.resolve(undefined),
    sourceId&&requestId?workbenchApi.sources(projectId,signal,sourceId):Promise.resolve(undefined),
    flowId&&revision?operationFlowsApi.read(projectId,flowId,Number(revision),signal):Promise.resolve(undefined)
  ]))
  if(state.loading)return <Loading page/>
  if(state.error)return <PageError title="接口流程" error={state.error}/>
  const [trial,sources,flow]=state.data??[]
  if(flow&&flow.business_action_id!==actionId)return <PageError title="接口流程" error={new Error('这份流程不属于当前业务操作，请返回原任务核对。')}/>
  const initial=sources?.sources.find(item=>item.source_id===sourceId)?.requests.find(item=>item.item_id===requestId)
  return <OperationFlowEditor projectId={projectId} actionId={actionId} candidateFlow={route.query.get('review')==='1'?flow:undefined} initialFlow={flow&&route.query.get('review')!=='1'?flow:trial?.request.plan.flow.business_action_id===actionId?trial.request.plan.flow:undefined} initialTrialId={trialId??undefined} initialRequest={initial} initialSource={sources?.request_references.find(item=>item.source_id===sourceId&&item.item_id===requestId)} onBack={()=>go('/testing',projectId)}/>
}
