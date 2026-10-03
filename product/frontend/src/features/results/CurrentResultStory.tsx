// 结果总览与单项调查分层；只组织发布事实，证据详情重新校验，异步响应不得跨 Run/Case 复用。
import { Alert, Button, Descriptions, Empty, Pagination, Select, Spin, Typography } from 'antd'
import { useContext, useEffect, useRef, useState } from 'react'
import { WorkPageVisible } from '../../shared/runtime/visibility'
import { currentChecksApi, type CheckBreakpoint, type CheckEvidence, type EvidenceExplanation, type ResultStory, type StoryTraceEvent, type StoryProofCoverage } from '../../api/checks/currentChecks'
import { ApiError } from '../../api/http'
import { AssistantPanel } from '../assistant/AssistantPanel'
import { formatTimestamp } from '../../shared/format/time'
import { RuleSentence } from '../../shared/ui/Editorial'
import { ProofCoverage } from './overview/ProofCoverage'
import { DiagnosisSummary } from './investigation/DiagnosisSummary'
import { breakpointLabels, precisionDescriptions, traceEventLabel } from './investigation/tracePresentation'
import { ExecutionPath } from './investigation/ExecutionPath'
import { observationStatus, phaseLabels, sourceLabels, sourceReading } from './observations/observationPresentation'
import { ObservationSources } from './observations/ObservationSources'
import { BusinessEffects, caseJudgement, resourceOwner, ResultBadge, ResultOverviewHeader, ResultScope } from './overview/ResultOverview'
import './testing.css'
import './investigation/trace-investigation.css'
import './overview/result-review.css'

const controlLabels = { SAFE: '正常对照已通过', VULNERABLE: '正常对照发现问题', INCONCLUSIVE: '正常对照证据不足' }
type InvestigationTab = 'facts' | 'trace' | 'records'

export function CurrentResultStory({ story, onError, onNavigate, requestedCaseId, onCaseChange, historicalOnly, embedded = false }: {
  story: ResultStory; onError: (error: ApiError) => void; onNavigate?: (path: string) => void
  requestedCaseId?: string | null; onCaseChange?: (caseId: string | null) => void; historicalOnly?: boolean; embedded?: boolean
}) {
  const visible = useContext(WorkPageVisible)
  const panel = useRef<HTMLDivElement>(null)
  const returnFocus = useRef<{ label: string; tab: InvestigationTab } | undefined>(undefined)
  const restorePending = useRef(false)
  const selectedTrigger = useRef<string | undefined>(undefined)
  const scrollPosition = useRef(0)
  const [selectedCase, setSelectedCase] = useState<string | undefined>(requestedCaseId ?? undefined)
  const [tab, setTab] = useState<InvestigationTab>('facts')
  const [page, setPage] = useState(1)
  const [detail, setDetail] = useState<{ source?: EvidenceExplanation; breakpoint?: CheckBreakpoint; event?: StoryTraceEvent; coverage?: StoryProofCoverage; refs: string[] }>()
  const [documents, setDocuments] = useState<CheckEvidence[]>([])
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const requestEpoch = useRef(0)
  // 排序只使用服务端已发布判断的展示分类；未知文案不借用 HTTP、效果或别项结论推断。
  const priority: Record<string,number> = { block: 0, unknown: 1, neutral: 2, pass: 3 }
  const ordered = [...story.actions].sort((a,b) => priority[caseJudgement(a).tone] - priority[caseJudgement(b).tone])
  const action = selectedCase ? ordered.find(item => item.case_id === selectedCase) : undefined
  const comparison = action?.fact_comparison
  const actual = comparison?.verified_actual_identity
  const clearEvidence = () => { requestEpoch.current += 1; setDetail(undefined); setDocuments([]); setLoading(false); setFailed(false) }
  useEffect(() => { setSelectedCase(requestedCaseId ?? undefined); setTab('facts'); clearEvidence() }, [requestedCaseId, story.run_id])
  useEffect(() => { setPage(1); selectedTrigger.current = undefined; return () => { requestEpoch.current += 1 } }, [story.run_id])
  useEffect(() => { if (!visible) clearEvidence() }, [visible])
  useEffect(() => {
    if (detail) panel.current?.querySelector<HTMLElement>('.result-evidence-document')?.focus({ preventScroll: true })
    else if (restorePending.current) {
      restorePending.current = false
      const target = Array.from(panel.current?.querySelectorAll<HTMLElement>('button') ?? []).find(button => (button.getAttribute('aria-label') ?? button.textContent) === returnFocus.current?.label)
      // 证据详情返回时重新展开原来源，避免将焦点还给折叠区内不可见的按钮。
      const stages = target?.closest('details')
      if (stages) stages.open = true
      target?.focus({ preventScroll: true })
    }
  }, [detail, tab])
  useEffect(() => {
    if (selectedCase || !selectedTrigger.current) return
    const target = Array.from(panel.current?.querySelectorAll<HTMLElement>('[data-result-case]') ?? []).find(button => button.dataset.resultCase === selectedTrigger.current)
    target?.focus({ preventScroll: true }); window.scrollTo({ top: scrollPosition.current, behavior: 'instant' })
  }, [selectedCase])
  const selectCase = (caseId: string | null) => {
    if (!selectedCase) scrollPosition.current = window.scrollY
    if (caseId) selectedTrigger.current = caseId
    clearEvidence(); setTab('facts'); setSelectedCase(caseId ?? undefined); onCaseChange?.(caseId)
  }
  const selectTab = (value: InvestigationTab) => { clearEvidence(); setTab(value) }
  const closeEvidence = () => { restorePending.current = true; clearEvidence(); setTab(returnFocus.current?.tab ?? 'records') }
  const openEvidence = async (refs: string[], source?: EvidenceExplanation, breakpoint?: CheckBreakpoint, event?: StoryTraceEvent, coverage?: StoryProofCoverage) => {
    if (!action) return
    const epoch = ++requestEpoch.current
    const trigger = document.activeElement as HTMLElement | null
    returnFocus.current = { label: trigger?.getAttribute('aria-label') ?? trigger?.textContent ?? '', tab }
    setDetail({ refs, source, breakpoint, event, coverage }); setTab('records'); setDocuments([]); setLoading(true); setFailed(false)
    try {
      // 索引与摘要不是证据文件；详情仍走严格 reader，核对 Run、Action、Case 以及具体执行节点。
      if (!refs.length) throw new ApiError('ARTIFACT_MANIFEST', '所选事实没有发布证据引用。')
      const values = await Promise.all([...new Set(refs)].map(async id => {
        const value = await currentChecksApi.evidence(story.run_id, id)
        if (value.evidence_id !== id || value.run_id !== story.run_id || value.action_id !== action.action_id || value.case.case_id !== action.case_id)
          throw new ApiError('ARTIFACT_MANIFEST', '证据与当前检查项不一致。')
        return value
      }))
      if (event && !values.some(value => value.trace?.events.some(item => item.event_id === event.event_id && item.kind === event.kind && item.source_component === event.source_component && item.source_location === event.source_location && JSON.stringify(item.parent_event_ids) === JSON.stringify(event.parent_event_ids))))
        throw new ApiError('ARTIFACT_MANIFEST', '发布证据中没有对应的执行节点。')
      if (requestEpoch.current === epoch) setDocuments(values)
    } catch (error) { if (requestEpoch.current === epoch) { setFailed(true); onError(error as ApiError) } }
    finally { if (requestEpoch.current === epoch) setLoading(false) }
  }
  const evidenceRow = (item: EvidenceExplanation, index: number) => <section className="result-proof-row" key={`${item.observed_fact.observer_id}:${item.observed_fact.phase}:${index}`}>
    <div className="result-proof-title"><h4>{sourceLabels[item.source_label] ?? item.source_label}</h4><span>{item.observed_fact.level === 'VERDICT_REQUIRED' ? '必要证明' : '辅助材料'}</span></div>
    <p><strong>{sourceReading(item).label}</strong> · {phaseLabels[item.observed_fact.phase]}</p><p className="editorial-muted">{item.supports_claim}</p>
    {!!item.evidence_refs.length && <div className="result-proof-links"><Button type="link" onClick={() => void openEvidence(item.evidence_refs, item)}>查看{item.source_label}证据</Button></div>}
  </section>
  const requiredProofs = action?.proof_coverage?.filter(row => row.required_level === 'VERDICT_REQUIRED') ?? []
  const requiredSources = action?.decisive_proof_chain.filter(item => item.observed_fact.level === 'VERDICT_REQUIRED') ?? []
  const publishedReading = (fact: CheckEvidence['observations'][number]) => {
    const source = action?.evidence_explanations.find(item => item.observed_fact.observer_id === fact.observer_id && item.observed_fact.phase === fact.phase && item.observed_fact.effect_id === fact.effect_id && item.observed_fact.proof_fingerprint === fact.proof_fingerprint && item.observed_fact.window_end_us === fact.window_end_us)
    return source ? sourceReading(source) : observationStatus(fact)
  }
  const proofSummary = requiredProofs.length ? <ProofCoverage rows={requiredProofs} onEvidence={(row, refs) => void openEvidence(refs, undefined, undefined, undefined, row)}/> : requiredSources.length ? requiredSources.map(evidenceRow) : <p className="result-proof-missing">必要证明尚不完整。补足对应证明后发起新的检查；不能用缺少记录推断没有发生业务后果。</p>
  const evidenceContent = <>
      {detail?.coverage && <div className="evidence-selection"><p className="editorial-eyebrow">来自所选证明要求</p><h3>{detail.coverage.business_label}</h3><p>{detail.coverage.source_label} · {detail.coverage.required_level === 'VERDICT_REQUIRED' ? '必要证明' : '辅助材料'}</p><p className="editorial-muted">下方只显示对应本项要求的观察；完整文档保留在技术引用中。</p></div>}
      {detail?.event && <div className="evidence-selection"><p className="editorial-eyebrow">来自所选节点</p><h3>{traceEventLabel(detail.event)}</h3><p className="editorial-muted">只读取本轮发布的记录，当前配置不会改变这些证据。</p></div>}
      {loading && <Spin tip="正在核验发布证据"><div style={{ minHeight: 80 }} /></Spin>}
      {failed && <Alert showIcon type="error" message="证据未能通过读取或完整性检查，请返回刷新检查结果。" />}
      {!loading && !failed && detail?.source && <Descriptions column={1} layout="vertical" items={[
        { key: 'where', label: '在哪里看到', children: `${detail.source.source_label} · ${detail.source.source_location}` },
        { key: 'what', label: '看到什么', children: `${phaseLabels[detail.source.observed_fact.phase]}：${sourceReading(detail.source).label}` },
        { key: 'reading', label: '这条记录的含义', children: sourceReading(detail.source).detail },
        { key: 'supports', label: '因此支持什么', children: detail.source.supports_claim },
        { key: 'limit', label: '不能单独证明什么', children: detail.source.does_not_prove },
      ]} />}
      {!loading && !failed && detail?.breakpoint && <dl className="evidence-answers"><dt>在哪里看到</dt><dd>本轮已发布的执行路径与定位边界，具体位置见下方。</dd><dt>看到什么</dt><dd>{detail.breakpoint.breakpoint_type ? breakpointLabels[detail.breakpoint.breakpoint_type] : '已有后果证据，定位范围有限'}</dd><dt>因此支持什么</dt><dd>{precisionDescriptions[detail.breakpoint.precision]}</dd><dt>不能单独证明什么</dt><dd>定位只解释已有后果，不能替代决定性业务结果证据；不完整路径不支持更细的位置。</dd></dl>}
      {!loading && !failed && detail?.event && <dl className="evidence-answers"><dt>在哪里看到</dt><dd>{detail.event.source_component} · {detail.event.source_location}</dd><dt>看到什么</dt><dd>{traceEventLabel(detail.event)}</dd><dt>因此支持什么</dt><dd>该节点及记录中明确提供的前序关系。未记录的关联保持未知。</dd><dt>不能单独证明什么</dt><dd>节点存在不等于业务结果已形成，也不能单独证明权限安全；最终后果以独立观察为准。</dd></dl>}
      {documents.map((document) => <section key={document.evidence_id}>
        {detail?.breakpoint && document.trace && <>
          <Typography.Title level={5}>已发布的定位边界</Typography.Title>
          {document.trace.events.filter((event) => [detail.breakpoint?.first_violation_event_id, detail.breakpoint?.range_start_event_id, detail.breakpoint?.range_end_event_id].includes(event.event_id)).map((event) => <Typography.Paragraph key={event.event_id}>{event.source_component} · {event.source_location}</Typography.Paragraph>)}
          {!document.trace.complete && <Typography.Paragraph type="secondary">执行路径不完整，定位精度以本项判断为准。</Typography.Paragraph>}
        </>}
        {!detail?.event && <><Typography.Title level={5}>观察记录</Typography.Title>
        {document.observations.filter(item => (!detail?.coverage || (item.effect_id === detail.coverage.effect_id && item.proof_fingerprint === detail.coverage.proof_fingerprint)) && (!detail?.source || (item.observer_id === detail.source.observed_fact.observer_id && item.phase === detail.source.observed_fact.phase && item.effect_id === detail.source.observed_fact.effect_id && item.proof_fingerprint === detail.source.observed_fact.proof_fingerprint))).map((item, index) => <Typography.Paragraph key={index}>{phaseLabels[item.phase]} · {publishedReading(item).label} · {formatTimestamp(item.window_end_us)}</Typography.Paragraph>)}</>}
        <details><summary>证据文件与技术引用</summary><pre className="check-evidence-json">{JSON.stringify(document, null, 2)}</pre></details>
      </section>)}
  </>
  return <div className="result-story result-review" aria-label="已发布的权限与证据故事" ref={panel}>
    {!embedded && <><ResultOverviewHeader story={story} onNavigate={onNavigate} historicalOnly={historicalOnly}/><div className="result-standalone-scope"><ResultScope story={story}/></div></>}
    {!selectedCase ? <section aria-label="逐项检查结果">
      <div className="result-section-heading"><h2>逐项检查结果</h2><p>已确认的要求与实际结果，对照阅读</p></div>
      {ordered.length ? <><table className="result-overview-table"><thead><tr><th scope="col">业务要求</th><th scope="col">实际结果</th><th scope="col">本项判断</th><th scope="col">依据</th></tr></thead><tbody>{ordered.slice((page-1)*10, page*10).map((item,index) => {
        const judgement = caseJudgement(item)
        return <tr key={item.case_id} data-tone={judgement.tone}><td><div className="result-requirement-label"><span className="result-case-number">{String((page-1)*10+index+1).padStart(2,'0')}</span><div><strong>{item.permission.expectation === 'DENY' ? '禁止' : '允许'}{item.display_name}</strong><p>{item.fact_comparison.planned_identity.label ?? item.fact_comparison.planned_identity.actor_label ?? '计划账号'} · 资源属于{resourceOwner(item)}</p></div></div></td><td data-label="实际结果"><BusinessEffects action={item}/></td><td data-label="本项判断"><ResultBadge tone={judgement.tone}>{judgement.label}</ResultBadge></td><td><Button type="link" data-result-case={item.case_id} aria-label={`查看第 ${(page-1)*10+index+1} 项依据`} onClick={() => selectCase(item.case_id)}>查看依据</Button></td></tr>
      })}</tbody></table>{ordered.length > 10 && <Pagination className="result-case-pagination" current={page} pageSize={10} total={ordered.length} showSizeChanger={false} showTotal={total => `共 ${total} 项检查`} onChange={setPage}/>}</> : <Empty description="本次没有可展示的检查项"/>}
      <p className="result-reading-note">实际结果来自业务后果观察。点开任一项，可核对账号、接口响应与对应证明。</p>
    </section> : <>
      <div className="result-investigation-nav"><Button type="link" onClick={() => selectCase(null)}>← 返回 {ordered.length} 项结果</Button>{ordered.length <= 8 ? <nav aria-label="选择检查项"><span>检查项</span>{ordered.map((item,index) => <Button key={item.case_id} aria-label={`查看第 ${index+1} 项依据`} aria-pressed={item.case_id === selectedCase} onClick={() => selectCase(item.case_id)}>{index+1}</Button>)}</nav> : <Select aria-label="选择检查项" value={selectedCase} options={ordered.map((item,index) => ({value:item.case_id,label:`${index+1}. ${item.display_name} · ${item.fact_comparison.planned_identity.label ?? '计划账号'}`}))} onChange={selectCase}/>}</div>
      {action && comparison && actual ? <article className="result-investigation-surface">
        <header className="result-investigation-heading"><div><h2>{action.display_name}</h2><p>{comparison.planned_identity.label ?? comparison.planned_identity.actor_label ?? '计划账号'} · 资源属于{resourceOwner(action)}</p></div><ResultBadge tone={caseJudgement(action).tone}>{caseJudgement(action).label}</ResultBadge></header>
        <nav className="result-detail-tabs" aria-label="检查项详情">{([['facts','事实与证明'],['trace','执行过程'],['records','证据记录']] as const).map(([id,label]) => <button key={id} aria-current={tab === id ? 'page' : undefined} onClick={() => selectTab(id)}>{label}</button>)}</nav>
        <div className="result-investigation-body">
          {tab === 'facts' && <>
            <div className="result-expectation-comparison"><section><p className="editorial-eyebrow">已确认的要求</p><h3>{action.permission.expectation === 'DENY' ? '禁止' : '允许'}{action.display_name}</h3><RuleSentence>{comparison.planned_identity.label ?? comparison.planned_identity.actor_label ?? '原操作账号'} 对{resourceOwner(action)}拥有的资源，{action.permission.expectation === 'DENY' ? '不得' : '可以'}{action.display_name}。</RuleSentence></section><section data-tone={caseJudgement(action).tone}><p className="editorial-eyebrow">实际发生的结果</p><BusinessEffects action={action}/></section></div>
            <section className="result-proof-summary" aria-label="判断依据"><h3>判断依据</h3>{proofSummary}<div className="result-http-fact"><span>接口响应</span><div><strong>{comparison.http_surface.http_status === null ? '未取得 HTTP 状态' : `HTTP ${comparison.http_surface.http_status}`}</strong> · {comparison.http_explanation}<p>接口响应不单独证明业务后果。</p></div></div></section>
            <dl className="result-identity-line"><div><dt>实际操作账号</dt><dd>{actual.verification_status === 'MATCH' ? actual.label ?? '身份已独立确认' : actual.verification_status === 'MISMATCH' ? '实际身份与计划不一致' : '无法独立确认'}</dd></div><div><dt>初始条件</dt><dd>{comparison.http_surface.baseline_trusted ? '已独立核对' : '尚未确认'}</dd></div><div><dt>恢复条件</dt><dd>{comparison.http_surface.recovery_verified ? '恢复要求已满足' : '尚未确认恢复'}</dd></div></dl>
            <p className="result-control-fact"><strong>正常业务对照</strong> · {comparison.allow_control ? controlLabels[comparison.allow_control.verdict] : action.permission.expectation === 'ALLOW' ? '本项为正常业务验证' : '未提供正常业务对照'}。</p>
          </>}
          {tab === 'trace' && <>{action.execution_path?.events.length ? <ExecutionPath key={`${story.run_id}:${action.case_id}`} action={action} selectedEvent={detail?.event?.event_id} onSelect={(event,refs) => void openEvidence(refs,undefined,undefined,event)}/> : <p className="result-path-unavailable">本轮没有可展示的明确执行路径；保留已有业务后果证据，不补画因果链。</p>}{action.breakpoint && <DiagnosisSummary action={action} onEvidence={() => void openEvidence(action.breakpoint!.evidence_refs,undefined,action.breakpoint!)}/>}</>}
          {tab === 'records' && (detail ? <section className="result-evidence-document" aria-label="已发布证据" tabIndex={-1} onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); closeEvidence() } }}><Button type="link" className="result-evidence-back" onClick={closeEvidence}>← 返回{(returnFocus.current?.tab ?? 'records') === 'trace' ? '执行过程' : returnFocus.current?.tab === 'facts' ? '事实与证明' : '证据目录'}</Button>{evidenceContent}</section> : <>
            <h3>必要证明记录</h3>{proofSummary}
            <ProofCoverage rows={action.proof_coverage?.filter(row => row.required_level === 'SUPPORTING') ?? []} onEvidence={(row,refs) => void openEvidence(refs,undefined,undefined,undefined,row)}/>
            <ObservationSources sources={action.evidence_explanations} onEvidence={item => void openEvidence(item.evidence_refs,item)}/>
            {action.claim_boundary.length > 0 && <div className="result-case-boundary"><h3>这项结果的适用边界</h3>{action.claim_boundary.map(text => <p key={text}>{text}</p>)}</div>}
            <details className="result-explanation"><summary>解释已有结果</summary><AssistantPanel runId={story.run_id} title="理解本次检查结果" actionLabel="解释已有结果"/></details>
          </>)}
        </div>
      </article> : <Empty description="本轮没有指定的检查项，请返回本轮结果选择已有记录。"/>}
    </>}
    <footer className="result-overall-boundary">{story.claim_boundary.map(text => <p key={text}>{text}</p>)}</footer>
  </div>
}
