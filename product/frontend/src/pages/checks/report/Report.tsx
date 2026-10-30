import { useEffect, useRef, useState } from 'react';
import { ArrowLeftOutlined, ArrowRightOutlined, CheckCircleOutlined, ExclamationCircleOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import type { ActionResultStory, ResultStory } from '../../../entities/check/api/currentChecks';
import type { RepairComparisonRow } from '../../../entities/check/api/repairs';
import { Badge, Empty, Notice } from "../../../shared/ui/feedback";
import { Button } from "../../../shared/ui/actions";
import { Dialog } from "../../../shared/ui/Dialog";
import { Heading } from "../../../shared/ui/layout";
import { date, text } from '../../../shared/lib/format';
import { go } from '../../../shared/lib/navigation';
import { actual, gaps, judgement, judgementLabels, owner, requirement, repairGap, resultTitle, subject, type Tone } from '../../../entities/check/model/checks';
import { EvidenceInspector } from './EvidenceInspector';
export function Report({ story, selectedCaseId, tab, evidenceId, recordId, proofId, stepId, checkedAt, onError, readOnly = false, basePath = '/reports', returnPath = '/reports' }: {
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
}) {
    const [page, setPage] = useState(1), [assist, setAssist] = useState(false), [copied, setCopied] = useState(false), [copyError, setCopyError] = useState('');
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
    const request = `请读取界鉴中这一份检查报告，解释权限要求、实际结果与缺少的证据，并与我讨论下一步。\nproject_id=${story.project_id}\nrun_id=${story.run_id}${selectedCaseId ? '\ncase_id=' + selectedCaseId : ''}\n使用 jiejian_result_show 读取指定记录，通过 jiejian_evidence_show 核对必要证据。不要用最近一次报告替代本报告。发现问题时读取 jiejian_repair_show，保留原问题与正常业务的修复要求。先解释结果，不自动修改权限、源码、材料或提交新检查。`;
    const reportTone = story.verdict === 'PASS' ? 'positive' : story.verdict === 'BLOCK' ? 'negative' : 'caution';
    return <div ref={root} className="jj-report">
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => go(returnPath)}>全部报告</Button></div>
    <section className="jj-report-workspace" aria-label="检查报告" data-tone={reportTone}>
    <section className="jj-report-hero" data-tone={reportTone}>
      <div className="jj-report-heading"><span className="jj-report-symbol" aria-hidden="true">{reportTone === 'positive' ? <CheckCircleOutlined /> : reportTone === 'negative' ? <ExclamationCircleOutlined /> : <QuestionCircleOutlined />}</span><Heading eyebrow={story.repair_verification ? '修复复验' : '检查报告'} title={resultTitle(story)} actions={<><Button kind="quiet" onClick={() => setAssist(true)}>交给 Agent 解读</Button>{!readOnly && story.verdict === 'INCONCLUSIVE' && <Button kind="primary" onClick={resolveGap}>处理本项证据缺口</Button>}{!readOnly && story.verdict === 'BLOCK' && story.actions.some(item => item.repair_requirement) && <Button kind="primary" onClick={() => go('/permissions?repair_reference=' + encodeURIComponent(story.actions.find(item => item.repair_requirement)!.repair_requirement!.repair_fingerprint))}>查看修复要求</Button>}</>}/></div>
      <div className="jj-report-context"><div className="jj-report-metadata"><span>{story.actions.length} 项检查</span>{checkedAt && <span>{date(checkedAt)}</span>}<span>权限版本 {story.policy_epoch}</span>{story.runtime_status === 'MATCHED' && <span>运行代码已核对</span>}</div>{!readOnly && <Button kind="quiet" onClick={() => go(caseItem?.permission.intent_id ? '/permissions?rule_id=' + encodeURIComponent(caseItem.permission.intent_id) : '/permissions')}>{caseItem ? '查看这条权限规则' : '查看权限规则与问题处理'}<ArrowRightOutlined aria-hidden="true"/></Button>}</div>
    </section>
    {story.runtime_status !== 'MATCHED' && <Notice>运行代码尚未对应到本次检查。本报告保留检查时的事实，暂不能用于验收当前源码。</Notice>}
    <div className={`jj-report-layout${selectedCaseId ? ' has-inspector' : ''}${story.actions.length <= 2 && !story.repair_verification ? ' is-short-report' : ''}`}>
      <div className="jj-report-results is-balanced">
        {story.repair_verification ? <RepairReading story={story} onInspect={open}/> : story.actions.length ? <div className="jj-result-groups" aria-label="逐项检查结果">{groups.map(group => { const items = visible.filter(action => judgement(action) === group.tone); return items.length > 0 ? <section className="jj-report-group" key={group.tone}><div className="jj-section-header"><h2>{group.title}</h2><span>{items.length} 项</span></div><div className="jj-result-list">{items.map(action => <ResultRow key={action.case_id} action={action} selected={selectedCaseId === action.case_id} compact={Boolean(selectedCaseId)} onOpen={() => open(action.case_id)}/>)}</div></section> : null; })}</div> : <Empty title="本报告没有可读取的检查项"/>}
        {!story.repair_verification && ordered.length > 10 && <div className="jj-pagination"><Button disabled={page === 1} onClick={() => setPage(value => value - 1)}>上一页</Button><span>第 {page} / {Math.ceil(ordered.length / 10)} 页</span><Button disabled={page * 10 >= ordered.length} onClick={() => setPage(value => value + 1)}>下一页</Button></div>}
      </div>
      <div className="jj-inspector-slot">{selectedCaseId && <EvidenceInspector key={story.run_id + ':' + selectedCaseId} story={story} action={caseItem} tab={tab} evidenceId={evidenceId} recordId={recordId} proofId={proofId} stepId={stepId} onClose={() => open(null)} onLocate={navigateEvidence} onError={onError}/>}</div>
    </div><details className="jj-report-scope"><summary>本次检查的适用范围</summary><div className="jj-panel"><p className="jj-small jj-muted">本报告对应检查时的规则、代码、账号、资源与读取范围。</p>{story.requirement_scope?.flatMap(scope => scope.requirements).map((item, index) => <div className="jj-scope-item" key={index}><Badge>{item.disposition === 'IN_SCOPE' ? '已检查' : item.disposition === 'PREPARATION' ? '准备条件' : '本次未覆盖'}</Badge><p>{text(item.requirement)}</p></div>)}<details><summary>完整适用条件与记录引用</summary>{[...new Set([...story.claim_boundary, ...story.actions.flatMap(item => item.claim_boundary)])].map((item, index) => <p className="jj-small jj-muted" key={index}>{text(item)}</p>)}<p className="jj-small">检查编号：{story.run_id}</p>{story.change_context && <p className="jj-small">源码修改：{story.change_context.change_id}</p>}</details></div></details>
    </section>
    {assist && <Dialog title={story.verdict === 'BLOCK' ? '把问题和修复要求带回开发工具' : '请 Agent 解读这份报告'} onClose={() => { setAssist(false); setCopied(false); }} actions={dismiss => <><Button onClick={dismiss}>关闭</Button><Button kind="primary" onClick={() => void navigator.clipboard.writeText(request).then(() => { setCopied(true); setCopyError(''); }).catch(() => setCopyError('复制未完成，可以选择下方请求手动复制。'))}>{copied ? '已复制请求' : '复制请求'}</Button></>}><p>把请求粘贴到开发 Agent 的对话中。它将读取这一轮报告及证据，并保留原始检查结论。</p>{copied && <Notice tone="positive">已复制，尚未发送给 Agent。</Notice>}{copyError && <Notice>{copyError}</Notice>}<details><summary>查看将要复制的请求</summary><pre>{request}</pre></details></Dialog>}
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
        return <article className="jj-result-row is-compact" data-tone={tone} data-selected={selected}><button className="jj-case-select" data-case={action.case_id} aria-pressed={selected} aria-label={`查看${subject(action)}${text(action.display_name)}的依据`} onClick={onOpen}><span className="jj-result-symbol" aria-hidden="true">{tone === 'positive' ? <CheckCircleOutlined /> : tone === 'negative' ? <ExclamationCircleOutlined /> : <QuestionCircleOutlined />}</span><span><strong>{requirement(action)}</strong><small>{owner(action)}的资源</small><span className="jj-sr-only">{judgementLabels[tone]}</span></span><ArrowRightOutlined aria-hidden="true"/></button></article>;
    return <article className="jj-result-row" data-tone={tone} data-selected={selected}>
    <div className="jj-result-reading">
      <div className="jj-result-expectation"><div className="jj-result-object"><span className="jj-result-symbol" aria-hidden="true">{tone === 'positive' ? <CheckCircleOutlined /> : tone === 'negative' ? <ExclamationCircleOutlined /> : <QuestionCircleOutlined />}</span><div><h3>{requirement(action)}</h3><p>{owner(action)}的资源</p></div></div>{tone !== 'positive' && <Badge tone={tone}>{judgementLabels[tone]}</Badge>}</div>
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
    const verification = story.repair_verification!, rows = story.repair_comparison ?? story.actions.flatMap(item => item.repair_comparison ?? []).filter(row => row.after_run_id === story.run_id);
    const map = new Map<string, {
        row: RepairComparisonRow;
        roles: Set<string>;
    }>();
    for (const row of rows) {
        const key = JSON.stringify([row.source_case_id, row.after_case_id, row.after_run_id, row.match_status, row.before_verdict, row.after_verdict, row.action_label, row.subject_label, row.resource_owner_label, row.resource_id, row.effect_labels]);
        const existing = map.get(key);
        if (existing)
            existing.roles.add(row.role);
        else
            map.set(key, { row, roles: new Set([row.role]) });
    }
    const entries = [...map.values()], covered = new Set(rows.filter(row => row.match_status === 'MATCHED' && row.after_run_id === story.run_id).map(row => row.after_case_id));
    const sections = [{ title: '原问题解决了吗', id: 'DENY' }, { title: '正常功能保留了吗', id: 'NORMAL' }];
    return <>{sections.map(section => {
            const items = entries.filter(item => section.id === 'DENY' ? item.roles.has('DENY') : [...item.roles].some(role => role !== 'DENY'));
            const allNormal = section.id === 'NORMAL' && items.length > 0 && items.every(item => item.row.match_status === 'MATCHED' && item.row.after_run_id === story.run_id && item.row.after_verdict === 'SAFE' && story.actions.some(action => action.case_id === item.row.after_case_id && judgement(action) === 'positive'));
            return <section className="jj-report-group jj-repair-group" key={section.id}>
      <div className="jj-section-header"><h2>{section.title}</h2><Badge tone={section.id === 'DENY' && verification.status === 'VERIFIED' || allNormal ? 'positive' : 'caution'}>{section.id === 'DENY' ? verification.status === 'VERIFIED' ? '已验证解决' : '尚未通过验证' : allNormal ? '本轮功能符合要求' : '仍需核对'}</Badge></div>
      {items.length ? <div className={`jj-repair-cards${section.id === 'DENY' ? ' is-original' : ''}`}>{items.map(({ row, roles }, index) => {
                        const action = row.match_status === 'MATCHED' && row.after_run_id === story.run_id ? story.actions.find(item => item.case_id === row.after_case_id) : undefined;
                        return <RepairResultRow key={index} row={row} roles={roles} action={action} sourceRunId={verification.source_run_id} onInspect={onInspect}/>;
                    })}</div> : <Notice>缺少这部分前后对照，无法据此完成验收。</Notice>}
    </section>;
        })}{story.actions.filter(item => !covered.has(item.case_id)).length > 0 && <section className="jj-report-group"><div className="jj-section-header"><h2>本轮其他检查</h2></div><div className="jj-result-cards">{story.actions.filter(item => !covered.has(item.case_id)).map(action => <ResultRow key={action.case_id} action={action} onOpen={() => onInspect(action.case_id)}/>)}</div></section>}{['INCONCLUSIVE', 'STALE'].includes(verification.status) && <Notice>{repairGap(verification.reason_codes)}</Notice>}</>;
}
function RepairResultRow({ row, roles, action, sourceRunId, onInspect }: {
    row: RepairComparisonRow;
    roles: Set<string>;
    action?: ActionResultStory;
    sourceRunId: string;
    onInspect: (id: string) => void;
}) {
    return <article className="jj-repair-row"><div className="jj-repair-reading">
    <div className="jj-repair-requirement">
      <div className="jj-item-heading"><h3>{action ? requirement(action) : `${text(row.subject_label ?? '原测试账号')} ${text(row.action_label)}`}</h3>{action && judgement(action) !== 'positive' && <Badge tone={judgement(action)}>{judgementLabels[judgement(action)]}</Badge>}</div>
      <p className="jj-small jj-muted">资源归属：{action ? owner(action) : text(row.resource_owner_label ?? '原资源所有者')}</p>
    </div>
    <div className="jj-repair-outcome">
      {action ? <div className="jj-result-actual">{action.fact_comparison.effects.map(effect => <p key={effect.effect_id}>{actual(effect)}</p>)}{!action.fact_comparison.effects.length && <p>{text(action.judgement)}</p>}</div> : <Notice>{row.match_status === 'AMBIGUOUS' ? '找到多个可能对应的结果，不能确认逐项关系。' : '未找到能与原检查逐项对应的结果。'}</Notice>}
      <div className="jj-repair-links">
        {action && <Button kind="quiet" data-case={action.case_id} onClick={() => onInspect(action.case_id)}>查看本次依据</Button>}
        <details><summary>修改前的结果与复验范围</summary><dl className="jj-facts"><div><dt>修改前</dt><dd>{({ SAFE: '符合当时规则', VULNERABLE: '存在权限问题', INCONCLUSIVE: '未能确认' })[row.before_verdict]}</dd></div><div><dt>资源归属</dt><dd>{text(row.resource_owner_label ?? '原资源所有者')}</dd></div><div><dt>核对结果</dt><dd>{row.effect_labels.map(text).join('、')}</dd></div><div><dt>检查用途</dt><dd>{[...roles].map(role => role === 'DENY' ? '原问题' : role === 'SELECTED_ALLOW' ? '正常操作对照' : '其他功能回归').join('、')}</dd></div></dl><Button kind="quiet" onClick={() => go('/reports?run_id=' + encodeURIComponent(sourceRunId) + '&case_id=' + encodeURIComponent(row.source_case_id))}>查看修改前的依据</Button></details>
      </div>
    </div>
  </div></article>;
}
