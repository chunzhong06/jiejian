import type {ScenarioContext,ScenarioInvocation} from '../../entities/preparation/api/businessScenarios'
import {operationFlowsApi} from '../../entities/preparation/api/operationFlows'
import {FlowTrialPanel} from '../../entities/preparation/ui/FlowTrialPanel'
import {useRead} from '../../shared/lib/useRead'
import {Dialog} from '../../shared/ui/Dialog'
import {Loading,ErrorNote} from '../../shared/ui/feedback'
import type {ScenarioOption} from './ScenarioResources'

export function ScenarioNodeTrial({projectId,node,option,context,onClose}:{projectId:string;node:ScenarioInvocation;option:ScenarioOption;context:ScenarioContext;onClose:()=>void}){
  const reference=option.action.trial_flow!
  const flow=useRead('scenario-node-flow:'+projectId+':'+reference.flow_id+':'+reference.revision,signal=>operationFlowsApi.read(projectId,reference.flow_id,reference.revision,signal))
  return <Dialog title={'单独试运行 · '+node.label} onClose={onClose} size="wide">
    <p className="jj-small jj-muted">只执行当前动作及其已有准备步骤，不执行本实验的前序节点。先预览本次账号、资源和恢复请求，再确认执行；试运行不采用草稿，也不提供权限结论。关闭窗口不会取消已提交的任务。</p>
    {flow.loading&&!flow.data?<Loading/>:!flow.data?<ErrorNote error={flow.error}/>:<FlowTrialPanel projectId={projectId} flow={flow.data} accounts={context.identities} initialSelection={{flow_id:reference.flow_id,revision:reference.revision,subject_identity_id:option.value.subject_test_identity_id!,resource_owner_identity_id:option.value.resource_owner_test_identity_id,resource_id:option.value.resource_id}}/>}
  </Dialog>
}
