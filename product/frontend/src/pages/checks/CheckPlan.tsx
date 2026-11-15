import {TaskActions} from '../../shared/ui/layout'
import {DiscoveryCoveragePanel} from '../../entities/permission/ui/DiscoveryCoverage'
import {PendingRecovery} from '../../shared/ui/PendingRecovery'
import type {ScenarioReference} from '../../entities/preparation/api/businessScenarios'
import {conditionLabels} from '../../entities/permission/ui/RuleConditions';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import { currentChecksApi as api, type CheckPreview } from '../../entities/check/api/currentChecks';
import { preparationApi, type PermissionReference, type ActionPreparation } from '../../entities/preparation/api/preparation';
import { testIdentitiesApi } from '../../entities/preparation/api/testIdentities';
import { ApiError } from '../../shared/api/http';
import {ActionLink,Button} from '../../shared/ui/actions'
import {PageError, Badge, ErrorNote, InlineFeedback, Notice} from '../../shared/ui/feedback';
import { Heading,ObjectIdentity,SectionHeading } from '../../shared/ui/layout';
import UserOutlined from '@ant-design/icons/UserOutlined';
import ClockCircleOutlined from '@ant-design/icons/ClockCircleOutlined';
import {MaterialWorkbench,materialNames,materialStatus,type MaterialKind} from '../../entities/preparation/ui/MaterialWorkbench';
import { PageSkeleton } from '../../shared/ui/PageSkeleton';
import { assertProject, type PageProps } from '../../shared/model/page';
import { text } from '../../shared/lib/format';
import {go,scopedPath,returnDestination,returnDestinationLabel} from '../../shared/lib/navigation'
import { operationId, readPending, savePending, notAccepted, isRecord, isOperationId, isPublicId, isRevision } from '../../shared/lib/operations';
import { useRead } from '../../shared/lib/useRead';
import { RuleCheckScope } from './RuleCheckScope';
import { CheckScopePicker } from './CheckScopePicker';
import {TaskSurface} from '../../shared/ui/TaskSurface';
import {useWorkflow} from '../../shared/lib/workflow';
import {PreparationNext} from '../../entities/workspace/PreparationNext';
import {PreparationReview} from '../../entities/preparation/ui/PreparationReview';
import {CheckExecutionPreview} from './CheckExecutionPreview';

export function Plan({ projectId, onError, route, refresh, official }: PageProps) {
    const workflow=useWorkflow();
    const [scopeFocused,setScopeFocused]=useState(false);
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
        if(scopeFocused)query.set('plan_tab','scope');
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
    if(invalidScenario)return <PageError title="本次检查" error={new Error('场景引用缺少准确修订，请返回场景目录重新预览。')}/>;
    if (state.loading || (selected === null && chosen.loading)) return <PageSkeleton layout="report" view="/reports" title="本次检查"/>;
    if (!state.data || state.error) return <PageError title="本次检查" error={state.error}/>;
    const { materials, identities } = state.data;
    const preview = activePreview;
    const returnTo = '/reports?' + new URLSearchParams({ view: 'plan', ...(scenario ? {scenario_id:scenario.scenario_id,scenario_revision:String(scenario.revision)} : {}), ...(selection!=='RULE'&&selected !== null ? {scope_id: scopeId.current} : {}), ...(changeId ? { change_id: changeId } : {}), ...(ruleId ? { rule_id: ruleId } : {}), ...(route.query.has('repair_reference')?{repair_reference:route.query.get('repair_reference')!}:{}), ...(origin ? {return_to:origin} : {}) });
    return <>
        {!scopeFocused&&<><div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin ?? (ruleId ? '/permissions?rule_id=' + encodeURIComponent(ruleId) : '/reports'))} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}{origin ? returnDestinationLabel(origin) : ruleId ? '返回权限规则' : '全部检查记录'}</ActionLink></div>
        </>}<PendingRecovery storageKey={key} projectId={projectId}/>
        {pending && <Notice tone="caution">上次提交的结果尚未确认。<Button busy={busy} onClick={() => void act(recover)} busyLabel="正在查询">查看上次提交结果</Button>{notFound && <><span>尚未查到检查记录。</span>{pending.fingerprint === preview?.plan_fingerprint ? <Button busy={busy} onClick={() => void act(submit)}>继续上次提交</Button> : <span>原范围已变化，请保留请求并稍后查询。</span>}</>}</Notice>}
        {chosen.error && <><ErrorNote error={chosen.error} onRetry={chosen.reload} retryLabel="重新读取检查方案"/>{!changeId&&!scenario&&<Button onClick={() => {state.reload(); select([]);}}>重新选择规则</Button>}</>}
        <PlanWorkspace onScopeFocus={setScopeFocused} official={official} preview={preview} actions={materials.actions} identities={identities} returnTo={returnTo} changeId={changeId}
            initialView={route.query.get('plan_tab')} initialItem={route.query.get('plan_item')}
            scope={<>{!changeId&&!scenario&&<CheckScopePicker materials={materials} selected={selected} disabled={Boolean(pending)||busy} onChange={select}/>}{changeId&&<RuleCheckScope projectId={projectId} changeId={changeId}/>}</>}
            loading={chosen.loading} busy={busy} pending={Boolean(pending)} error={Boolean(chosen.error)} onSubmit={()=>void act(submit)}/>
    </>;
}

type PlanWorkspaceProps = {
    preview?: CheckPreview; actions: ActionPreparation[]; identities: {identity_id:string;label:string}[]; official?:boolean;
    returnTo:string; changeId:string|null; initialView:string|null; initialItem:string|null; scope:ReactNode;
    title?:string;eyebrow?:string;loading:boolean; busy:boolean; pending:boolean; error:boolean; onSubmit:()=>void; executionAction?:ReactNode; executionExplanation?:string; onScopeFocus?:(focused:boolean)=>void; inlineScope?:boolean;
};

export function PlanWorkspace({preview,actions,identities,returnTo,changeId,initialView,initialItem,scope,loading,busy,pending,error,onSubmit,executionAction,executionExplanation,onScopeFocus,inlineScope=false,official=false,title='检查准备',eyebrow}:PlanWorkspaceProps) {
 const workflow=useWorkflow()
 const [chosenView,setChosenView]=useState<string|null>(initialView==='scope'?'scope':initialView==='execute'?'execute':initialView?'review':null)
 const setView=(next:string)=>{
  setChosenView(next)
  // 本地范围首次获得scope_id后，父任务可能按新身份重建；URL保留实际阅读位置。
  const query=new URLSearchParams(location.hash.split('?')[1]);query.set('plan_tab',next)
  history.replaceState(null,'',location.hash.split('?')[0]+'?'+query)
 }
 const view=chosenView??(preview?'review':'scope')
 const [selectedAction,setAction]=useState(initialItem?.split(':')[0]??'')
 const [selectedMaterial,setMaterial]=useState<MaterialKind>(['identity','execution','resource','evidence','recovery'].includes(initialItem?.split(':')[1]??'')?initialItem!.split(':')[1] as MaterialKind:'identity')
 const work=preview&&preview.preparation_work?.project_id===preview.project_id&&preview.preparation_work.plan_fingerprint===preview.plan_fingerprint?preview.preparation_work:undefined
 // 只组合本次预览涉及的操作，不把未选择要求的材料混入当前任务。
 const operationIds=new Set([...(preview?.actions.map(item=>item.action_id)??[]),...(preview?.gaps.map(item=>item.action_id)??[]),...(work?.impacts.map(item=>item.action_id)??[])])
 const scopedActions=actions.filter(item=>operationIds.has(item.action_id))
 const action=scopedActions.find(item=>item.action_id===selectedAction)??scopedActions[0]
 const allGaps=preview?.gaps??[]
 const boundaries=preview?.boundary_review_gaps??[]
 const unlisted=allGaps.filter(item=>!actions.some(action=>action.action_id===item.action_id))
 const attention=actions.reduce((sum,item)=>sum+groupGaps(allGaps.filter(gap=>gap.action_id===item.action_id)).length,0)+unlisted.length+boundaries.length
 const selectedGaps=allGaps.filter(item=>item.action_id===action?.action_id)
 const groups=groupGaps(selectedGaps)
 const firstGap=groups[0]&&action&&gapEntryItems(action,groups[0].items)[0]
 const backTo=(kind:string)=>returnTo+'&'+new URLSearchParams({plan_tab:'prepare',plan_item:(action?.action_id??'')+':'+kind})
 const fallback=firstGap&&action?{destination:gapDestination(firstGap,backTo(groups[0].kind),changeId),label:gapLinkLabel(action,firstGap)}:undefined
 const plan=preview?.actions.find(item=>item.action_id===action?.action_id)
 useEffect(()=>{onScopeFocus?.(view==='scope'||view==='execute')},[onScopeFocus,view])
 useEffect(()=>()=>onScopeFocus?.(false),[onScopeFocus])
 const task=view==='execute'&&preview&&!executionAction?<CheckExecutionPreview preview={preview} actions={actions} identities={identities} busy={busy} disabled={pending||loading||error} onBack={()=>setView('review')} onScope={()=>setView('scope')} onSubmit={onSubmit}/>:view==='scope'?<TaskSurface title={inlineScope?'本次检查范围':'调整检查范围'} onBack={()=>setView('review')} backLabel="返回检查准备" actions={<Button kind="primary" disabled={loading||!preview} onClick={()=>setView('review')}>核对本次检查</Button>}><div className="jj-plan-range">{scope}
  {preview?.scenario&&<section><h3>{preview.scenario.document.label}</h3><p>先执行所选规则的基础检查，再执行所选实验；每次实验结束后核对恢复。</p><ol>{preview.scenario.document.experiments.map(item=><li key={item.id}><strong>{item.label}</strong><p>{item.invocations.map(step=>step.label+(step.batch?'（一次批量，'+step.items.length+' 项）':'')).join(' → ')}</p></li>)}</ol></section>}
  <DiscoveryCoveragePanel coverage={preview?.discovery_coverage}/>
  {!!preview?.requirement_scope?.length&&<section><h3>业务要求与覆盖范围</h3>{preview.requirement_scope.flatMap(scope=>scope.requirements.map(item=>({...item,scope}))).map(({scope,...item},index)=><div className="jj-scope-item" key={index}><Badge>{item.disposition==='IN_SCOPE'?(preview.selection?.uncovered_requirements.includes(`${scope.candidate_id}@${scope.revision}/${item.requirement_id}`)?'本次未覆盖':'纳入检查'):item.disposition==='PREPARATION'?'准备条件':'未覆盖'}</Badge><p>{text(item.requirement)}</p></div>)}</section>}
  {!!preview?.omitted_review_gaps?.length&&<section><h3>{preview.omitted_review_gaps.length} 项未决要求未纳入本次检查</h3>{preview.omitted_review_gaps.map(item=><p key={item.issue_id}>{text(item.message)}</p>)}</section>}
  {preview&&<PreparationReview preview={preview}/>}
 </div></TaskSurface>:null
 const materialGroups=action?[{kind:'identity' as const,items:action.identity_requirements.slots},{kind:'execution' as const,items:[action.execution]},{kind:'resource' as const,items:action.resources},{kind:'evidence' as const,items:action.effect_evidence},{kind:'recovery' as const,items:[action.recovery]}]:[]
 const materials=materialGroups.map(group=>({kind:group.kind,items:work?(work.impacts.some(item=>item.action_id===action?.action_id&&item.kind===group.kind)?work.impacts.filter(item=>item.action_id===action?.action_id&&item.kind===group.kind):group.items.every(item=>item.status==='NOT_REQUIRED')?group.items:[]):group.items}))
 // 保留准备正文和真实触发入口，使独立任务返回后恢复选择、焦点与滚动位置。
 return <><section hidden={Boolean(task)} className="jj-plan-review" aria-label="检查准备工作面" aria-busy={loading}>
  <Heading title={title} eyebrow={eyebrow} actions={<Button kind="quiet" disabled={busy||pending} onClick={()=>setView('scope')}>{inlineScope?'查看检查范围':'查看本次范围'}</Button>}/>
  {preview&&action&&<MaterialWorkbench actions={scopedActions.map(item=>({id:item.action_id,label:text(item.display_name),complete:preview.can_execute||item.preparation_complete}))} actionId={action.action_id} onActionChange={setAction} materials={materials} selected={selectedMaterial} onSelect={setMaterial} disabled={busy||pending} footer={<footer className="jj-plan-material-footnote"><ClockCircleOutlined aria-hidden="true"/><span>{preview.can_execute?'本次所选材料已齐备，可核对执行安排。':action.preparation_complete?'当前操作材料已齐备，其余待处理事项继续保留。':'尚需核对“'+text(action.display_name)+'”的账号与材料。'}</span></footer>}>
   {initialItem===action.action_id+':'+selectedMaterial&&!groups.some(group=>group.kind===selectedMaterial)&&<InlineFeedback>刚才处理的准备项已不在当前缺口中。已保存的材料继续保留。{groups[0]&&<Button kind="quiet" onClick={()=>setMaterial(groups[0].kind as MaterialKind)}>继续处理下一项</Button>}</InlineFeedback>}
   <PlanMaterialReading action={action} kind={selectedMaterial} preview={preview} identities={identities} returnTo={backTo(selectedMaterial)} changeId={changeId}/>
  </MaterialWorkbench>}
  {boundaries.map(item=><section className="jj-plan-current-material" aria-label="待核对权限要求" key={item.issue_id}><h2>核对权限要求</h2><p>{text(item.message)}</p>{preview?.requirement_scope?.filter(scope=>scope.candidate_id===item.candidate_id&&scope.revision===item.revision).flatMap(scope=>scope.requirements).map(requirement=><p key={requirement.requirement_id}>{text(requirement.requirement)}</p>)}<TaskActions><ActionLink href={'#'+scopedPath(item.review_url.replace(/^#/, '')+'&'+new URLSearchParams({return_to:returnTo+'&'+new URLSearchParams({plan_tab:'prepare',plan_item:'requirement:'+item.issue_id})}))}>核对要求</ActionLink></TaskActions></section>)}
  {unlisted.map((item,index)=><section key={index}><h2>核对检查条件</h2><p>{gapName(item.reason)}</p><ActionLink href={'#'+scopedPath(gapDestination(item,returnTo,changeId))}>核对检查条件</ActionLink></section>)}
  {preview&&plan&&plan.cases.length>0&&<details className="jj-plan-execution" open={initialView==='execute'||attention===0}><summary>将执行的操作与正常对照</summary><div className="jj-plan-detail"><h3>{text(action?.display_name??'实际执行对象')}</h3><div className="jj-scroll-table"><table className="jj-content-table" data-density="compact"><thead><tr><th>操作账号</th><th>预期结果</th><th>数据所有者</th><th>测试数据</th></tr></thead><tbody>{plan.cases.map(item=><tr key={item.case_id}><td>{text(item.subject_test_identity_id===null?'未登录访客':identities.find(identity=>identity.identity_id===item.subject_test_identity_id)?.label??'所选测试账号')}</td><td>{item.batch_effect_expectation==='ABSENT'?'不应产生效果':item.permission.expectation==='DENY'?'不应完成':'应当完成'}</td><td>{text(identities.find(identity=>identity.identity_id===item.resource_owner_test_identity_id)?.label??'所选资源账号')}</td><td>{item.resource_id}{conditionLabels(item.permission.conditions).length>0&&<small>{conditionLabels(item.permission.conditions).join('，')}</small>}</td></tr>)}</tbody></table></div></div></details>}
  {!preview&&!error&&<p role="status">{loading?'正在核对所选规则与必要材料…':'请在检查范围中选择规则。'}</p>}
  {workflow?.reviewed&&preview&&<InlineFeedback>已重新核对本次检查。{attention?`还有 ${attention} 项待处理，已保存的材料继续保留。`:preview.can_execute?'材料已齐备，请核对执行安排后开始检查。':'请继续确认本次使用的材料与执行条件。'}</InlineFeedback>}
  {preview&&attention>0&&!executionAction&&<TaskActions separated note="先完成当前材料核对，再预览实际执行范围。"><PreparationNext compact official={official} preview={preview} disabled={busy||pending||loading} returnTo={backTo(selectedMaterial)} fallback={fallback} onReview={()=>setView('review')}/></TaskActions>}
  {(!preview||attention===0||executionAction)&&<TaskActions separated note={executionExplanation??(preview?.can_execute?'材料已齐备，继续核对实际执行安排。':'已有材料会保留，可按具体缺口继续处理。')}>{executionAction??<Button kind="primary" disabled={!preview?.can_execute||pending||loading||error||busy} onClick={()=>setView('execute')}>预览这次检查<ArrowRightOutlined aria-hidden="true"/></Button>}</TaskActions>}
 </section>{task}</>
}

function PlanMaterialReading({action,kind,preview,identities,returnTo,changeId}:{action:ActionPreparation;kind:MaterialKind;preview:CheckPreview;identities:Array<{identity_id:string;label:string}>;returnTo:string;changeId:string|null}){
 const groups=groupGaps(preview.gaps.filter(item=>item.action_id===action.action_id))
 const group=groups.find(item=>item.kind===kind)
 const work=preview.preparation_work?.project_id===preview.project_id&&preview.preparation_work.plan_fingerprint===preview.plan_fingerprint?preview.preparation_work:undefined
 const impacts=work?.impacts.filter(item=>item.action_id===action.action_id&&item.kind===kind)??[]
 const requiredSlots=work?action.identity_requirements.slots.filter(slot=>work.impacts.some(item=>item.action_id===action.action_id&&item.kind==='identity'&&(item.slot_id===slot.requirement.slot_id||!item.slot_id&&item.member_id===slot.test_identity_id))):action.identity_requirements.slots
 // 已绑定身份按准确ID复用；尚未绑定的槽位各自保留，不按角色名合并主体。
 const accounts=new Map<string,typeof action.identity_requirements.slots>()
 for(const slot of requiredSlots){const key=slot.test_identity_id??slot.requirement.slot_id;accounts.set(key,[...(accounts.get(key)??[]),slot])}
 const general='/preparation?'+new URLSearchParams({action_id:action.action_id,action_revision:String(action.action_revision),focus:kind,return_to:returnTo,...(kind==='evidence'?{proof_sources:'1'}:kind==='execution'||kind==='recovery'?{material_kind:kind}:{})})
 return <section className="jj-plan-current-material" aria-label="当前准备事项"><SectionHeading title={materialNames[kind]} level={2}/>
  {kind==='identity'?<div>{!accounts.size&&group&&<ul className="jj-plan-gap-links">{gapEntryItems(action,group.items).map(item=><MaterialEntry key={JSON.stringify(item)} action={action} gap={item} returnTo={returnTo} changeId={changeId}/>)}</ul>}{!accounts.size&&group&&<ul className="jj-plan-reasons">{group.messages.map(message=><li key={message}>{message}</li>)}</ul>}{[...accounts].map(([key,slots])=>{const slot=slots[0],state=materialStatus(slots),alias=identities.find(item=>item.identity_id===slot.test_identity_id)?.label;const destination='/preparation?'+new URLSearchParams({action_id:action.action_id,action_revision:String(action.action_revision),identities:'1',account_slot:slot.requirement.slot_id,return_to:returnTo,...(slot.test_identity_id?{identity_id:slot.test_identity_id}:{})});return <article className="jj-plan-material-account" key={key}><span aria-hidden="true"><UserOutlined/></span><div><ObjectIdentity name={<><strong>{text(slot.actor_display_name)}账号{slot.requirement.ordinal>1?' '+slot.requirement.ordinal:''}</strong>{alias&&<span className="jj-plan-material-alias">{text(alias.split(' · ')[0])}</span>}</>} status={<Badge tone={state.tone}>{slots.some(item=>item.reason_codes.includes('TEST_IDENTITY_LOGIN_REQUIRED'))?'会话需核对':state.label}</Badge>}/><p>{action.resources.some(item=>slots.some(slot=>slot.requirement.slot_id===item.owner_slot_id))?'提供本次检查所用资源，并核对对应身份。':'执行对应角色的业务操作，核对实际访问结果。'}</p></div><ActionLink aria-label={(slot.test_identity_id?'核对账号：':'准备账号：')+text(slot.actor_display_name)+'账号'+(alias?' · '+text(alias):'')} href={'#'+scopedPath(destination)}>{slot.test_identity_id?'核对账号':'准备账号'}</ActionLink></article>})}</div>:<>
   <p className="jj-plan-material-purpose">{kind==='execution'?'核对这项业务操作使用的流程、账号和资源。':kind==='resource'?'确认本次测试数据的实际归属与状态，使其对应当前访问要求。':kind==='evidence'?'核对实际业务结果的判断方式及可读取的来源。':'核对操作后的数据恢复方式，保留必要正常对照。'}</p>
   {kind==='evidence'&&action.effect_evidence.map(item=><ObjectIdentity key={item.effect_id} name={text(item.business_label)} status={<Badge tone={materialStatus([item]).tone}>{materialStatus([item]).label}</Badge>}/>)}
   {group?<><ul className="jj-plan-reasons">{group.messages.map(message=><li key={message}>{message}</li>)}</ul><ul className="jj-plan-gap-links">{gapEntryItems(action,group.items).map(item=><MaterialEntry key={JSON.stringify(item)} action={action} gap={item} returnTo={returnTo} changeId={changeId}/>)}</ul></>:<TaskActions><ActionLink href={'#'+scopedPath(general)}>核对{materialNames[kind]}</ActionLink></TaskActions>}
  </>}
  {(impacts.length>0||kind==='identity'&&group)&&<details><summary>材料核对信息</summary>{kind==='identity'&&group&&<ul>{group.messages.map(message=><li key={message}>{message}</li>)}</ul>}{impacts.map((item,index)=><p className="jj-plan-material-purpose" key={index}>{item.explanation??item.next_step}</p>)}<details><summary>准确材料与槽位引用</summary><pre>{JSON.stringify(impacts,null,2)}</pre></details></details>}
  <details><summary>关联的权限要求 · {action.permissions.length} 条</summary>{action.permissions.map(item=><p key={item.intent_id}>{text(action.identity_requirements.slots.find(slot=>slot.requirement.actor_id===item.subject_actor_id)?.actor_display_name??'操作人')}{item.expectation==='ALLOW'?'可以':'不得'}{text(action.display_name)} · {item.relation==='OWNS'?'本人的资源':'其他账号的资源'}{conditionLabels(item.conditions).length?' · '+conditionLabels(item.conditions).join('，'):''}</p>)}</details>
 </section>
}

export function gapName(reason: string) {
    return ({ IDENTITY_MATERIAL_ASSIGNMENT_CONFLICT:'已有材料的主体对应发生冲突，请核对归属后继续', MATERIAL_OWNER_CHANGED:'材料绑定的数据所属账号已变化，需要重新确认归属', SCENARIO_REQUEST_BUDGET_INSUFFICIENT:'当前请求上限不足以完成检查和数据恢复，请先调整检查连接中的请求上限', SCENARIO_RESOURCE_PRODUCER_REQUIRED:'前一步尚未准备好可独立确认的新建对象', SCENARIO_ITEM_NOT_PREPARED:'本步引用的账号、资源或规则需要重新准备', SCENARIO_CONTROL_REQUIRED:'需要保留相同操作方式的完整正常流程作为对照', SCENARIO_FULL_CONTROL_REQUIRED:'本步正常对照需要覆盖全部保护效果', BATCH_REQUEST_MAPPING_INVALID:'批量资源数组或返回项映射需要核对', BATCH_RESOURCE_ASSOCIATION_REQUIRED:'批量项必须使用同一动作并能逐项关联资源', TEST_IDENTITY_LOGIN_REQUIRED: '测试账号需要重新登录', RESOURCE_OWNER_SOURCE_STALE: '测试数据的归属需要重新确认', RESOURCE_INJECTION_STALE: '操作中的测试数据位置需要重新确认', CONDITION_SOURCE_REQUIRED:'尚未设置租户或数据状态的判断依据', RULE_CASE_DATA_STALE:'规则的测试数据需要重新核对', TEST_IDENTITY_REQUIRED: '测试账号尚未就绪', IDENTITY_REQUIRED: '测试账号尚未就绪', ACTION_RESOURCE_REQUIRED: '测试资源尚未确认', RESOURCE_REQUIRED: '测试资源尚未确认', ACTION_EXECUTION_REQUIRED: '尚未准备可重复执行的录制或接口流程', ACTION_EXECUTION_MISSING: '尚未准备可重复执行的录制或接口流程', EXECUTION_REQUIRED: '尚未准备可重复执行的录制或接口流程', EFFECT_EVIDENCE_REQUIRED: '尚未设置如何判断业务结果', EFFECT_VERDICT_PROOF_REQUIRED: '业务结果的判断依据还未准备好', REGISTERED_OBSERVER_UNAVAILABLE: '证明来源当前不可用', ACTION_RECOVERY_REQUIRED: '缺少恢复方式', RECOVERY_REQUIRED: '缺少恢复方式', ALLOW_CONTROL_REQUIRED: '需要选择一项应当成功的正常操作', PERMISSION_SEMANTICS_REQUIRED: '权限要求尚未确认', CREATED_RESOURCE_PROOF_REQUIRED: '缺少新建资源的独立记录', PREPARATION_REQUIRED: '材料需要重新核对' } as Record<string, string>)[reason] ?? '本项检查条件需要重新核对';
}
export function gapDestination(gap: CheckPreview['gaps'][number], returnTo: string, changeId?: string | null) {
    if(gap.reason==='SCENARIO_REQUEST_BUDGET_INSUFFICIENT')return '/application?'+new URLSearchParams({view:'environment',return_to:returnTo});
    const focus = gapKind(gap.reason);
    return '/preparation?' + new URLSearchParams({ action_id: gap.action_id, return_to: returnTo, ...(['identity','resource','execution','recovery','evidence'].includes(focus) ? { focus } : {}), ...(gap.action_revision?{action_revision:String(gap.action_revision)}:{}), ...(focus==='identity'?{identities:'1'}:focus==='execution'||focus==='recovery'?{material_kind:focus}:focus==='evidence'?{proof_sources:'1'}:{}), ...(gap.intent_id ? { rule_id: gap.intent_id } : {}), ...(gap.effect_id ? { effect_id: gap.effect_id } : {}), ...(changeId ? { change_id: changeId } : {}) });
}

function gapKind(reason: string) {
    if(reason==='CONDITION_SOURCE_REQUIRED')return 'evidence';
    if(reason==='RULE_CASE_DATA_STALE'||reason==='MATERIAL_OWNER_CHANGED')return 'resource';
    return /IDENTITY/.test(reason) ? 'identity' : /RESOURCE/.test(reason) && !/PROOF/.test(reason) ? 'resource' : /EXECUTION/.test(reason) ? 'execution' : /RECOVERY/.test(reason) ? 'recovery' : /EVIDENCE|PROOF|OBSERVER/.test(reason) ? 'evidence' : reason;
}

function groupGaps(gaps: CheckPreview['gaps']) {
    // 同一恢复去向合并入口，所有原因仍保留；执行门禁继续使用完整缺口。
    const groups = new Map<string, CheckPreview['gaps']>();
    for (const gap of gaps) { const kind = gapKind(gap.reason), key=['identity','resource','execution','recovery','evidence'].includes(kind)?kind:gapDestination(gap,''); groups.set(key, [...(groups.get(key) ?? []), gap]); }
    return Array.from(groups.values(), items => ({ kind:gapKind(items[0].reason), items, messages: [...new Set(items.map(item => gapName(item.reason)))] }));
}

function gapAction(kind: string) {
    return ({ identity: '准备测试账号', resource: '确认测试资源', execution: '准备执行操作', recovery: '准备恢复方式', evidence: '准备结果判断依据' } as Record<string, string>)[kind] ?? '核对检查条件';
}

/** 共用材料只提供一个准备入口；规则特有的资源条件与结果定位仍分别保留。 */
function gapEntryItems(action:ActionPreparation,items:CheckPreview['gaps']){
 const unique=new Map<string,CheckPreview['gaps'][number]>()
 for(const item of items){
  const kind=gapKind(item.reason),rule=action.permissions?.find(rule=>rule.intent_id===item.intent_id)
  const key=JSON.stringify([kind,kind==='identity'&&rule?[rule.subject_actor_id,rule.conditions?.principal]:['execution','recovery'].includes(kind)?'shared':gapDestination(item,'')])
  if(!unique.has(key))unique.set(key,item)
 }
 const entries=[...unique.values()]
 // 逐角色入口覆盖全部所需身份时，总入口只会重复同一工作；覆盖不完整仍保留总入口。
 const required=action.identity_requirements.slots.map(slot=>slot.requirement.actor_id)
 const directed=new Set(entries.filter(item=>gapKind(item.reason)==='identity').flatMap(item=>{
  const rule=action.permissions?.find(rule=>rule.intent_id===item.intent_id)
  return rule?[rule.subject_actor_id]:[]
 }))
 const covered=required.length>0&&required.every(actor=>directed.has(actor))
 return entries.filter(item=>!covered||gapKind(item.reason)!=='identity'||Boolean(action.permissions?.some(rule=>rule.intent_id===item.intent_id)))
}

function gapLinkLabel(action: ActionPreparation, gap: CheckPreview['gaps'][number]) {
    const rule=action.permissions?.find(rule=>rule.intent_id===gap.intent_id);
    const actor=(id:string)=>text(action.identity_requirements.slots.find(slot=>slot.requirement.actor_id===id)?.actor_display_name??'所选角色');
    const context=rule?`${rule.conditions?.principal==='ANONYMOUS'?'未登录访客':actor(rule.subject_actor_id)}${rule.expectation==='ALLOW'?'可以':'不得'}${text(action.display_name)}`
        :action.effect_evidence.find(effect=>effect.effect_id===gap.effect_id)?.business_label;
    if(gapKind(gap.reason)==='identity'&&rule)return '准备'+actor(rule.subject_actor_id)+'账号';
    return (context?context+'：':'')+gapAction(gapKind(gap.reason));
}

/** 名称和准备状态属于材料；入口只导航到原编辑器，不据展示状态放宽执行门槛。 */
function MaterialEntry({action,gap,returnTo,changeId}:{action:ActionPreparation;gap:CheckPreview['gaps'][number];returnTo:string;changeId:string|null}){
    const kind=gapKind(gap.reason),rule=action.permissions?.find(item=>item.intent_id===gap.intent_id);
    const slots=rule?action.identity_requirements.slots.filter(slot=>slot.requirement.actor_id===rule.subject_actor_id):[];
    const actor=(id:string)=>text(action.identity_requirements.slots.find(slot=>slot.requirement.actor_id===id)?.actor_display_name??'所选角色');
    const requirement=rule?`${rule.conditions?.principal==='ANONYMOUS'?'未登录访客':actor(rule.subject_actor_id)}${rule.expectation==='ALLOW'?'可以':'不得'}${text(action.display_name)}`:undefined;
    const effect=action.effect_evidence.find(item=>item.effect_id===gap.effect_id)?.business_label;
    const label=kind==='identity'&&rule?actor(rule.subject_actor_id)+'账号':requirement??text(effect??({identity:'所需测试账号',resource:'本次测试数据',execution:'操作步骤',recovery:'恢复方式',evidence:'业务结果'} as Record<string,string>)[kind]??'检查条件');
    const caption=({identity:'准备账号',resource:'确认资源',execution:'设置操作',recovery:'设置恢复',evidence:'设置依据'} as Record<string,string>)[kind]??'核对条件';
    const loginRequired=gap.reason==='TEST_IDENTITY_LOGIN_REQUIRED'||slots.some(slot=>slot.reason_codes?.includes('TEST_IDENTITY_LOGIN_REQUIRED'));
    const stale=/STALE|CHANGED/.test(gap.reason)||slots.some(slot=>slot.status==='STALE');
    const status=kind==='identity'?(loginRequired?'需重新登录':stale?'需重核':'待准备'):gap.reason==='REGISTERED_OBSERVER_UNAVAILABLE'?'当前不可用':stale?'需重核':kind==='resource'?'待确认':'待设置';
    return <li className="jj-plan-material-entry"><div className="jj-plan-entry-object"><span className="jj-plan-entry-name">{label}</span><span className="jj-plan-entry-state">{status}</span></div><ActionLink kind="default" data-size="compact" aria-label={caption+'：'+label} href={'#'+scopedPath(gapDestination(gap,returnTo,changeId))}>{caption}</ActionLink></li>;
}
