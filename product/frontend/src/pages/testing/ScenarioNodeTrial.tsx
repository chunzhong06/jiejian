import type {ScenarioContext,ScenarioInvocation} from '../../entities/preparation/api/businessScenarios'
import {operationFlowsApi} from '../../entities/preparation/api/operationFlows'
import {FlowTrialPanel} from '../../entities/preparation/ui/FlowTrialPanel'
import {useRead} from '../../shared/lib/useRead'
import {TaskSurface} from '../../shared/ui/TaskSurface'
import {Loading,ErrorNote} from '../../shared/ui/feedback'
import type {ScenarioOption} from './ScenarioResources'

export function ScenarioNodeTrial({projectId,node,option,context,onClose}:{projectId:string;node:ScenarioInvocation;option:ScenarioOption;context:ScenarioContext;onClose:()=>void}){
  const reference=option.action.trial_flow!
  const flow=useRead('scenario-node-flow:'+projectId+':'+reference.flow_id+':'+reference.revision,signal=>operationFlowsApi.read(projectId,reference.flow_id,reference.revision,signal))
  return <TaskSurface title={'单独试运行 · '+node.label} onBack={onClose} backLabel="返回场景草稿">
    <dl className="jj-facts jj-scenario-trial-scope" data-layout="columns"><div><dt>执行范围</dt><dd>当前动作及其已有准备步骤<p className="jj-small jj-muted">本实验的前序节点不执行。</p></dd></div><div><dt>草稿与结果</dt><dd>保留场景草稿<p className="jj-small jj-muted">试运行不采用草稿，权限结论由正式检查提供。</p></dd></div></dl>
    {flow.loading&&!flow.data?<Loading/>:!flow.data?<ErrorNote error={flow.error} onRetry={flow.reload} retryLabel="重新读取场景操作"/>:<FlowTrialPanel projectId={projectId} flow={flow.data} actionLabel={option.action.label} accounts={context.identities} showHeading={false} mode="current" initialSelection={{flow_id:reference.flow_id,revision:reference.revision,subject_identity_id:option.value.subject_test_identity_id!,resource_owner_identity_id:option.value.resource_owner_test_identity_id,resource_id:option.value.resource_id}}/>}
    <p className="jj-small jj-muted jj-scenario-trial-lifecycle">先预览本次账号、资源和恢复请求，再确认执行。关闭窗口不会取消已提交的任务。</p>
  </TaskSurface>
}
