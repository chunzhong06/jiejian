import {ObjectTable} from '../../shared/ui/ObjectTable'
import {Inspector} from '../../shared/ui/Inspector'
import {SearchField} from '../../shared/ui/SearchField'
import {useContentTransition} from '../../shared/lib/contentTransition'
import {Segmented} from '../../shared/ui/Segmented'
import {conditionLabels} from '../../entities/permission/ui/RuleConditions';
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined';
import ExclamationCircleOutlined from '@ant-design/icons/ExclamationCircleOutlined';
import type { BusinessBoundaryViewDto } from '../../entities/permission/api/businessBoundaries';
import { ruleWorkspaceApi, type RuleItem, type RuleState } from '../../entities/permission/api/ruleWorkspace';
import { ChangeRegistration, changeTargetOptions } from '../../entities/source-change/ui/ChangeRegistration';
import { repairReference, type ProjectRepair } from '../../entities/check/api/repairs';
import { assertProject, type PageProps } from '../../shared/model/page';
import { date, text } from '../../shared/lib/format';
import {go,scopedPath,returnDestination,returnDestinationLabel,withReturnDestination} from '../../shared/lib/navigation'
import {useDirectoryState} from '../../shared/lib/directoryState'
import { useRead } from '../../shared/lib/useRead';
import {ActionLink,Button} from '../../shared/ui/actions'
import { Badge, Empty, PageError, Notice, ResultList } from "../../shared/ui/feedback";
import { ObjectHeading, Heading } from "../../shared/ui/layout";
import { Tabs } from "../../shared/ui/Tabs";
import { repairGap } from '../../entities/check/model/checks';
import { RepairTask } from '../../entities/check/ui/RepairTask';
const stateLabels: Record<RuleState, string> = { UNCONFIRMED: '运行版本待确认', UNTESTED: '尚未检查', STALE: '版本变化，待重查', SAFE: '符合规则', VULNERABLE: '不符合规则', INCONCLUSIVE: '证据不足', REPAIR_PENDING: '原问题待复验' };
const issueLabels: Record<string, string> = { REPAIR_REQUIRED: '待修复', CHANGE_SUBMITTED: '修复已提交', READY_TO_VERIFY: '待复验', VERIFIED: '已验证修复', NOT_VERIFIED: '问题仍存在', INCONCLUSIVE: '复验未能确认', STALE: '规则已变化' };
const tone = (state: RuleState) => state === 'SAFE' ? 'positive' : state === 'VULNERABLE' ? 'negative' : state === 'INCONCLUSIVE' || state === 'REPAIR_PENDING' || state === 'STALE' ? 'caution' : 'neutral';
const issueTone = (state: string) => state === 'VERIFIED' ? 'positive' : state === 'NOT_VERIFIED' || state === 'REPAIR_REQUIRED' ? 'negative' : state === 'STALE' || state === 'INCONCLUSIVE' ? 'caution' : state === 'CHANGE_SUBMITTED' || state === 'READY_TO_VERIFY' ? 'accent' : 'neutral';
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
    const collection=useRef<HTMLElement>(null)
    const here=route.path+'?'+route.query,origin=returnDestination(route.query.get('return_to'))
    const directory=useDirectoryState('jiejian.directory:'+projectId+':permissions',{focusedId:'',query:'',filter:'ALL',stateFilter:'ALL',detailOpen:true as boolean},Boolean(state.data)&&!route.query.has('rule_id')&&!route.query.has('repair_reference'),collection)
    const {focusedId,query,filter,stateFilter,detailOpen}=directory.value
    const setDetailOpen=(detailOpen:boolean)=>directory.update({detailOpen})
    const setFocusedId=(focusedId:string)=>directory.update({focusedId})
    const setQuery=(query:string)=>directory.update({query})
    const setFilter=(filter:string)=>directory.update({filter})
    const setStateFilter=(stateFilter:string)=>directory.update({stateFilter})
    const closeDetails=()=>{collection.current?.querySelector<HTMLButtonElement>('.jj-object-select[aria-pressed=true]')?.focus({preventScroll:true});setDetailOpen(false)};
  const results=useContentTransition(filter)
    if (state.loading)
        return <PageSkeleton view="/permissions"/>;
    if (state.error || !state.data)
        return <PageError title="权限与覆盖" error={state.error}/>;
    if (state.data.policy_epoch !== boundary.policy_epoch)
        return <><Heading title="权限与覆盖"/><Notice tone="caution">权限规则已变化，请重新读取。</Notice></>;
    const { rules } = state.data, reference = route.query.get('repair_reference');
    const id = route.query.get('rule_id') ?? rules.find(rule => rule.issues.some(issue => issue.contract.repair_fingerprint === reference))?.permission.intent_id;
    const selected = rules.find(rule => rule.permission.intent_id === id);
    if (id && !selected)
        return <Empty title="这条规则已不在当前权限范围中" action={<ActionLink navigationScope="page" href={'#'+scopedPath('/permissions')}  kind="quiet">返回权限规则</ActionLink>}>历史检查仍可从检查记录查阅。</Empty>;
    if (selected && (reference || route.query.get('view') === 'repair')) {
        const issue = selected.issues.find(item => item.contract.repair_fingerprint === reference);
        return issue ? <RepairTask key={issue.contract.repair_fingerprint + (route.query.get('change_id') ?? '')} rule={selected} rules={rules} issue={issue} returnTo={origin??undefined} projectId={projectId} changeId={route.query.get('change_id')} onError={onError} onReload={() => { state.reload(); refresh(); }}/>
            : <Empty title="这项原问题已不在当前修复范围中" action={<ActionLink navigationScope="page" href={'#'+scopedPath(rulePath(selected))}  kind="quiet">返回权限规则</ActionLink>}>原检查报告仍可从检查记录查阅。</Empty>;
    }
    if (selected)
        return <RuleDetail key={projectId + selected.permission.intent_id} rule={selected} rules={rules} projectId={projectId} route={route} onError={onError} onReload={() => { state.reload(); refresh(); }}/>;
    const roles = boundary.actors.filter(role => role.effective_state === 'ACTIVE');
    const actions = boundary.actions.filter(action => action.effective_state === 'ACTIVE');
    const active = new Set(boundary.permission_intents.filter(intent => intent.effective_state === 'ACTIVE' && actions.some(action => action.action_id === intent.business_action_id && action.revision === intent.action_revision) && roles.some(role => role.actor_id === intent.subject_actor_id && role.revision === intent.subject_actor_revision) && roles.some(role => role.actor_id === intent.resource_owner_actor_id && role.revision === intent.resource_owner_actor_revision)).map(intent => intent.intent_id + '@' + intent.revision));
    const needsAttention=(rule:RuleItem)=>['VULNERABLE','INCONCLUSIVE','REPAIR_PENDING','STALE','UNCONFIRMED'].includes(rule.state)||rule.issues.some(issue=>!['VERIFIED','STALE'].includes(issue.status));
    const visible = rules.filter(rule => active.has(rule.permission.intent_id + '@' + rule.permission.revision) && (filter === 'ALL' || rule.expectation === filter) && (stateFilter==='ALL'||(stateFilter==='SAFE'?rule.state==='SAFE':needsAttention(rule))) && (!query.trim() || [rule.title, rule.subject, rule.action, rule.resource_scope, ...conditionLabels(rule.conditions)].some(value => value.includes(query.trim()))));
    const attention = rules.filter(needsAttention).length;
    const focused=visible.find(rule=>rule.permission.intent_id===focusedId)??visible[0];
    return <>
      {origin&&<div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin)} kind="quiet">{returnDestinationLabel(origin)}</ActionLink></div>}
      <Heading title="权限与覆盖" actions={<><Button onClick={onManage}>编辑权限要求</Button><ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/reports?view=plan',here))} kind="primary">检查权限<ArrowRightOutlined aria-hidden="true"/></ActionLink></>}>明确哪些角色可以对哪些数据执行哪些操作。确认后的规则将作为检查依据，用于判断应用的实际行为是否符合要求。</Heading>
      {reviewActions}
      <div className="jj-workspace-toolbar"><SearchField label="查找规则" value={query} onValueChange={setQuery} placeholder="查找角色、操作或资源"/><Segmented label="筛选规则" value={filter} items={[{value:'ALL',label:'全部'},{value:'ALLOW',label:'允许'},{value:'DENY',label:'禁止'}]} onValueChange={setFilter}/></div>
      <div className="jj-rule-directory-summary"><span>{active.size} 条生效规则 · 权限版本 {state.data.policy_epoch}</span><div><Button kind="quiet" aria-pressed={stateFilter==='ATTENTION'} onClick={()=>setStateFilter(stateFilter==='ATTENTION'?'ALL':'ATTENTION')}>{attention} 条需要处理</Button><Button kind="quiet" aria-pressed={stateFilter==='SAFE'} onClick={()=>setStateFilter(stateFilter==='SAFE'?'ALL':'SAFE')}>{rules.filter(rule=>rule.state==='SAFE').length} 条检查通过</Button></div></div>
      <section ref={collection} data-detail-open={Boolean(focused)&&detailOpen} className="jj-collection jj-rule-directory" aria-label="权限规则目录"><div className="jj-collection-layout">
        <div className="jj-collection-main"><ObjectTable containerRef={results} selection={focused?.permission.intent_id??""}><thead><tr><th scope="col">访问要求</th><th scope="col" className="jj-table-state">检查情况</th><th scope="col">最近检查</th></tr></thead><tbody>{visible.map(rule=><tr key={rule.permission.intent_id} data-selected={focused?.permission.intent_id===rule.permission.intent_id}>
          <th scope="row"><button className="jj-object-select" data-directory-id={rule.permission.intent_id} aria-pressed={focused?.permission.intent_id===rule.permission.intent_id} onClick={()=>{setFocusedId(rule.permission.intent_id);setDetailOpen(true)}}><strong>{text(rule.title)}</strong><small className="jj-object-summary">{text(rule.resource_scope)}{conditionLabels(rule.conditions).length?' · '+conditionLabels(rule.conditions).join('，'):''}</small></button></th>
          <td className="jj-table-state"><Badge tone={tone(rule.state)}>{stateLabels[rule.state]}</Badge></td><td className="jj-object-meta">{rule.latest?date(rule.latest.created_at_us):'尚无记录'}</td>
        </tr>)}</tbody></ObjectTable>{!visible.length&&<Empty title="没有符合条件的规则" action={<Button onClick={()=>{setQuery('');setFilter('ALL');setStateFilter('ALL')}}>显示全部规则</Button>}/>}</div>
        {focused&&detailOpen&&<Inspector identity={focused.permission.intent_id} title={text(focused.title)} caption="当前规则" status={<Badge tone={tone(focused.state)}>{stateLabels[focused.state]}</Badge>} onClose={closeDetails}><h3>业务含义</h3><dl className="jj-facts"><div><dt>操作角色</dt><dd>{text(focused.subject)}</dd></div><div><dt>业务操作</dt><dd>{text(focused.action)}</dd></div><div><dt>资源范围</dt><dd>{text(focused.resource_scope)}</dd></div><div><dt>访问要求</dt><dd>{focused.expectation==='ALLOW'?'允许':'禁止'}</dd></div>{conditionLabels(focused.conditions).length>0&&<div><dt>适用条件</dt><dd>{conditionLabels(focused.conditions).join('，')}</dd></div>}</dl><h3>关联工作</h3><nav className="jj-rule-inspector-links"><ActionLink presentation="row" onClick={()=>directory.remember(focused?.permission.intent_id)} href={'#'+scopedPath(rulePath(focused),projectId)}>规则、结果与修改<ArrowRightOutlined aria-hidden="true"/></ActionLink><ActionLink presentation="row" onClick={()=>directory.remember(focused?.permission.intent_id)} href={'#'+scopedPath(withReturnDestination('/preparation?rule_id='+encodeURIComponent(focused.permission.intent_id),here),projectId)}>查看检查材料<ArrowRightOutlined aria-hidden="true"/></ActionLink>{focused.latest&&<ActionLink presentation="row" onClick={()=>directory.remember(focused?.permission.intent_id)} href={'#'+scopedPath(withReturnDestination('/reports?run_id='+focused.latest.run_id+(focused.latest.case_ids[0]?'&case_id='+focused.latest.case_ids[0]:''),here),projectId)}>阅读最近证据<ArrowRightOutlined aria-hidden="true"/></ActionLink>}</nav></Inspector>}
      </div></section>
      <div className="jj-rule-archive"><ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/reports',here))} kind="quiet">全部检查记录<ArrowRightOutlined aria-hidden="true"/></ActionLink><ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/changes',here))} kind="quiet">代码变更档案<ArrowRightOutlined aria-hidden="true"/></ActionLink></div>
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
    const here=route.path+'?'+route.query,origin=returnDestination(route.query.get('return_to'))
    const localRulePath=(item:RuleItem,suffix='')=>origin?withReturnDestination(rulePath(item,suffix),origin):rulePath(item,suffix)
    const [repair, setRepair] = useState<Issue | null | undefined>(undefined);
    const section = route.query.get('section') ?? 'results', reference = route.query.get('repair_reference');
    const panelId = useId(), panel = useRef<HTMLDivElement>(null), focusRegistration = useRef(false);
    const beginRegistration = (issue: Issue | null) => {
        focusRegistration.current = true;
        setRepair(issue);
        go(localRulePath(rule, '&section=changes'));
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
    <div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin??'/permissions')} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}{origin?returnDestinationLabel(origin):'返回权限规则'}</ActionLink></div>
    <section className="jj-rule-detail-header"><div><div className="jj-rule-detail-label"><Badge>{rule.expectation === 'ALLOW' ? '允许' : '禁止'}</Badge><span>规则版本 {rule.permission.revision}</span></div><div className="jj-object-line"><h1>{text(rule.title)}</h1><Badge tone={tone(rule.state)}>{stateLabels[rule.state]}</Badge></div><p>{text(rule.resource_scope)}</p>{conditionLabels(rule.conditions).length>0&&<p className="jj-small jj-muted">{conditionLabels(rule.conditions).join("，")}</p>}</div><div className="jj-rule-detail-status"><ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/reports?'+new URLSearchParams({view:'plan',rule_id:rule.permission.intent_id,return_to:localRulePath(rule,'&section='+section)}),here))}  kind="default">检查这条规则<ArrowRightOutlined aria-hidden="true"/></ActionLink></div></section>

    <section className="jj-rule-detail-workspace">
    <div className="jj-rule-section-bar"><Tabs label="规则详情" value={section} idPrefix={panelId} panelId={panelId + '-content'} onValueChange={value => { setRepair(undefined); go(localRulePath(rule, '&section=' + value)); }} items={[{ value: 'results', label: '检查结果' }, { value: 'changes', label: '修改记录' }, { value: 'history', label: '检查历史' }]}/></div>
    <div className="jj-rule-detail-panel" role="tabpanel" id={panelId + '-content'} aria-labelledby={panelId + '-' + section} ref={panel} key={section} tabIndex={0}>
    {section === 'results' && <div className="jj-rule-result-layout"><section className="jj-rule-result-main"><div className="jj-section-header"><h2>{issues.length ? '发现的问题' : '检查情况'}</h2><span className="jj-small jj-muted">{issues.length ? `${issues.length} 项` : ''}</span></div>
      {issues.map(issue => <article className="jj-rule-issue" key={issue.task_reference}><div className="jj-rule-issue-reading"><div className="jj-rule-issue-context">
        <header><ObjectHeading level={3} title={issue.status === 'VERIFIED' ? '原问题已解决，正常功能保留' : issue.status === 'NOT_VERIFIED' ? '修改后仍出现了不应发生的结果' : '检查中出现了不应发生的业务结果'} icon={<span className="jj-rule-issue-icon" data-state={issue.status}>{issue.status === 'VERIFIED' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}</span>} status={<Badge tone={issueTone(issue.status)}>{issue.status === 'REPAIR_REQUIRED' && (issue.recurrence_count ?? 0) > 0 ? '问题再次出现' : issueLabels[issue.status]}</Badge>} description={<span className="jj-small">{issue.history?.at(-1)?.kind === 'CONDITIONS_CHANGED' ? '新的证明条件下发现违规，继续跟进这项原问题。' : issue.recurrence_count ? '已确认修复后再次发现违规，累计 '+issue.recurrence_count+' 次。' : '按原问题的账号、资源与证明要求复查。'}</span>}/></header>
        {issue.verification && ['INCONCLUSIVE', 'STALE'].includes(issue.verification.status) && <div className="jj-rule-verification-gap"><Notice tone="caution">{repairGap(issue.verification.reason_codes)}</Notice></div>}
        </div><ResultList label="原问题复验范围" items={(['DENY', 'SELECTED_ALLOW', 'REGRESSION'] as const).map(role => { const rows = issue.comparison?.filter(item => item.role === role) ?? []; return {label:role==='DENY'?'原违规场景':role==='SELECTED_ALLOW'?'正常功能':'相关功能回归',status:<Badge tone={!rows.length?'neutral':rows.every(item=>item.after_verdict==='SAFE')?'positive':rows.some(item=>item.after_verdict==='VULNERABLE')?'negative':rows.some(item=>item.after_verdict==='INCONCLUSIVE')?'caution':'neutral'}>{!rows.length?'未安排':rows.every(item=>item.after_verdict==='SAFE')?'本次均符合规则':rows.some(item=>item.after_verdict==='VULNERABLE')?'仍有违规':rows.some(item=>item.after_verdict==='INCONCLUSIVE')?'证据不足':'等待复验'}</Badge>}; })}/>
        </div><IssueHistory issue={issue} returnTo={here}/><footer><ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/reports?run_id=' + encodeURIComponent(issue.contract.source_run_id) + '&case_id=' + encodeURIComponent(issue.contract.source_case_id),here))} kind="quiet">原问题与证据<ArrowRightOutlined aria-hidden="true"/></ActionLink><ActionLink navigationScope="page" href={'#'+scopedPath(localRulePath(rule, '&view=repair&repair_reference=' + encodeURIComponent(issue.contract.repair_fingerprint)))} kind="primary">{issue.status === 'VERIFIED' ? '查看修复结果' : issue.status === 'STALE' ? '核对原问题' : '继续处理问题'}<ArrowRightOutlined aria-hidden="true"/></ActionLink></footer>
      </article>)}
      {!issues.length && (latest ? <article className="jj-rule-current"><header><div className="jj-object-line"><h3>{rule.state === 'SAFE' ? '本次已检查场景符合这条规则' : rule.state === 'INCONCLUSIVE' ? '还缺少能够确认结果的证据' : rule.state === 'STALE' ? '已有结果对应先前的规则或代码' : '查看本次检查记录'}</h3><Badge tone={tone(rule.state)}>{stateLabels[rule.state]}</Badge></div></header><dl className="jj-facts jj-rule-current-facts" data-layout="columns"><div><dt>检查范围</dt><dd>{latest.case_count} 个检查场景</dd></div><div><dt>检查时间</dt><dd>{date(latest.created_at_us)}</dd></div></dl><footer><ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/reports?run_id=' + encodeURIComponent(latest.run_id) + '&case_id=' + encodeURIComponent(latest.case_ids[0]),here))}  kind="quiet">阅读检查依据<ArrowRightOutlined aria-hidden="true"/></ActionLink></footer></article> : <Empty title="还没有这条规则的检查记录" action={<ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/preparation?rule_id=' + encodeURIComponent(rule.permission.intent_id),here))} kind="primary">准备检查材料</ActionLink>}/>)}
    </section>{Boolean(issues.length || latest || rule.changes.length) && <section className="jj-rule-related" aria-label="接续维护这条规则">{Boolean(issues.length || latest) && <ActionLink href={'#' + scopedPath(withReturnDestination('/preparation?rule_id=' + encodeURIComponent(rule.permission.intent_id),here), projectId)}>查看检查材料<ArrowRightOutlined aria-hidden="true"/></ActionLink>}{rule.changes[0] && <div><h3>最近修改</h3><p>{text(rule.changes[0].reason)}</p><ActionLink href={'#' + localRulePath(rule, '&section=changes')}>查看修改与复验<ArrowRightOutlined aria-hidden="true"/></ActionLink></div>}</section>}</div>}
    {section === 'changes' && (repair !== undefined ? <ChangeRegistration key={repair?.task_reference ?? 'rule'} options={changeTargetOptions(rules)} initialTargets={[{permission: rule.permission, repair: repair ? repairReference(repair.contract) : null}]} projectId={projectId} closeLabel="返回修改记录" onClose={() => setRepair(undefined)} onError={onError} onSaved={changeId => { setRepair(undefined); onReload(); go(localRulePath(rule, '&section=changes&change_id=' + encodeURIComponent(changeId))); }}/> : <section className="jj-rule-change-list"><div className="jj-section-header"><h2>关联修改</h2><Button kind="primary" onClick={() => beginRegistration(rule.issues.find(issue => !['VERIFIED', 'STALE'].includes(issue.status)) ?? null)}>登记修改<ArrowRightOutlined aria-hidden="true"/></Button></div>{rule.changes.map(change => <article className="jj-rule-change" key={change.change_id}><div><span className="jj-small jj-muted">{date(change.created_at_us)}</span><h3>{text(change.reason)}</h3><p>{change.file_count} 个文件发生变化{change.targets.some(target => target.repair) ? '，用于修复已发现的问题' : '，声明涉及这条权限规则'}</p></div><div className="jj-inline-actions"><ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/changes?change_id=' + encodeURIComponent(change.change_id),here))}  kind="default">代码变化</ActionLink><ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/reports?view=plan&change_id=' + encodeURIComponent(change.change_id) + '&rule_id=' + encodeURIComponent(rule.permission.intent_id),here))} kind="primary">预览复验范围<ArrowRightOutlined aria-hidden="true"/></ActionLink></div></article>)}{!rule.changes.length && <Empty title="尚未提交关联修改">完成代码修改后，从这里登记实际变化及修复目标。</Empty>}</section>)}
    {section === 'history' && <section className="jj-rule-history"><header><h2>这条规则的检查历史</h2><span className="jj-small jj-muted">每次检查保留当时的规则与代码范围</span></header>{rule.history.map(item => <button key={item.run_id} onClick={() => go(withReturnDestination('/reports?run_id=' + encodeURIComponent(item.run_id) + '&case_id=' + encodeURIComponent(item.case_ids[0]),here))}><time>{date(item.created_at_us)}</time><Badge tone={tone(item.verdict)}>{stateLabels[item.verdict]}</Badge><span>{item.case_count} 个场景</span><span>{item.change_id ? '关联代码修改' : '常规检查'}</span><ArrowRightOutlined aria-hidden="true"/></button>)}{!rule.history.length && <Empty title="暂无检查记录">完成这条规则的检查后，这里会保留每次结果和当时的范围。可通过“检查这条规则”先核对准备情况。</Empty>}{rule.history_has_more && <ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/reports?intent_id=' + rule.permission.intent_id + '&revision=' + rule.permission.revision + '&intent_hash=' + rule.permission.intent_hash,here))} kind="quiet">更早的检查</ActionLink>}</section>}
    </div></section>
  </>;
}

function IssueHistory({ issue,returnTo }: { issue: Issue;returnTo:string }) {
    const names = { FOUND: '首次发现问题', CHECKED: '再次检查', VERIFIED: '修复已验证', RECURRED: '问题再次出现', CONDITIONS_CHANGED: '新条件下发现违规', CHECK_PENDING: '复验正在进行', CHECK_INTERRUPTED: '复验已中断' };
    return issue.history?.length ? <details className="jj-issue-history"><summary>问题处理历史 <span>{issue.history.length} 条记录</span></summary><ol>{issue.history.map(event => <li key={event.run_id}><time>{date(event.created_at_us)}</time><div><strong>{names[event.kind]}</strong>{event.status && <span>{issueLabels[event.status]}</span>}{event.kind === 'CHECKED' && !event.status && <small>本次未关联原问题修复</small>}</div><ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/reports?run_id=' + encodeURIComponent(event.run_id),returnTo))} kind="quiet">查看报告<ArrowRightOutlined aria-hidden="true"/></ActionLink></li>)}</ol></details> : null;
}
