import {conditionLabels} from '../../entities/permission/ui/RuleConditions';
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined';
import CheckOutlined from '@ant-design/icons/CheckOutlined';
import ExclamationCircleOutlined from '@ant-design/icons/ExclamationCircleOutlined';
import MinusOutlined from '@ant-design/icons/MinusOutlined';
import SafetyOutlined from '@ant-design/icons/SafetyOutlined';
import type { BusinessBoundaryViewDto } from '../../entities/permission/api/businessBoundaries';
import { ruleWorkspaceApi, type RuleItem, type RuleState } from '../../entities/permission/api/ruleWorkspace';
import { ChangeRegistration, changeTargetOptions } from '../../entities/source-change/ui/ChangeRegistration';
import { repairReference, type ProjectRepair } from '../../entities/check/api/repairs';
import { assertProject, type PageProps } from '../../shared/model/page';
import { date, text } from '../../shared/lib/format';
import { go, scopedPath } from '../../shared/lib/navigation';
import { useRead } from '../../shared/lib/useRead';
import { ActionLink, Button } from "../../shared/ui/actions";
import { Badge, Empty, ErrorNote, Notice } from "../../shared/ui/feedback";
import { Heading } from "../../shared/ui/layout";
import { Tabs } from "../../shared/ui/Tabs";
import { repairGap } from '../../entities/check/model/checks';
import { RepairTask } from './RepairTask';
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
    if (selected && (reference || route.query.get('view') === 'repair')) {
        const issue = selected.issues.find(item => item.contract.repair_fingerprint === reference);
        return issue ? <RepairTask key={issue.contract.repair_fingerprint + (route.query.get('change_id') ?? '')} rule={selected} rules={rules} issue={issue} projectId={projectId} changeId={route.query.get('change_id')} onError={onError} onReload={() => { state.reload(); refresh(); }}/>
            : <Empty title="这项原问题已不在当前修复范围中" action={<Button onClick={() => go(rulePath(selected))}>返回权限规则</Button>}>原检查报告仍可从检查记录查阅。</Empty>;
    }
    if (selected)
        return <RuleDetail key={projectId + selected.permission.intent_id} rule={selected} rules={rules} projectId={projectId} route={route} onError={onError} onReload={() => { state.reload(); refresh(); }}/>;
    const roles = boundary.actors.filter(role => role.effective_state === 'ACTIVE');
    const actions = boundary.actions.filter(action => action.effective_state === 'ACTIVE');
    const active = new Set(boundary.permission_intents.filter(intent => intent.effective_state === 'ACTIVE' && actions.some(action => action.action_id === intent.business_action_id && action.revision === intent.action_revision) && roles.some(role => role.actor_id === intent.subject_actor_id && role.revision === intent.subject_actor_revision) && roles.some(role => role.actor_id === intent.resource_owner_actor_id && role.revision === intent.resource_owner_actor_revision)).map(intent => intent.intent_id + '@' + intent.revision));
    const visible = rules.filter(rule => active.has(rule.permission.intent_id + '@' + rule.permission.revision) && (filter === 'ALL' || rule.expectation === filter) && (!query.trim() || [rule.title, rule.subject, rule.action, rule.resource_scope, ...conditionLabels(rule.conditions)].some(value => value.includes(query.trim()))));
    const open = rules.flatMap(rule => rule.issues).filter(issue => !['VERIFIED', 'STALE'].includes(issue.status)).length;
    return <>
    <Heading title="权限规则" actions={<><Button onClick={onManage}>编辑权限要求</Button><Button kind="primary" onClick={() => go('/reports?view=plan')}>检查权限<ArrowRightOutlined aria-hidden="true"/></Button></>}/>
    {reviewActions}
    <section className="jj-rule-workspace jj-rule-matrix">
      <header className="jj-rule-summary"><SafetyOutlined aria-hidden="true"/><div><strong>{rules.length} 条权限规则</strong><span>权限版本 {state.data.policy_epoch}，按已登记源码检查</span></div><div className="jj-rule-totals"><span><strong>{open}</strong> 个待处理问题</span><span><strong>{rules.filter(rule => rule.state === 'SAFE').length}</strong> 条检查通过</span></div></header>
      <div className="jj-rule-toolbar"><input aria-label="查找规则" value={query} onChange={event => setQuery(event.target.value)} placeholder="查找角色、操作或资源"/><div className="jj-toggle-group" aria-label="筛选规则">{[['ALL', '全部'], ['ALLOW', '允许'], ['DENY', '禁止']].map(([value, label]) => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div></div>
      <div className="jj-scroll-table jj-permission-table"><table className="jj-rule-table"><colgroup><col className="jj-rule-meaning-column"/><col className="jj-rule-condition-column"/><col className="jj-rule-state-column"/><col className="jj-rule-date-column"/><col className="jj-rule-open-column"/></colgroup><thead><tr><th scope="col">访问要求</th><th scope="col">适用条件</th><th scope="col" className="jj-table-state">检查情况</th><th scope="col">最近检查</th><th scope="col"><span className="jj-sr-only">操作</span></th></tr></thead><tbody>{visible.map(rule => <tr key={rule.permission.intent_id}>
        <th scope="row"><div className="jj-rule-meaning"><span className="jj-rule-expectation" data-allowed={rule.expectation === 'ALLOW'} aria-label={rule.expectation === 'ALLOW' ? '允许' : '禁止'}>{rule.expectation === 'ALLOW' ? <CheckOutlined aria-hidden="true"/> : <MinusOutlined aria-hidden="true"/>}</span><div><strong>{text(rule.title)}</strong><small>{text(rule.resource_scope)}</small></div></div></th>
        <td><div className="jj-rule-conditions-reading">{conditionLabels(rule.conditions).length ? conditionLabels(rule.conditions).map(label => <span key={label}>{label}</span>) : <span className="jj-muted">不限定</span>}</div></td>
        <td className="jj-table-state"><Badge tone={tone(rule.state)}>{stateLabels[rule.state]}</Badge></td><td className="jj-rule-date">{rule.latest ? date(rule.latest.created_at_us) : <span className="jj-muted">尚无记录</span>}</td>
        <td><ActionLink href={'#' + scopedPath(rulePath(rule), projectId)} aria-label={'查看' + text(rule.title) + '，' + text(rule.resource_scope) + (conditionLabels(rule.conditions).length ? '，' + conditionLabels(rule.conditions).join('，') : '')}>查看<ArrowRightOutlined aria-hidden="true"/></ActionLink></td>
      </tr>)}</tbody></table></div>
      {!visible.length && <Empty title="没有符合条件的规则"/>}
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
    const panelId = useId(), panel = useRef<HTMLDivElement>(null), focusRegistration = useRef(false);
    const beginRegistration = (issue: Issue | null) => {
        focusRegistration.current = true;
        setRepair(issue);
        go(rulePath(rule, '&section=changes'));
    };
    useLayoutEffect(() => {
        if (section !== 'changes' || repair === undefined || !focusRegistration.current) return;
        focusRegistration.current = false;
        panel.current?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
        panel.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus({ preventScroll: true });
    }, [section, repair]);
    const issues = reference ? rule.issues.filter(issue => issue.contract.repair_fingerprint === reference) : rule.issues;
    const latest = rule.latest;
    return <>
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => go('/permissions')}>权限规则</Button></div>
    <section className="jj-rule-detail-header"><div><div className="jj-rule-detail-label"><Badge tone={rule.expectation === 'ALLOW' ? 'positive' : 'negative'}>{rule.expectation === 'ALLOW' ? '允许' : '禁止'}</Badge><span>规则版本 {rule.permission.revision}</span></div><div className="jj-item-heading"><h1>{text(rule.title)}</h1><Badge tone={tone(rule.state)}>{stateLabels[rule.state]}</Badge></div><p>{text(rule.resource_scope)}</p>{conditionLabels(rule.conditions).length>0&&<p className="jj-small jj-muted">{conditionLabels(rule.conditions).join("，")}</p>}</div><div className="jj-rule-detail-status"><Button onClick={() => go('/reports?view=plan&rule_id=' + encodeURIComponent(rule.permission.intent_id))}>检查相关规则<ArrowRightOutlined aria-hidden="true"/></Button></div></section>

    <section className="jj-rule-detail-workspace">
    <div className="jj-rule-section-bar"><Tabs label="规则详情" value={section} idPrefix={panelId} panelId={panelId + '-content'} onValueChange={value => { setRepair(undefined); go(rulePath(rule, '&section=' + value)); }} items={[{ value: 'results', label: '检查结果' }, { value: 'changes', label: '修改记录' }, { value: 'history', label: '检查历史' }]} className="jj-action-tabs"/></div>
    <div className="jj-rule-detail-panel" role="tabpanel" id={panelId + '-content'} aria-labelledby={panelId + '-' + section} ref={panel} key={section} tabIndex={0}>
    {section === 'results' && <div className="jj-rule-result-layout"><section className="jj-rule-result-main"><div className="jj-section-header"><h2>{issues.length ? '发现的问题' : '检查情况'}</h2><span className="jj-small jj-muted">{issues.length ? `${issues.length} 项` : ''}</span></div>
      {issues.map(issue => <article className="jj-rule-issue" key={issue.task_reference}>
        <header><span className="jj-rule-issue-icon" data-state={issue.status}>{issue.status === 'VERIFIED' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}</span><div><Badge tone={issueTone(issue.status)}>{issue.status === 'REPAIR_REQUIRED' && (issue.recurrence_count ?? 0) > 0 ? '问题再次出现' : issueLabels[issue.status]}</Badge><h3>{issue.status === 'VERIFIED' ? '原问题已解决，正常功能保留' : issue.status === 'NOT_VERIFIED' ? '修改后仍出现了不应发生的结果' : '检查中出现了不应发生的业务结果'}</h3><p>{issue.history?.at(-1)?.kind === 'CONDITIONS_CHANGED' ? '新的证明条件下发现违规，作为新一轮原题处理。' : issue.recurrence_count ? `已确认修复后再次发现违规，累计 ${issue.recurrence_count} 次。` : '按原问题的账号、资源与证明要求复查。'}</p></div></header>
        {issue.verification && ['INCONCLUSIVE', 'STALE'].includes(issue.verification.status) && <div className="jj-rule-verification-gap"><Notice>{repairGap(issue.verification.reason_codes)}</Notice></div>}
        <div className="jj-rule-obligations">{(['DENY', 'SELECTED_ALLOW', 'REGRESSION'] as const).map(role => { const rows = issue.comparison?.filter(item => item.role === role) ?? []; return <div key={role}><span>{role === 'DENY' ? '原违规场景' : role === 'SELECTED_ALLOW' ? '正常功能' : '相关功能回归'}</span><strong>{!rows.length ? '未安排' : rows.every(item => item.after_verdict === 'SAFE') ? '本次均符合规则' : rows.some(item => item.after_verdict === 'VULNERABLE') ? '仍有违规' : rows.some(item => item.after_verdict === 'INCONCLUSIVE') ? '证据不足' : '等待复验'}</strong></div>; })}</div>
        <IssueHistory issue={issue}/><footer><Button kind="quiet" onClick={() => go('/reports?run_id=' + encodeURIComponent(issue.contract.source_run_id) + '&case_id=' + encodeURIComponent(issue.contract.source_case_id))}>原问题与证据<ArrowRightOutlined aria-hidden="true"/></Button><Button kind="primary" onClick={() => go(rulePath(rule, '&view=repair&repair_reference=' + encodeURIComponent(issue.contract.repair_fingerprint)))}>{issue.status === 'VERIFIED' ? '查看修复结果' : issue.status === 'STALE' ? '核对原问题' : '继续处理问题'}<ArrowRightOutlined aria-hidden="true"/></Button></footer>
      </article>)}
      {!issues.length && (latest ? <article className="jj-rule-current"><Badge tone={tone(rule.state)}>{stateLabels[rule.state]}</Badge><h3>{rule.state === 'SAFE' ? '本次已检查场景符合这条规则' : rule.state === 'INCONCLUSIVE' ? '还缺少能够确认结果的证据' : rule.state === 'STALE' ? '已有结果对应先前的规则或代码' : '查看本次检查记录'}</h3><p>{latest.case_count} 个检查场景，{date(latest.created_at_us)}</p><Button onClick={() => go('/reports?run_id=' + encodeURIComponent(latest.run_id) + '&case_id=' + encodeURIComponent(latest.case_ids[0]))}>阅读检查依据<ArrowRightOutlined aria-hidden="true"/></Button></article> : <Empty title="还没有这条规则的检查记录" action={<Button kind="primary" onClick={() => go('/preparation?rule_id=' + encodeURIComponent(rule.permission.intent_id))}>准备检查材料</Button>}/>)}
    </section><aside className="jj-rule-context"><h2>这条规则</h2><dl><div><dt>操作角色</dt><dd>{text(rule.subject)}</dd></div><div><dt>业务操作</dt><dd>{text(rule.action)}</dd></div><div><dt>资源范围</dt><dd>{text(rule.resource_scope)}</dd></div></dl><ActionLink href={'#/preparation?rule_id=' + encodeURIComponent(rule.permission.intent_id)}>查看检查材料<ArrowRightOutlined aria-hidden="true"/></ActionLink><div className="jj-rule-context-divider"/><h3>最近修改</h3>{rule.changes[0] ? <><p>{text(rule.changes[0].reason)}</p><ActionLink href={'#' + rulePath(rule, '&section=changes')}>查看修改与复验<ArrowRightOutlined aria-hidden="true"/></ActionLink></> : <p className="jj-small jj-muted">尚未提交关联修改。</p>}</aside></div>}
    {section === 'changes' && (repair !== undefined ? <ChangeRegistration key={repair?.task_reference ?? 'rule'} options={changeTargetOptions(rules)} initialTargets={[{permission: rule.permission, repair: repair ? repairReference(repair.contract) : null}]} projectId={projectId} closeLabel="返回修改记录" onClose={() => setRepair(undefined)} onError={onError} onSaved={changeId => { setRepair(undefined); onReload(); go(rulePath(rule, '&section=changes&change_id=' + encodeURIComponent(changeId))); }}/> : <section className="jj-rule-change-list"><div className="jj-section-header"><h2>关联修改</h2><Button kind="primary" onClick={() => beginRegistration(rule.issues.find(issue => !['VERIFIED', 'STALE'].includes(issue.status)) ?? null)}>登记修改<ArrowRightOutlined aria-hidden="true"/></Button></div>{rule.changes.map(change => <article className="jj-rule-change" key={change.change_id}><div><span className="jj-small jj-muted">{date(change.created_at_us)}</span><h3>{text(change.reason)}</h3><p>{change.file_count} 个文件发生变化{change.targets.some(target => target.repair) ? '，用于修复已发现的问题' : '，声明涉及这条权限规则'}</p></div><div className="jj-inline-actions"><Button onClick={() => go('/changes?change_id=' + encodeURIComponent(change.change_id))}>代码变化</Button><Button kind="primary" onClick={() => go('/reports?view=plan&change_id=' + encodeURIComponent(change.change_id) + '&rule_id=' + encodeURIComponent(rule.permission.intent_id))}>预览复验范围<ArrowRightOutlined aria-hidden="true"/></Button></div></article>)}{!rule.changes.length && <Empty title="尚未提交关联修改">完成代码修改后，从这里登记实际变化及修复目标。</Empty>}</section>)}
    {section === 'history' && <section className="jj-rule-history"><header><h2>这条规则的检查历史</h2><span className="jj-small jj-muted">每次检查保留当时的规则与代码范围</span></header>{rule.history.map(item => <button key={item.run_id} onClick={() => go('/reports?run_id=' + encodeURIComponent(item.run_id) + '&case_id=' + encodeURIComponent(item.case_ids[0]))}><time>{date(item.created_at_us)}</time><Badge tone={tone(item.verdict)}>{stateLabels[item.verdict]}</Badge><span>{item.case_count} 个场景</span><span>{item.change_id ? '关联代码修改' : '常规检查'}</span><ArrowRightOutlined aria-hidden="true"/></button>)}{!rule.history.length && <Empty title="暂无检查记录"/>}{rule.history_has_more && <Button kind="quiet" onClick={() => go('/reports?intent_id=' + rule.permission.intent_id + '&revision=' + rule.permission.revision + '&intent_hash=' + rule.permission.intent_hash)}>更早的检查</Button>}</section>}
    </div></section>
  </>;
}

function IssueHistory({ issue }: { issue: Issue }) {
    const names = { FOUND: '首次发现问题', CHECKED: '再次检查', VERIFIED: '修复已验证', RECURRED: '问题再次出现', CONDITIONS_CHANGED: '新条件下发现违规', CHECK_PENDING: '复验正在进行', CHECK_INTERRUPTED: '复验已中断' };
    return issue.history?.length ? <details className="jj-issue-history"><summary>问题处理历史 <span>{issue.history.length} 条记录</span></summary><ol>{issue.history.map(event => <li key={event.run_id}><time>{date(event.created_at_us)}</time><div><strong>{names[event.kind]}</strong>{event.status && <span>{issueLabels[event.status]}</span>}{event.kind === 'CHECKED' && !event.status && <small>本次未关联原题修复</small>}</div><Button kind="quiet" onClick={() => go('/reports?run_id=' + encodeURIComponent(event.run_id))}>查看报告<ArrowRightOutlined aria-hidden="true"/></Button></li>)}</ol></details> : null;
}
