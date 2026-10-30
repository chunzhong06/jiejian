import { materialReasons } from './materials/reasons';
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import './styles/preparation.css'
import './styles/materials.css'
import { useEffect, useRef, useState } from 'react';
import { ArrowLeftOutlined, UserOutlined, VideoCameraOutlined, DatabaseOutlined, FileDoneOutlined, UndoOutlined, ArrowRightOutlined, CheckOutlined, CheckCircleOutlined, ClockCircleOutlined, RightOutlined } from '@ant-design/icons';
import { preparationApi, type ActionPreparation, type MaterialReference, type PreparationItem } from '../../entities/preparation/api/preparation';
import { preparationBatchesApi as batches, type PreparationBatchPlan } from '../../entities/preparation/api/batches';
import { assertProject, type PageProps } from '../../shared/model/page';
import { go, returnDestination } from '../../shared/lib/navigation';
import { text } from '../../shared/lib/format';
import { useRead } from '../../shared/lib/useRead';
import { Badge, Empty, ErrorNote, Notice } from "../../shared/ui/feedback";
import { Button } from "../../shared/ui/actions";
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
    const navigate = (values: Record<string, string | null>) => { const query = new URLSearchParams(route.query); for (const [key, value] of Object.entries(values)) {
        if (value === null)
            query.delete(key);
        else
            query.set(key, value);
    } go('/preparation' + (query.size ? '?' + query : '')); };
    const closeMaterial = () => { setOpened(undefined); navigate({ material_kind: null, member_id: null, identities: null, proof_sources: null, source_id: null, recording_id: null, preparation_id: null }); reload(); };
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
    if (state.loading)
        return <PageSkeleton view="/preparation"/>;
    if (state.error && !state.data)
        return <ErrorNote error={state.error} onRetry={state.reload}/>;
    if (!state.data)
        return null;
    const preparation = state.data, batch = batchState.data;
    const actorName=(id?:string)=>preparation.actions.flatMap(item=>item.identity_requirements.slots).find(item=>item.requirement.actor_id===id)?.actor_display_name;
    const ruleId = route.query.get('rule_id'), ruleAction = ruleId ? preparation.actions.find(item => item.permissions.some(rule => rule.intent_id === ruleId)) : undefined;
    const action = ruleAction ?? preparation.actions.find(item => item.action_id === (route.query.get('action_id') || selected || preparation.recommended_action_id)) ?? preparation.actions[0];
    const running = batch && ['RUNNING', 'CANCELLING'].includes(batch.state);
    const pending = Boolean(sessionStorage.getItem(key)) && !batch;
    const changed = state.error !== undefined || batchState.error !== undefined || batchState.loading;
    if (ruleId && !ruleAction)
        return <><Heading title="检查准备"/><Notice>这条规则已不在当前准备范围中。<Button onClick={() => go('/permissions?rule_id=' + encodeURIComponent(ruleId))}>重新核对规则</Button></Notice></>;
    const requestedKind = route.query.get('material_kind') as Kind | null;
    const requestedMaterial = action && requestedKind && ['execution', 'recovery', 'resource', 'evidence'].includes(requestedKind) ? { ref: { action_id: action.action_id, action_revision: action.action_revision, kind: requestedKind as MaterialReference['kind'], member_id: route.query.get('member_id') }, label: materialNames[requestedKind] } : undefined;
    const currentMaterial = requestedMaterial;
    if (currentMaterial)
        return <MaterialEditor resumeRecordingId={route.query.get('recording_id') ?? undefined} projectId={projectId} reference={currentMaterial.ref} label={currentMaterial.label} actionName={preparation.actions.find(item => item.action_id === currentMaterial.ref.action_id)?.display_name} onBack={closeMaterial} onError={onError}/>;
    if (opened === 'identity')
        return <Accounts projectId={projectId} actions={preparation.actions} requestedPreparation={route.query.get('preparation_id')} onBack={closeMaterial} onError={onError}/>;
    if (opened === 'evidence')
        return <Sources projectId={projectId} actionId={action?.action_id} requestedSource={route.query.get('source_id')} onLocate={id => navigate({ action_id: action?.action_id ?? null, source_id: id, proof_sources: '1' })} onBack={closeMaterial} onError={onError}/>;
    if (plan)
        return <><div><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} disabled={busy} onClick={() => setPlan(undefined)}>检查准备</Button></div><Heading eyebrow="材料读取与准备" title={official ? '为数字展馆准备检查材料' : '确认这批材料的使用范围'}/><div className="jj-consent-review"><section className="jj-panel"><h2>本次会做什么</h2><ol className="jj-preparation-consent">{official && <><li><h3>准备测试账号</h3><p>登录示例中的负责人和评审账号，使用独立测试数据。</p></li><li><h3>建立操作与测试资料</h3><p>准备校园展馆的下载、预览操作，以及检查后的恢复方式。</p></li></>}<li><h3>核对业务结果证明</h3><p>{official ? '使用负责人和评审测试账号核对身份，读取校园展馆记录及完整测试文件，核对通过后用于本示例检查。' : '仅访问下面列出的来源，核对通过后用于当前应用的检查。'}</p>{official && <dl className="jj-facts"><div><dt>身份核对</dt><dd>/api/me</dd></div><div><dt>展馆记录</dt><dd>{'/collections/galleries/{resource_id}'}</dd></div><div><dt>文件参照</dt><dd>负责人可取得的内部完整包和公开展示版</dd></div></dl>}<ul>{plan.sources.map(source => <li key={source.source_id}>{text(source.label)}<small>版本 {source.revision}</small></li>)}</ul></li></ol><dl className="jj-facts"><div><dt>应用地址</dt><dd>{plan.runtime_origin}</dd></div><div><dt>适用应用</dt><dd>{props.name}</dd></div></dl></section><aside className="jj-panel jj-sticky"><h3>确认后开始准备</h3><p className="jj-review-summary">本次只准备材料。正式检查会在预览范围后另行提交。</p><label className="jj-checkbox"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} disabled={busy}/><span>允许上述操作、来源读取及材料采用</span></label><div className="jj-review-buttons jj-confirmation-actions"><Button disabled={busy} onClick={() => setPlan(undefined)}>返回</Button><Button kind="primary" busy={busy} disabled={!ack} onClick={() => void act(async () => { const existing = sessionStorage.getItem(key); if (existing) {
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
        } })}>允许并开始准备</Button></div></aside></div></>;
    const groups = action ? groupsFor(action) : [];
    const nextKind: Kind | undefined = action?.next_material ?? undefined;
    const focus = focused ?? route.query.get('focus') ?? nextKind ?? 'identity';
    const selectedGroup = groups.find(group => group.key === focus) ?? groups[0];
    const openMaterial = (kind: Kind) => { if (kind === 'identity' || kind === 'evidence') {
        setOpened(kind);
        navigate({ action_id: action.action_id, [kind === 'identity' ? 'identities' : 'proof_sources']: '1' });
    }
    else if (kind === 'execution' || kind === 'recovery')
        navigate({ action_id: action.action_id, material_kind: kind });
    else
        setFocused(kind); };
    const primary = () => { if (preparation.preparation_complete)
        go('/reports?view=plan' + (route.query.get('change_id') ? '&change_id=' + encodeURIComponent(route.query.get('change_id')!) : '') + (route.query.get('rule_id') ? '&rule_id=' + encodeURIComponent(route.query.get('rule_id')!) : ''));
    else if (nextKind)
        openMaterial(nextKind);
    else if (selectedGroup)
        openMaterial(selectedGroup.key); };
    const effectName = (id: string) => action?.effect_evidence.find(item => item.effect_id === id)?.business_label ?? '业务结果';
    return <>{returnTo && <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => go(returnTo)}>返回本次检查</Button></div>}<Heading title="检查准备" actions={preparation.actions.length > 0 ? <Button busy={busy} disabled={Boolean(running) || pending || changed} onClick={() => void act(async () => { setAck(false); setPlan(await batches.preview(projectId, official ? 'OFFICIAL' : 'REVIEWED')); })}>{preparation.preparation_complete ? '核对整批材料' : official ? '准备示例材料' : '核对整批材料'}</Button> : undefined}/>{state.error && <ErrorNote error={state.error} onRetry={state.reload}/>}{batchState.error && <ErrorNote error={batchState.error} onRetry={batchState.reload}/>}
    {running && <section className="jj-panel"><div className="jj-panel-heading"><h2>正在准备材料</h2><Badge tone="accent">{batch.completed} / {batch.total}</Badge></div><progress value={batch.completed} max={batch.total || 1}/><div className="jj-batch-items">{batch.identities?.map(item => <div key={item.account}><span>{item.account === 'curator' ? '负责人账号' : item.account === 'judge' ? '评审账号' : item.account}</span><span>{item.state === 'PREPARED' ? '已登录' : item.state === 'FAILED' ? '准备中断' : '处理中'}</span></div>)}{batch.items?.map(item => <div key={item.label}><span>{text(item.label)}</span><span>{({ READY: '已就绪', CHECKING: '正在核对', BLOCKED: '需要处理', WAITING: '等待处理' } as Record<string, string>)[item.state] ?? text(item.state)}</span></div>)}</div><Button kind="quiet" disabled={batch.cancel_requested} onClick={() => void act(async () => { await batches.cancel(projectId, batch.operation_id); reload(); })}>{batch.cancel_requested ? '正在停止' : '停止准备'}</Button></section>}
    {pending && <Notice>准备请求的结果尚未确认。<Button onClick={batchState.reload}>查询本次准备</Button></Notice>}{batch?.state === 'BLOCKED' && <Notice tone={batch.error_code === 'PREPARATION_INTERNAL_ERROR' ? 'negative' : 'caution'}>{text(batch.message)}</Notice>}{batch?.state === 'CANCELLED' && <Notice tone="neutral">{text(batch.message)}</Notice>}
    {preparation.impacts?.some(item=>['STALE','BLOCKED'].includes(item.status)) && <details className="jj-preparation-impact"><summary>{preparation.impacts.filter(item=>['NEEDS_USER','STALE','BLOCKED'].includes(item.status)).length} 项材料需要处理，{preparation.impacts.filter(item=>item.status==='SATISFIED').length} 项仍可沿用</summary><div>{preparation.impacts.filter(item=>['NEEDS_USER','STALE','BLOCKED'].includes(item.status)).map((item,index)=><article key={item.action_id+item.kind+index}><div><strong>{text(item.action_label)} / {materialNames[item.kind]}{item.member_label ? ' / '+text(item.member_label) : ''}</strong>{materialReasons(item.reason_codes).map(reason=><p className="jj-small jj-muted" key={reason}>{reason}</p>)}</div><span className="jj-small jj-muted">涉及 {item.permission_ids.length} 条规则</span><Button onClick={()=>{setSelected(item.action_id);setFocused(item.kind);navigate({action_id:item.action_id,focus:item.kind,rule_id:null,material_kind:['execution','resource','recovery'].includes(item.kind)?item.kind:null,member_id:item.member_id,identities:item.kind==='identity'?'1':null,proof_sources:item.kind==='evidence'?'1':null});}}>核对材料</Button></article>)}</div></details>}
    {!preparation.actions.length ? <Empty title="先确认要检查的权限" action={<Button kind="primary" onClick={() => go('/permissions')}>打开权限规则</Button>}/> : <>
      {action.assurance_contract.allow_controls.filter(control => !control.resolved_allow_permission && control.candidate_allow_permissions.length > 1).map(control => <section className="jj-panel" key={control.selection_fingerprint}><h3>选择用来确认正常功能的操作</h3><fieldset className="jj-choice-field">{control.candidate_allow_permissions.map(candidate => { const permission = action.permissions.find(item => item.intent_id === candidate.intent_id), actor = actorName(permission?.subject_actor_id), owner = actorName(permission?.resource_owner_actor_id); return <label key={candidate.intent_id}><input type="radio" name={control.selection_fingerprint} checked={controls[control.selection_fingerprint] === candidate.intent_id} onChange={() => setControls(value => ({ ...value, [control.selection_fingerprint]: candidate.intent_id }))}/><span>{text(actor ?? '指定账号')}{text(action.display_name)}<small>{permission?.relation === 'OWNS' ? '使用自己的资源' : `使用${text(owner ?? '对应所有者')}的资源`}</small></span></label>; })}</fieldset><Button kind="primary" busy={busy} disabled={!controls[control.selection_fingerprint] || changed} onClick={() => void act(async () => { const selected = control.candidate_allow_permissions.find(item => item.intent_id === controls[control.selection_fingerprint]); if (selected) {
            await preparationApi.selectAllowControl(projectId, control, selected);
            reload();
        } })}>保存正常操作对照</Button></section>)}
      <section className="jj-preparation-workbench" aria-label="当前业务操作所需材料">
        <header className="jj-preparation-context">
          <div className="jj-item-heading"><h2>{text(action.display_name)}</h2><Badge tone={action.preparation_complete ? 'positive' : 'neutral'}>{action.preparation_complete ? '材料齐备' : '准备检查材料'}</Badge></div>
          {preparation.actions.length > 1 && <div className="jj-action-tabs" aria-label="选择业务动作">{preparation.actions.map(item => <button key={item.action_id} aria-current={action.action_id === item.action_id ? 'page' : undefined} onClick={() => { setSelected(item.action_id); setOpened(undefined); setFocused(undefined); navigate({ action_id: item.action_id, rule_id: null, focus: null, material_kind: null, member_id: null }); }}>{item.preparation_complete && <CheckOutlined aria-hidden="true"/>}{text(item.display_name)}</button>)}</div>}
        </header>
        <div className="jj-material-index">
          <div className="jj-material-index-heading"><h2>所需材料</h2></div>
          {materialSections.map(section => <div className="jj-material-section" key={section.title}>
            <h3>{section.title}</h3>
            {groups.filter(group => section.kinds.includes(group.key)).map(group => {
                    const state = status(group.items);
                    return <button className="jj-material-select" key={group.key} aria-pressed={selectedGroup?.key === group.key} aria-label={`查看${materialNames[group.key]}`} onClick={() => { setFocused(group.key); navigate({ action_id: action.action_id, focus: group.key }); }}>
              <span className="jj-material-icon">{group.icon}</span>
              <span className="jj-material-select-label"><strong>{materialNames[group.key]}</strong><span data-tone={state.tone}>{state.tone === 'positive' && <CheckOutlined aria-hidden="true"/>}{state.label}</span></span>
              <RightOutlined aria-hidden="true"/>
            </button>;
                })}
          </div>)}
        </div>
        {selectedGroup && <div className="jj-material-detail" data-material-kind={selectedGroup.key} key={action.action_id + selectedGroup.key}>
          <header><h2>{materialNames[selectedGroup.key]}</h2>{selectedGroup.key !== 'identity' && <Badge tone={status(selectedGroup.items).tone}>{status(selectedGroup.items).label}</Badge>}</header>
          <div className="jj-material-reading"><div className="jj-material-primary">
          <div className="jj-material-requirements">
            {selectedGroup.key === 'identity' ? <div className="jj-account-entities">{action.identity_requirements.slots.map(slot => <article className="jj-account-entity" key={slot.requirement.slot_id}><header><span className="jj-account-entity-icon"><UserOutlined aria-hidden="true"/></span><div><h3>{text(slot.actor_display_name)}账号{slot.requirement.ordinal > 1 ? ` ${slot.requirement.ordinal}` : ''}</h3><p>{action.resources.some(resource => resource.owner_slot_id === slot.requirement.slot_id) ? '提供本次检查所用资源' : '执行对应角色的业务操作'}</p></div></header><footer><Badge tone={status([slot]).tone}>{status([slot]).label}</Badge><Button kind="quiet" disabled={busy || changed} onClick={() => openMaterial('identity')}>{slot.test_identity_id ? '核对账号' : '准备账号'}<ArrowRightOutlined aria-hidden="true"/></Button></footer></article>)}</div> :
                    selectedGroup.key === 'evidence' ? action.effect_evidence.map(item => <div className="jj-material-requirement" key={item.effect_id}><span>{text(effectName(item.effect_id))}</span><span data-tone={status([item]).tone}>{status([item]).label}</span></div>) :
                        selectedGroup.key === 'resource' ? action.resources.map((item, index) => <div className="jj-material-requirement" key={item.owner_slot_id}><span>测试资源 {index + 1}</span><Button kind="quiet" disabled={busy || changed || !item.owner_test_identity_id} onClick={() => navigate({ action_id: action.action_id, material_kind: 'resource', member_id: item.owner_test_identity_id })}>{item.owner_test_identity_id ? '核对资源绑定' : '先准备所有者账号'}</Button></div>) :
                            <div className="jj-material-requirement"><span>{selectedGroup.key === 'execution' ? text(action.display_name) : action.recovery.status === 'NOT_REQUIRED' ? '本项操作不改变业务数据' : '恢复本次操作改变的数据'}</span><span data-tone={status(selectedGroup.items).tone}>{status(selectedGroup.items).label}</span></div>}
          </div>
          {selectedGroup.key !== 'identity' && selectedGroup.key !== 'resource' && status(selectedGroup.items).label !== '不需要' && <div className="jj-material-detail-actions"><Button disabled={busy || changed} onClick={() => openMaterial(selectedGroup.key)}>{selectedGroup.key === 'evidence' ? '核对证明来源' : selectedGroup.key === 'recovery' ? '核对恢复方式' : '选择或录制操作'}<ArrowRightOutlined aria-hidden="true"/></Button></div>}
          {selectedGroup.items.some(item => item.reason_codes.length > 0) && <details><summary>材料核对信息</summary><ul>{[...new Set(selectedGroup.items.flatMap(item => item.reason_codes))].map(code => <li className="jj-small jj-muted" key={code}>{materialReasons([code])[0]}</li>)}</ul></details>}
          </div>
          <section className="jj-material-used-by"><h3>使用这些材料的规则</h3><ul>{action.permissions.map((rule, index) => { const subject = actorName(rule.subject_actor_id) ?? '操作人', owner = actorName(rule.resource_owner_actor_id) ?? '资源所有者'; return <li key={rule.intent_id ?? index}><span className="jj-material-rule-mark" data-allowed={rule.expectation === 'ALLOW'} aria-hidden="true">{rule.expectation === 'ALLOW' ? <CheckOutlined /> : '−'}</span><div><p>{text(subject)}{rule.expectation === 'ALLOW' ? '可以' : '不得'}{text(action.display_name)}</p><small>{rule.relation === 'OWNS' ? '自己的资源' : rule.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `其他${text(owner)}账号的资源` : `${text(owner)}的资源`}</small></div></li>; })}</ul></section>
          </div>
        </div>}
        <footer className="jj-preparation-footer"><div className="jj-preparation-progress">{preparation.preparation_complete ? <CheckCircleOutlined aria-hidden="true"/> : <ClockCircleOutlined aria-hidden="true"/>}<div><strong>{preparation.preparation_complete ? '所有业务操作的材料已齐备' : `${preparation.actions.filter(item => item.preparation_complete).length} / ${preparation.actions.length} 项业务操作已准备`}</strong><p>{preparation.preparation_complete ? '提交前还会核对本次检查范围。' : nextKind ? `下一步：${materialNames[nextKind]}` : '按当前材料状态继续核对。'}</p></div></div><Button kind="primary" onClick={primary} disabled={changed || Boolean(running) || pending}>{preparation.preparation_complete ? '预览检查' : nextKind ? '准备' + materialNames[nextKind].replace(/^测试|^业务/, '') : '查看当前材料'}<ArrowRightOutlined aria-hidden="true"/></Button></footer>
      </section>
    </>}
  </>;
}
function groupsFor(action: ActionPreparation): Array<{
    key: Kind;
    icon: React.ReactNode;
    items: PreparationItem[];
}> { return [{ key: 'identity', icon: <UserOutlined aria-hidden="true"/>, items: action.identity_requirements.slots }, { key: 'execution', icon: <VideoCameraOutlined aria-hidden="true"/>, items: [action.execution] }, { key: 'resource', icon: <DatabaseOutlined aria-hidden="true"/>, items: action.resources }, { key: 'evidence', icon: <FileDoneOutlined aria-hidden="true"/>, items: action.effect_evidence }, { key: 'recovery', icon: <UndoOutlined aria-hidden="true"/>, items: [action.recovery] }]; }
