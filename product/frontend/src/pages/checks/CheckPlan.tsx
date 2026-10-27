import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { useRef, useState } from 'react';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { currentChecksApi as api } from '../../entities/check/api/currentChecks';
import { workspaceApi } from '../../entities/workspace/api/workspace';
import { ApiError } from '../../shared/api/http';
import { Button } from "../../shared/ui/actions";
import { Badge, ErrorNote, Notice } from "../../shared/ui/feedback";
import { Heading } from "../../shared/ui/layout";
import { assertProject, type PageProps } from '../../shared/model/page';
import { text } from '../../shared/lib/format';
import { go } from '../../shared/lib/navigation';
import { useRead } from '../../shared/lib/useRead';
import { RuleCheckScope } from './RuleCheckScope';
export function Plan({ projectId, onError, route, refresh }: PageProps) {
    const ruleId = route.query.get('rule_id'), returnRule = ruleId ? '&rule_id=' + encodeURIComponent(ruleId) : '', changeId = route.query.get('change_id'), key = `jiejian.studio.check:${projectId}`;
    const state = useRead('plan:' + projectId + ':' + changeId, async () => { const workspace = await workspaceApi.current(projectId); assertProject(workspace.project.project_id, projectId); const change = changeId ?? null; const preview = await api.preview(projectId, change); assertProject(preview.project_id, projectId); return { preview, workspace, change }; });
    const [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(Boolean(sessionStorage.getItem(key))), lock = useRef(false);
    const submit = async () => {
        if (lock.current || !state.data?.preview.can_execute)
            return;
        lock.current = true;
        setBusy(true);
        try {
            const data = state.data, existing = sessionStorage.getItem(key), prior = existing ? JSON.parse(existing) as {
                fingerprint: string;
                operation: string;
                change: string | null;
            } : undefined;
            const active = await api.list(projectId, true);
            active.forEach(item => assertProject(item.run.project_id, projectId));
            if (active.length) {
                go('/reports?run_id=' + encodeURIComponent(active[0].run.run_id) + returnRule);
                return;
            }
            const preview = await api.preview(projectId, data.change);
            assertProject(preview.project_id, projectId);
            if (!preview.can_execute || preview.plan_fingerprint !== data.preview.plan_fingerprint || prior && prior.fingerprint !== preview.plan_fingerprint)
                throw new ApiError('STATE_PRECONDITION', '检查范围已变化，请重新核对；已有请求仍需查询原回执。');
            const pending = prior ?? { fingerprint: preview.plan_fingerprint, operation: crypto.randomUUID(), change: data.change ?? null };
            sessionStorage.setItem(key, JSON.stringify(pending));
            setUncertain(true);
            const result = await api.submit(projectId, pending.fingerprint, pending.operation, pending.change);
            assertProject(result.run.project_id, projectId);
            sessionStorage.removeItem(key);
            setUncertain(false);
            refresh();
            go('/reports?run_id=' + encodeURIComponent(result.run.run_id) + returnRule);
        }
        catch (error) {
            onError(error);
        }
        finally {
            lock.current = false;
            setBusy(false);
        }
    };
    if (state.loading)
        return <PageSkeleton view="/reports" title="检查范围"/>;
    if (!state.data || state.error)
        return <ErrorNote error={state.error} onRetry={state.reload}/>;
    const { preview, workspace } = state.data;
    return <><div><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => go(ruleId ? '/permissions?rule_id=' + encodeURIComponent(ruleId) : '/reports')}>{ruleId ? '返回权限规则' : '全部检查记录'}</Button></div><Heading eyebrow="提交前预览" title="这次检查哪些访问要求"/>{state.data.change && <RuleCheckScope projectId={projectId} changeId={state.data.change}/>}<section className="jj-panel jj-check-preview"><div className="jj-plan-reading"><div className="jj-panel-heading"><h2>检查范围</h2><span className="jj-small jj-muted">{preview.action_count} 项业务操作，{preview.case_count} 项检查</span></div><div className="jj-plan-actions">{preview.actions.map(action => <article className="jj-plan-action" key={action.action_id}><h3>{text(workspace.actions.find(item => item.action_id === action.action_id && item.action_revision === action.action_revision)?.display_name ?? '当前业务操作')}</h3><span>{action.cases.length} 项检查</span></article>)}</div>{preview.requirement_scope?.flatMap(scope => scope.requirements).length ? <details><summary>业务要求与本次覆盖范围</summary>{preview.requirement_scope.flatMap(scope => scope.requirements).map((item, index) => <div className="jj-scope-item" key={index}><Badge>{item.disposition === 'IN_SCOPE' ? '纳入检查' : item.disposition === 'PREPARATION' ? '准备条件' : '未覆盖'}</Badge><p>{text(item.requirement)}</p></div>)}</details> : null}{preview.boundary_review_gaps?.map((gap, index) => <Notice key={index}>{text(gap.message)}<Button onClick={() => go(gap.review_url.replace(/^#/, ''))}>核对要求</Button></Notice>)}</div><footer className="jj-plan-confirmation"><Badge tone={preview.can_execute ? 'accent' : 'caution'}>{preview.can_execute ? '可以提交' : '仍有准备缺口'}</Badge><h2 className="jj-plan-summary">{preview.can_execute ? '按这份范围执行检查' : '先补齐缺少的条件'}</h2><p className="jj-review-summary">{preview.can_execute ? '界鉴会执行真实操作并采集独立业务记录。检查进行期间可以离开此页。' : '已保存的材料会保留。处理缺口后，重新预览本次范围。'}</p>{preview.gaps.length > 0 && <ul className="jj-gap-list">{[...new Set(preview.gaps.map(item => gapName(item.reason)))].map(item => <li key={item}>{item}</li>)}</ul>}<div className="jj-review-buttons jj-confirmation-actions"><Button disabled={busy} onClick={state.reload}>重新核对范围</Button>{preview.can_execute ? <Button kind="primary" busy={busy} onClick={() => void submit()}>{uncertain ? '查询原请求并继续' : '开始检查'}</Button> : <Button kind="primary" onClick={() => go(preview.boundary_review_gaps?.length ? '/permissions' : ('/preparation?' + (changeId ? 'change_id=' + encodeURIComponent(changeId) : '') + returnRule))}>处理准备缺口</Button>}</div>{uncertain && <Notice>保留上一次请求编号，查询时不会重复创建检查。</Notice>}</footer></section></>;
}
export function gapName(reason: string) { return ({ IDENTITY_REQUIRED: '账号尚未就绪', PREPARATION_REQUIRED: '部分材料尚未就绪', PERMISSION_SEMANTICS_REQUIRED: '权限要求尚未确认', ALLOW_CONTROL_REQUIRED: '缺少正常操作对照', EXECUTION_REQUIRED: '缺少操作录制', RESOURCE_REQUIRED: '测试资源尚未确认', EFFECT_EVIDENCE_REQUIRED: '业务结果证明尚未齐备', RECOVERY_REQUIRED: '缺少恢复方式', CREATED_RESOURCE_PROOF_REQUIRED: '缺少本次新建资源的独立记录' } as Record<string, string>)[reason] ?? '有检查条件需要重新核对'; }
