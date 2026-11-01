import {conditionLabels} from '../../../entities/permission/ui/RuleConditions';
import { useEffect, useRef, useState } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined';
import ExclamationCircleOutlined from '@ant-design/icons/ExclamationCircleOutlined';
import QuestionCircleOutlined from '@ant-design/icons/QuestionCircleOutlined';
import type { ActionResultStory, ResultStory } from '../../../entities/check/api/currentChecks';
import type { RepairComparisonRow } from '../../../entities/check/api/repairs';
import { Badge, Empty, Notice } from "../../../shared/ui/feedback";
import { Button } from "../../../shared/ui/actions";
import { AgentHandoff } from '../../../entities/check/ui/AgentHandoff';
import { repairReference } from '../../../entities/check/api/repairs';
import { Heading } from "../../../shared/ui/layout";
import { date, text } from '../../../shared/lib/format';
import { go } from '../../../shared/lib/navigation';
import { actual, gaps, judgement, judgementLabels, owner, requirement, repairGap, resultTitle, subject, type Tone } from '../../../entities/check/model/checks';
import { EvidenceInspector } from './EvidenceInspector';
export function Report({ story, selectedCaseId, tab, evidenceId, recordId, proofId, stepId, checkedAt, onError, readOnly = false, basePath = '/reports', returnPath = '/reports', returnLabel = '全部报告' }: {
    story: ResultStory;
    selectedCaseId: string | null;
    tab: string | null;
    evidenceId: string | null;
    recordId: string | null;
    proofId?: string | null;
    stepId?: string | null;
    checkedAt?: number;
    onError: (error: unknown) => void;
    readOnly?: boolean;
    basePath?: string;
    returnPath?: string;
    returnLabel?: string;
}) {
    const [page, setPage] = useState(1), [assist, setAssist] = useState(false);
    const trigger = useRef<HTMLElement | null>(null), root = useRef<HTMLDivElement>(null), scroll = useRef(0);
    const caseItem = story.actions.find(item => item.case_id === selectedCaseId);
    const gapAction = caseItem ?? story.actions.find(item => judgement(item) === 'caution');
    const resolveGap = () => { if (!gapAction) return; const surface = gapAction.fact_comparison.http_surface; const focus = gapAction.fact_comparison.verified_actual_identity.verification_status !== 'MATCH' ? 'identity' : !surface.recovery_verified ? 'recovery' : 'evidence'; go('/preparation?' + new URLSearchParams({ action_id: gapAction.action_id, focus, return_to: address('run_id=' + story.run_id + '&case_id=' + gapAction.case_id), ...(gapAction.permission.intent_id ? { rule_id: gapAction.permission.intent_id } : {}), ...(story.change_context ? { change_id: story.change_context.change_id } : {}) })); };
    const address = (query: string) => basePath + (basePath.includes('?') ? '&' : '?') + query;
    const open = (id: string | null) => { if (!selectedCaseId) {
        trigger.current = document.activeElement as HTMLElement;
        scroll.current = window.scrollY;
    } go(address(`run_id=${encodeURIComponent(story.run_id)}${id ? '&case_id=' + encodeURIComponent(id) : ''}`)); };
    useEffect(() => { if (!selectedCaseId && trigger.current) {
        const original = trigger.current, fresh = original.isConnected ? original : root.current?.querySelector<HTMLElement>('[data-case="' + original.dataset.case + '"]');
        fresh?.focus({ preventScroll: true });
        window.scrollTo({ top: scroll.current, behavior: 'instant' });
    } }, [selectedCaseId]);
    const groups: Array<{
        tone: Tone;
        title: string;
    }> = [{ tone: 'negative', title: '不符合规则的结果' }, { tone: 'caution', title: '尚未确认的结果' }, { tone: 'neutral', title: '其他已发布结果' }, { tone: 'positive', title: '符合规则的结果' }];
    const ordered = [...story.actions].sort((a, b) => groups.findIndex(item => item.tone === judgement(a)) - groups.findIndex(item => item.tone === judgement(b)));
    const visible = ordered.slice((page - 1) * 10, page * 10);
    const navigateEvidence = (kind: string, evidence?: string, record?: string, proof?: string, step?: string) => { if (!selectedCaseId)
        return; const query = new URLSearchParams({ run_id: story.run_id, case_id: selectedCaseId, tab: kind }); if (evidence)
        query.set('evidence_id', evidence); if (record)
        query.set('record_id', record); if (proof)
        query.set('proof_id', proof); if (step ?? stepId)
        query.set('step_id', (step ?? stepId)!); go(address(query.toString())); };
    const reportTone = story.verdict === 'PASS' ? 'positive' : story.verdict === 'BLOCK' ? 'negative' : 'caution';
    return <div ref={root} className="jj-report">
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => go(returnPath)}>{returnLabel}</Button></div>
    <section className="jj-report-workspace" aria-label="检查报告" data-tone={reportTone}>
    <section className="jj-report-hero" data-tone={reportTone}>
      <div className="jj-report-heading"><span className="jj-report-symbol" aria-hidden="true">{reportTone === 'positive' ? <CheckCircleOutlined /> : reportTone === 'negative' ? <ExclamationCircleOutlined /> : <QuestionCircleOutlined />}</span><Heading eyebrow={story.repair_verification ? '修复复验' : story.selection ? '选定规则检查' : '检查报告'} title={resultTitle(story)} actions={<><Button kind="quiet" onClick={() => setAssist(true)}>交给 Agent 解读</Button>{!readOnly && story.verdict === 'INCONCLUSIVE' && <Button kind="primary" onClick={resolveGap}>处理证据缺口</Button>}{!readOnly && story.verdict === 'BLOCK' && story.actions.some(item => item.repair_requirement) && <Button kind="primary" onClick={() => go('/permissions?repair_reference=' + encodeURIComponent((caseItem?.repair_requirement ?? story.actions.find(item => item.repair_requirement)!.repair_requirement!).repair_fingerprint))}>处理权限问题</Button>}</>}/></div>
      <div className="jj-report-context"><div className="jj-report-metadata"><span>{story.actions.length} 项检查</span>{checkedAt && <span>{date(checkedAt)}</span>}<span>权限版本 {story.policy_epoch}</span>{story.runtime_status === 'MATCHED' && <span>运行代码已核对</span>}</div>{!readOnly && <Button kind="quiet" onClick={() => go(caseItem?.permission.intent_id ? '/permissions?rule_id=' + encodeURIComponent(caseItem.permission.intent_id) : '/permissions')}>{caseItem ? '查看这条权限规则' : '查看权限规则与问题处理'}<ArrowRightOutlined aria-hidden="true"/></Button>}</div>
    </section>
    {story.runtime_status !== 'MATCHED' && <Notice>运行代码尚未对应到本次检查。本报告保留检查时的事实，暂不能用于验收当前源码。</Notice>}
    {story.selection && <div className="jj-selected-coverage"><strong>选定 {story.selection.selected.length} 条规则</strong><span>正常对照 {story.selection.added_controls.length} 条</span><span>另有 {story.selection.omitted.length} 条规则未检查</span>{story.selection.pending_review_ids.length > 0 && <span>{story.selection.pending_review_ids.length} 项未决要求不在本次结论内</span>}</div>}
    <div className={`jj-report-layout${selectedCaseId ? ' has-inspector' : ''}`}>
      <div className="jj-report-results is-balanced">
        {story.repair_verification ? <RepairReading story={story} onInspect={open}/> : story.actions.length ? <div className="jj-result-groups" aria-label="逐项检查结果">{groups.map(group => { const items = visible.filter(action => judgement(action) === group.tone); return items.length > 0 ? <section className="jj-report-group" key={group.tone}><div className="jj-section-header"><h2>{group.title}</h2><span>{items.length} 项</span></div><div className="jj-result-list">{items.map(action => <ResultRow key={action.case_id} action={action} selected={selectedCaseId === action.case_id} compact={Boolean(selectedCaseId)} onOpen={() => open(action.case_id)}/>)}</div></section> : null; })}</div> : <Empty title="本报告没有可读取的检查项"/>}
        {!story.repair_verification && ordered.length > 10 && <div className="jj-pagination"><Button disabled={page === 1} onClick={() => setPage(value => value - 1)}>上一页</Button><span>第 {page} / {Math.ceil(ordered.length / 10)} 页</span><Button disabled={page * 10 >= ordered.length} onClick={() => setPage(value => value + 1)}>下一页</Button></div>}
      </div>
      <div className="jj-inspector-slot">{selectedCaseId && <EvidenceInspector key={story.run_id + ':' + selectedCaseId} story={story} action={caseItem} tab={tab} evidenceId={evidenceId} recordId={recordId} proofId={proofId} stepId={stepId} onClose={() => open(null)} onLocate={navigateEvidence} onError={onError}/>}</div>
    </div><details className="jj-report-scope"><summary>本次检查的适用范围</summary><div className="jj-panel"><p className="jj-small jj-muted">本报告对应检查时的规则、代码、账号、资源与读取范围。</p>{story.requirement_scope?.flatMap(scope => scope.requirements.map(item => ({...item, scope}))).map(({scope, ...item}, index) => <div className="jj-scope-item" key={index}><Badge>{item.disposition === 'IN_SCOPE' ? (story.selection?.uncovered_requirements.includes(`${scope.candidate_id}@${scope.revision}/${item.requirement_id}`) ? '本次未覆盖' : '已检查') : item.disposition === 'PREPARATION' ? '准备条件' : '本次未覆盖'}</Badge><p>{text(item.requirement)}</p></div>)}<details><summary>完整适用条件与记录引用</summary>{[...new Set([...story.claim_boundary, ...story.actions.flatMap(item => item.claim_boundary)])].map((item, index) => <p className="jj-small jj-muted" key={index}>{text(item)}</p>)}<p className="jj-small">检查编号：{story.run_id}</p>{story.change_context && <p className="jj-small">源码修改：{story.change_context.change_id}</p>}</details></div></details>
    </section>
    {assist && <AgentHandoff projectId={story.project_id} runId={story.run_id} caseId={selectedCaseId} targets={story.repair_reviews?.map(item => item.reference) ?? story.actions.filter(item => item.repair_requirement).map(item => repairReference(item.repair_requirement!))} onClose={() => setAssist(false)}/>}

  </div>;
}
function ResultRow({ action, onOpen, selected = false, compact = false }: {
    action: ActionResultStory;
    onOpen: () => void;
    selected?: boolean;
    compact?: boolean;
}) {
    const tone = judgement(action), missing = gaps(action);
    if (compact)
        return <article className="jj-result-row is-compact" data-tone={tone} data-selected={selected}><button className="jj-case-select" data-case={action.case_id} aria-pressed={selected} aria-label={`查看${subject(action)}${text(action.display_name)}的依据`} onClick={onOpen}><span className="jj-result-symbol" aria-hidden="true">{tone === 'positive' ? <CheckCircleOutlined /> : tone === 'negative' ? <ExclamationCircleOutlined /> : <QuestionCircleOutlined />}</span><span><strong>{requirement(action)}</strong><small>{owner(action)}的资源</small><span className="jj-case-outcome">{action.fact_comparison.effects.slice(0, 1).map(effect => actual(effect))}</span><span className="jj-sr-only">{judgementLabels[tone]}</span></span><ArrowRightOutlined aria-hidden="true"/></button></article>;
    return <article className="jj-result-row" data-tone={tone} data-selected={selected}>
    <div className="jj-result-reading">
      <div className="jj-result-expectation"><div className="jj-result-object"><span className="jj-result-symbol" aria-hidden="true">{tone === 'positive' ? <CheckCircleOutlined /> : tone === 'negative' ? <ExclamationCircleOutlined /> : <QuestionCircleOutlined />}</span><div><h3>{requirement(action)}</h3><p>{owner(action)}的资源{conditionLabels(action.permission.conditions).length>0?"，"+conditionLabels(action.permission.conditions).join("，"):""}</p></div></div>{tone !== 'positive' && <Badge tone={tone}>{judgementLabels[tone]}</Badge>}</div>
      <div className="jj-result-actual">{action.fact_comparison.effects.map(effect => <p key={effect.effect_id}>{actual(effect)}</p>)}{!action.fact_comparison.effects.length && <p>{text(action.judgement)}</p>}{tone === 'neutral' && action.fact_comparison.effects.length > 0 && <p className="jj-small jj-muted">{text(action.judgement)}</p>}</div>
      <Button kind="quiet" data-case={action.case_id} aria-label={`查看${subject(action)}${text(action.display_name)}的依据`} onClick={onOpen}>查看依据 <ArrowRightOutlined aria-hidden="true"/></Button>
      {tone === 'caution' && missing.length > 0 && <div className="jj-result-gap"><p>{missing[0]}</p>{missing.length > 1 && <details><summary>其余 {missing.length - 1} 项缺口</summary><ul>{missing.slice(1).map(item => <li key={item}>{item}</li>)}</ul></details>}</div>}
    </div>
  </article>;
}
function RepairReading({ story, onInspect }: {
    story: ResultStory;
    onInspect: (id: string) => void;
}) {
    const reviews = story.repair_reviews?.length ? story.repair_reviews : [{ reference: {source_run_id: story.repair_verification!.source_run_id}, verification: story.repair_verification!, comparison: story.repair_comparison ?? [] }];
    const entries = new Map<string, {row: RepairComparisonRow; roles: Set<string>; source: string; statuses: string[]}>();
    for (const review of reviews) for (const row of review.comparison) {
        const key = JSON.stringify([review.reference.source_run_id, row.source_case_id, row.after_case_id, row.match_status]);
        const existing = entries.get(key);
        if (existing) { existing.roles.add(row.role); existing.statuses.push(review.verification.status); }
        else entries.set(key, {row, roles: new Set([row.role]), source: review.reference.source_run_id, statuses: [review.verification.status]});
    }
    const rows = [...entries.values()], covered = new Set(rows.filter(item => item.row.match_status === 'MATCHED').map(item => item.row.after_case_id));
    const verified = reviews.filter(review => review.verification.status === 'VERIFIED').length;
    return <>{[{ id: 'DENY', title: '原问题' }, { id: 'NORMAL', title: '正常功能与相关回归' }].map(section => {
        const items = rows.filter(item => section.id === 'DENY' ? item.roles.has('DENY') : !item.roles.has('DENY'));
        return <section className="jj-report-group jj-repair-group" key={section.id}>
            <div className="jj-section-header"><h2>{section.title}</h2><Badge tone={verified === reviews.length ? 'positive' : 'caution'}>{section.id === 'DENY' ? `${verified} / ${reviews.length} 项已验证解决` : verified === reviews.length ? '已验证保留' : '尚未完成原题验收'}</Badge></div>
            <div className="jj-repair-cards">{items.map(({row, roles, source, statuses}, index) => <RepairResultRow key={index} row={row} roles={roles} action={row.match_status === 'MATCHED' ? story.actions.find(item => item.case_id === row.after_case_id) : undefined} sourceRunId={source} onInspect={onInspect} reviewStatus={section.id === 'DENY' ? statuses.includes('NOT_VERIFIED') ? '问题仍存在' : statuses.every(status => status === 'VERIFIED') ? '已验证解决' : '尚未确认修复' : undefined}/>)}</div>
            {!items.length && <Notice>缺少对应的检查场景，无法完成这部分验收。</Notice>}
        </section>;
    })}{story.actions.filter(item => !covered.has(item.case_id)).length > 0 && <section className="jj-report-group"><div className="jj-section-header"><h2>本轮其他检查</h2></div><div className="jj-result-cards">{story.actions.filter(item => !covered.has(item.case_id)).map(action => <ResultRow key={action.case_id} action={action} onOpen={() => onInspect(action.case_id)}/>)}</div></section>}
    {[...new Set(reviews.filter(review => ['INCONCLUSIVE', 'STALE'].includes(review.verification.status)).map(review => repairGap(review.verification.reason_codes)))].map(message => <Notice key={message}>{message}</Notice>)}</>;
}

function RepairResultRow({ row, roles, action, sourceRunId, onInspect, reviewStatus }: {
    reviewStatus?: string;
    row: RepairComparisonRow;
    roles: Set<string>;
    action?: ActionResultStory;
    sourceRunId: string;
    onInspect: (id: string) => void;
}) {
    return <article className="jj-repair-row"><div className="jj-repair-reading">
    <div className="jj-repair-requirement">
      {reviewStatus && <span className="jj-repair-status">{reviewStatus}</span>}
      <div className="jj-item-heading"><h3>{action ? requirement(action) : `${text(row.subject_label ?? '原测试账号')} ${text(row.action_label)}`}</h3>{action && judgement(action) !== 'positive' && <Badge tone={judgement(action)}>{judgementLabels[judgement(action)]}</Badge>}</div>
      <p className="jj-small jj-muted">资源归属：{action ? owner(action) : text(row.resource_owner_label ?? '原资源所有者')}</p>
    </div>
    <div className="jj-repair-outcome">
      {action ? <div className="jj-result-actual">{action.fact_comparison.effects.map(effect => <p key={effect.effect_id}>{actual(effect)}</p>)}{!action.fact_comparison.effects.length && <p>{text(action.judgement)}</p>}</div> : <Notice>{row.match_status === 'AMBIGUOUS' ? '找到多个可能对应的结果，不能确认逐项关系。' : '未找到能与原检查逐项对应的结果。'}</Notice>}
      <div className="jj-repair-links">
        {action && <Button kind="quiet" data-case={action.case_id} onClick={() => onInspect(action.case_id)}>查看本次依据</Button>}
        <details><summary>修改前的结果与复验范围</summary><div className="jj-repair-prior"><dl className="jj-facts"><div><dt>修改前</dt><dd>{({ SAFE: '符合当时规则', VULNERABLE: '存在权限问题', INCONCLUSIVE: '未能确认' })[row.before_verdict]}</dd></div><div><dt>资源归属</dt><dd>{text(row.resource_owner_label ?? '原资源所有者')}</dd></div><div><dt>核对结果</dt><dd>{row.effect_labels.map(text).join('、')}</dd></div><div><dt>检查用途</dt><dd>{[...roles].map(role => role === 'DENY' ? '原问题' : role === 'SELECTED_ALLOW' ? '正常操作对照' : '其他功能回归').join('、')}</dd></div></dl><Button kind="quiet" onClick={() => go('/reports?run_id=' + encodeURIComponent(sourceRunId) + '&case_id=' + encodeURIComponent(row.source_case_id))}>查看修改前的依据</Button></div></details>
      </div>
    </div>
  </div></article>;
}
