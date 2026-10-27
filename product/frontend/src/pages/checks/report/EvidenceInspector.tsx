import { useEffect, useId, useRef, useState } from 'react';
import { CloseOutlined, ArrowLeftOutlined, ArrowRightOutlined, CheckOutlined, QuestionOutlined } from '@ant-design/icons';
import { currentChecksApi as api, type ActionResultStory, type EvidenceRecordIndex, type ResultStory, type StoryTraceEvent } from '../../../entities/check/api/currentChecks';
import { ApiError } from '../../../shared/api/http';
import { assertProject } from '../../../shared/model/page';
import { text } from '../../../shared/lib/format';
import { useRead } from '../../../shared/lib/useRead';
import { Badge, Empty, ErrorNote, Loading } from "../../../shared/ui/feedback";
import { Button } from "../../../shared/ui/actions";
import { Tabs } from "../../../shared/ui/Tabs";
import { Choice } from "../../../shared/ui/Choice";
import { actual, gaps, judgement, judgementLabels, owner, requirement } from '../../../entities/check/model/checks';
type Props = {
    story: ResultStory;
    action?: ActionResultStory;
    tab: string | null;
    evidenceId: string | null;
    recordId: string | null;
    proofId?: string | null;
    stepId?: string | null;
    onClose: () => void;
    onLocate: (tab: string, evidence?: string, record?: string, proof?: string, step?: string) => void;
    onError: (error: unknown) => void;
};
export function EvidenceInspector({ story, action, tab, evidenceId, recordId, proofId, stepId, onClose, onLocate }: Props) {
    const heading = useRef<HTMLHeadingElement>(null), tabId = useId();
    const [event, setEvent] = useState<StoryTraceEvent>();
    useEffect(() => { const node = heading.current; node?.focus({ preventScroll: true }); const panel = node?.closest('.jj-evidence-inspector'), top = panel?.getBoundingClientRect().top; if (top !== undefined && (top < 84 || top > innerHeight - 180))
        window.scrollTo({ top: window.scrollY + top - 92, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }); }, []);
    if (!action)
        return <aside className="jj-evidence-inspector"><Empty title="本报告没有这项检查" action={<Button onClick={onClose}>返回本次结果</Button>}/></aside>;
    const currentTab = ['trace', 'records'].includes(tab ?? '') ? tab : 'facts', tone = judgement(action), missing = gaps(action);
    const openRecord = (id: string, proof?: string) => { setEvent(undefined); onLocate('records', id, undefined, proof, ''); };
    const evidenceSources = action.proof_coverage?.filter(item => item.required_level === 'VERDICT_REQUIRED') ?? [];
    return <aside className="jj-evidence-inspector" aria-label="检查依据" onKeyDown={e => { if (e.key === 'Escape') {
        e.stopPropagation();
        if (evidenceId)
            onLocate('records');
        else
            onClose();
    } }}><header className="jj-inspector-header"><span>检查依据</span><Button kind="quiet" aria-label="关闭检查依据" onClick={onClose} icon={<CloseOutlined aria-hidden="true"/>}/></header><div className="jj-inspector-title"><Badge tone={tone}>{judgementLabels[tone]}</Badge><h2 ref={heading} tabIndex={-1}>{text(action.display_name)}</h2><p>{requirement(action)}</p></div><Tabs className="jj-inspector-tabs" label="依据视图" value={currentTab ?? 'facts'} idPrefix={tabId} panelId={tabId + '-panel'} items={[{ value: 'facts', label: '业务结果' }, { value: 'trace', label: '操作经过' }, { value: 'records', label: '证明记录' }]} onValueChange={onLocate}/><div className="jj-inspector-content" role="tabpanel" id={tabId + '-panel'} aria-labelledby={tabId + '-' + currentTab} key={currentTab}>
    {currentTab === 'facts' && <><section className="jj-inspector-section"><h3>实际结果</h3>{action.fact_comparison.effects.map(effect => <p key={effect.effect_id}>{actual(effect)}</p>)}</section>{tone === 'caution' && missing.length > 0 && <section className="jj-inspector-section"><h3>还缺哪些依据</h3><ul className="jj-gap-list">{missing.map(item => <li key={item}>{item}</li>)}</ul></section>}<section className="jj-inspector-section"><h3>核对对象</h3><dl className="jj-facts"><div><dt>实际账号</dt><dd>{action.fact_comparison.verified_actual_identity.verification_status === 'MATCH' ? text(action.fact_comparison.verified_actual_identity.label ?? '账号已独立确认') : action.fact_comparison.verified_actual_identity.verification_status === 'MISMATCH' ? '与计划不一致' : '尚未确认'}</dd></div><div><dt>资源归属</dt><dd>{owner(action)}</dd></div><div><dt>测试资源</dt><dd>{action.fact_comparison.resource_id ?? '未提供资源编号'}</dd></div></dl></section><section className="jj-inspector-section"><h3>判断所用的记录</h3>{evidenceSources.length ? evidenceSources.map((source, index) => <div className="jj-proof-entry" key={source.proof_fingerprint + index}><strong>{text(source.business_label)}</strong><span>{text(source.source_label)}</span>{source.evidence_refs.length > 0 ? <Button kind="quiet" onClick={() => openRecord(source.evidence_refs[0], source.proof_fingerprint)}>打开证明记录</Button> : <p className="jj-small jj-muted">没有可读取的发布记录</p>}</div>) : action.decisive_proof_chain.map((item, index) => <div className="jj-proof-entry" key={index}><strong>{text(item.source_label)}</strong>{item.evidence_refs.length > 0 && <Button kind="quiet" onClick={() => openRecord(item.evidence_refs[0])}>打开证明记录</Button>}</div>)}</section><details><summary>接口响应与其他检查条件</summary><dl className="jj-facts"><div><dt>接口响应</dt><dd>{action.fact_comparison.http_surface.http_status ?? '未取得状态码'}</dd></div><div><dt>请求对应</dt><dd>{action.fact_comparison.http_surface.run_correlated ? '已确认' : '未确认'}</dd></div><div><dt>资源对应</dt><dd>{action.fact_comparison.http_surface.resource_correlated ? '已确认' : '未确认'}</dd></div><div><dt>操作前状态</dt><dd>{action.fact_comparison.http_surface.baseline_trusted ? '已核对' : '未确认'}</dd></div><div><dt>操作后恢复</dt><dd>{action.fact_comparison.http_surface.recovery_verified ? '满足恢复要求' : '未确认'}</dd></div></dl><p className="jj-small jj-muted">接口响应仅作为过程信息，业务结果依据独立记录判断。</p></details></>}
    {currentTab === 'trace' && <TraceTimeline action={action} selectedId={stepId} onSelect={id => onLocate('trace', undefined, undefined, undefined, id)} onRead={item => { setEvent(item); onLocate('records', action.execution_path!.evidence_refs[0], undefined, undefined, item.event_id); }}/>}
    {currentTab === 'records' && (evidenceId ? <PublishedRecords story={story} action={action} evidenceId={evidenceId} recordId={recordId} proofId={proofId} selectedEvent={stepId ? action.execution_path?.events.find(item => item.event_id === stepId) : event} onLocate={onLocate}/> : <><h3>业务证明与辅助记录</h3>{[...new Set([...action.decisive_proof_chain.flatMap(item => item.evidence_refs), ...action.evidence_explanations.flatMap(item => item.evidence_refs), ...(action.proof_coverage ?? []).flatMap(item => [...item.evidence_refs, ...item.supporting_evidence_refs])])].map((id, index) => <button className="jj-record-link" key={id} onClick={() => openRecord(id)}><span>已发布记录 {index + 1}</span><span>查看内容</span></button>)}</>)}
  </div></aside>;
}
const traceLabels: Record<StoryTraceEvent['kind'], string> = { ENTRY: '收到业务请求', IDENTITY: '确认操作身份', AUTHORIZATION: '执行权限判断', PERSISTENT_EFFECT: '提交业务数据', MESSAGE: '发出业务消息', DELEGATION: '调用下游服务', FINAL_EFFECT: '形成业务结果', RECOVERY: '恢复业务状态' };
function TraceTimeline({ action, selectedId, onSelect, onRead }: {
    action: ActionResultStory;
    selectedId?: string | null;
    onSelect: (id: string) => void;
    onRead: (event: StoryTraceEvent) => void;
}) {
    const path = action.execution_path, detailId = useId();
    if (!path?.events.length)
        return <Empty title="本次未采集到操作路径"/>;
    const selected = selectedId ? path.events.find(item => item.event_id === selectedId) : path.events.find(item => item.kind === 'AUTHORIZATION') ?? path.events[0];
    if (!selected)
        return <Empty title="这个步骤不在本次操作路径中" action={<Button onClick={() => onSelect(path.events[0].event_id)}>查看操作路径</Button>}/>;
    const index = path.events.indexOf(selected);
    const prior = (ids: string[]) => ids.length ? ids.map(id => { const position = path.events.findIndex(event => event.event_id === id); return position < 0 ? '未采集到对应步骤' : `第 ${position + 1} 步`; }).join('，') : '未声明前序';
    return <section className="jj-operation-path" aria-label="操作经过">
    <div className="jj-trace-summary"><Badge tone={path.complete ? 'neutral' : 'caution'}>{path.complete ? '完整路径' : '路径不完整'}</Badge><span>{path.events.length} 个步骤</span></div>
    {!path.complete && <p className="jj-small jj-muted">仅展示已采集的步骤。</p>}
    <div className="jj-step-workspace">
      <div className="jj-step-mobile"><Choice aria-label="查看执行步骤" value={selected.event_id} onValueChange={onSelect}>{path.events.map((item, position) => <option key={item.event_id} value={item.event_id}>第 {position + 1} 步　{traceLabels[item.kind]}</option>)}</Choice></div>
      <ol className="jj-operation-steps" aria-label="执行步骤">{path.events.map((item, position) => <li key={item.event_id}>
        <button className="jj-step-select" aria-current={selected.event_id === item.event_id ? 'step' : undefined} aria-controls={detailId} onClick={() => onSelect(item.event_id)}>
          <span className="jj-trace-order" aria-hidden="true">{position + 1}</span><strong>{traceLabels[item.kind]}</strong><ArrowRightOutlined aria-hidden="true"/>
        </button>
      </li>)}</ol>
      <article className="jj-step-reading" id={detailId} aria-labelledby={detailId + '-title'} key={selected.event_id}>
        <header><div><span className="jj-small jj-muted">第 {index + 1} 步</span><h3 id={detailId + '-title'}>{traceLabels[selected.kind]}</h3></div>{selected.authorization_decision && <Badge tone={selected.authorization_decision === 'ALLOW' ? 'positive' : 'negative'}>{selected.authorization_decision === 'ALLOW' ? '允许' : '拒绝'}</Badge>}</header>
        <dl><div><dt>执行组件</dt><dd>{text(selected.source_component)}</dd></div><div><dt>记录位置</dt><dd>{text(selected.source_location)}</dd></div><div><dt>直接前序</dt><dd>{prior(selected.parent_event_ids)}</dd></div></dl>
        {path.evidence_refs.length > 0 && <footer><Button kind="quiet" aria-label={`查看第 ${index + 1} 步的记录`} onClick={() => onRead(selected)}>查看本步记录<ArrowRightOutlined aria-hidden="true"/></Button></footer>}
      </article>
    </div>
    <span className="jj-sr-only" role="status">当前查看第 {index + 1} 步，{traceLabels[selected.kind]}</span>
  </section>;
}
function PublishedRecords({ story, action, evidenceId, recordId, proofId, selectedEvent, onLocate }: {
    story: ResultStory;
    action: ActionResultStory;
    evidenceId: string;
    recordId: string | null;
    proofId?: string | null;
    selectedEvent?: StoryTraceEvent;
    onLocate: Props['onLocate'];
}) {
    const allowed = new Set([...action.decisive_proof_chain.flatMap(item => item.evidence_refs), ...action.evidence_explanations.flatMap(item => item.evidence_refs), ...(action.proof_coverage ?? []).flatMap(item => [...item.evidence_refs, ...item.supporting_evidence_refs]), ...(action.execution_path?.evidence_refs ?? [])]);
    const bundle = useRead(`evidence:${story.project_id}:${story.run_id}:${action.case_id}:${evidenceId}`, async () => {
        if (!allowed.has(evidenceId))
            throw new ApiError('ARTIFACT_MANIFEST', '这份记录未被本项检查引用。');
        const result = await api.evidenceBundle(story.project_id, story.run_id, action.case_id, [evidenceId]);
        assertProject(result.project_id, story.project_id);
        if (result.run_id !== story.run_id || result.case_id !== action.case_id || result.items.length !== 1)
            throw new Error('证据归属不一致，已停止展示。');
        const item = result.items[0], document = item.document, index = item.index;
        validateIndex(index, story, action, evidenceId);
        if (!['1', '2', '3'].includes(document.schema_version) || document.run_id !== story.run_id || document.case.case_id !== action.case_id || document.action_id !== action.action_id || document.evidence_id !== evidenceId)
            throw new Error('发布证据与当前检查不一致。');
        if (selectedEvent && !document.trace?.events.some(event => event.event_id === selectedEvent.event_id && event.kind === selectedEvent.kind && event.source_component === selectedEvent.source_component && event.source_location === selectedEvent.source_location && JSON.stringify(event.parent_event_ids) === JSON.stringify(selectedEvent.parent_event_ids)))
            throw new Error('发布记录中没有对应的执行节点。');
        return item;
    });
    const record = useRead(`record:${story.run_id}:${action.case_id}:${evidenceId}:${recordId}:${bundle.data?.index.evidence_id}`, async () => {
        if (!recordId || !bundle.data)
            return null;
        if (!bundle.data.index.records.some(item => item.record_id === recordId && (!proofId || item.proof_fingerprint === proofId) && (!selectedEvent || item.event_id === selectedEvent.event_id)))
            throw new Error('索引没有引用这条记录。');
        const value = await api.evidenceRecord(story.project_id, story.run_id, evidenceId, action.case_id, recordId);
        validateIndex(value, story, action, evidenceId);
        if (value.record.record_id !== recordId)
            throw new Error('读取的记录与所选项不一致。');
        return value;
    });
    if (bundle.loading)
        return <Loading>正在核对发布证据</Loading>;
    if (bundle.error)
        return <ErrorNote error={bundle.error} onRetry={bundle.reload}/>;
    const value = record.data, links = bundle.data?.index.records.filter(item => (!proofId || item.proof_fingerprint === proofId) && (!selectedEvent || item.event_id === selectedEvent.event_id)) ?? [];
    return <><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => onLocate('records', recordId ? evidenceId : undefined, undefined, recordId ? proofId ?? undefined : undefined)}>{recordId ? '全部证明片段' : '全部发布记录'}</Button>{recordId ? record.loading ? <Loading /> : record.error ? <ErrorNote error={record.error} onRetry={record.reload}/> : value && <article className="jj-record-reading"><Badge tone={value.role === 'PROOF' ? 'accent' : 'neutral'}>{value.role === 'PROOF' ? '判断依据' : '辅助记录'}</Badge><h3>{text(value.record.label)}</h3><p>{text(value.summary)}</p>{value.verification.length > 0 && <section><h3>如何核对</h3>{value.verification.map((item, index) => <div className="jj-verification-item" key={item.key + index}><span aria-hidden="true">{item.status === 'CONFIRMED' ? <CheckOutlined aria-hidden="true"/> : <QuestionOutlined aria-hidden="true"/>}</span><div><h4>{text(item.title)}</h4><p>{text(item.text)}</p></div></div>)}</section>}{value.values.length > 0 && <section><h3>记录中的值</h3><dl className="jj-facts">{value.values.map((item, index) => <div key={index}><dt>{text(item.label)}</dt><dd>{item.value !== undefined ? displayValue(item.value) : <>{item.before_label ?? '操作前'}：{displayValue(item.before)}<br />{item.after_label ?? '操作后'}：{displayValue(item.after)}</>}</dd></div>)}</dl></section>}{value.limitations.length > 0 && <section><h3>这条记录的限制</h3>{value.limitations.map((item, index) => <p key={index} className="jj-small jj-muted">{text(item)}</p>)}</section>}<details><summary>原始片段与技术位置</summary><pre>{JSON.stringify({ location: value.location, fragment: value.fragment }, null, 2)}</pre></details></article> : <section><h3>{proofId ? '这项业务结果的证明片段' : selectedEvent ? '对应的执行节点' : '这份证据包含的记录'}</h3>{!links.length && <Empty title="没有找到对应的证明片段"/>}{links.map(item => <button className="jj-record-link" key={item.record_id} onClick={() => onLocate('records', evidenceId, item.record_id, proofId ?? undefined)}><span>{text(item.label)}{item.phase && <small className="jj-record-phase">{({ BASELINE: '初始状态', BEFORE: '操作前', AFTER: '操作后', EVENTUAL: '最终观察', RECOVERY: '恢复后' } as Record<string, string>)[item.phase] ?? '已采集观察'}</small>}</span><span>{item.kind === 'FACT' ? '业务事实' : item.kind === 'TRACE' ? '过程节点' : item.kind === 'OUTCOME' ? '请求结果' : '业务观察'}</span></button>)}</section>}</>;
}
function validateIndex(index: Omit<EvidenceRecordIndex, 'records'>, story: ResultStory, action: ActionResultStory, id: string) { if (index.project_id !== story.project_id || index.run_id !== story.run_id || index.case_id !== action.case_id || index.action_id !== action.action_id || index.evidence_id !== id)
    throw new Error('证据索引与当前检查不一致。'); }
function displayValue(value: unknown) { return value === null || value === undefined ? '未记录' : typeof value === 'boolean' ? value ? '是' : '否' : typeof value === 'object' ? JSON.stringify(value) : String(value); }
