import {IndexSelection} from '../../../shared/ui/IndexSelection'
import {conditionLabels} from '../../../entities/permission/ui/RuleConditions';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import CloseOutlined from '@ant-design/icons/CloseOutlined';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import { currentChecksApi as api, type ActivityEvent, type ActionResultStory, type EvidenceRecordIndex, type ResultStory, type StoryTraceEvent } from '../../../entities/check/api/currentChecks';
import { ApiError } from '../../../shared/api/http';
import { assertProject } from '../../../shared/model/page';
import { text } from '../../../shared/lib/format';
import { useRead } from '../../../shared/lib/useRead';
import { Badge, Empty, ErrorNote, Loading } from "../../../shared/ui/feedback";
import { Button } from "../../../shared/ui/actions";
import { Tabs } from "../../../shared/ui/Tabs";
import { Choice } from "../../../shared/ui/Choice";
import {EvidenceRecord} from './EvidenceRecord';
import { actual, gaps, judgement, judgementLabels, owner, requirement } from '../../../entities/check/model/checks';
type Props = {
    story: ResultStory;
    action?: ActionResultStory;
    tab: string | null;
    evidenceId: string | null;
    recordId: string | null;
    proofId?: string | null;
    stepId?: string | null;
    comparison?: ReactNode;
    onClose: () => void;
    onLocate: (tab: string, evidence?: string, record?: string, proof?: string, step?: string) => void;
    onError: (error: unknown) => void;
};
type PublishedEvent = StoryTraceEvent | ActivityEvent;
export function EvidenceInspector({ story, action, tab, evidenceId, recordId, proofId, stepId, comparison, onClose, onLocate }: Props) {
    const heading = useRef<HTMLHeadingElement>(null), tabId = useId();
    const [event, setEvent] = useState<PublishedEvent>();
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
    } }}><header className="jj-inspector-header"><span>检查依据</span><Button kind="quiet" aria-label="关闭检查依据" onClick={onClose} icon={<CloseOutlined aria-hidden="true"/>}/></header><div className="jj-inspector-title"><h2 ref={heading} tabIndex={-1}>{text(action.display_name)}</h2><p>{owner(action)}的资源</p><Badge tone={tone}>{judgementLabels[tone]}</Badge></div><Tabs density="compact" className="jj-inspector-tabs" label="依据视图" value={currentTab ?? 'facts'} idPrefix={tabId} panelId={tabId + '-panel'} items={[{ value: 'facts', label: '业务结果' }, { value: 'trace', label: '操作经过' }, { value: 'records', label: '证明记录' }]} onValueChange={onLocate}/><div className="jj-inspector-content" data-view={currentTab} role="tabpanel" id={tabId + '-panel'} aria-labelledby={tabId + '-' + currentTab} key={currentTab}>
    {currentTab === 'facts' && <div className="jj-evidence-reading">
      <div className="jj-evidence-main">
        <section className="jj-evidence-comparison" aria-label="权限要求与实际结果">
          <div><h3>权限要求</h3><p>{requirement(action)}</p><small>{owner(action)}的资源</small></div>
          <div data-tone={tone}><h3>实际结果</h3>{action.fact_comparison.effects.map(effect => <p key={effect.effect_id}>{actual(effect)}</p>)}{!action.fact_comparison.effects.length && <p>{text(action.judgement)}</p>}</div>
        </section>
        {tone === 'caution' && missing.length > 0 && <section className="jj-inspector-section is-gap"><h3>还缺哪些依据</h3><ul className="jj-gap-list">{missing.map(item => <li key={item}>{item}</li>)}</ul></section>}
        <section className="jj-inspector-section is-proofs"><h3>判断所用的记录</h3>{evidenceSources.length ? evidenceSources.map((source, index) => <ProofEntry key={source.proof_fingerprint + index} label={text(source.business_label)} source={text(source.source_label)} onRead={source.evidence_refs.length ? () => openRecord(source.evidence_refs[0], source.proof_fingerprint) : undefined}/>) : action.decisive_proof_chain.map((item, index) => <ProofEntry key={index} label={text(item.source_label)} onRead={item.evidence_refs.length ? () => openRecord(item.evidence_refs[0]) : undefined}/>)}</section>
        {comparison}
      </div>
      <aside className="jj-evidence-context" aria-label="本项检查上下文">
        <section><h3>核对对象</h3><dl className="jj-facts"><div><dt>实际账号</dt><dd>{action.fact_comparison.verified_actual_identity.verification_status === 'MATCH' ? text(action.fact_comparison.verified_actual_identity.label ?? '账号已独立确认') : action.fact_comparison.verified_actual_identity.verification_status === 'MISMATCH' ? '与计划不一致' : '尚未确认'}</dd></div><div><dt>资源归属</dt><dd>{owner(action)}</dd></div><div><dt>测试资源</dt><dd>{action.fact_comparison.resource_id ?? '未提供资源编号'}</dd></div></dl></section>
        {action.permission.conditions && <section><h3>适用条件</h3><p>{conditionLabels(action.permission.conditions).join('，')}</p>{(action.fact_comparison.http_surface.condition_observations ?? []).map(item => <p className="jj-small jj-muted" key={item.proof_fingerprint}>执行前读取：{[item.principal === 'ANONYMOUS' ? '未登录访问' : '已登录', item.subject_tenant ? '操作人租户 '+item.subject_tenant : null, item.resource_tenant ? '资源租户 '+item.resource_tenant : null, item.resource_state ? '数据状态 '+item.resource_state : null].filter(Boolean).join('，')}</p>)}</section>}
        <details><summary>请求与恢复核对</summary><dl className="jj-facts"><div><dt>接口响应</dt><dd>{action.fact_comparison.http_surface.http_status ?? '未取得状态码'}</dd></div><div><dt>请求对应</dt><dd>{action.fact_comparison.http_surface.run_correlated ? '已确认' : '未确认'}</dd></div><div><dt>资源对应</dt><dd>{action.fact_comparison.http_surface.resource_correlated ? '已确认' : '未确认'}</dd></div><div><dt>操作前状态</dt><dd>{action.fact_comparison.http_surface.baseline_trusted ? '已核对' : '未确认'}</dd></div><div><dt>操作后恢复</dt><dd>{action.fact_comparison.http_surface.recovery_verified ? '满足恢复要求' : '未确认'}</dd></div></dl><p className="jj-small jj-muted">接口响应仅作为过程信息，业务结果依据独立记录判断。</p></details>
      </aside>
    </div>}
    {currentTab === 'trace' && <OperationPath action={action} selectedId={stepId} onSelect={id => onLocate('trace', undefined, undefined, undefined, id)} onRead={item => { setEvent(item); onLocate('records', ('parent_event_id' in item ? action.request_activity!.evidence_refs : action.execution_path!.evidence_refs)[0], undefined, undefined, item.event_id); }}/>}
    {currentTab === 'records' && (evidenceId ? <PublishedRecords story={story} action={action} evidenceId={evidenceId} recordId={recordId} proofId={proofId} selectedEvent={stepId ? action.request_activity?.capture.events.find(item => item.event_id === stepId) ?? action.execution_path?.events.find(item => item.event_id === stepId) : event} onLocate={onLocate}/> : <><h3>业务证明与辅助记录</h3>{[...new Set([...action.decisive_proof_chain.flatMap(item => item.evidence_refs), ...action.evidence_explanations.flatMap(item => item.evidence_refs), ...(action.proof_coverage ?? []).flatMap(item => [...item.evidence_refs, ...item.supporting_evidence_refs])])].map((id, index) => <button className="jj-record-link" key={id} onClick={() => openRecord(id)}><span>已发布记录 {index + 1}</span><span>查看内容</span></button>)}</>)}
  </div></aside>;
}
function ProofEntry({label, source, onRead}: {label: string; source?: string; onRead?: () => void}) {
    const content = <><span><strong>{label}</strong><small>{source ?? '已发布证明记录'}</small></span><span>{onRead ? '查看记录' : '没有可读取的记录'}{onRead && <ArrowRightOutlined aria-hidden="true"/>}</span></>;
    return onRead ? <Button kind="quiet" className="jj-proof-entry" onClick={onRead} aria-label={'打开证明记录：' + label}>{content}</Button> : <div className="jj-proof-entry">{content}</div>;
}
const traceLabels: Record<StoryTraceEvent['kind'], string> = { ENTRY: '收到业务请求', IDENTITY: '确认操作身份', AUTHORIZATION: '执行权限判断', PERSISTENT_EFFECT: '提交业务数据', MESSAGE: '发出业务消息', DELEGATION: '调用下游服务', FINAL_EFFECT: '形成业务结果', RECOVERY: '恢复业务状态' };
const callLabels: Record<ActivityEvent['operation'], string> = {REQUEST:'处理请求', EXEC:'执行数据库语句', PREPARE:'准备数据库语句', RUN:'执行数据操作', GET:'查询一条记录', ALL:'查询记录列表', ITERATE:'逐条读取记录', READ:'读取文件', WRITE:'写入文件', APPEND:'追加文件'};
function callLabel(event: ActivityEvent) { return event.kind === 'HTTP_SERVER' ? '接收与返回请求' : event.kind === 'HTTP_CLIENT' ? '请求下游服务' : callLabels[event.operation]; }
function OperationPath(props: {action: ActionResultStory; selectedId?: string | null; onSelect: (id: string) => void; onRead: (event: PublishedEvent) => void}) {
    const {action} = props;
    if (action.activity_error) return <Empty title={action.activity_error==='ACTIVITY_RECORDS_CONFLICT' ? '本次调用记录存在冲突' : '本次自动采集未完成'}>已发布记录未形成可核对的调用路径。业务结果保留原判断，补齐采集条件后重新检查。</Empty>;
    return action.request_activity ? <><ActivityTimeline {...props}/>{!!action.execution_path?.events.length && <details className="jj-semantic-events"><summary>应用提供的权限与业务事件</summary><TraceTimeline {...props}/></details>}</> : <TraceTimeline {...props}/>;
}
function ActivityTimeline({action, selectedId, onSelect, onRead}: {action: ActionResultStory; selectedId?: string | null; onSelect: (id: string) => void; onRead: (event: PublishedEvent) => void}) {
    const detailId = useId(), capture = action.request_activity!.capture;
    const selected = capture.events.find(event => event.event_id === selectedId) ?? capture.events[0];
    const position = capture.events.indexOf(selected), parent = capture.events.findIndex(event => event.event_id === selected.parent_event_id);
    const status = {OK:'调用已结束', ERROR:'调用发生异常', INCOMPLETE:'结束记录未收齐'}[selected.outcome];
    return <section className="jj-operation-path" aria-label="自动采集的调用路径">
      <div className="jj-trace-summary"><Badge tone={capture.complete ? 'neutral' : 'caution'}>{capture.complete ? '本次调用已收齐' : '调用记录不完整'}</Badge><span>{capture.events.length} 个调用</span></div>
      <p className="jj-small jj-muted">宿主自动采集。技术调用不代表权限决定或业务提交结果。</p>
      {!!capture.dropped_count && <p className="jj-small jj-muted">超出本次采集上限，省略 {capture.dropped_count} 个调用。</p>}
      <div className="jj-step-workspace">
        <div className="jj-step-mobile"><Choice aria-label="查看采集调用" value={selected.event_id} onValueChange={onSelect}>{capture.events.map((event,index)=><option key={event.event_id} value={event.event_id}>第 {index+1} 项　{callLabel(event)}</option>)}</Choice></div>
        <IndexSelection as="ol" className="jj-operation-steps" label="采集调用" identity={selected.event_id}>{capture.events.map((event,index)=><li key={event.event_id}><button className="jj-step-select jj-index-item" aria-current={event.event_id===selected.event_id?'step':undefined} aria-controls={detailId} onClick={()=>onSelect(event.event_id)}><span className="jj-trace-order" aria-hidden="true">{index+1}</span><strong>{callLabel(event)}</strong><ArrowRightOutlined aria-hidden="true"/></button></li>)}</IndexSelection>
        <article className="jj-step-reading" key={selected.event_id} id={detailId} aria-labelledby={detailId+'-title'}>
          <header><div><span className="jj-small jj-muted">第 {position+1} 项</span><h3 id={detailId+'-title'}>{callLabel(selected)}</h3></div><Badge tone={selected.outcome==='ERROR'?'negative':selected.outcome==='INCOMPLETE'?'caution':'neutral'}>{status}</Badge></header>
          <dl><div><dt>调用来源</dt><dd>{selected.kind==='SQLITE'?'SQLite':selected.kind==='FILESYSTEM'?'应用文件':'HTTP'}</dd></div><div><dt>代码位置</dt><dd>{selected.source_location ?? 'HTTP 服务入口'}</dd></div><div><dt>耗时</dt><dd>{(selected.duration_us/1000).toFixed(2)} ms</dd></div>{selected.http_status!==null && <div><dt>响应状态</dt><dd>{selected.http_method} {selected.http_status}</dd></div>}<div><dt>所属请求</dt><dd>{parent<0?'本次请求入口':`第 ${parent+1} 项`}</dd></div></dl>
          <footer><Button kind="quiet" onClick={()=>onRead(selected)}>查看本次调用记录<ArrowRightOutlined aria-hidden="true"/></Button></footer>
        </article>
      </div>
      <details className="jj-capture-coverage"><summary>采集范围</summary><p className="jj-small jj-muted">已启用：{capture.adapters.join('、')}。文件探针覆盖 readFile、writeFile、appendFile；SQLite 探针覆盖 exec 与语句执行。应用内部函数、未支持的驱动和后台任务不在此范围内。</p></details>
      <span className="jj-sr-only" role="status">当前查看第 {position+1} 项，{callLabel(selected)}</span>
    </section>;
}
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
      <IndexSelection as="ol" className="jj-operation-steps" label="执行步骤" identity={selected.event_id}>{path.events.map((item, position) => <li key={item.event_id}>
        <button className="jj-step-select jj-index-item" aria-current={selected.event_id === item.event_id ? 'step' : undefined} aria-controls={detailId} onClick={() => onSelect(item.event_id)}>
          <span className="jj-trace-order" aria-hidden="true">{position + 1}</span><strong>{traceLabels[item.kind]}</strong><ArrowRightOutlined aria-hidden="true"/>
        </button>
      </li>)}</IndexSelection>
      <article className="jj-step-reading" id={detailId} aria-labelledby={detailId + '-title'} key={selected.event_id}>
        <header><div><span className="jj-small jj-muted">第 {index + 1} 步</span><h3 id={detailId + '-title'}>{traceLabels[selected.kind]}</h3></div>{selected.authorization_decision && <Badge>{selected.authorization_decision === 'ALLOW' ? '允许' : '拒绝'}</Badge>}</header>
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
    selectedEvent?: PublishedEvent;
    onLocate: Props['onLocate'];
}) {
    const allowed = new Set([...action.decisive_proof_chain.flatMap(item => item.evidence_refs), ...action.evidence_explanations.flatMap(item => item.evidence_refs), ...(action.proof_coverage ?? []).flatMap(item => [...item.evidence_refs, ...item.supporting_evidence_refs]), ...(action.execution_path?.evidence_refs ?? []), ...(action.request_activity?.evidence_refs ?? [])]);
    const bundle = useRead(`evidence:${story.project_id}:${story.run_id}:${action.case_id}:${evidenceId}:${recordId}:${proofId}:${selectedEvent?.event_id}`, async () => {
        if (!allowed.has(evidenceId))
            throw new ApiError('ARTIFACT_MANIFEST', '这份记录未被本项检查引用。');
        const result = await api.evidenceBundle(story.project_id, story.run_id, action.case_id, [evidenceId], recordId);
        assertProject(result.project_id, story.project_id);
        if (result.run_id !== story.run_id || result.case_id !== action.case_id || result.items.length !== 1)
            throw new Error('证据归属不一致，已停止展示。');
        const item = result.items[0], document = item.document, index = item.index;
        validateIndex(index, story, action, evidenceId);
        if (!['1', '2', '3'].includes(document.schema_version) || document.run_id !== story.run_id || document.case.case_id !== action.case_id || document.action_id !== action.action_id || document.evidence_id !== evidenceId)
            throw new Error('发布证据与当前检查不一致。');
        if (selectedEvent && !('parent_event_id' in selectedEvent ? document.activity?.events.some(event => Object.keys(event).every(key => event[key as keyof ActivityEvent] === selectedEvent[key as keyof ActivityEvent])) : document.trace?.events.some(event => event.event_id === selectedEvent.event_id && event.kind === selectedEvent.kind && event.source_component === selectedEvent.source_component && event.source_location === selectedEvent.source_location && JSON.stringify(event.parent_event_ids) === JSON.stringify(selectedEvent.parent_event_ids))))
            throw new Error('发布记录中没有对应的执行节点。');
        if(recordId){
            if(!index.records.some(item=>item.record_id===recordId&&(!proofId||item.proof_fingerprint===proofId)&&(!selectedEvent||item.event_id===selectedEvent.event_id)))
                throw new Error('索引没有引用这条记录。');
            if(!item.record)throw new Error('发布证据没有返回所选记录。');
            validateIndex(item.record,story,action,evidenceId);
            if(item.record.record.record_id!==recordId)throw new Error('读取的记录与所选项不一致。');
        }
        return item;
    });
    if (bundle.loading)
        return <Loading>正在核对发布证据</Loading>;
    if (bundle.error)
        return <ErrorNote error={bundle.error}/>;
    const value = bundle.data?.record, links = bundle.data?.index.records.filter(item => (!proofId || item.proof_fingerprint === proofId) && (!selectedEvent || item.event_id === selectedEvent.event_id)) ?? [];
    return <><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => onLocate('records', recordId ? evidenceId : undefined, undefined, recordId ? proofId ?? undefined : undefined)}>{recordId ? '全部证明片段' : '全部发布记录'}</Button>{recordId ? value && <EvidenceRecord key={value.evidence_id+':'+value.record.record_id} value={value}/> : <section><h3>{proofId ? '这项业务结果的证明片段' : selectedEvent ? '对应的执行节点' : '这份证据包含的记录'}</h3>{!links.length && <Empty title="没有找到对应的证明片段"/>}{links.map(item => <button className="jj-record-link" key={item.record_id} onClick={() => onLocate('records', evidenceId, item.record_id, proofId ?? undefined)}><span>{text(item.label)}{item.phase && <small className="jj-record-phase">{({ BASELINE: '初始状态', BEFORE: '操作前', AFTER: '操作后', EVENTUAL: '最终观察', RECOVERY: '恢复后' } as Record<string, string>)[item.phase] ?? '已采集观察'}</small>}</span><span>{item.kind === 'FACT' ? '业务事实' : ['TRACE', 'ACTIVITY'].includes(item.kind) ? '过程节点' : item.kind === 'OUTCOME' ? '请求结果' : '业务观察'}</span></button>)}</section>}</>;
}
function validateIndex(index: Omit<EvidenceRecordIndex, 'records'>, story: ResultStory, action: ActionResultStory, id: string) { if (index.project_id !== story.project_id || index.run_id !== story.run_id || index.case_id !== action.case_id || index.action_id !== action.action_id || index.evidence_id !== id)
    throw new Error('证据索引与当前检查不一致。'); }

