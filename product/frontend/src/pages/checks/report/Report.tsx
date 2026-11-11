import {TaskActions} from '../../../shared/ui/layout'
import {commitReadingTransition} from '../../../shared/lib/pageTransition'
import {issueDestination} from '../../../entities/check/issueDestination'
import {TaskSurface} from '../../../shared/ui/TaskSurface'
import {IndexSelection} from '../../../shared/ui/IndexSelection'
import {Segmented} from '../../../shared/ui/Segmented'
import {conditionLabels} from '../../../entities/permission/ui/RuleConditions';
import { useEffect, useRef, useState } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined';
import ExclamationCircleOutlined from '@ant-design/icons/ExclamationCircleOutlined';
import QuestionCircleOutlined from '@ant-design/icons/QuestionCircleOutlined';
import type { ActionResultStory, ResultStory } from '../../../entities/check/api/currentChecks';
import type { RepairComparisonRow } from '../../../entities/check/api/repairs';
import { Badge, Empty, Notice, ContextNote } from "../../../shared/ui/feedback";
import {ActionLink,Button} from '../../../shared/ui/actions'
import { AgentHandoff } from '../../../entities/check/ui/AgentHandoff';
import { repairReference } from '../../../entities/check/api/repairs';
import { ObjectHeading, Heading, SectionHeading } from "../../../shared/ui/layout";

import { date, text } from '../../../shared/lib/format';
import {go,withReturnDestination,scopedPath} from '../../../shared/lib/navigation'
import { actual, gaps, judgement, judgementLabels, owner, requirement, repairGap, resultTitle, subject, type Tone } from '../../../entities/check/model/checks';
import { EvidenceInspector } from './EvidenceInspector';
import {ScenarioResults} from './ScenarioResults';
import {RoutineRunContext} from '../../../entities/check/ui/RoutineRunContext';
export function Report({ story, selectedCaseId, tab, evidenceId, recordId, proofId, stepId, checkedAt, onError, readOnly = false, basePath = '/reports', returnPath = '/reports', returnLabel = '全部检查记录', archiveName }: {
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
    archiveName?: string;
}) {
    const [page, setPage] = useState(1), [assist, setAssist] = useState(false), [resultFilter,setResultFilter]=useState<Tone|'all'>('all');
    const trigger = useRef<HTMLElement | null>(null), root = useRef<HTMLDivElement>(null), scroll = useRef(0);
    const caseItem = story.actions.find(item => item.case_id === selectedCaseId);
    const inlineReading=!story.repair_verification&&story.actions.length<=4&&!story.actions.some(action=>action.scenario_context);
    const detailReading=Boolean(selectedCaseId&&['trace','records'].includes(tab??''));
    const gapAction = caseItem ?? story.actions.find(item => judgement(item) === 'caution');
    const resolveGap = () => { if (!gapAction) return; const surface = gapAction.fact_comparison.http_surface; const focus = gapAction.fact_comparison.verified_actual_identity.verification_status !== 'MATCH' ? 'identity' : !surface.recovery_verified ? 'recovery' : 'evidence'; go('/preparation?' + new URLSearchParams({ action_id: gapAction.action_id, focus, return_to: address('run_id=' + story.run_id + '&case_id=' + gapAction.case_id), ...(gapAction.permission.intent_id ? { rule_id: gapAction.permission.intent_id } : {}), ...(story.change_context ? { change_id: story.change_context.change_id } : {}) })); };
    // 依据、页内分类与关闭仍属于同一份报告，必须保留发起它的比较页或业务对象。
    const address = (query: string) => withReturnDestination(basePath + (basePath.includes('?') ? '&' : '?') + query, returnPath);
    const here=address('run_id='+encodeURIComponent(story.run_id)+(selectedCaseId?'&case_id='+encodeURIComponent(selectedCaseId):''))
    const open = (id: string | null) => { if (id) {
        trigger.current = document.activeElement as HTMLElement;
        if (!selectedCaseId) scroll.current = window.scrollY;
    } go(address(`run_id=${encodeURIComponent(story.run_id)}${id ? '&case_id=' + encodeURIComponent(id) : ''}`)); };
    useEffect(() => { if (!selectedCaseId && trigger.current) {
        const original = trigger.current, fresh = original.isConnected ? original : root.current?.querySelector<HTMLElement>('[data-case="' + original.dataset.case + '"]');
        fresh?.focus({ preventScroll: true });
        window.scrollTo({ top: scroll.current, behavior: 'instant' });
    } }, [selectedCaseId]);
    const groups: Array<{
        tone: Tone;
        title: string;
    }> = [{ tone: 'negative', title: '不符合规则的结果' }, { tone: 'caution', title: '证据不足的结果' }, { tone: 'neutral', title: '其他检查结果' }, { tone: 'positive', title: '符合规则的结果' }];
    const ordered = [...story.actions].sort((a, b) => groups.findIndex(item => item.tone === judgement(a)) - groups.findIndex(item => item.tone === judgement(b)));
    const requirementCounts = new Map<string, number>();
    for (const action of ordered) requirementCounts.set(requirement(action), (requirementCounts.get(requirement(action)) ?? 0) + 1);
    const filtered=ordered.filter(action=>resultFilter==='all'||judgement(action)===resultFilter);
    const visible = filtered.slice((page - 1) * 10, page * 10);
    const navigateEvidence = (kind: string, evidence?: string, record?: string, proof?: string, step?: string) => { if (!selectedCaseId)
        return; const query = new URLSearchParams({ run_id: story.run_id, case_id: selectedCaseId, tab: kind }); if (evidence)
        query.set('evidence_id', evidence); if (record)
        query.set('record_id', record); if (proof)
        query.set('proof_id', proof); if (step ?? stepId)
        query.set('step_id', (step ?? stepId)!); go(address(query.toString())); };
    const reportTone = story.verdict === 'PASS' ? 'positive' : story.verdict === 'BLOCK' ? 'negative' : 'caution';
    // 深入记录时保留同一报告状态所有者，退出总览而不丢失原筛选、页码与回程。
    if(detailReading&&caseItem)return <div ref={root} className="jj-report"><TaskSurface width="wide" title={tab==='trace'?'操作经过':'证明记录'} context={<>{requirement(caseItem)} · {caseItem.fact_comparison.resource_id}</>} onBack={()=>navigateEvidence('facts')} backLabel="返回本项业务结果"><EvidenceInspector standalone key={story.run_id+':'+selectedCaseId} story={story} action={caseItem} tab={tab} evidenceId={evidenceId} recordId={recordId} proofId={proofId} stepId={stepId} comparison={<RepairPrior story={story} caseId={selectedCaseId!}/>} onClose={()=>navigateEvidence('facts')} onLocate={navigateEvidence} onError={onError}/></TaskSurface></div>;
    return <div ref={root} className="jj-report">
    <div className="jj-back-link jj-report-navigation"><ActionLink navigationScope="page" href={'#'+scopedPath(returnPath)} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}{returnLabel}</ActionLink>{archiveName&&<ActionLink href="#/environment">返回官方示例<ArrowRightOutlined aria-hidden="true"/></ActionLink>}</div>
    <section className="jj-report-workspace" aria-label="检查报告" data-tone={reportTone}>
    <div className="jj-report-overview"><section className="jj-report-hero" data-tone={reportTone}>
      <div data-milestone-part="heading" className="jj-report-heading"><Heading titleIcon={<span className="jj-report-symbol" aria-hidden="true">{reportTone === 'positive' ? <CheckCircleOutlined /> : reportTone === 'negative' ? <ExclamationCircleOutlined /> : <QuestionCircleOutlined />}</span>} eyebrow={story.repair_verification?.verification_scope==='EXTERNAL_OBSERVATION'?'外部应用再次验证':story.repair_verification ? '修复复验' : story.selection ? '选定规则检查' : '检查报告'} title={resultTitle(story)}/></div>
      <div data-milestone-part="facts" className="jj-report-context"><div className="jj-report-metadata">{archiveName&&<span className="jj-archive-label"><Badge>已归档</Badge>{text(archiveName)}</span>}<span>{story.actions.length} 项检查</span>{checkedAt && <span>{date(checkedAt)}</span>}<span>权限版本 {story.policy_epoch}</span>{story.runtime_status === 'MATCHED' && <span>运行代码已核对</span>}</div><RoutineRunContext projectId={story.project_id} routine={story.routine} environment={story.environment} origin={here} readOnly={readOnly}/>{story.selection && <div className="jj-selected-coverage" aria-label="本次检查范围"><strong>选定 {story.selection.selected.length} 条规则</strong><span>正常对照 {story.selection.added_controls.length} 条</span>{story.selection.omitted.length>0&&<span>另有 {story.selection.omitted.length} 条规则未检查</span>}{story.selection.pending_review_ids.length > 0 && <span>{story.selection.pending_review_ids.length} 项未决要求不在本次结论内</span>}</div>}{!readOnly && <ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination(caseItem?.permission.intent_id ? '/permissions?rule_id=' + encodeURIComponent(caseItem.permission.intent_id) : '/permissions',here))} kind="quiet">{caseItem ? '查看这条权限规则' : '权限规则'}<ArrowRightOutlined aria-hidden="true"/></ActionLink>}</div>
    </section>
    {story.repair_verification?.verification_scope==='EXTERNAL_OBSERVATION'?<ContextNote label="本次验证的适用范围"><p>本次已核对原问题和正常业务对照的实际行为；源码修改与部署版本的对应关系尚未独立核验。</p>{story.external_recheck&&<details><summary>本次部署声明</summary><p>{text(story.external_recheck.deployment_statement)}</p></details>}</ContextNote>:story.runtime_status !== 'MATCHED'&&<ContextNote label="运行代码核对情况"><p><strong>运行代码尚未核对。</strong>本报告记录实际观察结果；确认源码修复有效，还需核对对应的运行版本。</p></ContextNote>}
    </div>
    {!story.repair_verification&&story.actions.length>4&&<Segmented label="按检查结果筛选" className="jj-report-summary" value={resultFilter} items={([{tone:'all',label:'全部结果'},{tone:'negative',label:'不符合规则'},{tone:'caution',label:'证据不足'},{tone:'positive',label:'符合规则'}] as const).filter(item=>item.tone==='all'||ordered.some(action=>judgement(action)===item.tone)).map(item=>({value:item.tone,tone:item.tone,label:<><strong>{item.tone==='all'?ordered.length:ordered.filter(action=>judgement(action)===item.tone).length}</strong><span>{item.label}</span></>}))} onValueChange={value=>{if(selectedCaseId){setResultFilter(value);setPage(1);open(null)}else commitReadingTransition(root.current?.querySelector('.jj-report-results')??null,()=>{setResultFilter(value);setPage(1)})}}/>}
    <div data-milestone-part="results" className={`jj-report-layout${selectedCaseId&&!inlineReading ? ' has-inspector' : ''}`} data-detail-reading={detailReading||undefined}>
      <div className="jj-report-results is-balanced" hidden={detailReading}>
        {story.repair_verification ? <RepairReading story={story} selectedCaseId={selectedCaseId} onInspect={open}/> : story.actions.some(action=>action.scenario_context) ? <ScenarioResults actions={visible} selected={selectedCaseId} onOpen={open}/> : story.actions.length ? <div className="jj-result-groups" aria-label="逐项检查结果">{groups.map(group => { const items = visible.filter(action => judgement(action) === group.tone); return items.length > 0 ? <section className="jj-report-group" key={group.tone}><SectionHeading title={group.title} appearance="group" meta={items.length+' 项'}/><IndexSelection className="jj-result-list" identity={selectedCaseId??""}>{items.map(action => <div className="jj-result-entry" key={action.case_id}><ResultRow action={action} selected={selectedCaseId === action.case_id} compact={Boolean(selectedCaseId)&&!inlineReading} compactContext={(requirementCounts.get(requirement(action)) ?? 0) > 1 ? owner(action) + "的资源" : undefined} onOpen={() => open(selectedCaseId===action.case_id&&inlineReading?null:action.case_id)}/>{inlineReading&&selectedCaseId===action.case_id&&<EvidenceInspector summaryPresented story={story} action={action} tab={tab} evidenceId={evidenceId} recordId={recordId} proofId={proofId} stepId={stepId} onClose={()=>open(null)} onLocate={navigateEvidence} onError={onError}/>}</div>)}</IndexSelection></section> : null; })}</div> : <Empty title="本报告没有可读取的检查项">可返回检查记录核对运行与发布状态；没有逐项结果不表示检查通过。</Empty>}
        {!story.repair_verification&&story.actions.length>0&&!filtered.length&&<Empty title="本次没有这类结果" action={<Button onClick={()=>setResultFilter('all')}>查看全部结果</Button>}/>}
        {!story.repair_verification && filtered.length > 10 && <div className="jj-pagination"><Button disabled={page === 1} onClick={() => setPage(value => value - 1)}>上一页</Button><span>第 {page} / {Math.ceil(filtered.length / 10)} 页</span><Button disabled={page * 10 >= filtered.length} onClick={() => setPage(value => value + 1)}>下一页</Button></div>}
      </div>
      <div className="jj-inspector-slot">{selectedCaseId && (!inlineReading||!caseItem) && <EvidenceInspector key={story.run_id + ':' + selectedCaseId} story={story} action={caseItem} tab={tab} evidenceId={evidenceId} recordId={recordId} proofId={proofId} stepId={stepId} comparison={<RepairPrior story={story} caseId={selectedCaseId}/>} onClose={() => open(null)} onLocate={navigateEvidence} onError={onError}/>}</div>
    </div><details className="jj-report-scope"><summary>本次检查的适用范围</summary><div className="jj-panel"><p className="jj-small jj-muted">本报告对应检查时的规则、代码、账号、资源与读取范围。</p>{story.requirement_scope?.flatMap(scope => scope.requirements.map(item => ({...item, scope}))).map(({scope, ...item}, index) => <div className="jj-scope-item" key={index}><Badge>{item.disposition === 'IN_SCOPE' ? (story.selection?.uncovered_requirements.includes(`${scope.candidate_id}@${scope.revision}/${item.requirement_id}`) ? '本次未覆盖' : '已检查') : item.disposition === 'PREPARATION' ? '准备条件' : '本次未覆盖'}</Badge><p>{text(item.requirement)}</p></div>)}<details><summary>完整适用条件与记录引用</summary>{[...new Set([...story.claim_boundary, ...story.actions.flatMap(item => item.claim_boundary)])].map((item, index) => <p className="jj-small jj-muted" key={index}>{text(item)}</p>)}<p className="jj-small">检查编号：{story.run_id}</p>{story.change_context && <p className="jj-small">源码修改：{story.change_context.change_id}</p>}</details></div></details>
    <TaskActions separated data-milestone-part="actions" aria-label="处理本次结果"><><Button kind="quiet" onClick={() => setAssist(true)}>交给 Agent 解读</Button>{!readOnly && story.verdict === 'PASS' && <ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/reports?view=plan&resume_run='+encodeURIComponent(story.run_id),here))} kind="primary">沿用本次范围继续检查</ActionLink>}{!readOnly && story.verdict === 'INCONCLUSIVE' && <Button kind="primary" onClick={resolveGap}>处理证据缺口</Button>}{!readOnly && story.verdict === 'BLOCK' && story.actions.some(item => item.repair_requirement) && <ActionLink navigationScope="page" href={'#'+scopedPath(caseItem?.repair_requirement?issueDestination(caseItem.repair_requirement,here,{section:'repair',run_id:story.run_id,change_id:story.change_context?.change_id}):withReturnDestination('/issues',here))} kind="primary">处理权限问题</ActionLink>}</></TaskActions>
    </section>
    {assist && <AgentHandoff projectId={story.project_id} runId={story.run_id} caseId={selectedCaseId} targets={story.repair_reviews?.map(item => item.reference) ?? story.actions.filter(item => item.repair_requirement).map(item => repairReference(item.repair_requirement!))} onClose={() => setAssist(false)}/>}

  </div>;
}
function ResultRow({ action, onOpen, selected = false, compact = false, compactContext }: {
    action: ActionResultStory;
    onOpen: () => void;
    selected?: boolean;
    compact?: boolean;
    compactContext?: string;
}) {
    const tone = judgement(action), missing = gaps(action);
    if (compact)
        return <article className="jj-result-row is-compact" data-tone={tone} data-selected={selected}><button className="jj-case-select jj-index-item" data-case={action.case_id} aria-pressed={selected} aria-label={`查看${subject(action)}${text(action.display_name)}的依据`} onClick={onOpen}><span className="jj-result-symbol" aria-hidden="true">{tone === 'positive' ? <CheckCircleOutlined /> : tone === 'negative' ? <ExclamationCircleOutlined /> : <QuestionCircleOutlined />}</span><span><strong>{requirement(action)}</strong>{compactContext && <small>{compactContext}</small>}<span className="jj-sr-only">{judgementLabels[tone]}</span></span><ArrowRightOutlined aria-hidden="true"/></button></article>;
    return <article className="jj-result-row" data-tone={tone} data-selected={selected}>
    <div className="jj-result-reading">
      <div className="jj-result-expectation"><ObjectHeading level={3} title={requirement(action)} icon={<span className="jj-result-symbol">{tone === 'positive' ? <CheckCircleOutlined /> : tone === 'negative' ? <ExclamationCircleOutlined /> : <QuestionCircleOutlined />}</span>} status={tone === 'caution' && <Badge tone={tone}>{judgementLabels[tone]}</Badge>} description={<span className="jj-small">{owner(action)}的资源{conditionLabels(action.permission.conditions).length>0?"，"+conditionLabels(action.permission.conditions).join("，"):""}</span>}/></div>
      <div className="jj-result-actual">{action.fact_comparison.effects.map(effect => <p key={effect.effect_id}>{actual(effect)}</p>)}{!action.fact_comparison.effects.length && <p>{text(action.judgement)}</p>}{tone === 'neutral' && action.fact_comparison.effects.length > 0 && <p className="jj-small jj-muted">{text(action.judgement)}</p>}</div>
      <Button kind="quiet" data-case={action.case_id} aria-label={`查看${subject(action)}${text(action.display_name)}的依据`} onClick={onOpen}>查看依据 <ArrowRightOutlined aria-hidden="true"/></Button>
      {tone === 'caution' && missing.length > 0 && <div className="jj-result-gap"><p>{missing[0]}</p>{missing.length > 1 && <details><summary>其余 {missing.length - 1} 项缺口</summary><ul>{missing.slice(1).map(item => <li key={item}>{item}</li>)}</ul></details>}</div>}
    </div>
  </article>;
}
type RepairEntry = {row: RepairComparisonRow; roles: Set<string>; source: string; statuses: string[]};
function repairEntries(story: ResultStory) {
    const reviews = story.repair_reviews?.length ? story.repair_reviews : story.repair_verification ? [{reference: {source_run_id: story.repair_verification.source_run_id}, verification: story.repair_verification, comparison: story.repair_comparison ?? []}] : [];
    const entries = new Map<string, RepairEntry>();
    // 同一正常场景可服务多个修复目标；合并展示，仍保留原检查身份和每份验收状态。
    for (const review of reviews) for (const row of review.comparison) {
        const key = JSON.stringify([review.reference.source_run_id, row.source_case_id, row.after_case_id, row.match_status]);
        const existing = entries.get(key);
        if (existing) { existing.roles.add(row.role); existing.statuses.push(review.verification.status); }
        else entries.set(key, {row, roles: new Set([row.role]), source: review.reference.source_run_id, statuses: [review.verification.status]});
    }
    return {rows: [...entries.values()], reviews};
}
function repairResult(entry: RepairEntry, action?: ActionResultStory, external=false): {label: string; tone: Tone} {
    if (!action) return {label: entry.row.match_status === 'AMBIGUOUS' ? '对应关系不明确' : '缺少对应场景', tone: 'caution'};
    if (judgement(action) !== 'positive') return {label: judgement(action) === 'negative' ? (entry.roles.has('DENY') ? '问题仍存在' : '正常功能异常') : '依据不足', tone: judgement(action)};
    if (!entry.roles.has('DENY')) return {label: '正常功能保留', tone: 'positive'};
    return entry.statuses.every(status => status === 'VERIFIED') ? {label: external?'本次符合要求':'已解决', tone: 'positive'} : {label: '尚未确认修复', tone: 'caution'};
}
const beforeLabels = {SAFE: '符合当时规则', VULNERABLE: '存在权限问题', INCONCLUSIVE: '当时未能确认'};
function RepairReading({story, selectedCaseId, onInspect}: {story: ResultStory; selectedCaseId: string | null; onInspect: (id: string) => void}) {
    const {rows, reviews} = repairEntries(story);
    const covered = new Set(rows.filter(item => item.row.match_status === 'MATCHED').map(item => item.row.after_case_id));
    const gaps = [...new Set(reviews.filter(review => ['INCONCLUSIVE', 'STALE'].includes(review.verification.status)).map(review => repairGap(review.verification.reason_codes)))];
    return <>{[{id: 'DENY', title: '原权限问题'}, {id: 'NORMAL', title: '正常功能'}].map(section => {
        const items = rows.filter(item => section.id === 'DENY' ? item.roles.has('DENY') : !item.roles.has('DENY'));
        return <section className="jj-report-group jj-repair-group" key={section.id}>
            <SectionHeading title={section.title} appearance="group" meta={items.length+' 项'}/>
            {items.length ? <IndexSelection className="jj-repair-cards" identity={selectedCaseId??""}>{selectedCaseId ? items.map((entry, index) => {
                const action = entry.row.match_status === 'MATCHED' ? story.actions.find(item => item.case_id === entry.row.after_case_id) : undefined;
                const result = repairResult(entry, action,story.repair_verification?.verification_scope==='EXTERNAL_OBSERVATION');
                return <article className="jj-result-row is-compact" data-selected={selectedCaseId === action?.case_id} data-tone={result.tone} key={index}>
                    {action ? <button className="jj-case-select jj-repair-select jj-index-item" data-case={action.case_id} aria-pressed={selectedCaseId === action.case_id} aria-label={'查看' + requirement(action) + '的复验依据'} onClick={() => onInspect(action.case_id)}><span className="jj-result-symbol" aria-hidden="true">{result.tone === 'positive' ? <CheckCircleOutlined/> : result.tone === 'negative' ? <ExclamationCircleOutlined/> : <QuestionCircleOutlined/>}</span><span><strong>{requirement(action)}</strong><span className="jj-repair-status" data-tone={result.tone}>{result.label}</span></span><ArrowRightOutlined aria-hidden="true"/></button> : <div className="jj-repair-unmatched"><strong>{text(entry.row.subject_label ?? '原测试账号')}{text(entry.row.action_label)}</strong><p>{result.label}</p></div>}
                </article>;
            }) : <div className="jj-scroll-table"><table className="jj-content-table jj-repair-table"><thead><tr><th scope="col">核对事项</th><th scope="col" className="jj-table-state">修改前</th><th scope="col" className="jj-table-state">本次复验</th><th scope="col" className="jj-table-actions"><span className="jj-sr-only">依据</span></th></tr></thead><tbody>{items.map((entry, index) => {
                const action = entry.row.match_status === 'MATCHED' ? story.actions.find(item => item.case_id === entry.row.after_case_id) : undefined, result = repairResult(entry, action,story.repair_verification?.verification_scope==='EXTERNAL_OBSERVATION');
                return <tr key={index}><td><strong>{action ? requirement(action) : text(entry.row.subject_label ?? '原测试账号') + text(entry.row.action_label)}</strong><small>{action ? owner(action) : text(entry.row.resource_owner_label ?? '原资源所有者')}的资源</small></td><td className="jj-table-state">{beforeLabels[entry.row.before_verdict]}</td><td className="jj-table-state"><Badge tone={result.tone}>{result.label}</Badge></td><td className="jj-table-actions">{action && <Button kind="quiet" data-case={action.case_id} aria-label={'查看' + requirement(action) + '的复验依据'} onClick={() => onInspect(action.case_id)}>查看依据<ArrowRightOutlined aria-hidden="true"/></Button>}</td></tr>;
            })}</tbody></table></div>}</IndexSelection> : <Notice tone="caution">缺少对应的检查场景，无法完成这部分验收。</Notice>}
        </section>;
    })}{story.actions.filter(item => !covered.has(item.case_id)).length > 0 && <section className="jj-report-group"><SectionHeading title="本轮其他检查" appearance="group"/><div className="jj-result-cards">{story.actions.filter(item => !covered.has(item.case_id)).map(action => <ResultRow key={action.case_id} action={action} onOpen={() => onInspect(action.case_id)}/>)}</div></section>}
    {gaps.length>0&&<Notice tone="caution" title="复验仍需核对"><ul>{gaps.map(message=><li key={message}>{message}</li>)}</ul></Notice>}</>;
}
function RepairPrior({story, caseId}: {story: ResultStory; caseId: string}) {
    const entries = repairEntries(story).rows.filter(item => item.row.match_status === 'MATCHED' && item.row.after_case_id === caseId);
    if (!entries.length) return null;
    return <details className="jj-repair-prior"><summary>修改前的结果与原检查</summary>{entries.map(({row, source, roles}, index) => <div key={index}><dl className="jj-facts"><div><dt>修改前</dt><dd>{beforeLabels[row.before_verdict]}</dd></div><div><dt>核对结果</dt><dd>{row.effect_labels.map(text).join('、')}</dd></div><div><dt>检查用途</dt><dd>{[...roles].map(role => role === 'DENY' ? '原问题' : role === 'SELECTED_ALLOW' ? '正常操作对照' : '其他功能回归').join('、')}</dd></div></dl><ActionLink navigationScope="page" href={'#'+scopedPath('/reports?run_id=' + encodeURIComponent(source) + '&case_id=' + encodeURIComponent(row.source_case_id))} kind="quiet">查看原检查依据<ArrowRightOutlined aria-hidden="true"/></ActionLink></div>)}</details>;
}
