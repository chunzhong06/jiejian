import type {CollaborationTask} from '../../entities/runtime/api/collaboration'
import {editorDraft} from '../../entities/runtime/model/handoff'
import {operationFlowsApi} from '../../entities/preparation/api/operationFlows'
import {testIdentitiesApi} from '../../entities/preparation/api/testIdentities'
import {FlowComparison,flowDraftKey,type FlowComparisonBaseline} from '../../entities/preparation/ui/FlowCandidateReview'
import type {FlowEditorDraft} from '../../entities/preparation/ui/flowDraft'
import {decodeSteps} from '../../entities/preparation/ui/flowInputs'
import {useRead} from '../../shared/lib/useRead'
import {scopedPath} from '../../shared/lib/navigation'
import {ActionLink} from '../../shared/ui/actions'
import {Badge,ErrorNote,Loading} from '../../shared/ui/feedback'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'

type Review=NonNullable<CollaborationTask['reviews']>[number]

export function CollaborationArtifactReview({projectId,task,review}:{projectId:string;task:CollaborationTask;review:Review}) {
    const [path,search]=review.destination.split('?'),query=new URLSearchParams(search);
    const id=query.get('flow_id'),revision=Number(query.get('revision')),actionId=query.get('action_id');
    // 只解读与成功回执相符的准确产物，不把任意链接或模型描述当成可读取的流程。
    const operation=task.operations.find(item=>{
        if(item.state!=='SUCCEEDED'||item.result===null||typeof item.result!=='object')return false;
        const result=item.result as Record<string,unknown>;
        return item.capability==='flows.save'&&path==='/testing'&&result.id===id&&result.revision===revision;
    });
    const flowReview=Boolean(operation&&id&&actionId&&Number.isSafeInteger(revision)&&revision>0&&review.id===id+'@'+revision);
    const data=useRead(flowReview?'artifact-flow:'+projectId+':'+id+':'+revision+':'+task.task_id:null,async signal=>{
        const [candidate,accounts]=await Promise.all([operationFlowsApi.read(projectId,id!,revision,signal),testIdentitiesApi.list(projectId,signal)]);
        if(candidate.id!==id||candidate.revision!==revision||candidate.business_action_id!==actionId)throw new Error('产物关联已变化，请返回任务重新核对。');
        let previous:FlowComparisonBaseline|undefined=editorDraft<FlowEditorDraft>(flowDraftKey(projectId,actionId!),projectId);
        let baselineLabel='当前本地草稿';
        if(!previous&&task.editor?.kind==='FLOW'&&task.editor.action_id===actionId){
            const baseline=task.editor.flow_id===id&&task.editor.revision===revision?candidate:await operationFlowsApi.read(projectId,task.editor.flow_id,task.editor.revision,signal);
            if(baseline.business_action_id!==actionId)throw new Error('交接流程不属于当前业务操作。');
            previous={steps:decodeSteps(baseline.workflow.steps),target:baseline.workflow.target_step_id,subject:baseline.subject_test_identity_id,owner:baseline.resource_owner_test_identity_id,resource:baseline.actual_resource_id,entityEvidence:baseline.entity_evidence??[],recovery:baseline.recovery?.relative_path??'',restoreMethod:baseline.recovery?.method??'POST'};
            baselineLabel='交接时保存的流程';
        }
        return {candidate,accounts,previous,baselineLabel};
    });
    const destination=review.destination+(review.destination.includes('?')?'&':'?')+new URLSearchParams({return_to:'/workspace?'+new URLSearchParams({view:'collaboration',task_id:task.task_id})});
    return <div className="jj-collaboration-artifact-review">
        <div data-milestone-part="heading" className="jj-collaboration-artifact-state"><span>{flowReview?`接口流程 · 第 ${revision} 修订`:'已保存产物 · 待核对配置'}</span><Badge tone="accent">待确认使用</Badge></div>
        {flowReview?<>
            <p className="jj-collaboration-hint">在编辑器中比较候选与当前草稿，再决定是否带入。</p>
            {data.loading?<Loading/>:data.error?<ErrorNote error={data.error}/>:data.data&&<FlowComparison {...data.data}/>}
        </>:<><p className="jj-collaboration-hint">打开对应配置，核对内容后再确认使用。</p><dl className="jj-facts jj-collaboration-artifact-facts" data-layout="columns"><div><dt>本次目标</dt><dd>{task.goal}</dd></div><div><dt>审阅动作</dt><dd>{review.action_label}</dd></div></dl></>}
        <footer data-milestone-part="actions"><ActionLink kind="primary" href={'#'+scopedPath(destination,projectId)}>{flowReview?'进入流程继续核对':review.action_label}<ArrowRightOutlined aria-hidden="true"/></ActionLink></footer>
    </div>;
}
