import { useRef, useState } from 'react';
import { ArrowLeftOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { currentChecksApi as api, type CheckPreview } from '../../entities/check/api/currentChecks';
import { preparationApi } from '../../entities/preparation/api/preparation';
import { testIdentitiesApi } from '../../entities/preparation/api/testIdentities';
import { ApiError } from '../../shared/api/http';
import { Button } from '../../shared/ui/actions';
import { Badge, ErrorNote, Notice } from '../../shared/ui/feedback';
import { Heading } from '../../shared/ui/layout';
import { PageSkeleton } from '../../shared/ui/PageSkeleton';
import { assertProject, type PageProps } from '../../shared/model/page';
import { text } from '../../shared/lib/format';
import { go } from '../../shared/lib/navigation';
import { operationId, readPending, savePending } from '../../shared/lib/operations';
import { useRead } from '../../shared/lib/useRead';
import { RuleCheckScope } from './RuleCheckScope';

export function Plan({ projectId, onError, route, refresh }: PageProps) {
    const ruleId = route.query.get('rule_id'), changeId = route.query.get('change_id'), key = `jiejian.studio.check:${projectId}`;
    type Pending = { fingerprint: string; operation: string; change: string | null };
    const [pending, setPending] = useState(() => readPending<Pending>(key));
    const [busy, setBusy] = useState(false), [notFound, setNotFound] = useState(false), lock = useRef(false);
    const state = useRead('plan:' + projectId + ':' + changeId, async () => {
        const [preview, materials, identities] = await Promise.all([api.preview(projectId, changeId), preparationApi.get(projectId), testIdentitiesApi.list(projectId)]);
        [preview.project_id, materials.project_id].forEach(id => assertProject(id, projectId));
        identities.forEach(item => assertProject(item.project_id, projectId));
        return { preview, materials, identities };
    });
    const open = (runId: string) => { savePending(key, undefined); setPending(undefined); refresh(); go('/reports?' + new URLSearchParams({ run_id: runId, ...(ruleId ? { rule_id: ruleId } : {}) })); };
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
        if (!state.data?.preview.can_execute) return;
        const preview = await api.preview(projectId, changeId);
        if (!preview.can_execute || preview.plan_fingerprint !== state.data.preview.plan_fingerprint || pending && pending.fingerprint !== preview.plan_fingerprint) {
            state.reload(); throw new ApiError('STATE_PRECONDITION', '检查范围已变化，请重新核对。');
        }
        const active = await api.list(projectId, true);
        if (active.length) { open(active[0].run.run_id); return; }
        const saved = pending ?? { fingerprint: preview.plan_fingerprint, operation: operationId(), change: changeId };
        savePending(key, saved); setPending(saved);
        const result = await api.submit(projectId, saved.fingerprint, saved.operation, saved.change);
        assertProject(result.run.project_id, projectId); open(result.run.run_id);
    };
    if (state.loading) return <PageSkeleton view="/reports" title="检查范围"/>;
    if (!state.data || state.error) return <ErrorNote error={state.error} onRetry={state.reload}/>;
    const { preview, materials, identities } = state.data;
    const returnTo = '/reports?' + new URLSearchParams({ view: 'plan', ...(changeId ? { change_id: changeId } : {}), ...(ruleId ? { rule_id: ruleId } : {}) });
    return <>
        <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => go(ruleId ? '/permissions?rule_id=' + encodeURIComponent(ruleId) : '/reports')}>{ruleId ? '返回权限规则' : '全部检查记录'}</Button></div>
        <Heading eyebrow="提交前预览" title="核对本次检查范围"/>
        {changeId && <RuleCheckScope projectId={projectId} changeId={changeId}/>}
        {pending && <Notice>上次提交的结果尚未确认。<Button busy={busy} onClick={() => void act(recover)}>查询原检查</Button>{notFound && <><span>尚未查到检查记录。</span>{pending.fingerprint === preview.plan_fingerprint ? <Button busy={busy} onClick={() => void act(submit)}>重试原提交</Button> : <span>原范围已变化，请保留请求并稍后查询。</span>}</>}</Notice>}
        <section className="jj-panel jj-check-preview jj-plan-workspace">
            <header className="jj-plan-overview"><div><h2>{preview.action_count} 项业务操作</h2><p className="jj-small jj-muted">{preview.case_count ? `${preview.case_count} 项检查` : '按已批准权限核对所需材料'}</p></div><Badge tone={preview.can_execute ? 'positive' : 'caution'}>{preview.can_execute ? '准备齐全' : '需要补齐材料'}</Badge></header>
            <div className="jj-plan-reading">{materials.actions.map(action => {
                const plan = preview.actions.find(item => item.action_id === action.action_id), gaps = preview.gaps.filter(item => item.action_id === action.action_id).filter((item, index, all) => all.findIndex(other => gapKind(other.reason) === gapKind(item.reason)) === index);
                return <article className="jj-plan-task" key={action.action_id}><header><h3>{text(action.display_name)}</h3><Badge tone={gaps.length ? 'caution' : 'neutral'}>{gaps.length ? `${gaps.length} 类待准备` : `${plan?.cases.length ?? 0} 项检查`}</Badge></header>
                    <div className="jj-plan-task-details"><div><span>测试账号</span><p>{action.identity_requirements.slots.map(slot => text(slot.actor_display_name) + (slot.requirement.ordinal > 1 ? ` ${slot.requirement.ordinal}` : '')).join('、') || '尚未确定'}</p></div><div><span>核对结果</span><p>{action.effect_evidence.map(effect => text(effect.business_label)).join('、') || '尚未确定'}</p></div></div>
                    {!!plan?.cases.length && <details className="jj-plan-objects"><summary>检查账号与资源</summary>{plan.cases.map(item => <div key={item.case_id}><div className="jj-item-heading"><Badge tone={item.permission.expectation === 'DENY' ? 'caution' : 'neutral'}>{item.permission.expectation === 'DENY' ? '禁止' : '允许'}</Badge><strong>{text(identities.find(identity => identity.identity_id === item.subject_test_identity_id)?.label ?? '所选测试账号')}</strong></div><dl><div><dt>资源所有者</dt><dd>{text(identities.find(identity => identity.identity_id === item.resource_owner_test_identity_id)?.label ?? '所选资源账号')}</dd></div><div><dt>测试资源</dt><dd>{item.resource_id}</dd></div></dl></div>)}</details>}
                    {gaps.length > 0 && <ul className="jj-plan-gaps">{gaps.map((gap, index) => <li key={index}><span>{gapName(gap.reason)}</span><Button kind="quiet" onClick={() => go(gapDestination(gap, returnTo, changeId))}>处理<ArrowRightOutlined aria-hidden="true"/></Button></li>)}</ul>}
                </article>;
            })}{!materials.actions.length && <p>请先确认本应用的权限规则。</p>}</div>
            {preview.boundary_review_gaps?.map((gap, index) => <Notice key={index}>{text(gap.message)}<Button onClick={() => go(gap.review_url.replace(/^#/, ''))}>核对要求</Button></Notice>)}
            {!!preview.requirement_scope?.length && <details className="jj-plan-scope"><summary>业务要求与覆盖范围</summary>{preview.requirement_scope.flatMap(scope => scope.requirements).map((item, index) => <div className="jj-scope-item" key={index}><Badge>{item.disposition === 'IN_SCOPE' ? '纳入检查' : item.disposition === 'PREPARATION' ? '准备条件' : '未覆盖'}</Badge><p>{text(item.requirement)}</p></div>)}</details>}
            <footer className="jj-plan-confirmation"><div><strong>{preview.can_execute ? '按已确认权限和当前材料执行' : '材料补齐后，再核对本次范围'}</strong><p className="jj-small jj-muted">{preview.can_execute ? '将执行真实业务操作，检查期间可以离开此页。' : '已有材料保留，缺口按各项业务操作列出。'}</p></div><div className="jj-inline-actions"><Button disabled={busy} onClick={state.reload}>重新核对</Button><Button kind="primary" busy={busy} disabled={!preview.can_execute || Boolean(pending)} onClick={() => void act(submit)}>开始检查<ArrowRightOutlined aria-hidden="true"/></Button></div></footer>
        </section>
    </>;
}

export function gapName(reason: string) {
    return ({ TEST_IDENTITY_REQUIRED: '测试账号尚未就绪', IDENTITY_REQUIRED: '测试账号尚未就绪', ACTION_RESOURCE_REQUIRED: '测试资源尚未确认', RESOURCE_REQUIRED: '测试资源尚未确认', ACTION_EXECUTION_REQUIRED: '缺少操作录制', ACTION_EXECUTION_MISSING: '缺少可用操作录制', EXECUTION_REQUIRED: '缺少操作录制', EFFECT_EVIDENCE_REQUIRED: '业务结果缺少证明来源', ACTION_RECOVERY_REQUIRED: '缺少恢复方式', RECOVERY_REQUIRED: '缺少恢复方式', ALLOW_CONTROL_REQUIRED: '需要选择正常操作对照', PERMISSION_SEMANTICS_REQUIRED: '权限要求尚未确认', CREATED_RESOURCE_PROOF_REQUIRED: '缺少新建资源的独立记录', PREPARATION_REQUIRED: '材料需要重新核对' } as Record<string, string>)[reason] ?? '本项检查条件需要重新核对';
}
export function gapDestination(gap: CheckPreview['gaps'][number], returnTo: string, changeId?: string | null) {
    const focus = gapKind(gap.reason);
    return '/preparation?' + new URLSearchParams({ action_id: gap.action_id, return_to: returnTo, ...(['identity','resource','execution','recovery','evidence'].includes(focus) ? { focus } : {}), ...(gap.intent_id ? { rule_id: gap.intent_id } : {}), ...(gap.effect_id ? { effect_id: gap.effect_id } : {}), ...(changeId ? { change_id: changeId } : {}) });
}

function gapKind(reason: string) {
    return /IDENTITY/.test(reason) ? 'identity' : /RESOURCE/.test(reason) && !/PROOF/.test(reason) ? 'resource' : /EXECUTION/.test(reason) ? 'execution' : /RECOVERY/.test(reason) ? 'recovery' : /EVIDENCE|PROOF/.test(reason) ? 'evidence' : reason;
}
