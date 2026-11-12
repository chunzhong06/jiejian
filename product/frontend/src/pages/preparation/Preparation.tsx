import {useMilestoneTransition} from '../../shared/lib/milestone'
import {Dialog} from '../../shared/ui/Dialog'
import {TaskSurface} from '../../shared/ui/TaskSurface'
import {BatchProgress} from './BatchProgress'
import {Choice} from '../../shared/ui/Choice'
import {Field,FormColumns,ObjectIdentity,ObjectHeading} from '../../shared/ui/layout'
import {useWorkflow} from '../../shared/lib/workflow';
import {IndexSelection} from '../../shared/ui/IndexSelection'
import {conditionLabels} from '../../entities/permission/ui/RuleConditions';
import {RuleCaseData} from './materials/RuleCaseData';
import { materialReasons } from './materials/reasons';
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import './styles/preparation.css'
import './styles/materials.css'
import { useEffect, useRef, useState, type ReactNode } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import UserOutlined from '@ant-design/icons/UserOutlined';
import VideoCameraOutlined from '@ant-design/icons/VideoCameraOutlined';
import DatabaseOutlined from '@ant-design/icons/DatabaseOutlined';
import FileDoneOutlined from '@ant-design/icons/FileDoneOutlined';
import UndoOutlined from '@ant-design/icons/UndoOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import CheckOutlined from '@ant-design/icons/CheckOutlined';
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined';
import ClockCircleOutlined from '@ant-design/icons/ClockCircleOutlined';
import RightOutlined from '@ant-design/icons/RightOutlined';
import { preparationApi, type ActionPreparation, type MaterialReference, type PreparationItem } from '../../entities/preparation/api/preparation';
import { preparationBatchesApi as batches, type PreparationBatchPlan } from '../../entities/preparation/api/batches';
import { assertProject, type PageProps } from '../../shared/model/page';
import {go,returnDestination,returnDestinationLabel,scopedPath} from '../../shared/lib/navigation'
import { text } from '../../shared/lib/format';
import { useRead } from '../../shared/lib/useRead';
import {PageError,  Badge, Empty, ErrorNote, InlineFeedback, Notice,Status} from "../../shared/ui/feedback"
import {Button,ActionLink} from '../../shared/ui/actions'
import { Heading } from "../../shared/ui/layout";
import { Accounts } from './materials/Accounts';
import { MaterialEditor } from './materials/MaterialEditor';
import { Sources } from './materials/Sources';
const materialNames = { identity: '测试账号', execution: '操作录制', resource: '测试资源', evidence: '业务结果证明', recovery: '操作恢复' };
type Kind = keyof typeof materialNames;
const materialSections: Array<{
    title: string;
    kinds: Kind[];
}> = [{ title: '操作准备', kinds: ['identity', 'execution', 'resource'] }, { title: '结果核对', kinds: ['evidence', 'recovery'] }];
function status(items: PreparationItem[]) { if (!items.length)
    return { label: '没有要求', tone: 'neutral' as const }; if (items.every(item => item.status === 'NOT_REQUIRED'))
    return { label: '不需要', tone: 'neutral' as const }; if (items.every(item => ['SATISFIED', 'NOT_REQUIRED'].includes(item.status)))
    return { label: '已就绪', tone: 'positive' as const }; if (items.some(item => item.status === 'BLOCKED'))
    return { label: '需要处理', tone: 'caution' as const }; if (items.some(item => item.status === 'STALE'))
    return { label: '需重新核对', tone: 'caution' as const }; return { label: '待准备', tone: 'neutral' as const }; }
export function Preparation(props: PageProps) {
    const { projectId, official, onError, refresh, route } = props;
    const workflow=useWorkflow();
    const returnTo = returnDestination(route.query.get('return_to'));
    const [selected, setSelected] = useState(''), [opened, setOpened] = useState<Kind>(), [plan, setPlan] = useState<PreparationBatchPlan>(), [ack, setAck] = useState(false), [busy, setBusy] = useState(false);
    const lock = useRef(false), key = `jiejian.studio.batch:${projectId}`;
    const [controls, setControls] = useState<Record<string, string>>({});
    const [focused, setFocused] = useState<Kind>();
    useEffect(() => { if (route.query.has('proof_sources') || route.query.has('source_id'))
        setOpened('evidence');
    else if (route.query.has('identities'))
        setOpened('identity');
    else if (route.query.has('material_kind'))
        setOpened(route.query.get('material_kind') as Kind);
    else
        setOpened(undefined); }, [route.query.get('source_id'), route.query.get('proof_sources'), route.query.get('identities'), route.query.get('material_kind')]);
    const batchState = useRead('preparation-batch:' + projectId, async (signal) => {
        const batch = await (sessionStorage.getItem(key) ? batches.status(projectId, sessionStorage.getItem(key)!, signal) : batches.latest(projectId, signal));
        if (batch)
            assertProject(batch.project_id, projectId);
        if (batch && !['RUNNING', 'CANCELLING'].includes(batch.state))
            sessionStorage.removeItem(key);
        return batch;
    }, value => value && ['RUNNING', 'CANCELLING'].includes(value.state) ? 700 : 0);
    const state = useRead('preparation:' + projectId, async (signal) => { const value = await preparationApi.get(projectId, signal); assertProject(value.project_id, projectId); return value; }, batchState.data && ['RUNNING', 'CANCELLING'].includes(batchState.data.state) ? 2000 : 0);
    const completion=useMilestoneTransition<HTMLElement>('materials:'+projectId+':'+(route.query.get('action_id')??'all'),state.data?Boolean(route.query.get('action_id')?state.data.actions.find(item=>item.action_id===route.query.get('action_id'))?.preparation_complete:state.data.preparation_complete)&&!['RUNNING','CANCELLING'].includes(batchState.data?.state??''):undefined,'materials');
    const navigate = (values: Record<string, string | null>) => { const query = new URLSearchParams(route.query); for (const [key, value] of Object.entries(values)) {
        if (value === null)
            query.delete(key);
        else
            query.set(key, value);
    } (workflow?.open??go)('/preparation' + (query.size ? '?' + query : '')); };
    const closeMaterial = () => { if(workflow){reload();workflow.finish();return;} setOpened(undefined); navigate({ material_kind: null, member_id: null, identities: null, account_slot: null, proof_sources: null, source_id: null, recording_id: null, preparation_id: null }); reload(); };
    const act = async (callback: () => Promise<unknown>) => { if (lock.current)
        return; lock.current = true; setBusy(true); try {
        await callback();
    }
    catch (error) {
        onError(error);
    }
    finally {
        lock.current = false;
        setBusy(false);
    } };
    const reload = () => { state.reload(); batchState.reload(); refresh(); };
    const exampleRequested=route.query.get('prepare_example')==='1',examplePreviewed=useRef(false);
    // 一键入口只打开原有范围确认；刷新和返回均不自动授权或重放准备批次。
    useEffect(()=>{
        if(!official||!exampleRequested||examplePreviewed.current||batchState.loading)return;
        examplePreviewed.current=true;
        setOpened(undefined);
        if(batchState.data&&['RUNNING','CANCELLING'].includes(batchState.data.state))return;
        void act(async()=>{setAck(false);setPlan(await batches.preview(projectId,'OFFICIAL'));});
    },[official,exampleRequested,projectId,batchState.loading,batchState.data]);
    if (state.loading)
        return <PageSkeleton view="/preparation"/>;
    if (state.error && !state.data)
        return <PageError title="检查准备" error={state.error}/>;
    if (!state.data)
        return null;
    const requestedAction=route.query.get('action_id');
    const scopedActions=workflow&&requestedAction?state.data.actions.filter(item=>item.action_id===requestedAction):state.data.actions;
    // 当前事项只汇总自己的材料；全应用的缺项不能覆盖这次检查的进度。
    const preparation = {...state.data,actions:scopedActions,preparation_complete:workflow&&requestedAction?scopedActions.length>0&&scopedActions.every(item=>item.preparation_complete):state.data.preparation_complete,impacts:state.data.impacts?.filter(item=>scopedActions.some(action=>action.action_id===item.action_id))}, batch = batchState.data;
    if(requestedAction&&(!preparation.actions.some(item=>item.action_id===requestedAction)||route.query.has('action_revision')&&!preparation.actions.some(item=>item.action_id===requestedAction&&String(item.action_revision)===route.query.get('action_revision'))))
        return <><Heading title="检查准备"/><Notice tone="caution">指定的业务操作或修订已不在当前准备范围中，请返回原事项核对。<Button onClick={()=>workflow?workflow.finish():go(returnTo??'/permissions')}>返回原事项</Button></Notice></>;
    const actorName=(id?:string)=>preparation.actions.flatMap(item=>item.identity_requirements.slots).find(item=>item.requirement.actor_id===id)?.actor_display_name;
    const ruleId = route.query.get('rule_id'), ruleAction = ruleId ? preparation.actions.find(item => item.permissions.some(rule => rule.intent_id === ruleId)) : undefined;
    const action = ruleAction ?? preparation.actions.find(item => item.action_id === (route.query.get('action_id') || selected || preparation.recommended_action_id)) ?? preparation.actions[0];
    const running = batch && ['RUNNING', 'CANCELLING'].includes(batch.state);
    const pending = Boolean(sessionStorage.getItem(key)) && !batch;
    const changed = state.error !== undefined || batchState.error !== undefined || batchState.loading;
    if (ruleId && !ruleAction)
        return <><Heading title="检查准备"/><Notice tone="caution">这条规则已不在当前准备范围中。<ActionLink navigationScope="page" href={'#'+scopedPath('/permissions?rule_id=' + encodeURIComponent(ruleId))}  kind="default">重新核对规则</ActionLink></Notice></>;
    const requestedKind = route.query.get('material_kind') as Kind | null;
    const requestedMaterial = action && requestedKind && ['execution', 'recovery', 'resource', 'evidence'].includes(requestedKind) ? { ref: { action_id: action.action_id, action_revision: action.action_revision, kind: requestedKind as MaterialReference['kind'], member_id: route.query.get('member_id') }, label: materialNames[requestedKind] } : undefined;
    const currentMaterial = requestedMaterial;
    if (currentMaterial)
        return <MaterialEditor resumeRecordingId={route.query.get('recording_id') ?? undefined} projectId={projectId} reference={currentMaterial.ref} label={currentMaterial.label} actionName={preparation.actions.find(item => item.action_id === currentMaterial.ref.action_id)?.display_name} onBack={closeMaterial} onError={onError}/>;
    if (opened === 'identity')
        return <Accounts projectId={projectId} actions={preparation.actions} requestedIdentity={route.query.get('identity_id')} requestedSlot={route.query.get('account_slot')??(ruleId?action?.identity_requirements.slots.find(slot=>slot.requirement.actor_id===action.permissions.find(item=>item.intent_id===ruleId)?.subject_actor_id)?.requirement.slot_id:null)} requestedPreparation={route.query.get('preparation_id')} onBack={closeMaterial} onError={onError}/>;
    if (opened === 'evidence')
        return <Sources projectId={projectId} actionId={action?.action_id} requestedEffect={route.query.get('effect_id')} requestedSource={route.query.get('source_id')} onLocate={id => navigate({ action_id: action?.action_id ?? null, source_id: id, proof_sources: '1' })} onBack={closeMaterial} onError={onError}/>;
    const batchBody=plan&&<div className="jj-batch-review-body">
      <dl className="jj-facts" data-layout="columns"><div><dt>适用应用</dt><dd>{props.name}</dd></div><div><dt>应用地址</dt><dd>{plan.runtime_origin}</dd></div></dl>
      <FormColumns>
        <section className="jj-batch-review-work"><h2 className="jj-title-group">本次准备内容</h2><ol className="jj-preparation-consent">
          {official&&<><li><h3>准备测试账号</h3><p>登录示例中的负责人和评审账号，使用独立测试数据。</p></li><li><h3>建立操作与测试资料</h3><p>准备校园展馆的下载、预览操作，以及检查后的恢复方式。</p></li></>}
          <li><h3>核对业务结果证明</h3><p>{official?'使用负责人和评审测试账号核对身份，按本次读取范围检查展馆记录与完整文件。':'只访问本次列出的证明来源。'}核对通过后，将这些材料用于当前应用的检查。</p></li>
        </ol></section>
        <section className="jj-batch-review-sources"><h2 className="jj-title-group">本次读取范围</h2>
          {official&&<dl className="jj-facts"><div><dt>身份核对</dt><dd>/api/me</dd></div><div><dt>展馆记录</dt><dd>{'/collections/galleries/{resource_id}'}</dd></div><div><dt>文件参照</dt><dd>负责人可取得的内部完整包和公开展示版</dd></div></dl>}
          <ul>{plan.sources.map(source=><li key={source.source_id}><span>{text(source.label)}</span><small>第 {source.revision} 修订</small></li>)}</ul>
        </section>
      </FormColumns>
      <section className="jj-batch-review-consent"><h3>确认后开始准备</h3><p>本次只准备材料。正式检查会在预览范围后另行提交。</p><label className="jj-checkbox"><input type="checkbox" checked={ack} onChange={event=>setAck(event.target.checked)} disabled={busy}/><span>允许上述操作、来源读取及材料采用</span></label></section>
    </div>;
    const batchActions=plan&&((dismiss:()=>void)=><><Button disabled={busy} onClick={dismiss}>返回</Button><Button kind="primary" busy={busy} disabled={!ack} onClick={() => void act(async () => { const existing = sessionStorage.getItem(key); if (existing) {
            await batches.status(projectId, existing);
            setPlan(undefined);
            reload();
            return;
        } const operation = crypto.randomUUID().replaceAll('-', ''); sessionStorage.setItem(key, operation); try {
            await batches.start(projectId, operation, plan);
            setPlan(undefined);
            reload();
        }
        catch (error) {
            setPlan(undefined);
            reload();
            throw error;
        } })}>允许并开始准备</Button></>);
    if(plan&&official)return <TaskSurface title="为数字展馆准备检查材料" onBack={()=>{if(!busy)setPlan(undefined)}} backLabel="返回检查准备" actions={batchActions}>{batchBody}</TaskSurface>;
    const groups = action ? groupsFor(action) : [];
    const nextKind: Kind | undefined = action?.next_material ?? undefined;
    const focus = focused ?? route.query.get('focus') ?? nextKind ?? 'identity';
    const selectedGroup = groups.find(group => group.key === focus) ?? groups[0];
    const openMaterial = (kind: Kind, slotId?: string) => { if (kind === 'identity' || kind === 'evidence') {
        setOpened(kind);
        navigate({ action_id: action.action_id, account_slot: kind === 'identity' ? slotId ?? null : null, [kind === 'identity' ? 'identities' : 'proof_sources']: '1' });
    }
    else if (kind === 'execution' || kind === 'recovery')
        navigate({ action_id: action.action_id, material_kind: kind });
    else
        setFocused(kind); };
    const primary = () => { if(preparation.preparation_complete&&workflow){workflow.finish();return;} if(preparation.preparation_complete&&returnTo){go(returnTo);return;} if (preparation.preparation_complete)
        go('/reports?view=plan' + (route.query.get('change_id') ? '&change_id=' + encodeURIComponent(route.query.get('change_id')!) : '') + (route.query.get('rule_id') ? '&rule_id=' + encodeURIComponent(route.query.get('rule_id')!) : ''));
    else if (nextKind)
        openMaterial(nextKind);
    else if (selectedGroup)
        openMaterial(selectedGroup.key); };
    const effectName = (id: string) => action?.effect_evidence.find(item => item.effect_id === id)?.business_label ?? '业务结果';
    return <>{returnTo && !workflow && <div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(returnTo)} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}{returnDestinationLabel(returnTo)}</ActionLink></div>}<Heading title="检查准备" actions={!running&&(!workflow||official)&&preparation.actions.length > 0 ? <Button busy={busy} disabled={Boolean(running) || pending || changed} onClick={() => void act(async () => { setAck(false); setPlan(await batches.preview(projectId, official ? 'OFFICIAL' : 'REVIEWED')); })}>{preparation.preparation_complete ? '核对整批材料' : official ? '一键准备示例材料' : '核对整批材料'}</Button> : undefined}/>{state.error && <ErrorNote error={state.error}/>}{batchState.error && <ErrorNote error={batchState.error}/>}
    {plan&&!official&&<Dialog title="确认这批材料的使用范围" size="wide" onClose={()=>setPlan(undefined)} closeDisabled={busy} actions={batchActions}>{batchBody}</Dialog>}
    {running && <BatchProgress batch={batch} onCancel={() => void act(async () => { await batches.cancel(projectId, batch.operation_id); reload(); })}/>}
    {pending && <Notice tone="caution">准备请求的结果尚未确认。<Button onClick={batchState.reload}>查询本次准备</Button></Notice>}{batch?.state === 'BLOCKED' && <Notice tone={batch.error_code === 'PREPARATION_INTERNAL_ERROR' ? 'negative' : 'caution'}>{text(batch.message)}</Notice>}{batch?.state === 'CANCELLED' && <InlineFeedback>{text(batch.message)}</InlineFeedback>}

    {!preparation.actions.length ? <Empty layout="section" title="先确认要检查的权限" action={<ActionLink navigationScope="page" href={'#'+scopedPath('/permissions')} kind="primary">打开权限规则</ActionLink>}>先明确谁可以对哪些数据执行什么操作。确认权限要求后，这里会列出所需账号、测试数据、操作步骤和结果证明。</Empty> : <>
      {action.assurance_contract.allow_controls.filter(control => !control.resolved_allow_permission && control.candidate_allow_permissions.length > 1).map(control => <section className="jj-panel jj-preparation-decision" key={control.selection_fingerprint}><div className="jj-preparation-decision-body"><header><h2 className="jj-title-group">选择用来确认正常功能的操作</h2><p>选择一项本来允许的操作，与禁止场景一起检查，确认正常功能仍能完成。</p></header><fieldset className="jj-choice-field">{control.candidate_allow_permissions.map(candidate => { const permission = action.permissions.find(item => item.intent_id === candidate.intent_id), actor = actorName(permission?.subject_actor_id), owner = actorName(permission?.resource_owner_actor_id); return <label key={candidate.intent_id}><input type="radio" name={control.selection_fingerprint} checked={controls[control.selection_fingerprint] === candidate.intent_id} onChange={() => setControls(value => ({ ...value, [control.selection_fingerprint]: candidate.intent_id }))}/><span>{text(actor ?? '指定账号')}{text(action.display_name)}<small>{permission?.relation === 'OWNS' ? '使用自己的资源' : `使用${text(owner ?? '对应所有者')}的资源`}</small></span></label>; })}</fieldset></div><footer><Button kind="primary" busy={busy} disabled={!controls[control.selection_fingerprint] || changed} onClick={() => void act(async () => { const selected = control.candidate_allow_permissions.find(item => item.intent_id === controls[control.selection_fingerprint]); if (selected) {
            await preparationApi.selectAllowControl(projectId, control, selected);
            reload();
        } })}>确认这项正常操作</Button></footer></section>)}
      <section ref={completion} hidden={Boolean(running)} className="jj-preparation-workbench" data-single={groups.length===1||undefined} data-focused={route.query.has('focus')||groups.length===1||undefined} aria-label="当前业务操作所需材料">
        <header data-milestone-part="heading" className="jj-preparation-context">
          {preparation.actions.length === 1 && <h2>{text(action.display_name)}</h2>}
          {preparation.actions.length > 1 && <div className="jj-operation-selector"><Field label="当前业务操作" status={<Badge tone={action.preparation_complete?'positive':'neutral'}>{action.preparation_complete?'材料齐备':'材料待准备'}</Badge>}><Choice value={action.action_id} onValueChange={value=>{setSelected(value);setOpened(undefined);setFocused(undefined);navigate({action_id:value,rule_id:null,focus:null,material_kind:null,member_id:null})}}>{preparation.actions.map(item=><option key={item.action_id} value={item.action_id}>{text(item.display_name)}{item.preparation_complete?' · 材料已准备':''}</option>)}</Choice></Field></div>}
          {preparation.actions.length===1&&<Badge tone={action.preparation_complete ? 'positive' : 'neutral'}>{action.preparation_complete ? '材料齐备' : '材料待准备'}</Badge>}
        </header>
        {groups.length>1&&<MaterialIndex identity={action.action_id+selectedGroup?.key}>
          <div className="jj-material-index-heading"><h2 className="jj-title-group">所需材料</h2></div>
          {materialSections.map(section => <div className="jj-material-section" key={section.title}>
            <h3 className="jj-title-caption">{section.title}</h3>
            {groups.filter(group => section.kinds.includes(group.key)).map(group => {
                    const state = status(group.items);
                    return <button className="jj-material-select jj-index-item" key={group.key} aria-pressed={selectedGroup?.key === group.key} aria-label={`查看${materialNames[group.key]}`} onClick={() => { setFocused(group.key); navigate({ action_id: action.action_id, focus: group.key }); }}>
              <span className="jj-material-icon">{group.icon}</span>
              <span className="jj-object-identity"><strong className="jj-material-select-label">{materialNames[group.key]}</strong><Status className="jj-material-select-status" tone={state.tone} title={state.label}>{state.tone === 'positive' && <CheckOutlined aria-hidden="true"/>}{state.label === '需要重新核对' ? '需核对' : state.label}</Status></span>
              <RightOutlined aria-hidden="true"/>
            </button>;
                })}
          </div>)}
        </MaterialIndex>}
        {selectedGroup && <div className="jj-material-detail" data-material-kind={selectedGroup.key} key={action.action_id + selectedGroup.key}>
          <Button className="jj-material-back" kind="quiet" onClick={()=>{setFocused(undefined);navigate({focus:null})}}>返回材料目录</Button><header><h2>{materialNames[selectedGroup.key]}</h2>{selectedGroup.key !== 'identity' && <Badge tone={status(selectedGroup.items).tone}>{status(selectedGroup.items).label}</Badge>}</header>
          <div className="jj-material-reading"><div className="jj-material-primary">
          <div className="jj-material-requirements">
            {selectedGroup.key === 'identity' ? <div className="jj-account-entities">{action.identity_requirements.slots.map(slot => <article className="jj-account-entity" key={slot.requirement.slot_id}><span className="jj-account-entity-icon"><UserOutlined aria-hidden="true"/></span><ObjectHeading level={3} title={<>{text(slot.actor_display_name)}账号{slot.requirement.ordinal > 1 ? ` ${slot.requirement.ordinal}` : ''}</>} status={<Badge tone={status([slot]).tone}>{status([slot]).label}</Badge>} description={action.resources.some(resource => resource.owner_slot_id === slot.requirement.slot_id) ? '提供本次检查所用资源' : '执行对应角色的业务操作'}/><Button kind="quiet" disabled={busy || changed} onClick={() => openMaterial('identity', slot.requirement.slot_id)}>{slot.test_identity_id ? '核对账号' : '准备账号'}<ArrowRightOutlined aria-hidden="true"/></Button></article>)}</div> :
                    selectedGroup.key === 'evidence' ? action.effect_evidence.map(item => <div className="jj-material-requirement" key={item.effect_id}><ObjectIdentity name={text(effectName(item.effect_id))} status={<Status tone={status([item]).tone}>{status([item]).label}</Status>}/></div>) :
                        selectedGroup.key === 'resource' ? action.resources.map((item, index) => <div className="jj-material-requirement" key={item.owner_slot_id}><span>测试资源 {index + 1}</span><Button kind="quiet" disabled={busy || changed || !item.owner_test_identity_id} onClick={() => navigate({ action_id: action.action_id, material_kind: 'resource', member_id: item.owner_test_identity_id })}>{item.owner_test_identity_id ? '确认测试数据' : '先准备所有者账号'}</Button></div>) :
                            <div className="jj-material-requirement"><ObjectIdentity name={selectedGroup.key === 'execution' ? text(action.display_name) : action.recovery.status === 'NOT_REQUIRED' ? '本项操作不改变业务数据' : '恢复本次操作改变的数据'} status={<Status tone={status(selectedGroup.items).tone}>{status(selectedGroup.items).label}</Status>}/></div>}
          </div>
          {selectedGroup.key === "resource" && <RuleCaseData projectId={projectId} action={action} onSaved={reload}/>}
          {selectedGroup.key !== 'identity' && selectedGroup.key !== 'resource' && status(selectedGroup.items).label !== '不需要' && <div className="jj-material-detail-actions"><Button disabled={busy || changed} onClick={() => openMaterial(selectedGroup.key)}>{selectedGroup.key === 'evidence' ? '准备结果判断依据' : selectedGroup.key === 'recovery' ? '核对恢复方式' : '选择或录制操作'}<ArrowRightOutlined aria-hidden="true"/></Button></div>}
          {selectedGroup.items.some(item => item.reason_codes.length > 0) && <details><summary>材料核对信息</summary><ul>{[...new Set(selectedGroup.items.flatMap(item => item.reason_codes))].map(code => <li className="jj-small jj-muted" key={code}>{materialReasons([code])[0]}</li>)}</ul></details>}
          </div>
          <details className="jj-material-used-by"><summary>关联的权限要求<span>{action.permissions.length} 条</span></summary><ul>{action.permissions.map((rule, index) => { const subject = rule.conditions?.principal==='ANONYMOUS'?'未登录访客':actorName(rule.subject_actor_id) ?? '操作人', owner = actorName(rule.resource_owner_actor_id) ?? '资源所有者'; return <li key={rule.intent_id ?? index}><span className="jj-material-rule-mark" data-allowed={rule.expectation === 'ALLOW'} aria-hidden="true">{rule.expectation === 'ALLOW' ? <CheckOutlined /> : '−'}</span><div><p>{text(subject)}{rule.expectation === 'ALLOW' ? '可以' : '不得'}{text(action.display_name)}</p><small>{rule.relation === 'OWNS' ? '自己的资源' : rule.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `其他${text(owner)}账号的资源` : `${text(owner)}的资源`}{conditionLabels(rule.conditions).length>0?"，"+conditionLabels(rule.conditions).join("，"):""}</small></div></li>; })}</ul></details>
          </div>
        </div>}
        <footer data-milestone-part="actions" className="jj-preparation-footer"><div className="jj-preparation-progress">{preparation.preparation_complete ? <CheckCircleOutlined aria-hidden="true"/> : <ClockCircleOutlined aria-hidden="true"/>}<strong>{preparation.preparation_complete ? workflow?'当前事项的材料已齐备':'所有业务操作的材料已齐备' : action.preparation_complete?'当前操作的材料已齐备':'尚需准备'+text(action.display_name)}</strong></div><div className="jj-preparation-next">{!preparation.preparation_complete&&!nextKind&&<p>选择一项材料查看待处理内容。</p>}{preparation.preparation_complete&&<Button kind="primary" onClick={primary} disabled={changed || Boolean(running) || pending}>{preparation.preparation_complete ? workflow?'继续本次检查':'预览检查' : nextKind ? '准备' + materialNames[nextKind].replace(/^测试|^业务/, '') : '查看当前材料'}<ArrowRightOutlined aria-hidden="true"/></Button>}</div></footer>
      </section>
    {!running&&preparation.impacts?.some(item=>['STALE','BLOCKED'].includes(item.status)) && <details className="jj-preparation-impact"><summary>跨业务操作的材料影响：{preparation.impacts.filter(item=>['NEEDS_USER','STALE','BLOCKED'].includes(item.status)).length} 项材料需要处理，{preparation.impacts.filter(item=>item.status==='SATISFIED').length} 项仍可沿用</summary><div>{preparation.impacts.filter(item=>['NEEDS_USER','STALE','BLOCKED'].includes(item.status)).map((item,index)=><article key={item.action_id+item.kind+index}><div><strong>{text(item.action_label)} / {materialNames[item.kind]}{item.member_label ? ' / '+text(item.member_label) : ''}</strong>{materialReasons(item.reason_codes).map(reason=><p className="jj-small jj-muted" key={reason}>{reason}</p>)}</div><span className="jj-small jj-muted">涉及 {item.permission_ids.length} 条规则</span><Button onClick={()=>{setSelected(item.action_id);setFocused(item.kind);navigate({action_id:item.action_id,focus:item.kind,rule_id:null,material_kind:['execution','resource','recovery'].includes(item.kind)?item.kind:null,member_id:item.member_id,identities:item.kind==='identity'?'1':null,proof_sources:item.kind==='evidence'?'1':null});}}>核对材料</Button></article>)}</div></details>}
    </>}
  </>;
}
function groupsFor(action: ActionPreparation): Array<{
    key: Kind;
    icon: React.ReactNode;
    items: PreparationItem[];
}> { return [{ key: 'identity', icon: <UserOutlined aria-hidden="true"/>, items: action.identity_requirements.slots }, { key: 'execution', icon: <VideoCameraOutlined aria-hidden="true"/>, items: [action.execution] }, { key: 'resource', icon: <DatabaseOutlined aria-hidden="true"/>, items: action.resources }, { key: 'evidence', icon: <FileDoneOutlined aria-hidden="true"/>, items: action.effect_evidence }, { key: 'recovery', icon: <UndoOutlined aria-hidden="true"/>, items: [action.recovery] }]; }

function MaterialIndex({identity,children}:{identity:string;children:ReactNode}) {
  return <IndexSelection className="jj-material-index" identity={identity}>{children}</IndexSelection>
}
