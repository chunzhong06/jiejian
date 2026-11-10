import {PendingRecovery} from '../../shared/ui/PendingRecovery'
import type {ScenarioReference} from '../../entities/preparation/api/businessScenarios'
import {conditionLabels} from '../../entities/permission/ui/RuleConditions';
import { useRef, useState, type ReactNode } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import { currentChecksApi as api, type CheckPreview } from '../../entities/check/api/currentChecks';
import { preparationApi, type PermissionReference, type ActionPreparation } from '../../entities/preparation/api/preparation';
import { testIdentitiesApi } from '../../entities/preparation/api/testIdentities';
import { ApiError } from '../../shared/api/http';
import {ActionLink,Button} from '../../shared/ui/actions'
import {PageError,  Badge, ErrorNote, Notice } from '../../shared/ui/feedback';
import { Heading,Field } from '../../shared/ui/layout';
import {Choice} from '../../shared/ui/Choice';
import { PageSkeleton } from '../../shared/ui/PageSkeleton';
import { assertProject, type PageProps } from '../../shared/model/page';
import { text } from '../../shared/lib/format';
import {go,scopedPath,returnDestination,returnDestinationLabel} from '../../shared/lib/navigation'
import { operationId, readPending, savePending, notAccepted, isRecord, isOperationId, isPublicId, isRevision } from '../../shared/lib/operations';
import { useRead } from '../../shared/lib/useRead';
import { RuleCheckScope } from './RuleCheckScope';
import { CheckScopePicker } from './CheckScopePicker';
import {TaskSurface} from '../../shared/ui/TaskSurface';
import {IndexSelection} from '../../shared/ui/IndexSelection';
import {useWorkflow} from '../../shared/lib/workflow';
import {PreparationNext} from '../../entities/workspace/PreparationNext';

export function Plan({ projectId, onError, route, refresh, official }: PageProps) {
    const workflow=useWorkflow();
    const ruleId=route.query.get('rule_id'),changeId=route.query.get('change_id');
    const scenarioId=route.query.get('scenario_id'),scenarioRevision=Number(route.query.get('scenario_revision'));
    const scenario:ScenarioReference|undefined=scenarioId&&Number.isInteger(scenarioRevision)&&scenarioRevision>0?{scenario_id:scenarioId,revision:scenarioRevision}:undefined;
    const invalidScenario=Boolean(scenarioId&&!scenario);
    const key=`jiejian.studio.check:${projectId}`+(scenario?':'+scenario.scenario_id+':'+scenario.revision:'');
    const origin = returnDestination(route.query.get('return_to'));
    type Pending = { fingerprint: string; operation: string; change: string | null; selected?: PermissionReference[] | null; scenario?:ScenarioReference };
    const acceptsPending=(value:unknown):value is Pending=>isRecord(value)&&isOperationId(value.operation)&&isPublicId(value.fingerprint)&&(value.change===null||isPublicId(value.change))&&
        (value.selected==null||Array.isArray(value.selected)&&value.selected.length<=256&&value.selected.every(item=>isRecord(item)&&isPublicId(item.intent_id)&&isRevision(item.revision)&&isPublicId(item.intent_hash)))&&
        (value.scenario===undefined||isRecord(value.scenario)&&value.scenario.scenario_id===scenario?.scenario_id&&value.scenario.revision===scenario?.revision);
    const scopeId = useRef(route.query.get('scope_id') ?? operationId());
    const [selection, setSelected] = useState<PermissionReference[] | null | 'RULE'>(() => {
        if(changeId||scenario)return null;
        const pending=readPending<Pending>(key,acceptsPending);
        if(pending&&!ruleId&&!route.query.has('scope_id'))return pending.selected??null;
        if(route.query.has('scope_id'))return readPending<{refs:PermissionReference[]}>(`jiejian.studio.scope:${projectId}:${scopeId.current}`)?.refs??[];
        return ruleId?'RULE':null;
    });
    const select = (refs: PermissionReference[] | null) => {
        savePending(`jiejian.studio.scope:${projectId}:${scopeId.current}`, refs === null ? undefined : {refs});
        const query = new URLSearchParams(location.hash.split('?')[1]);
        if (refs === null) query.delete('scope_id'); else query.set('scope_id', scopeId.current);
        if(workflow)go('/reports?'+query,projectId);else history.replaceState(null, '', '#/reports?' + query);
        setSelected(refs);
    };
    const [pending, setPending] = useState(() => readPending<Pending>(key,acceptsPending));
    const [busy, setBusy] = useState(false), [notFound, setNotFound] = useState(false), lock = useRef(false);
    const state = useRead(invalidScenario?null:'plan-materials:' + projectId, async () => {
        const [materials, identities] = await Promise.all([preparationApi.get(projectId), testIdentitiesApi.list(projectId)]);
        assertProject(materials.project_id, projectId);
        identities.forEach(item => assertProject(item.project_id, projectId));
        return { materials, identities };
    });
    // 从规则详情进入时按当前生效版本定位；丢失的规则或本地范围不退回全量检查。
    const selected:PermissionReference[]|null=selection==='RULE'?(state.data?.materials.actions.flatMap(action=>(action.permissions??[])
        .filter(rule=>rule.intent_id===ruleId&&rule.effective_state==='ACTIVE'&&rule.revision&&rule.intent_hash)
        .map(rule=>({intent_id:rule.intent_id!,revision:rule.revision!,intent_hash:rule.intent_hash!})))??[]):selection;
    // 全部和选定范围共用一个预览所有者；空选区不构造全量计划，换键后不展示旧结果。
    const chosen = useRead(invalidScenario || selected?.length === 0 ? null : 'plan:' + projectId + ':' + JSON.stringify({changeId, scenario, selected}), async () => {
        const preview = await api.preview(projectId, changeId, selected, scenario);
        assertProject(preview.project_id, projectId);
        return preview;
    });
    const activePreview = chosen.data;
    const open = (runId: string, frozen?:Pending) => {
        const refs=frozen?frozen.selected??null:selected,scope=frozen?frozen.operation:scopeId.current;
        const change=frozen?frozen.change:changeId,caseScenario=frozen?frozen.scenario:scenario;
        const sameScope=!frozen||change===changeId&&JSON.stringify(refs)===JSON.stringify(selected)&&JSON.stringify(caseScenario)===JSON.stringify(scenario);
        // 原请求回执沿用自己的冻结范围，不借用正在阅读的另一条规则或修改。
        if(refs!==null)savePending(`jiejian.studio.scope:${projectId}:${scope}`,{refs});
        savePending(key, undefined);setPending(undefined);refresh();
        go('/reports?'+new URLSearchParams({run_id:runId,...(refs!==null?{scope_id:scope}:{}),...(sameScope&&ruleId?{rule_id:ruleId}:{}),...(change?{change_id:change}:{}),...(caseScenario?{scenario_id:caseScenario.scenario_id,scenario_revision:String(caseScenario.revision)}:{}),...(origin?{return_to:origin}:{})}));
    };
    const act = async (callback: () => Promise<void>) => {
        if (lock.current) return;
        lock.current = true; setBusy(true);
        try { await callback(); } catch (error) { onError(error); }
        finally { lock.current = false; setBusy(false); }
    };
    const recover = async () => {
        const saved = readPending<Pending>(key,acceptsPending);
        if (!saved) return;
        const receipt = await api.receipt(projectId, saved.operation);
        if (receipt) { assertProject(receipt.run.project_id, projectId); open(receipt.run.run_id,saved); }
        else setNotFound(true);
    };
    const submit = async () => {
        if (!activePreview?.can_execute) return;
        const preview = await api.preview(projectId,changeId,selected,scenario);
        if (!preview.can_execute || preview.plan_fingerprint !== activePreview.plan_fingerprint || pending && pending.fingerprint !== preview.plan_fingerprint) {
            state.reload(); chosen.reload(); throw new ApiError('STATE_PRECONDITION', '检查范围已变化，请重新核对。');
        }
        const active = await api.list(projectId, true);
        // 已有运行使用自己的事实；本次选择只作为返回位置，不能标成该运行的范围。
        if (active.length) { assertProject(active[0].run.project_id,projectId);refresh();go('/reports?'+new URLSearchParams({run_id:active[0].run.run_id,return_to:'/reports?'+route.query}),projectId);return; }
        const saved = pending ?? { fingerprint: preview.plan_fingerprint, operation: operationId(), change: changeId, selected, scenario };
        savePending(key, saved); setPending(saved);
        try {
            const result = await api.submit(projectId, saved.fingerprint, saved.operation, saved.change,saved.selected,undefined,saved.scenario);
            assertProject(result.run.project_id, projectId); open(result.run.run_id,saved);
        } catch(error) {
            if(notAccepted(error,Boolean(pending))){savePending(key,undefined);setPending(undefined);setNotFound(false)}
            throw error;
        }
    };
    if(invalidScenario)return <PageError title="核对业务场景" error={new Error('场景引用缺少准确修订，请返回场景目录重新预览。')}/>;
    if (state.loading || (selected === null && chosen.loading)) return <PageSkeleton view="/reports" title="检查范围"/>;
    if (!state.data || state.error) return <PageError title="核对本次检查范围" error={state.error}/>;
    const { materials, identities } = state.data;
    const preview = activePreview;
    const returnTo = '/reports?' + new URLSearchParams({ view: 'plan', ...(scenario ? {scenario_id:scenario.scenario_id,scenario_revision:String(scenario.revision)} : {}), ...(selection!=='RULE'&&selected !== null ? {scope_id: scopeId.current} : {}), ...(changeId ? { change_id: changeId } : {}), ...(ruleId ? { rule_id: ruleId } : {}), ...(route.query.has('repair_reference')?{repair_reference:route.query.get('repair_reference')!}:{}), ...(origin ? {return_to:origin} : {}) });
    return <>
        <div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin ?? (ruleId ? '/permissions?rule_id=' + encodeURIComponent(ruleId) : '/reports'))} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}{origin ? returnDestinationLabel(origin) : ruleId ? '返回权限规则' : '全部检查记录'}</ActionLink></div>
        <Heading title="本次检查"/><PendingRecovery storageKey={key} projectId={projectId}/>
        {pending && <Notice tone="caution">上次提交的结果尚未确认。<Button busy={busy} onClick={() => void act(recover)}>查看上次提交结果</Button>{notFound && <><span>尚未查到检查记录。</span>{pending.fingerprint === preview?.plan_fingerprint ? <Button busy={busy} onClick={() => void act(submit)}>继续上次提交</Button> : <span>原范围已变化，请保留请求并稍后查询。</span>}</>}</Notice>}
        {chosen.error && <><ErrorNote error={chosen.error}/>{!changeId&&!scenario&&<Button onClick={() => {state.reload(); select([]);}}>重新选择规则</Button>}</>}
        <PlanWorkspace official={official} preview={preview} actions={materials.actions} identities={identities} returnTo={returnTo} changeId={changeId}
            initialView={route.query.get('plan_tab')} initialItem={route.query.get('plan_item')}
            scope={<>{!changeId&&!scenario&&<CheckScopePicker materials={materials} selected={selected} disabled={Boolean(pending)||busy} onChange={select}/>}{changeId&&<RuleCheckScope projectId={projectId} changeId={changeId}/>}</>}
            loading={chosen.loading} busy={busy} pending={Boolean(pending)} error={Boolean(chosen.error)} onSubmit={()=>void act(submit)}/>
    </>;
}

type PlanWorkspaceProps = {
    preview?: CheckPreview; actions: ActionPreparation[]; identities: {identity_id:string;label:string}[]; official?:boolean;
    returnTo:string; changeId:string|null; initialView:string|null; initialItem:string|null; scope:ReactNode;
    loading:boolean; busy:boolean; pending:boolean; error:boolean; onSubmit:()=>void; executionAction?:ReactNode; executionExplanation?:string;
};

export function PlanWorkspace({preview,actions,identities,returnTo,changeId,initialView,initialItem,scope,loading,busy,pending,error,onSubmit,executionAction,executionExplanation,official=false}:PlanWorkspaceProps) {
    const workflow=useWorkflow();
    const [chosenView,setView]=useState<string|null>(initialView&&['scope','prepare','execute'].includes(initialView)?initialView:null);
    const [itemId,setItem]=useState(initialItem??'');
    const gaps=actions.flatMap(action=>{const groups=groupGaps(preview?.gaps.filter(gap=>gap.action_id===action.action_id)??[]);return groups.length?[{id:action.action_id,action,groups}]:[]});
    // 无目录元数据的缺口仍可处理，不因投影缺失而把阻塞原因隐藏。
    const unlisted=(preview?.gaps??[]).filter(gap=>!actions.some(action=>action.action_id===gap.action_id));
    const boundaries=preview?.boundary_review_gaps??[];
    const attention=gaps.reduce((sum,item)=>sum+item.groups.length,0)+unlisted.length+boundaries.length;
    const view=chosenView==='scope'||!preview&&chosenView===null?'scope':'review';
    const [executionId,setExecutionId]=useState('');
    const gap=gaps.find(item=>item.id===itemId||itemId.startsWith(item.id+':'))??(!itemId?gaps[0]:undefined);
    const completedItem=Boolean(itemId.includes(':')&&gap&&!gap.groups.some(group=>itemId===gap.id+':'+group.kind));
    const boundary=boundaries.find(item=>'requirement:'+item.issue_id===itemId)??(!itemId&&!gaps.length?boundaries[0]:undefined);
    const unlistedKey=(item:CheckPreview['gaps'][number])=>'unlisted:'+JSON.stringify([item.action_id,item.reason,item.intent_id,item.effect_id]);
    const orphan=unlisted.find(item=>unlistedKey(item)===itemId)??(!itemId&&!gaps.length&&!boundaries.length?unlisted[0]:undefined);
    const focused=gap?.id??(boundary?'requirement:'+boundary.issue_id:orphan?unlistedKey(orphan):itemId);
    const plans=preview?.actions??[];
    const actionId=gap&&plans.some(item=>item.action_id===gap.id)?gap.id:plans.some(item=>item.action_id===executionId)?executionId:plans[0]?.action_id;
    const action=actions.find(item=>item.action_id===actionId),plan=plans.find(item=>item.action_id===actionId);
    const backTo=(id:string)=>returnTo+'&'+new URLSearchParams({plan_tab:'prepare',plan_item:id});
    const selectView=(value:string)=>{setView(value==='scope'?'scope':'review');if(value==='prepare')setItem('');};
    if(view==='scope')return <TaskSurface level={2} title="调整检查范围" onBack={()=>setView('review')} backLabel="返回本次检查" actions={<Button kind="primary" disabled={loading||!preview} onClick={()=>setView('review')}>核对本次检查</Button>}>            <div className="jj-plan-range">{scope}
                {preview?.scenario&&<section><h3>{preview.scenario.document.label}</h3><p className="jj-small jj-muted">先执行所选规则的基础检查，再执行以下实验；每次实验结束后核对恢复。</p><ol>{preview.scenario.document.experiments.map(experiment=><li key={experiment.id}><strong>{experiment.label}</strong><p>{experiment.invocations.map(item=>item.label+(item.batch?'（一次批量，'+item.items.length+' 项）':'')).join(' → ')}</p></li>)}</ol></section>}
                {!!preview?.requirement_scope?.length&&<section><h3>业务要求与覆盖范围</h3>{preview.requirement_scope.flatMap(scope=>scope.requirements.map(item=>({...item,scope}))).map(({scope,...item},index)=><div className="jj-scope-item" key={index}><Badge>{item.disposition==='IN_SCOPE'?(preview.selection?.uncovered_requirements.includes(`${scope.candidate_id}@${scope.revision}/${item.requirement_id}`)?'本次未覆盖':'纳入检查'):item.disposition==='PREPARATION'?'准备条件':'未覆盖'}</Badge><p>{text(item.requirement)}</p></div>)}</section>}
                {!!preview?.omitted_review_gaps?.length&&<section><h3>{preview.omitted_review_gaps.length} 项未决要求未纳入本次检查</h3>{preview.omitted_review_gaps.map(item=><p key={item.issue_id}>{text(item.message)}</p>)}</section>}
            </div></TaskSurface>;
    return <section className="jj-plan-review" aria-label="检查准备工作面" aria-busy={loading}>
        <header className="jj-plan-review-summary"><div><div className="jj-object-line"><h2>{preview?(preview.case_count?`${preview.case_count} 项检查`:'检查尚待准备'):'选择检查范围'}</h2>{preview&&<Badge tone={preview.can_execute?'positive':'caution'}>{preview.can_execute?'可以开始':`${attention} 项待处理`}</Badge>}</div><p>{preview?`${preview.action_count} 项业务操作${preview.selection?` · ${preview.selection.added_controls.length} 项正常对照 · ${preview.selection.omitted.length} 条规则未检查`:''}`:'先选择要检查的规则，再核对测试账号、数据和将执行的操作。'}</p></div></header>
        <div className="jj-plan-scope-summary"><p>{preview?.scenario?'本次包括所选业务场景及其基础权限检查。':preview?.selection?'检查所选规则，并保留确认正常功能所需的对照。':'检查当前应用已确认的权限要求及其正常对照。'}</p><Button kind="quiet" disabled={busy||pending} onClick={()=>setView('scope')}>调整检查范围</Button></div>
        <div className="jj-plan-review-panel">
                        {preview&&(attention>0||Boolean(itemId))&&<div className="jj-plan-focus" data-empty={!attention}>
                {gaps.length+boundaries.length+unlisted.length>1&&<nav className="jj-plan-index" aria-label="准备事项"><IndexSelection identity={focused} label="缺口选择">
                  {gaps.map(item=><button type="button" key={item.id} className="jj-index-item" aria-current={focused===item.id?'true':undefined} onClick={()=>setItem(item.id)}><strong>{text(item.action.display_name)}</strong><small>{item.groups.length} 项材料需要准备</small></button>)}
                  {boundaries.map(item=><button type="button" key={item.issue_id} className="jj-index-item" aria-current={focused==='requirement:'+item.issue_id?'true':undefined} onClick={()=>setItem('requirement:'+item.issue_id)}><strong>核对权限要求</strong><small>{text(item.message)}</small></button>)}
                  {unlisted.map(item=><button type="button" key={unlistedKey(item)} className="jj-index-item" aria-current={focused===unlistedKey(item)?'true':undefined} onClick={()=>setItem(unlistedKey(item))}><strong>核对检查条件</strong><small>{gapName(item.reason)}</small></button>)}
                </IndexSelection></nav>}
                <section className="jj-plan-detail" key={focused||'ready'} aria-label="当前准备事项">
                    {gap&&!completedItem?<><header><p className="jj-eyebrow">本次检查准备</p><h3>{text(gap.action.display_name)}</h3><p>为这项操作准备账号、执行方式和判断依据。完成后返回本次检查，按实际材料重新核对。</p></header>
                      {itemId.includes(':')&&!gap.groups.some(group=>itemId===gap.id+':'+group.kind)&&<Notice tone="positive">刚才处理的准备项已不在当前缺口中。以下是这项操作仍需准备的材料。</Notice>}
                      <div className="jj-plan-gap-groups">{gap.groups.map(group=><article key={group.kind}><h4>{gapAction(group.kind)}</h4><ul className="jj-plan-reasons">{group.messages.map(message=><li key={message}>{message}</li>)}</ul>
                        <div className="jj-inline-actions">{gapEntryItems(gap.action,group.items).map(item=><ActionLink key={JSON.stringify(item)} href={'#'+scopedPath(gapDestination(item,backTo(gap.id+':'+group.kind),changeId))}>{gapLinkLabel(gap.action,item)}<ArrowRightOutlined aria-hidden="true"/></ActionLink>)}</div>
                      </article>)}</div></>:boundary?<><header><h3>核对权限要求</h3></header><p>{text(boundary.message)}</p>{preview.requirement_scope?.filter(scope=>scope.candidate_id===boundary.candidate_id&&scope.revision===boundary.revision).flatMap(scope=>scope.requirements).map(item=><p key={item.requirement_id}>{text(item.requirement)}</p>)}<p className="jj-small jj-muted">这项要求尚未批准。核对后将返回本次检查，重新确认对应材料。</p><footer><Button kind="quiet" onClick={()=>(workflow?.open??go)(boundary.review_url.replace(/^#/,'')+'&'+new URLSearchParams({return_to:backTo('requirement:'+boundary.issue_id)}))}>核对要求<ArrowRightOutlined aria-hidden="true"/></Button></footer></>:orphan?<><h3>核对检查条件</h3><p>{gapName(orphan.reason)}</p><footer><Button kind="quiet" onClick={()=>(workflow?.open??go)(gapDestination(orphan,backTo(focused),changeId))}>核对检查条件<ArrowRightOutlined aria-hidden="true"/></Button></footer></>:<><h3>{itemId?'这项准备已不在当前缺口中':'当前没有材料缺口'}</h3><p>{attention?'其余待处理事项保留在左侧，可继续逐项核对。':'材料已齐备，可核对执行安排。'}</p><footer><Button kind="primary" onClick={()=>completedItem&&gap?setItem(gap.id):selectView(attention?'prepare':'execute')}>{attention?'继续处理下一项':'查看执行安排'}<ArrowRightOutlined aria-hidden="true"/></Button></footer></>}
                </section>
            </div>}
            {preview&&plans.some(item=>item.cases.length>0)&&<details className="jj-plan-execution" open={initialView==='execute'||attention===0}><summary>将执行的操作与正常对照</summary><div className="jj-plan-focus" data-empty={!plans.length}>
                {plans.length>1&&!gap&&<Field label="查看执行操作"><Choice value={actionId??''} onValueChange={setExecutionId}>{plans.filter(item=>item.cases.length>0).map(item=><option key={item.action_id} value={item.action_id}>{text(actions.find(action=>action.action_id===item.action_id)?.display_name??'待核对业务操作')} · {item.cases.length} 个场景</option>)}</Choice></Field>}
                <section className="jj-plan-detail" key={actionId??'empty'} aria-label="当前执行场景"><header><h3>{text(action?.display_name??'实际执行对象')}</h3><p className="jj-small jj-muted">{action?.effect_evidence.map(effect=>text(effect.business_label)).join('、')||'准备齐备后，展示实际账号、资源和正常对照。'}</p></header>
                    {!!plan?.cases.length?<div className="jj-scroll-table"><table data-density="compact" className="jj-content-table jj-plan-case-table"><thead><tr><th>操作账号</th><th scope="col" className="jj-table-state">预期结果</th><th>数据所有者</th><th>测试数据</th></tr></thead><tbody>{plan.cases.map(item=><tr key={item.case_id}><td>{text(item.subject_test_identity_id===null?'未登录访客':identities.find(identity=>identity.identity_id===item.subject_test_identity_id)?.label??'所选测试账号')}</td><td className="jj-table-state">{item.batch_effect_expectation==='ABSENT'?'不应产生效果':item.permission.expectation==='DENY'?'不应完成':'应当完成'}</td><td>{text(identities.find(identity=>identity.identity_id===item.resource_owner_test_identity_id)?.label??'所选资源账号')}</td><td>{item.resource_id}{conditionLabels(item.permission.conditions).length>0&&<small>{conditionLabels(item.permission.conditions).join('，')}</small>}</td></tr>)}</tbody></table></div>:<p>还没有可执行的检查内容，请先选择规则并处理待准备事项。</p>}
                    
                </section>
            </div></details>}
            {!preview&&!error&&<p role="status">{loading?'正在核对所选规则与必要材料…':'请在检查范围中选择规则。'}</p>}
        </div>
        {workflow?.reviewed&&preview&&<Notice>已重新核对本次检查。{attention?`还有 ${attention} 项待处理，已保存的材料继续保留。`:preview.can_execute?'材料已齐备，请核对执行安排后开始检查。':'请继续确认本次使用的材料与执行条件。'}</Notice>}
        {workflow&&preview&&attention>0?<PreparationNext official={official} preview={preview} onReview={()=>selectView('prepare')}/>:<footer className="jj-plan-review-confirm"><div><p className="jj-small jj-muted">{executionExplanation??(preview?.can_execute?'将执行真实操作，检查期间可离开此页。':'已有材料会保留，可按具体缺口继续处理。')}</p></div>{executionAction??<Button kind="primary" busy={busy} disabled={!preview?.can_execute||pending||loading} onClick={onSubmit}>开始检查<ArrowRightOutlined aria-hidden="true"/></Button>}</footer>}
    </section>;
}

export function gapName(reason: string) {
    return ({ SCENARIO_REQUEST_BUDGET_INSUFFICIENT:'当前请求上限不足以完成检查和数据恢复，请先调整检查连接中的请求上限', SCENARIO_RESOURCE_PRODUCER_REQUIRED:'前一步尚未准备好可独立确认的新建对象', SCENARIO_ITEM_NOT_PREPARED:'本步引用的账号、资源或规则需要重新准备', SCENARIO_CONTROL_REQUIRED:'需要保留相同操作方式的完整正常流程作为对照', SCENARIO_FULL_CONTROL_REQUIRED:'本步正常对照需要覆盖全部保护效果', BATCH_REQUEST_MAPPING_INVALID:'批量资源数组或返回项映射需要核对', BATCH_RESOURCE_ASSOCIATION_REQUIRED:'批量项必须使用同一动作并能逐项关联资源', TEST_IDENTITY_LOGIN_REQUIRED: '测试账号需要重新登录', RESOURCE_OWNER_SOURCE_STALE: '测试数据的归属需要重新确认', RESOURCE_INJECTION_STALE: '操作中的测试数据位置需要重新确认', CONDITION_SOURCE_REQUIRED:'尚未设置租户或数据状态的判断依据', RULE_CASE_DATA_STALE:'规则的测试数据需要重新核对', TEST_IDENTITY_REQUIRED: '测试账号尚未就绪', IDENTITY_REQUIRED: '测试账号尚未就绪', ACTION_RESOURCE_REQUIRED: '测试资源尚未确认', RESOURCE_REQUIRED: '测试资源尚未确认', ACTION_EXECUTION_REQUIRED: '尚未准备可重复执行的录制或接口流程', ACTION_EXECUTION_MISSING: '尚未准备可重复执行的录制或接口流程', EXECUTION_REQUIRED: '尚未准备可重复执行的录制或接口流程', EFFECT_EVIDENCE_REQUIRED: '尚未设置如何判断业务结果', EFFECT_VERDICT_PROOF_REQUIRED: '业务结果的判断依据还未准备好', REGISTERED_OBSERVER_UNAVAILABLE: '证明来源当前不可用', ACTION_RECOVERY_REQUIRED: '缺少恢复方式', RECOVERY_REQUIRED: '缺少恢复方式', ALLOW_CONTROL_REQUIRED: '需要选择一项应当成功的正常操作', PERMISSION_SEMANTICS_REQUIRED: '权限要求尚未确认', CREATED_RESOURCE_PROOF_REQUIRED: '缺少新建资源的独立记录', PREPARATION_REQUIRED: '材料需要重新核对' } as Record<string, string>)[reason] ?? '本项检查条件需要重新核对';
}
export function gapDestination(gap: CheckPreview['gaps'][number], returnTo: string, changeId?: string | null) {
    if(gap.reason==='SCENARIO_REQUEST_BUDGET_INSUFFICIENT')return '/application?'+new URLSearchParams({view:'environment',return_to:returnTo});
    const focus = gapKind(gap.reason);
    return '/preparation?' + new URLSearchParams({ action_id: gap.action_id, return_to: returnTo, ...(['identity','resource','execution','recovery','evidence'].includes(focus) ? { focus } : {}), ...(gap.action_revision?{action_revision:String(gap.action_revision)}:{}), ...(focus==='identity'?{identities:'1'}:focus==='execution'||focus==='recovery'?{material_kind:focus}:focus==='evidence'?{proof_sources:'1'}:{}), ...(gap.intent_id ? { rule_id: gap.intent_id } : {}), ...(gap.effect_id ? { effect_id: gap.effect_id } : {}), ...(changeId ? { change_id: changeId } : {}) });
}

function gapKind(reason: string) {
    if(reason==='CONDITION_SOURCE_REQUIRED')return 'evidence';
    if(reason==='RULE_CASE_DATA_STALE')return 'resource';
    return /IDENTITY/.test(reason) ? 'identity' : /RESOURCE/.test(reason) && !/PROOF/.test(reason) ? 'resource' : /EXECUTION/.test(reason) ? 'execution' : /RECOVERY/.test(reason) ? 'recovery' : /EVIDENCE|PROOF|OBSERVER/.test(reason) ? 'evidence' : reason;
}

function groupGaps(gaps: CheckPreview['gaps']) {
    // 同一操作的同类原因集中解释，规则与结果定位仍逐条保留；执行门禁使用完整缺口。
    const groups = new Map<string, CheckPreview['gaps']>();
    for (const gap of gaps) { const kind = gapKind(gap.reason); groups.set(kind, [...(groups.get(kind) ?? []), gap]); }
    return Array.from(groups, ([kind, items]) => ({ kind, items, messages: [...new Set(items.map(item => gapName(item.reason)))] }));
}

function gapAction(kind: string) {
    return ({ identity: '准备测试账号', resource: '确认测试资源', execution: '准备执行操作', recovery: '准备恢复方式', evidence: '准备结果判断依据' } as Record<string, string>)[kind] ?? '核对检查条件';
}

/** 共用材料只提供一个准备入口；规则特有的资源条件与结果定位仍分别保留。 */
function gapEntryItems(action:ActionPreparation,items:CheckPreview['gaps']){
 const unique=new Map<string,CheckPreview['gaps'][number]>()
 for(const item of items){
  const kind=gapKind(item.reason),rule=action.permissions?.find(rule=>rule.intent_id===item.intent_id)
  const key=JSON.stringify([kind,kind==='identity'&&rule?[rule.subject_actor_id,rule.conditions?.principal]:['execution','recovery'].includes(kind)?'shared':[item.effect_id,item.intent_id,item.reason]])
  if(!unique.has(key))unique.set(key,item)
 }
 return [...unique.values()]
}

function gapLinkLabel(action: ActionPreparation, gap: CheckPreview['gaps'][number]) {
    const rule=action.permissions?.find(rule=>rule.intent_id===gap.intent_id);
    const actor=(id:string)=>text(action.identity_requirements.slots.find(slot=>slot.requirement.actor_id===id)?.actor_display_name??'所选角色');
    const context=rule?`${rule.conditions?.principal==='ANONYMOUS'?'未登录访客':actor(rule.subject_actor_id)}${rule.expectation==='ALLOW'?'可以':'不得'}${text(action.display_name)}`
        :action.effect_evidence.find(effect=>effect.effect_id===gap.effect_id)?.business_label;
    if(gapKind(gap.reason)==='identity'&&rule)return '准备'+actor(rule.subject_actor_id)+'账号';
    return (context?context+'：':'')+gapAction(gapKind(gap.reason));
}
