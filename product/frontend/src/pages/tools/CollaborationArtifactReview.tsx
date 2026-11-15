import type {CollaborationTask} from '../../entities/runtime/api/collaboration'
import {editorDraft} from '../../entities/runtime/model/handoff'
import {operationFlowsApi} from '../../entities/preparation/api/operationFlows'
import {testIdentitiesApi} from '../../entities/preparation/api/testIdentities'
import {proofSourcesApi} from '../../entities/preparation/api/proofSources'
import {proofSourceDescriptions} from '../../entities/preparation/model/proofSourceMethods'
import {ScenarioOverview} from '../../entities/preparation/ui/ScenarioOverview'
import {FlowComparison,flowComparisonBaseline,flowDraftKey,type FlowComparisonBaseline} from '../../entities/preparation/ui/FlowCandidateReview'
import type {FlowEditorDraft} from '../../entities/preparation/ui/flowDraft'
import {useRead} from '../../shared/lib/useRead'
import {scopedPath} from '../../shared/lib/navigation'
import {assertProject} from '../../shared/model/page'
import {ActionLink} from '../../shared/ui/actions'
import {Badge,ErrorNote,Loading,Notice} from '../../shared/ui/feedback'
import {ObjectHeading,TaskActions,TaskStage} from '../../shared/ui/layout'

type Review=NonNullable<CollaborationTask['reviews']>[number]

export function CollaborationArtifactReview({projectId,task,review,returnTo}:{projectId:string;task:CollaborationTask;review:Review;returnTo?:string}) {
    const [path,search]=review.destination.split('?'),query=new URLSearchParams(search);
    const id=query.get('flow_id'),revision=Number(query.get('revision')),actionId=query.get('action_id');
    const sourceId=query.get('source_id'),scenarioId=query.get('scenario');
    // 只解读与成功回执相符的准确产物，不把任意链接或模型描述当成可读取的流程。
    const operation=task.operations.find(item=>{
        if(item.state!=='SUCCEEDED'||item.result===null||typeof item.result!=='object')return false;
        const result=item.result as Record<string,unknown>;
        return item.capability==='flows.save'&&path==='/testing'&&result.id===id&&result.revision===revision;
    });
    const flowReview=Boolean(operation&&id&&actionId&&Number.isSafeInteger(revision)&&revision>0&&review.id===id+'@'+revision);
    const saved=(capability:string,matches:(result:Record<string,unknown>)=>boolean)=>task.operations.some(item=>item.state==='SUCCEEDED'&&item.capability===capability&&item.result!==null&&typeof item.result==='object'&&matches(item.result as Record<string,unknown>));
    const proofReview=Boolean(path==='/preparation'&&sourceId&&review.id===sourceId&&Number.isSafeInteger(revision)&&revision>0&&saved('proofs.save',result=>result.source_id===sourceId&&result.revision===revision));
    const scenarioReview=Boolean(path==='/testing'&&scenarioId&&review.id===scenarioId+'@'+revision&&Number.isSafeInteger(revision)&&revision>0&&saved('scenarios.save',result=>result.id===scenarioId&&result.revision===revision));
    const proof=useRead(proofReview?'artifact-proof:'+projectId+':'+sourceId+':'+revision:null,async signal=>{
        const context=await proofSourcesApi.context(projectId,'full',signal);assertProject(context.project_id,projectId);
        const source=context.sources.find(item=>item.source_id===sourceId);
        if(!source)throw new Error('这份判断方式已不存在，请在当前检查准备中核对。');
        if(source.revision!==revision)return {kind:'changed' as const,revision:source.revision};
        const action=context.actions.find(item=>item.action_id===source.config.action_id&&item.revision===source.config.action_revision);
        const effect=action?.effects.find(item=>item.effect_id===source.config.effect_id);
        if(!action||!effect)throw new Error('这份判断方式对应的业务结果已变化，请返回任务重新核对。');
        const resource=context.resources.find(item=>item.resource_binding_id===source.config.resource_binding_id);
        return {kind:'candidate' as const,source,action,effect,resource,owner:context.identities.find(item=>item.identity_id===resource?.owner_identity_id)?.label};
    });
    const data=useRead(flowReview?'artifact-flow:'+projectId+':'+id+':'+revision+':'+task.task_id:null,async signal=>{
        const [candidate,accounts]=await Promise.all([operationFlowsApi.read(projectId,id!,revision,signal),testIdentitiesApi.list(projectId,signal)]);
        if(candidate.id!==id||candidate.revision!==revision||candidate.business_action_id!==actionId)throw new Error('产物关联已变化，请返回任务重新核对。');
        let previous:FlowComparisonBaseline|undefined=editorDraft<FlowEditorDraft>(flowDraftKey(projectId,actionId!),projectId);
        let baselineLabel='当前本地草稿';
        if(!previous&&task.editor?.kind==='FLOW'&&task.editor.action_id===actionId){
            const baseline=task.editor.flow_id===id&&task.editor.revision===revision?candidate:await operationFlowsApi.read(projectId,task.editor.flow_id,task.editor.revision,signal);
            if(baseline.business_action_id!==actionId||baseline.id!==task.editor.flow_id||baseline.revision!==task.editor.revision)throw new Error('交接流程与原修订不一致，请返回任务重新核对。');
            previous=flowComparisonBaseline(baseline);
            baselineLabel='交接时保存的流程';
        }
        if(!previous){
            const context=await operationFlowsApi.context(projectId,signal);assertProject(context.project_id,projectId);
            const used=context.flows.find(item=>item.in_use&&item.document.business_action_id===actionId&&item.document.action_revision===candidate.action_revision);
            if(used){previous=flowComparisonBaseline(used.document);baselineLabel='当前已采用流程'}
        }
        return {candidate,accounts,previous,baselineLabel};
    });
    const destination=scopedPath(review.destination,projectId),[destinationPath,destinationSearch]=destination.split('?'),destinationQuery=new URLSearchParams(destinationSearch);
    destinationQuery.set('return_to',returnTo??'/workspace?'+new URLSearchParams({view:'collaboration',task_id:task.task_id,task_view:'work',task_item:'review:'+review.id}));
    const changed=proof.data?.kind==='changed'?proof.data:undefined;
    const currentQuery=new URLSearchParams(destinationQuery);if(changed)currentQuery.set('revision',String(changed.revision));
    const unavailable=flowReview?data.loading||Boolean(data.error):proofReview?proof.loading||Boolean(proof.error)||Boolean(changed):false;
    return <div className="jj-collaboration-artifact-review">
        <div data-milestone-part="heading" className="jj-collaboration-artifact-state"><span>{flowReview?'接口流程':proofReview?'结果判断方式':scenarioReview?'业务场景':'待审阅产物'}{(flowReview||proofReview||scenarioReview)&&` · 第 ${revision} 修订`}</span><Badge tone="accent">待审阅</Badge></div>
        {flowReview?<>
            <p className="jj-collaboration-hint">在编辑器中比较候选与当前草稿，再决定是否带入。</p>
            {data.loading?<Loading/>:data.error?<ErrorNote error={data.error} onRetry={data.reload} retryLabel="重新读取候选依据"/>:data.data&&<FlowComparison {...data.data}/>}
        </>:proofReview?<>{proof.loading?<Loading/>:proof.error?<ErrorNote error={proof.error} onRetry={proof.reload} retryLabel="重新读取候选依据"/>:changed?<Notice tone="caution" title="原候选已有新修订"><p>这项任务保存的是第 {revision} 修订，当前配置是第 {changed.revision} 修订。先核对当前内容，再决定是否用于检查。</p></Notice>:proof.data?.kind==='candidate'&&<TaskStage className="jj-collaboration-proof-review" context={<section aria-label="候选对应的业务结果"><ObjectHeading title={proof.data.action.label} level={3} description={'用来判断：'+proof.data.effect.label}/><dl className="jj-facts"><div><dt>测试资源</dt><dd>{proof.data.resource?.resource_id??'尚未对应测试资源'}</dd></div><div><dt>资源所有者</dt><dd>{proof.data.owner??'尚未确认'}</dd></div><div><dt>判断方法</dt><dd>{proofSourceDescriptions[proof.data.source.config.source_kind]}</dd></div></dl></section>}>
            <section aria-label="判断方式的准备进展"><h3 className="jj-title-group">接下来核对这份判断方式</h3><dl className="jj-facts"><div><dt>读取范围</dt><dd>{proof.data.source.read_scope_confirmed?'已有读取授权':'等待允许读取'}</dd></div><div><dt>当前使用</dt><dd>{proof.data.source.adopted?'已采用；本次仍需核对准备情况':'尚未用于检查'}</dd></div></dl><p>在对应工作面核对配置、读取范围与可用性，再决定是否用于检查。</p></section>
            <TaskActions data-milestone-part="actions"><ActionLink kind="primary" href={'#'+destinationPath+'?'+destinationQuery}>{review.action_label}</ActionLink></TaskActions>
        </TaskStage>}</>:scenarioReview?<ScenarioOverview key={review.id} projectId={projectId} id={scenarioId!} revision={revision} layout="split"/>:<p className="jj-collaboration-hint">打开对应配置，核对内容后再确认使用。</p>}
        {!(proofReview&&proof.data?.kind==='candidate')&&<TaskActions data-milestone-part="actions">{changed?<ActionLink kind="primary" href={'#'+destinationPath+'?'+currentQuery}>核对当前判断方式</ActionLink>:!unavailable&&<ActionLink kind="primary" href={'#'+destinationPath+'?'+destinationQuery}>{flowReview?'进入流程继续核对':review.action_label}</ActionLink>}</TaskActions>}
    </div>;
}
