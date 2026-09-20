// 已发布结果的业务展示；安全判断与断裂精度原样取自后端，原始证据只在明确详情中展开。
import { Alert, Button, Descriptions, Drawer, Empty, Grid, Spin, Typography } from 'antd'
import { useContext, useEffect, useRef, useState } from 'react'
import { WorkPageVisible } from '../../app/RetainedWorkPages'
import { currentChecksApi, type CheckBreakpoint, type CheckEvidence, type EvidenceExplanation, type ResultStory, type StoryTraceEvent, type StoryProofCoverage } from '../../api/currentChecks'
import { ApiError } from '../../api/http'
import { AssistantPanel } from '../../components/AssistantPanel'
import { formatTimestamp } from '../../app/presentation'
import { EvidenceSurface, RuleSentence } from '../../shared/ui/Editorial'
import { RepairComparison } from '../changes/RepairComparison'
import { ProofCoverage } from './ProofCoverage'
import { DiagnosisSummary } from './DiagnosisSummary'
import { breakpointLabels, precisionDescriptions, precisionLabels, traceEventLabel } from './tracePresentation'
import './testing.css'
import './trace-investigation.css'
import { ExecutionPath } from './ExecutionPath'
import { repairLabels } from '../../api/repairs'
import { ArrowLeftOutlined, CloseOutlined, FileTextOutlined } from '@ant-design/icons'

const phaseLabels = { BASELINE: '初始状态', BEFORE: '操作前', AFTER: '操作后', EVENTUAL: '最终观察', RECOVERY: '恢复后' }
const stateLabels = { CONFIRMED: '已发现', ABSENT: '未发现', UNKNOWN: '无法确认' }
const controlLabels = { SAFE: '正常对照已通过', VULNERABLE: '正常对照发现问题', INCONCLUSIVE: '正常对照证据不足' }

export function CurrentResultStory({ story, onError, onNavigate, requestedCaseId }: { story: ResultStory; onError: (error: ApiError) => void; onNavigate?: (path: string) => void; requestedCaseId?: string | null }) {
  const wide = Grid.useBreakpoint().lg
  const visible = useContext(WorkPageVisible)
  const evidencePanel = useRef<HTMLElement>(null)
  const returnFocus = useRef<HTMLElement | null>(null)
  const [selectedCase, setSelectedCase] = useState<string | undefined>(requestedCaseId ?? undefined)
  const [detail, setDetail] = useState<{ source?: EvidenceExplanation; breakpoint?: CheckBreakpoint; event?: StoryTraceEvent; coverage?: StoryProofCoverage; refs: string[] }>()
  const [documents, setDocuments] = useState<CheckEvidence[]>([])
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const requestEpoch = useRef(0)
  useEffect(() => { setSelectedCase(requestedCaseId ?? undefined); setDetail(undefined); setDocuments([]); requestEpoch.current += 1 }, [requestedCaseId, story.run_id])
  useEffect(() => { setDetail(undefined); setDocuments([]); requestEpoch.current += 1; return () => { requestEpoch.current += 1 } }, [story.run_id])
  useEffect(() => { if (detail && wide) evidencePanel.current?.focus({ preventScroll: true }) }, [detail, wide])
  // Drawer 通过 Portal 挂到 body；页面会话隐藏时必须主动关闭，不能覆盖新页面。
  useEffect(() => { if (!visible) { requestEpoch.current += 1; setDetail(undefined); setDocuments([]) } }, [visible])
  const closeEvidence = () => { requestEpoch.current += 1; setDetail(undefined); setDocuments([]); returnFocus.current?.focus({ preventScroll: true }) }
  const openEvidence = async (refs: string[], source?: EvidenceExplanation, breakpoint?: CheckBreakpoint, event?: StoryTraceEvent, coverage?: StoryProofCoverage) => {
    const epoch = ++requestEpoch.current
    returnFocus.current = document.activeElement as HTMLElement
    // 桌面证据占用独立列，画布按新宽度适配；窄屏只开一个 Drawer。
    setDetail({ refs, source, breakpoint, event, coverage }); setDocuments([]); setLoading(true); setFailed(false)
    try {
      // 详情必须重新走完整性 reader；不把索引或缓存中的显示文案当作证据文件。
      if (!refs.length) throw new ApiError('ARTIFACT_MANIFEST', '所选事实没有发布证据引用。')
      const values = await Promise.all([...new Set(refs)].map(async (id) => {
        const value = await currentChecksApi.evidence(story.run_id, id)
        if (value.evidence_id !== id || value.run_id !== story.run_id || value.action_id !== action?.action_id || value.case.case_id !== action?.case_id)
          throw new ApiError('ARTIFACT_MANIFEST', '证据与当前检查项不一致。')
        return value
      }))
      if (event && !values.some(value => value.trace?.events.some(item => item.event_id === event.event_id && item.kind === event.kind && item.source_component === event.source_component && item.source_location === event.source_location && JSON.stringify(item.parent_event_ids) === JSON.stringify(event.parent_event_ids))))
        throw new ApiError('ARTIFACT_MANIFEST', '发布证据中没有对应的执行节点。')
      if (requestEpoch.current === epoch) setDocuments(values)
    } catch (error) { if (requestEpoch.current === epoch) { setFailed(true); onError(error as ApiError) } }
    finally { if (requestEpoch.current === epoch) setLoading(false) }
  }
  const evidenceRow = (item: EvidenceExplanation, index: number) => <section className="evidence-question" data-selected={detail?.source === item} key={`${item.observed_fact.observer_id}:${item.observed_fact.phase}:${index}`}>
    <p><strong>{item.source_label}</strong> · {phaseLabels[item.observed_fact.phase]} · {stateLabels[item.observed_fact.state]}</p>
    <p className="editorial-muted">{item.supports_claim}</p>
    {item.evidence_refs.length > 0 && <Button onClick={() => void openEvidence(item.evidence_refs, item)}>为什么这样判断？查看{item.source_label}证据</Button>}
  </section>
  const ordered = [...story.actions].sort((a, b) => Number(a.permission.expectation === 'ALLOW') - Number(b.permission.expectation === 'ALLOW'))
  const action = selectedCase ? ordered.find((item) => item.case_id === selectedCase) : ordered.find((item) => item.repair_requirement) ?? ordered[0]
  const comparison = action?.fact_comparison
  const actual = comparison?.verified_actual_identity
  const evidenceContent = <>
      {detail?.coverage && <div className="evidence-selection"><p className="editorial-eyebrow">来自所选证明要求</p><h3>{detail.coverage.business_label}</h3><p>{detail.coverage.source_label} · {detail.coverage.required_level === 'VERDICT_REQUIRED' ? '必要证明' : '辅助材料'}</p><p className="editorial-muted">下方只显示对应本项要求的观察；完整文档保留在技术引用中。</p></div>}
      {detail?.event && <div className="evidence-selection"><p className="editorial-eyebrow">来自所选节点</p><h3>{traceEventLabel(detail.event)}</h3><p className="editorial-muted">只读取本轮发布的记录，当前配置不会改变这些证据。</p></div>}
      {loading && <Spin tip="正在核验发布证据"><div style={{ minHeight: 80 }} /></Spin>}
      {failed && <Alert showIcon type="error" message="证据未能通过读取或完整性检查，请返回刷新检查结果。" />}
      {!loading && !failed && detail?.source && <Descriptions column={1} layout="vertical" items={[
        { key: 'where', label: '在哪里看到', children: `${detail.source.source_label} · ${detail.source.source_location}` },
        { key: 'what', label: '看到什么', children: `${phaseLabels[detail.source.observed_fact.phase]}：${stateLabels[detail.source.observed_fact.state]}；${detail.source.observed_fact.closure === 'CLOSED' ? '观察窗口已闭合' : '观察窗口尚未闭合'}` },
        { key: 'supports', label: '因此支持什么', children: detail.source.supports_claim },
        { key: 'limit', label: '不能单独证明什么', children: detail.source.does_not_prove },
      ]} />}
      {!loading && !failed && detail?.breakpoint && <dl className="evidence-answers"><dt>在哪里看到</dt><dd>本轮已发布的执行路径与定位边界，具体位置见下方。</dd><dt>记录了什么</dt><dd>{detail.breakpoint.breakpoint_type ? breakpointLabels[detail.breakpoint.breakpoint_type] : '已有后果证据，定位范围有限'}</dd><dt>能够支持什么</dt><dd>{precisionDescriptions[detail.breakpoint.precision]}</dd><dt>不能单独证明什么</dt><dd>定位只解释已有后果，不能替代决定性业务结果证据；不完整路径不支持更细的位置。</dd></dl>}
      {!loading && !failed && detail?.event && <dl className="evidence-answers"><dt>在哪里看到</dt><dd>{detail.event.source_component}的已发布记录</dd><dt>记录了什么</dt><dd>{traceEventLabel(detail.event)}</dd><dt>能够支持什么</dt><dd>该节点及记录中明确提供的前序关系。未记录的关联保持未知。</dd><dt>不能单独证明什么</dt><dd>节点存在不等于业务结果已形成，也不能单独证明权限安全；最终后果以独立观察为准。</dd></dl>}
      {documents.map((document) => <section key={document.evidence_id}>
        {detail?.breakpoint && document.trace && <>
          <Typography.Title level={5}>已发布的定位边界</Typography.Title>
          {document.trace.events.filter((event) => [detail.breakpoint?.first_violation_event_id, detail.breakpoint?.range_start_event_id, detail.breakpoint?.range_end_event_id].includes(event.event_id)).map((event) => <Typography.Paragraph key={event.event_id}>{event.source_component} · {event.source_location}</Typography.Paragraph>)}
          {!document.trace.complete && <Typography.Paragraph type="secondary">执行路径不完整，定位精度以本项判断为准。</Typography.Paragraph>}
        </>}
        {!detail?.event && <><Typography.Title level={5}>观察记录</Typography.Title>
        {document.observations.filter(item => !detail?.coverage || (item.effect_id === detail.coverage.effect_id && item.proof_fingerprint === detail.coverage.proof_fingerprint)).map((item, index) => <Typography.Paragraph key={index}>{phaseLabels[item.phase]} · {stateLabels[item.state]} · {formatTimestamp(item.window_end_us)}</Typography.Paragraph>)}</>}
        <details><summary>证据文件与技术引用</summary><pre className="check-evidence-json">{JSON.stringify(document, null, 2)}</pre></details>
      </section>)}
  </>
  return <><div className="result-investigation" data-evidence-open={Boolean(detail && wide)}><div className="result-story" aria-label="已发布的权限与证据故事">
    {story.repair_verification && <section className="repair-verification-summary"><h2>{story.repair_verification.status === 'VERIFIED' ? '原问题已经通过复验，要求保留的合法能力未受影响' : repairLabels[story.repair_verification.status]}</h2><p>原问题与本次新检查均保留为独立记录。</p>{onNavigate && <Button onClick={() => onNavigate(`/tests?run_id=${encodeURIComponent(story.repair_verification!.source_run_id)}`)}>查看原问题</Button>}</section>}
    {ordered.length > 1 && <nav className="result-case-index" aria-label="本轮权限考题">{ordered.map((item) => <button key={item.case_id} aria-current={item.case_id === action?.case_id ? 'true' : undefined} onClick={() => { requestEpoch.current += 1; setDetail(undefined); setDocuments([]); setSelectedCase(item.case_id) }}>{item.display_name} · {item.fact_comparison.planned_identity.label ?? '计划账号'} · {item.permission.expectation === 'DENY' ? '应当拒绝' : '应当允许'}</button>)}</nav>}
    {action && comparison && actual ? <article>
      <header className="result-case-heading"><div><p className="editorial-eyebrow">{action.display_name} · 本项判断</p><h2>{action.judgement}</h2>{action.breakpoint && <p className="result-diagnosis-badge" data-precision={action.breakpoint.precision}>{precisionLabels[action.breakpoint.precision]}<span>{precisionDescriptions[action.breakpoint.precision]}</span></p>}</div>
      {action.repair_requirement && onNavigate && <Button type="primary" onClick={() => onNavigate(`/changes?repair_reference=${encodeURIComponent(action.repair_requirement!.repair_fingerprint)}`)}>查看修复要求</Button>}</header>
      <div className="result-human-rule"><p className="editorial-eyebrow">人的权限要求</p><RuleSentence><strong>{comparison.planned_identity.label ?? comparison.planned_identity.actor_label ?? '原操作账号'}</strong> 对<strong>{comparison.planned_resource_owner?.label ?? (action.permission.relation === 'OWNS' ? '自己' : action.permission.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? '另一个同权限组账号' : '原资源所有者')}</strong>拥有的资源，<strong>{action.permission.expectation === 'DENY' ? '不得' : '可以'}{action.display_name}</strong>。</RuleSentence></div>
      <p className="result-publication"><FileTextOutlined aria-hidden="true"/> 本轮证据已发布 · 权限版本 {story.policy_epoch}</p>
      <ExecutionPath key={`${story.run_id}:${action.case_id}`} action={action} selectedEvent={detail?.event?.event_id} onSelect={(event, refs) => void openEvidence(refs, undefined, undefined, event)} />
      <div className="result-evidence-summary"><EvidenceSurface label="本轮机器事实">
        <h3>已确认的事实</h3>
        <p>页面 / 请求回应：{comparison.http_surface.http_status !== null && <>HTTP {comparison.http_surface.http_status} · </>}{comparison.http_explanation}</p>
        {comparison.effects.map((effect) => <p key={effect.effect_id}><strong>{effect.business_label}：{effect.judgement}</strong></p>)}
        <p>正常业务对照：{comparison.allow_control ? controlLabels[comparison.allow_control.verdict] : '本项为正常业务验证'}</p>
      </EvidenceSurface><DiagnosisSummary action={action} onEvidence={() => action.breakpoint && void openEvidence(action.breakpoint.evidence_refs, undefined, action.breakpoint)} /></div>
      <div className="result-fact-notes"><section className="story-section" aria-label="实际身份"><div><h3>实际身份</h3><p>计划操作人：{comparison.planned_identity.label ?? '未提供账号名称'}；计划资源所有者：{comparison.planned_resource_owner?.label ?? '未提供可读身份'}。</p><p>目标独立确认的实际账号：{actual.verification_status === 'MATCH' ? actual.label ?? '身份已独立确认' : actual.verification_status === 'MISMATCH' ? '实际身份与计划不一致' : '无法独立确认'}。</p></div></section>
      <section className="story-section" aria-label="最终业务结果"><div><h3>最终业务结果与决定性证明</h3>{action.decisive_proof_chain.length ? action.decisive_proof_chain.map(evidenceRow) : <><p>当前没有完整的决定性证明；现有观察不足以支持新的安全判断。</p><p className="editorial-muted">查看下方缺少的事实，补足对应证明后发起新的检查。已经由其他权威事实确认的问题仍保留。</p></>}</div></section>
      </div><details className="story-observations"><summary>全部观察来源与说明边界</summary>{action.evidence_explanations.map(evidenceRow)}{action.claim_boundary.map((text) => <p key={text} className="editorial-muted">{text}</p>)}</details>
      <ProofCoverage rows={action.proof_coverage ?? []} onEvidence={(row, refs) => void openEvidence(refs, undefined, undefined, undefined, row)} />
      {action.repair_requirement && <details aria-label="原题修复要求"><summary>查看原题修复要求与全部合法能力</summary><h2>修复原问题，并保留正常业务</h2><p>原权限、操作账号、资源归属和证据标准保持不变。关闭功能不能证明修复成功。</p><RepairComparison rows={action.repair_comparison ?? []} sourceRunId={story.run_id} onNavigate={onNavigate}/></details>}
    </article> : <Empty description={selectedCase ? '本轮没有指定的检查项，请从上方选择本轮已有记录。' : '本次没有可展示的检查项'} />}
    {story.change_context && onNavigate && <Button onClick={() => onNavigate('/changes')}>查看关联变化与修复</Button>}
    <details><summary>解释本次结果</summary><AssistantPanel runId={story.run_id} title="理解本次检查结果" actionLabel="解释已有结果" /></details>
    {story.claim_boundary.map((text) => <p key={text} className="editorial-muted">{text}</p>)}

  </div>{detail && wide && <aside className="result-evidence-panel" aria-label="已发布证据" tabIndex={-1} ref={evidencePanel} onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); closeEvidence() } }}><div className="evidence-panel-header"><h2>已发布证据</h2><Button type="text" icon={<CloseOutlined aria-hidden="true" />} aria-label="关闭证据并返回事实" onClick={closeEvidence}/></div>{evidenceContent}<div className="evidence-panel-footer"><Button block type="link" icon={<ArrowLeftOutlined aria-hidden="true" />} onClick={closeEvidence}>返回所选事实</Button></div></aside>}</div>
    <Drawer title="已发布证据" open={Boolean(detail && !wide)} width="100%" onClose={closeEvidence} extra={<Button onClick={closeEvidence}>返回检查事实</Button>}>{!wide && evidenceContent}</Drawer>
  </>
}
