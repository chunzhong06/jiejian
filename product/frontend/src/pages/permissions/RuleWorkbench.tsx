import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { useRef, useState, type ReactNode } from 'react';
import { ArrowLeftOutlined, ArrowRightOutlined, CheckCircleOutlined, CheckOutlined, ExclamationCircleOutlined, MinusOutlined, SafetyOutlined } from '@ant-design/icons';
import type { BusinessBoundaryViewDto } from '../../entities/permission/api/businessBoundaries';
import { ruleWorkspaceApi, type RuleItem, type RuleState } from '../../entities/permission/api/ruleWorkspace';
import { sourceChangesApi, type RuleChangeTarget } from '../../entities/source-change/api/sourceChanges';
import { developmentApi } from '../../entities/source-change/api/development';
import { repairReference, type ProjectRepair } from '../../entities/check/api/repairs';
import { assertProject, type PageProps } from '../../shared/model/page';
import { date, text } from '../../shared/lib/format';
import { go } from '../../shared/lib/navigation';
import { useRead } from '../../shared/lib/useRead';
import { ActionLink, Button } from "../../shared/ui/actions";
import { Badge, Empty, ErrorNote, Notice } from "../../shared/ui/feedback";
import { Field, Heading } from "../../shared/ui/layout";
import { Tabs } from "../../shared/ui/Tabs";
import { repairGap } from '../../entities/check/model/checks';
const stateLabels: Record<RuleState, string> = { UNCONFIRMED: '运行版本待确认', UNTESTED: '尚未检查', STALE: '版本变化，待重查', SAFE: '符合规则', VULNERABLE: '发现违规', INCONCLUSIVE: '证据不足', REPAIR_PENDING: '原问题待复验' };
const issueLabels: Record<string, string> = { REPAIR_REQUIRED: '待修复', CHANGE_SUBMITTED: '修复已提交', READY_TO_VERIFY: '待复验', VERIFIED: '已验证修复', NOT_VERIFIED: '问题仍存在', INCONCLUSIVE: '复验未能确认', STALE: '规则已变化' };
const tone = (state: RuleState) => state === 'SAFE' ? 'positive' : state === 'VULNERABLE' ? 'negative' : state === 'INCONCLUSIVE' || state === 'REPAIR_PENDING' ? 'caution' : 'neutral';
const issueTone = (state: string) => state === 'VERIFIED' ? 'positive' : state === 'NOT_VERIFIED' || state === 'REPAIR_REQUIRED' ? 'negative' : state === 'STALE' ? 'neutral' : 'caution';
const rulePath = (rule: RuleItem, suffix = '') => '/permissions?rule_id=' + encodeURIComponent(rule.permission.intent_id) + suffix;
type Issue = ProjectRepair['tasks'][number];
export function RuleWorkbench({ projectId, route, refresh, onError, onManage, reviewActions, boundary }: Omit<PageProps, 'name'> & {
    onManage: () => void;
    reviewActions?: ReactNode;
    boundary: BusinessBoundaryViewDto;
}) {
    const state = useRead('rule-workspace:' + projectId, async () => {
        const value = await ruleWorkspaceApi.read(projectId);
        assertProject(value.project_id, projectId);
        if (value.schema_version !== '1')
            throw new Error('权限工作区格式不受支持。');
        return value;
    });
    const [query, setQuery] = useState(''), [filter, setFilter] = useState('ALL');
    if (state.loading)
        return <PageSkeleton view="/permissions"/>;
    if (state.error || !state.data)
        return <ErrorNote error={state.error} onRetry={state.reload}/>;
    if (state.data.policy_epoch !== boundary.policy_epoch)
        return <Notice>权限规则已变化，请重新读取。<Button onClick={() => { state.reload(); refresh(); }}>重新读取规则</Button></Notice>;
    const { rules } = state.data, reference = route.query.get('repair_reference');
    const id = route.query.get('rule_id') ?? rules.find(rule => rule.issues.some(issue => issue.contract.repair_fingerprint === reference))?.permission.intent_id;
    const selected = rules.find(rule => rule.permission.intent_id === id);
    if (id && !selected)
        return <Empty title="这条规则已不在当前权限范围中" action={<Button onClick={() => go('/permissions')}>返回权限规则</Button>}>历史检查仍可从检查记录查阅。</Empty>;
    if (selected)
        return <RuleDetail key={projectId + selected.permission.intent_id} rule={selected} rules={rules} projectId={projectId} route={route} onError={onError} onReload={() => { state.reload(); refresh(); }}/>;
    const roles = boundary.actors.filter(role => role.effective_state === 'ACTIVE');
    const actions = boundary.actions.filter(action => action.effective_state === 'ACTIVE');
    const matrix = actions.map(action => ({ action, cells: roles.map(role => ({ role, rules: boundary.permission_intents.filter(intent => intent.effective_state === 'ACTIVE' && intent.business_action_id === action.action_id && intent.action_revision === action.revision && intent.subject_actor_id === role.actor_id && intent.subject_actor_revision === role.revision && roles.some(owner => owner.actor_id === intent.resource_owner_actor_id && owner.revision === intent.resource_owner_actor_revision)).map(intent => rules.find(rule => rule.permission.intent_id === intent.intent_id && rule.permission.revision === intent.revision)).filter((rule): rule is RuleItem => Boolean(rule)) })) })).filter(row => row.cells.some(cell => cell.rules.some(rule => (filter === 'ALL' || rule.expectation === filter) && (!query.trim() || [rule.title, rule.resource_scope].some(value => value.includes(query.trim()))))));
    const open = rules.flatMap(rule => rule.issues).filter(issue => !['VERIFIED', 'STALE'].includes(issue.status)).length;
    return <>
    <Heading title="权限规则" actions={<><Button onClick={onManage}>编辑权限要求</Button><Button kind="primary" onClick={() => go('/reports?view=plan')}>检查权限<ArrowRightOutlined aria-hidden="true"/></Button></>}/>
    {reviewActions}
    <section className="jj-rule-workspace jj-rule-matrix">
      <header className="jj-rule-summary"><SafetyOutlined aria-hidden="true"/><div><strong>{rules.length} 条权限规则</strong><span>权限版本 {state.data.policy_epoch}，按已登记源码检查</span></div><div className="jj-rule-totals"><span><strong>{open}</strong> 个待处理问题</span><span><strong>{rules.filter(rule => rule.state === 'SAFE').length}</strong> 条检查通过</span></div></header>
      <div className="jj-rule-toolbar"><input aria-label="查找规则" value={query} onChange={event => setQuery(event.target.value)} placeholder="查找角色、操作或资源"/><div className="jj-toggle-group" aria-label="筛选规则">{[['ALL', '全部'], ['ALLOW', '允许'], ['DENY', '禁止']].map(([value, label]) => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div></div>
      <div className="jj-scroll-table jj-permission-table"><table style={{ minWidth: Math.max(640, (roles.length + 1) * 200) }}><thead><tr><th>业务操作</th>{roles.map(role => <th key={role.actor_id} scope="col">{text(role.display_name)}</th>)}</tr></thead><tbody>{matrix.map(({ action, cells }) => <tr key={action.action_id}><th scope="row"><strong>{text(action.display_name)}</strong><small>{text(action.primary_resource_concept)}</small></th>{cells.map(({ role, rules: cellRules }) => { const matching = cellRules.filter(rule => (filter === 'ALL' || rule.expectation === filter) && (!query.trim() || [rule.title, rule.resource_scope].some(value => value.includes(query.trim())))); return <td key={role.actor_id}>{matching.length ? matching.map(rule => <button className="jj-permission-cell" key={rule.permission.intent_id} aria-label={text(rule.title) + '，' + text(rule.resource_scope)} onClick={() => go(rulePath(rule))}><span data-allowed={rule.expectation === 'ALLOW'}>{rule.expectation === 'ALLOW' ? <CheckOutlined aria-hidden="true"/> : <MinusOutlined aria-hidden="true"/>}{rule.expectation === 'ALLOW' ? '允许' : '禁止'}</span><small>{text(rule.resource_scope)}</small>{rule.state !== 'UNTESTED' && <Badge tone={tone(rule.state)}>{stateLabels[rule.state]}</Badge>}</button>) : <span className="jj-small jj-muted">{cellRules.length ? '—' : '未设定'}</span>}</td>; })}</tr>)}</tbody></table></div>
      {!matrix.length && <Empty title="没有符合条件的规则"/>}
    </section>
    <div className="jj-rule-archive"><Button kind="quiet" onClick={() => go('/reports')}>全部检查记录<ArrowRightOutlined aria-hidden="true"/></Button><Button kind="quiet" onClick={() => go('/changes')}>代码变更档案<ArrowRightOutlined aria-hidden="true"/></Button></div>
  </>;
}
function RuleDetail({ rule, rules, projectId, route, onError, onReload }: {
    rule: RuleItem;
    rules: RuleItem[];
    projectId: string;
    route: PageProps['route'];
    onError: PageProps['onError'];
    onReload: () => void;
}) {
    const [repair, setRepair] = useState<Issue | null | undefined>(undefined);
    const section = route.query.get('section') ?? 'results', reference = route.query.get('repair_reference');
    const issues = reference ? rule.issues.filter(issue => issue.contract.repair_fingerprint === reference) : rule.issues;
    const latest = rule.latest;
    return <>
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => go('/permissions')}>权限规则</Button></div>
    <section className="jj-rule-detail-header"><div><div className="jj-rule-detail-label"><Badge tone={rule.expectation === 'ALLOW' ? 'positive' : 'negative'}>{rule.expectation === 'ALLOW' ? '允许' : '禁止'}</Badge><span>规则版本 {rule.permission.revision}</span></div><h1>{text(rule.title)}</h1><p>{text(rule.resource_scope)}</p></div><div className="jj-rule-detail-status"><Badge tone={tone(rule.state)}>{stateLabels[rule.state]}</Badge><Button onClick={() => go('/reports?view=plan&rule_id=' + encodeURIComponent(rule.permission.intent_id))}>检查相关规则<ArrowRightOutlined aria-hidden="true"/></Button></div></section>
    <Tabs label="规则详情" value={section} onValueChange={value => go(rulePath(rule, '&section=' + value))} items={[{ value: 'results', label: '检查结果' }, { value: 'changes', label: '修复与修改' }, { value: 'history', label: '检查历史' }]} className="jj-action-tabs"/>
    {repair !== undefined && <RepairSubmission key={repair?.task_reference ?? 'rule'} rule={rule} rules={rules} issue={repair} projectId={projectId} onClose={() => setRepair(undefined)} onError={onError} onSaved={changeId => { setRepair(undefined); onReload(); go(rulePath(rule, '&section=changes&change_id=' + encodeURIComponent(changeId))); }}/>}
    {section === 'results' && <div className="jj-rule-result-layout"><section className="jj-rule-result-main"><div className="jj-section-header"><h2>{issues.length ? '发现的问题' : '检查情况'}</h2><span className="jj-small jj-muted">{issues.length ? `${issues.length} 项` : ''}</span></div>
      {issues.map(issue => <article className="jj-rule-issue" key={issue.task_reference}>
        <header><span className="jj-rule-issue-icon" data-state={issue.status}>{issue.status === 'VERIFIED' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}</span><div><Badge tone={issueTone(issue.status)}>{issueLabels[issue.status]}</Badge><h3>{issue.status === 'VERIFIED' ? '已确认原违规消除，正常功能保留' : '检查中出现了不应发生的业务结果'}</h3><p>在原来的账号、资源与证明要求下复查。</p></div></header>
        {issue.verification && ['INCONCLUSIVE', 'STALE'].includes(issue.verification.status) && <div className="jj-rule-verification-gap"><Notice>{repairGap(issue.verification.reason_codes)}</Notice></div>}
        <div className="jj-rule-obligations">{(['DENY', 'SELECTED_ALLOW', 'REGRESSION'] as const).map(role => { const rows = issue.comparison?.filter(item => item.role === role) ?? []; return <div key={role}><span>{role === 'DENY' ? '原违规场景' : role === 'SELECTED_ALLOW' ? '正常功能' : '相关功能回归'}</span><strong>{!rows.length ? '未安排' : rows.every(item => item.after_verdict === 'SAFE') ? '本次均符合规则' : rows.some(item => item.after_verdict === 'VULNERABLE') ? '仍有违规' : rows.some(item => item.after_verdict === 'INCONCLUSIVE') ? '证据不足' : '等待复验'}</strong></div>; })}</div>
        <footer><Button kind="quiet" onClick={() => go('/reports?run_id=' + encodeURIComponent(issue.contract.source_run_id) + '&case_id=' + encodeURIComponent(issue.contract.source_case_id))}>原问题与证据<ArrowRightOutlined aria-hidden="true"/></Button><div className="jj-inline-actions">{issue.run_id && <Button onClick={() => go('/reports?run_id=' + encodeURIComponent(issue.run_id!))}>复验报告</Button>}{issue.status !== 'STALE' && issue.status !== 'VERIFIED' && (issue.change_id ? <><Button onClick={() => setRepair(issue)}>提交下一次修复</Button><Button kind="primary" onClick={() => go('/reports?view=plan&change_id=' + encodeURIComponent(issue.change_id!) + '&rule_id=' + encodeURIComponent(rule.permission.intent_id))}>复查这次修复</Button></> : <Button kind="primary" onClick={() => setRepair(issue)}>提交修复<ArrowRightOutlined aria-hidden="true"/></Button>)}</div></footer>
      </article>)}
      {!issues.length && (latest ? <article className="jj-rule-current"><Badge tone={tone(rule.state)}>{stateLabels[rule.state]}</Badge><h3>{rule.state === 'SAFE' ? '本次已检查场景符合这条规则' : rule.state === 'INCONCLUSIVE' ? '还缺少能够确认结果的证据' : rule.state === 'STALE' ? '已有结果对应先前的规则或代码' : '查看本次检查记录'}</h3><p>{latest.case_count} 个检查场景，{date(latest.created_at_us)}</p><Button onClick={() => go('/reports?run_id=' + encodeURIComponent(latest.run_id) + '&case_id=' + encodeURIComponent(latest.case_ids[0]))}>阅读检查依据<ArrowRightOutlined aria-hidden="true"/></Button></article> : <Empty title="还没有这条规则的检查记录" action={<Button kind="primary" onClick={() => go('/preparation?rule_id=' + encodeURIComponent(rule.permission.intent_id))}>准备检查材料</Button>}/>)}
    </section><aside className="jj-rule-context"><h2>这条规则</h2><dl><div><dt>操作角色</dt><dd>{text(rule.subject)}</dd></div><div><dt>业务操作</dt><dd>{text(rule.action)}</dd></div><div><dt>资源范围</dt><dd>{text(rule.resource_scope)}</dd></div></dl><ActionLink href={'#/preparation?rule_id=' + encodeURIComponent(rule.permission.intent_id)}>查看检查材料<ArrowRightOutlined aria-hidden="true"/></ActionLink><div className="jj-rule-context-divider"/><h3>最近修改</h3>{rule.changes[0] ? <><p>{text(rule.changes[0].reason)}</p><ActionLink href={'#' + rulePath(rule, '&section=changes')}>查看修改与复验<ArrowRightOutlined aria-hidden="true"/></ActionLink></> : <p className="jj-small jj-muted">尚未提交关联修改。</p>}</aside></div>}
    {section === 'changes' && <section className="jj-rule-change-list"><div className="jj-section-header"><h2>针对这条规则的修改</h2><Button onClick={() => setRepair(rule.issues.find(issue => !['VERIFIED', 'STALE'].includes(issue.status)) ?? null)}>提交修改</Button></div>{rule.changes.map(change => <article className="jj-rule-change" key={change.change_id}><div><span className="jj-small jj-muted">{date(change.created_at_us)}</span><h3>{text(change.reason)}</h3><p>{change.file_count} 个文件发生变化{change.targets.some(target => target.repair) ? '，用于修复已发现的问题' : '，声明涉及这条权限规则'}</p></div><div className="jj-inline-actions"><Button onClick={() => go('/changes?change_id=' + encodeURIComponent(change.change_id))}>代码变化</Button><Button kind="primary" onClick={() => go('/reports?view=plan&change_id=' + encodeURIComponent(change.change_id) + '&rule_id=' + encodeURIComponent(rule.permission.intent_id))}>预览复验范围<ArrowRightOutlined aria-hidden="true"/></Button></div></article>)}{!rule.changes.length && <Empty title="尚未提交关联修改">完成代码修改后，从这里登记实际变化及修复目标。</Empty>}</section>}
    {section === 'history' && <section className="jj-rule-history"><header><h2>这条规则的检查历史</h2><span className="jj-small jj-muted">每次检查保留当时的规则与代码范围</span></header>{rule.history.map(item => <button key={item.run_id} onClick={() => go('/reports?run_id=' + encodeURIComponent(item.run_id) + '&case_id=' + encodeURIComponent(item.case_ids[0]))}><time>{date(item.created_at_us)}</time><Badge tone={tone(item.verdict)}>{stateLabels[item.verdict]}</Badge><span>{item.case_count} 个场景</span><span>{item.change_id ? '关联代码修改' : '常规检查'}</span><ArrowRightOutlined aria-hidden="true"/></button>)}{!rule.history.length && <Empty title="暂无检查记录"/>}{rule.history_has_more && <Button kind="quiet" onClick={() => go('/reports?intent_id=' + rule.permission.intent_id + '&revision=' + rule.permission.revision + '&intent_hash=' + rule.permission.intent_hash)}>更早的检查</Button>}</section>}
  </>;
}
type Pending = {
    operation: string;
    reason: string;
    targets: RuleChangeTarget[];
};
function RepairSubmission({ rule, rules, issue, projectId, onClose, onSaved, onError }: {
    rule: RuleItem;
    rules: RuleItem[];
    issue: Issue | null;
    projectId: string;
    onClose: () => void;
    onSaved: (id: string) => void;
    onError: PageProps['onError'];
}) {
    const key = 'jiejian.studio.rule-change:' + projectId;
    const [pending, setPending] = useState<Pending | undefined>(() => { const saved = sessionStorage.getItem(key); if (!saved)
        return; try {
        return JSON.parse(saved) as Pending;
    }
    catch {
        return undefined;
    } });
    const base: RuleChangeTarget = { permission: rule.permission, repair: issue ? repairReference(issue.contract) : null };
    const [targets, setTargets] = useState<RuleChangeTarget[]>(pending?.targets ?? [base]), [reason, setReason] = useState(pending?.reason ?? ''), [busy, setBusy] = useState(false);
    const lock = useRef(false);
    const alternatives = rules.flatMap(item => item.issues.filter(task => !['VERIFIED', 'STALE'].includes(task.status)).map(task => ({ rule: item, task, target: { permission: item.permission, repair: repairReference(task.contract) } })));
    const save = async () => {
        if (lock.current)
            return;
        lock.current = true;
        setBusy(true);
        try {
            if (pending) {
                const receipt = await developmentApi.receipt(projectId, 'DELIVER', pending.operation);
                if (!receipt?.change_id)
                    throw new Error('本次提交回执尚未确认，请稍后查询。');
                assertProject(receipt.project_id, projectId);
                sessionStorage.removeItem(key);
                onSaved(receipt.change_id);
                return;
            }
            const preview = await sourceChangesApi.registrationPreview(projectId);
            assertProject(preview.project_id, projectId);
            const operation = { operation: crypto.randomUUID().replaceAll('-', ''), reason: reason.trim(), targets };
            sessionStorage.setItem(key, JSON.stringify(operation));
            setPending(operation);
            const receipt = await sourceChangesApi.register(projectId, { operation_id: operation.operation, expected_registration_fingerprint: preview.fingerprint, reason: operation.reason, claimed_paths: [], repair_reference: null, rule_targets: targets });
            assertProject(receipt.project_id, projectId);
            if (!receipt.change_id)
                throw new Error('提交未返回修改记录，请查询原回执。');
            sessionStorage.removeItem(key);
            onSaved(receipt.change_id);
        }
        catch (error) {
            onError(error);
        }
        finally {
            lock.current = false;
            setBusy(false);
        }
    };
    return <section className="jj-rule-submission" aria-label="提交规则修复"><header><div><h2>{issue ? '提交针对这个问题的修复' : '提交涉及这条规则的修改'}</h2><p>记录真实代码变化，随后复查原问题和正常功能。</p></div><Button disabled={busy} onClick={onClose}>收起</Button></header><div className="jj-rule-submission-body"><Field label="修改说明"><textarea autoFocus rows={3} maxLength={512} disabled={busy || Boolean(pending)} placeholder="说明修复了什么，以及正常功能如何保留" value={reason} onChange={event => setReason(event.target.value)}/></Field><fieldset><legend>本次修复目标</legend><label className="jj-rule-fix-target"><input type="checkbox" checked readOnly/><span><strong>{text(rule.title)}</strong><small>{text(rule.resource_scope)}</small></span></label>{alternatives.filter(item => item.task.task_reference !== issue?.task_reference).length > 0 && <details><summary>同一次修改还修复了其他问题</summary>{alternatives.filter(item => item.task.task_reference !== issue?.task_reference).map(item => <label className="jj-rule-fix-target" key={item.task.task_reference}><input type="checkbox" disabled={busy || Boolean(pending)} checked={targets.some(target => target.repair?.repair_fingerprint === item.task.contract.repair_fingerprint)} onChange={event => setTargets(values => event.target.checked ? [...values, item.target] : values.filter(target => target.repair?.repair_fingerprint !== item.task.contract.repair_fingerprint))}/><span><strong>{text(item.rule.title)}</strong><small>{text(item.rule.resource_scope)}</small></span></label>)}</details>}</fieldset></div><footer>{pending ? <Notice>提交结果尚未确认，查询原回执后继续。</Notice> : <span className="jj-small jj-muted">提交说明不会将问题标为已修复。</span>}<Button kind="primary" busy={busy} disabled={!reason.trim() && !pending} onClick={() => void save()}>{pending ? '查询本次提交' : '提交修复记录'}<ArrowRightOutlined aria-hidden="true"/></Button></footer></section>;
}
