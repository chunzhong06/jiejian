import {conditionLabels} from '../../entities/permission/ui/RuleConditions';
import { useRef, useState } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import { currentChecksApi as api, type CheckPreview } from '../../entities/check/api/currentChecks';
import { preparationApi, type PermissionReference } from '../../entities/preparation/api/preparation';
import { testIdentitiesApi } from '../../entities/preparation/api/testIdentities';
import { ApiError } from '../../shared/api/http';
import { Button } from '../../shared/ui/actions';
import { Badge, ErrorNote, Notice } from '../../shared/ui/feedback';
import { Heading } from '../../shared/ui/layout';
import { PageSkeleton } from '../../shared/ui/PageSkeleton';
import { assertProject, type PageProps } from '../../shared/model/page';
import { text } from '../../shared/lib/format';
import { go, returnDestination } from '../../shared/lib/navigation';
import { operationId, readPending, savePending } from '../../shared/lib/operations';
import { useRead } from '../../shared/lib/useRead';
import { RuleCheckScope } from './RuleCheckScope';
import { CheckScopePicker } from './CheckScopePicker';

export function Plan({ projectId, onError, route, refresh }: PageProps) {
    const ruleId = route.query.get('rule_id'), changeId = route.query.get('change_id'), key = `jiejian.studio.check:${projectId}`;
    const origin = returnDestination(route.query.get('return_to'));
    type Pending = { fingerprint: string; operation: string; change: string | null; selected?: PermissionReference[] | null };
    const scopeId = useRef(route.query.get('scope_id') ?? operationId());
    const [selected, setSelected] = useState<PermissionReference[] | null>(() => changeId ? null : readPending<{refs: PermissionReference[]}>(`jiejian.studio.scope:${projectId}:${scopeId.current}`)?.refs ?? readPending<Pending>(key)?.selected ?? null);
    const select = (refs: PermissionReference[] | null) => {
        savePending(`jiejian.studio.scope:${projectId}:${scopeId.current}`, refs === null ? undefined : {refs});
        const query = new URLSearchParams(location.hash.split('?')[1]);
        if (refs === null) query.delete('scope_id'); else query.set('scope_id', scopeId.current);
        history.replaceState(null, '', '#/reports?' + query);
        setSelected(refs);
    };
    const [pending, setPending] = useState(() => readPending<Pending>(key));
    const [busy, setBusy] = useState(false), [notFound, setNotFound] = useState(false), lock = useRef(false);
    const state = useRead('plan:' + projectId + ':' + changeId, async () => {
        const [preview, materials, identities] = await Promise.all([api.preview(projectId, changeId), preparationApi.get(projectId), testIdentitiesApi.list(projectId)]);
        [preview.project_id, materials.project_id].forEach(id => assertProject(id, projectId));
        identities.forEach(item => assertProject(item.project_id, projectId));
        return { preview, materials, identities };
    });
    const chosen = useRead(selected?.length ? 'selected-plan:' + projectId + ':' + JSON.stringify(selected) : null, () => api.preview(projectId, null, selected));
    const activePreview = selected === null ? state.data?.preview : chosen.data;
    const open = (runId: string) => { savePending(key, undefined); setPending(undefined); refresh(); go('/reports?' + new URLSearchParams({ run_id: runId, ...(ruleId ? { rule_id: ruleId } : {}), ...(origin ? {return_to:origin} : {}) })); };
    const act = async (callback: () => Promise<void>) => {
        if (lock.current) return;
        lock.current = true; setBusy(true);
        try { await callback(); } catch (error) { onError(error); }
        finally { lock.current = false; setBusy(false); }
    };
    const recover = async () => {
        const saved = readPending<Pending>(key);
        if (!saved) return;
        const receipt = await api.receipt(projectId, saved.operation);
        if (receipt) { assertProject(receipt.run.project_id, projectId); open(receipt.run.run_id); }
        else setNotFound(true);
    };
    const submit = async () => {
        if (!activePreview?.can_execute) return;
        const preview = await api.preview(projectId, changeId, selected);
        if (!preview.can_execute || preview.plan_fingerprint !== activePreview.plan_fingerprint || pending && pending.fingerprint !== preview.plan_fingerprint) {
            state.reload(); chosen.reload(); throw new ApiError('STATE_PRECONDITION', '检查范围已变化，请重新核对。');
        }
        const active = await api.list(projectId, true);
        if (active.length) { open(active[0].run.run_id); return; }
        const saved = pending ?? { fingerprint: preview.plan_fingerprint, operation: operationId(), change: changeId, selected };
        savePending(key, saved); setPending(saved);
        const result = await api.submit(projectId, saved.fingerprint, saved.operation, saved.change, saved.selected);
        assertProject(result.run.project_id, projectId); open(result.run.run_id);
    };
    if (state.loading) return <PageSkeleton view="/reports" title="检查范围"/>;
    if (!state.data || state.error) return <ErrorNote error={state.error} onRetry={state.reload}/>;
    const { materials, identities } = state.data;
    const preview = activePreview;
    // 只合并重复说明；每份要求的定位和服务端预览的执行门槛保持独立。
    const requirementGaps = new Map<string, NonNullable<CheckPreview['boundary_review_gaps']>>();
    for (const gap of preview?.boundary_review_gaps ?? []) {
        const key = gap.status + ':' + gap.message;
        requirementGaps.set(key, [...(requirementGaps.get(key) ?? []), gap]);
    }
    const returnTo = '/reports?' + new URLSearchParams({ view: 'plan', ...(selected !== null ? {scope_id: scopeId.current} : {}), ...(changeId ? { change_id: changeId } : {}), ...(ruleId ? { rule_id: ruleId } : {}), ...(origin ? {return_to:origin} : {}) });
    return <>
        <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => go(origin ?? (ruleId ? '/permissions?rule_id=' + encodeURIComponent(ruleId) : '/reports'))}>{origin ? '返回修复任务' : ruleId ? '返回权限规则' : '全部检查记录'}</Button></div>
        <Heading eyebrow="提交前预览" title="核对本次检查范围"/>
        {changeId && <RuleCheckScope projectId={projectId} changeId={changeId}/>}
        {pending && <Notice>上次提交的结果尚未确认。<Button busy={busy} onClick={() => void act(recover)}>查询原检查</Button>{notFound && <><span>尚未查到检查记录。</span>{pending.fingerprint === preview?.plan_fingerprint ? <Button busy={busy} onClick={() => void act(submit)}>重试原提交</Button> : <span>原范围已变化，请保留请求并稍后查询。</span>}</>}</Notice>}
        <div className="jj-plan-layout" data-revalidation={Boolean(changeId)}>
        {!changeId && <CheckScopePicker materials={materials} selected={selected} disabled={Boolean(pending) || busy} onChange={select}/>}
        <div className="jj-plan-output">
        {chosen.error && <><ErrorNote error={chosen.error} onRetry={() => {state.reload(); chosen.reload();}}/><Button onClick={() => {state.reload(); select([]);}}>重新选择规则</Button></>}
        {preview ? <section className="jj-panel jj-check-preview jj-plan-workspace" aria-busy={selected !== null && chosen.loading}>
            <header className="jj-plan-overview"><div><h2>{preview.case_count ? `将执行 ${preview.case_count} 项检查` : '准备检查材料'}</h2><p className="jj-small jj-muted">{preview.action_count} 项业务操作{preview.selection && `，含 ${preview.selection.added_controls.length} 项正常对照，另有 ${preview.selection.omitted.length} 条规则未检查`}</p></div><Badge tone={preview.can_execute ? 'positive' : 'caution'}>{preview.can_execute ? '可以开始' : '尚缺材料'}</Badge></header>
            <div className="jj-plan-reading">{materials.actions.filter(action => !selected || preview.actions.some(item => item.action_id === action.action_id)).map(action => {
                const plan = preview.actions.find(item => item.action_id === action.action_id), gaps = groupGaps(preview.gaps.filter(item => item.action_id === action.action_id));
                return <article className="jj-plan-task" key={action.action_id}>
                    <div className="jj-plan-task-summary"><header><h3>{text(action.display_name)}</h3>{gaps.length > 0 && <Badge tone="caution">{gaps.length} 类材料待准备</Badge>}</header>
                        <dl className="jj-plan-task-details">{!plan?.cases.length && <div><dt>测试账号</dt><dd>{action.identity_requirements.slots.map(slot => text(slot.actor_display_name) + (slot.requirement.ordinal > 1 ? ` ${slot.requirement.ordinal}` : '')).join('、') || '尚未确定'}</dd></div>}<div><dt>判断结果</dt><dd>{action.effect_evidence.map(effect => text(effect.business_label)).join('、') || '尚未确定'}</dd></div></dl>
                    </div>
                    <div className="jj-plan-task-preparation">
                        {gaps.length > 0 && <ul className="jj-plan-gaps">{gaps.map(({ kind, gap, messages }) => <li key={kind}><div><strong>{messages[0]}</strong>{messages.length > 1 && <p>{messages.slice(1).join('；')}</p>}</div><Button onClick={() => go(gapDestination(gap, returnTo, changeId))}>{gapAction(kind)}<ArrowRightOutlined aria-hidden="true"/></Button></li>)}</ul>}
                        {!!plan?.cases.length && <section className="jj-plan-objects" aria-label="实际执行场景"><div className="jj-scroll-table"><table className="jj-plan-case-table"><thead><tr><th scope="col">操作账号</th><th scope="col" className="jj-table-state">预期结果</th><th scope="col">数据所有者</th><th scope="col">测试数据</th></tr></thead><tbody>{plan.cases.map(item=><tr key={item.case_id}><td>{text(item.subject_test_identity_id === null ? '未登录访客' : identities.find(identity=>identity.identity_id===item.subject_test_identity_id)?.label??'所选测试账号')}</td><td className="jj-table-state"><span className="jj-plan-expectation" data-tone={item.permission.expectation==='DENY'?'caution':'positive'}>{item.permission.expectation==='DENY'?'不应完成':'应当完成'}</span></td><td>{text(identities.find(identity=>identity.identity_id===item.resource_owner_test_identity_id)?.label??'所选资源账号')}</td><td>{item.resource_id}{conditionLabels(item.permission.conditions).length > 0 && <small>{conditionLabels(item.permission.conditions).join("，")}</small>}</td></tr>)}</tbody></table></div></section>}
                    </div>
                </article>;
            })}{!materials.actions.length && <p>请先确认本应用的权限规则。</p>}</div>
            {[...requirementGaps].map(([key, items]) => <section className="jj-plan-boundary-group" key={key}><p>{text(items[0].message)}</p>{items.length === 1 ? <Button onClick={() => go(items[0].review_url.replace(/^#/, ''))}>核对要求<ArrowRightOutlined aria-hidden="true"/></Button> : <details><summary>查看 {items.length} 份相关要求</summary>{items.map(gap => <div key={gap.issue_id}><p>{text(preview.requirement_scope?.find(scope => scope.candidate_id === gap.candidate_id && scope.revision === gap.revision)?.requirements[0]?.requirement ?? '已确认的权限要求')}</p><Button onClick={() => go(gap.review_url.replace(/^#/, ''))}>核对要求<ArrowRightOutlined aria-hidden="true"/></Button></div>)}</details>}</section>)}
            {!!preview.requirement_scope?.length && <details className="jj-plan-scope"><summary>业务要求与覆盖范围</summary>{preview.requirement_scope.flatMap(scope => scope.requirements.map(item => ({...item, scope}))).map(({scope, ...item}, index) => <div className="jj-scope-item" key={index}><Badge>{item.disposition === 'IN_SCOPE' ? (preview.selection?.uncovered_requirements.includes(`${scope.candidate_id}@${scope.revision}/${item.requirement_id}`) ? '本次未覆盖' : '纳入检查') : item.disposition === 'PREPARATION' ? '准备条件' : '未覆盖'}</Badge><p>{text(item.requirement)}</p></div>)}</details>}
            {!!preview.omitted_review_gaps?.length && <details className="jj-plan-scope"><summary>{preview.omitted_review_gaps.length} 项未决要求未纳入本次检查</summary>{preview.omitted_review_gaps.map(item => <p key={item.issue_id}>{text(item.message)}</p>)}</details>}
            <footer className="jj-plan-confirmation"><div><strong>{preview.can_execute ? '执行前会核对当前条件' : '请先补齐上方材料'}</strong><p className="jj-small jj-muted">{preview.can_execute ? '将执行真实操作，检查期间可离开此页。' : '已有材料保留，无需重新准备。'}</p></div><div className="jj-inline-actions"><Button disabled={busy} onClick={() => {state.reload(); chosen.reload();}}>重新核对</Button><Button kind="primary" busy={busy} disabled={!preview.can_execute || Boolean(pending)} onClick={() => void act(submit)}>开始检查<ArrowRightOutlined aria-hidden="true"/></Button></div></footer>
        </section> : !chosen.error && <section className="jj-panel jj-plan-selection-empty" role="status">{selected?.length ? '正在核对所选规则与必要材料…' : '选中左侧规则，即可查看将执行的场景。'}</section>}
        </div></div>
    </>;
}

export function gapName(reason: string) {
    return ({ TEST_IDENTITY_LOGIN_REQUIRED: '测试账号需要重新登录', RESOURCE_OWNER_SOURCE_STALE: '测试数据的归属需要重新确认', RESOURCE_INJECTION_STALE: '操作中的测试数据位置需要重新确认', CONDITION_SOURCE_REQUIRED:'尚未设置租户或数据状态的判断依据', RULE_CASE_DATA_STALE:'规则的测试数据需要重新核对', TEST_IDENTITY_REQUIRED: '测试账号尚未就绪', IDENTITY_REQUIRED: '测试账号尚未就绪', ACTION_RESOURCE_REQUIRED: '测试资源尚未确认', RESOURCE_REQUIRED: '测试资源尚未确认', ACTION_EXECUTION_REQUIRED: '缺少操作录制', ACTION_EXECUTION_MISSING: '缺少可用操作录制', EXECUTION_REQUIRED: '缺少操作录制', EFFECT_EVIDENCE_REQUIRED: '尚未设置如何判断业务结果', EFFECT_VERDICT_PROOF_REQUIRED: '业务结果的判断依据还未准备好', REGISTERED_OBSERVER_UNAVAILABLE: '证明来源当前不可用', ACTION_RECOVERY_REQUIRED: '缺少恢复方式', RECOVERY_REQUIRED: '缺少恢复方式', ALLOW_CONTROL_REQUIRED: '需要选择一项应当成功的正常操作', PERMISSION_SEMANTICS_REQUIRED: '权限要求尚未确认', CREATED_RESOURCE_PROOF_REQUIRED: '缺少新建资源的独立记录', PREPARATION_REQUIRED: '材料需要重新核对' } as Record<string, string>)[reason] ?? '本项检查条件需要重新核对';
}
export function gapDestination(gap: CheckPreview['gaps'][number], returnTo: string, changeId?: string | null) {
    const focus = gapKind(gap.reason);
    return '/preparation?' + new URLSearchParams({ action_id: gap.action_id, return_to: returnTo, ...(['identity','resource','execution','recovery','evidence'].includes(focus) ? { focus } : {}), ...(gap.intent_id ? { rule_id: gap.intent_id } : {}), ...(gap.effect_id ? { effect_id: gap.effect_id } : {}), ...(changeId ? { change_id: changeId } : {}) });
}

function gapKind(reason: string) {
    if(reason==='CONDITION_SOURCE_REQUIRED')return 'evidence';
    if(reason==='RULE_CASE_DATA_STALE')return 'resource';
    return /IDENTITY/.test(reason) ? 'identity' : /RESOURCE/.test(reason) && !/PROOF/.test(reason) ? 'resource' : /EXECUTION/.test(reason) ? 'execution' : /RECOVERY/.test(reason) ? 'recovery' : /EVIDENCE|PROOF|OBSERVER/.test(reason) ? 'evidence' : reason;
}

function groupGaps(gaps: CheckPreview['gaps']) {
    // 只合并同一操作的补材料入口，保留不同原因；执行门禁仍使用服务端的完整缺口。
    const groups = new Map<string, CheckPreview['gaps']>();
    for (const gap of gaps) { const kind = gapKind(gap.reason); groups.set(kind, [...(groups.get(kind) ?? []), gap]); }
    return Array.from(groups, ([kind, items]) => ({ kind, gap: items.find(item => item.effect_id) ?? items[0], messages: [...new Set(items.map(item => gapName(item.reason)))] }));
}

function gapAction(kind: string) {
    return ({ identity: '准备测试账号', resource: '确认测试资源', execution: '补充操作录制', recovery: '准备恢复方式', evidence: '准备结果判断依据' } as Record<string, string>)[kind] ?? '核对检查条件';
}
