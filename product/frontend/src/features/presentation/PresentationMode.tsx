// 展示模式只重排当前正式事实与净化验证汇总；页面切换不创建 Run、Verdict 或演示数据。

import { Alert, Button, Empty, Skeleton, Tag, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import {
  experienceApi,
  type CompetitionValidationSummaryViewDto,
  type OfficialExperienceDto,
} from '../../api/experience'
import {
  resultsApi,
  type ExecutionTraceDto,
  type HistoryViewDto,
  type ResultEvidenceExplanationDto,
  type ResultIntentHistoryDto,
  type ResultPresentationDto,
  type ResultPresentationIssueDto,
  type ResultRelevantIntentDto,
  type TraceEventDto,
} from '../../api/results'
import type { RunDto } from '../../api/runs'
import { expectationLabel, formatTimestamp, integrityLabel, lifecycleLabel, verdictLabel } from '../../app/presentation'
import { EvidenceExplanationDrawer } from '../checks/EvidenceExplanationDrawer'
import { ResultFactChain } from '../checks/ResultFactChain'
import './PresentationMode.css'

type PresentationPage = 'conclusion' | 'live' | 'comparison' | 'boundaries'
type EvidenceDrawerState = { title: string; explanations: ResultEvidenceExplanationDto[] } | null

const pages: Array<{ key: PresentationPage; index: string; label: string; summary: string }> = [
  { key: 'conclusion', index: '01', label: '项目结论', summary: '一眼看懂权限与后果' },
  { key: 'live', index: '02', label: '现场验证', summary: '看清本轮因果与证据' },
  { key: 'comparison', index: '03', label: '修复前后', summary: '证明修复没有关闭功能' },
  { key: 'boundaries', index: '04', label: '数据与边界', summary: '区分产品事实与验证范围' },
]

const traceLabels: Record<TraceEventDto['kind'], string> = {
  ENTRY: '请求进入',
  IDENTITY: '识别实际账号',
  AUTHORIZATION: '执行权限判断',
  PERSISTENT_EFFECT: '业务状态发生变化',
  MESSAGE: '消息进入后台链路',
  DELEGATION: '后台 Worker 继续执行',
  FINAL_EFFECT: '最终业务效果形成',
  RECOVERY: '执行业务恢复',
}

function verdictTone(verdict: unknown) {
  if (['PASS', 'SAFE'].includes(String(verdict ?? ''))) return 'success'
  if (['BLOCK', 'VULNERABLE'].includes(String(verdict ?? ''))) return 'error'
  return 'warning'
}

function mainIssue(presentation: ResultPresentationDto | null) {
  if (!presentation) return null
  const preferred = presentation.verdict === 'BLOCK'
    ? 'VULNERABLE'
    : presentation.verdict === 'PASS'
      ? 'SAFE'
      : 'INCONCLUSIVE'
  return presentation.issues.find((item) => item.verdict === preferred) ?? presentation.issues[0] ?? null
}

function traceFor(issue: ResultPresentationIssueDto | null, presentation: ResultPresentationDto | null) {
  if (!issue || !presentation) return undefined
  return presentation.execution_traces.find((item) => (
    item.case_id === issue.diagnosis?.case_id && item.action_id === issue.diagnosis?.action_id
  )) ?? presentation.execution_traces.find((item) => item.action_id === issue.action_id)
}

function denyIntent(presentation: ResultPresentationDto | null) {
  return presentation?.relevant_intents.find((item) => item.expectation === 'DENY')
    ?? presentation?.relevant_intents[0]
    ?? null
}

function approvalFor(intent: ResultRelevantIntentDto | null, history: HistoryViewDto | null) {
  if (!intent || !history) return null
  const intentHistory = history.intents.find((item) => item.intent_id === intent.intent_id)
  return intentHistory?.revisions.find((item) => item.revision === intent.revision) ?? null
}

function intentLabel(intent: ResultRelevantIntentDto | null) {
  if (!intent) return '本次结果未发布权限编号'
  return intent.display_label?.trim() || intent.intent_id
}

function permissionStatement(intent: ResultRelevantIntentDto | null, issue: ResultPresentationIssueDto | null) {
  return intent?.business_statement?.trim()
    || issue?.expectation?.trim()
    || '本次结果没有发布可展示的业务权限句子。'
}

function presentationHeadline(presentation: ResultPresentationDto | null, issue: ResultPresentationIssueDto | null) {
  if (presentation?.verdict === 'BLOCK' && issue?.claim_boundary.business_effect_status === 'CONFIRMED') {
    return 'Bob 收到 403，但完整项目交付包仍在后台生成'
  }
  if (presentation?.verdict === 'PASS') return '修复成立，必须同时证明违规后果消失与合法功能保留'
  if (presentation?.verdict === 'INCONCLUSIVE') return '收到 403，但关键观察不可用，仍不能宣称安全'
  return '从权限要求，到真实业务后果'
}

export function PresentationMode({
  experience,
  projectName,
  runs,
  onExit,
  onOpenProductRoute,
}: {
  experience: OfficialExperienceDto
  projectName: string
  runs: RunDto[]
  onExit: () => void
  onOpenProductRoute: (path: '/results' | '/verification') => void
}) {
  const [page, setPage] = useState<PresentationPage>('conclusion')
  const [presentation, setPresentation] = useState<ResultPresentationDto | null>(null)
  const [sourcePresentation, setSourcePresentation] = useState<ResultPresentationDto | null>(null)
  const [history, setHistory] = useState<HistoryViewDto | null>(null)
  const [validation, setValidation] = useState<CompetitionValidationSummaryViewDto | null>(null)
  const [factsLoading, setFactsLoading] = useState(false)
  const [factsError, setFactsError] = useState<string | null>(null)
  const [retryEpoch, setRetryEpoch] = useState(0)
  const [drawer, setDrawer] = useState<EvidenceDrawerState>(null)
  const latest = useMemo(
    () => runs.find((item) => item.run_id && item.result_integrity === 'VERIFIED') ?? runs.find((item) => item.run_id),
    [runs],
  )
  const issue = mainIssue(presentation)
  const intent = denyIntent(presentation)
  const approval = approvalFor(intent, history)
  const current = pages.find((item) => item.key === page) ?? pages[0]

  useEffect(() => {
    let active = true
    void experienceApi.validationSummary().then((value) => {
      if (active) setValidation(value)
    }).catch(() => {
      if (active) setValidation({ available: false, unavailable_reason: '无法读取公开验证汇总', summary: null })
    })
    return () => { active = false }
  }, [retryEpoch])

  useEffect(() => {
    const runId = latest?.run_id
    const projectId = experience.project_id
    if (!runId || !projectId) {
      setPresentation(null)
      setSourcePresentation(null)
      setHistory(null)
      setFactsError(null)
      setFactsLoading(false)
      return
    }
    let active = true
    setFactsLoading(true)
    setFactsError(null)
    void (async () => {
      try {
        const [currentPresentation, currentHistory] = await Promise.all([
          resultsApi.presentation(runId),
          resultsApi.history(projectId),
        ])
        if (!active) return
        setPresentation(currentPresentation)
        setHistory(currentHistory)
        const sourceRunId = currentPresentation.repair_verification?.reference.source_run_id
        if (sourceRunId && sourceRunId !== runId) {
          try {
            const source = await resultsApi.presentation(sourceRunId)
            if (active) setSourcePresentation(source)
          } catch {
            if (active) setSourcePresentation(null)
          }
        } else {
          setSourcePresentation(null)
        }
      } catch {
        if (active) {
          setPresentation(null)
          setSourcePresentation(null)
          setHistory(null)
          setFactsError('无法读取当前 Run 的正式展示事实。')
        }
      } finally {
        if (active) setFactsLoading(false)
      }
    })()
    return () => { active = false }
  }, [experience.project_id, latest?.run_id, retryEpoch])

  const openEvidence = (title: string, explanations: ResultEvidenceExplanationDto[]) => {
    setDrawer({ title, explanations })
  }

  return <div className="presentation-mode">
    <header className="presentation-header">
      <div>
        <Typography.Text className="presentation-brand">界鉴 · 展示模式</Typography.Text>
        <Typography.Title level={1}>{presentationHeadline(presentation, issue)}</Typography.Title>
        <Typography.Text>{experience.display_name?.trim() || projectName} · 当前正式产品上下文</Typography.Text>
      </div>
      <div className="presentation-header-actions">
        <Tag className="presentation-data-tag">只读取正式产品数据</Tag>
        <Button onClick={onExit}>退出展示模式</Button>
      </div>
    </header>

    <div className="presentation-shell">
      <nav className="presentation-navigation" aria-label="展示页面">
        {pages.map((item) => <button
          aria-current={page === item.key ? 'page' : undefined}
          className={page === item.key ? 'is-active' : undefined}
          id={`presentation-tab-${item.key}`}
          key={item.key}
          onClick={() => setPage(item.key)}
          type="button"
        >
          <span>{item.index}</span>
          <strong>{item.label}</strong>
          <small>{item.summary}</small>
        </button>)}
      </nav>

      <main aria-labelledby={`presentation-tab-${page}`} className="presentation-content" id={`presentation-panel-${page}`}>
        <div className="presentation-page-heading">
          <Typography.Text className="presentation-kicker">{current.index} / {pages.length.toString().padStart(2, '0')}</Typography.Text>
          <Typography.Title level={2}>{current.label}</Typography.Title>
          <Typography.Paragraph>{current.summary}</Typography.Paragraph>
        </div>
        {page !== 'boundaries' && factsLoading && <Skeleton active paragraph={{ rows: 7 }} />}
        {page !== 'boundaries' && !factsLoading && factsError && <Alert
          action={<Button onClick={() => setRetryEpoch((value) => value + 1)}>重新读取</Button>}
          message={factsError}
          showIcon
          type="error"
        />}
        {page === 'conclusion' && !factsLoading && !factsError && <ConclusionPage
          experience={experience}
          run={latest}
          presentation={presentation}
          issue={issue}
          intent={intent}
          approval={approval}
        />}
        {page === 'live' && !factsLoading && !factsError && <LivePage
          presentation={presentation}
          issue={issue}
          intent={intent}
          approval={approval}
          onEvidence={openEvidence}
          onOpen={() => onOpenProductRoute('/verification')}
        />}
        {page === 'comparison' && !factsLoading && !factsError && <ComparisonPage
          presentation={presentation}
          sourcePresentation={sourcePresentation}
          issue={issue}
          onEvidence={openEvidence}
        />}
        {page === 'boundaries' && <BoundariesPage latest={latest} validation={validation} onOpen={() => onOpenProductRoute('/results')} />}
      </main>
    </div>
    <EvidenceExplanationDrawer open={drawer !== null} title={drawer?.title} explanations={drawer?.explanations ?? []} onClose={() => setDrawer(null)} />
  </div>
}

function ConclusionPage({ experience, run, presentation, issue, intent, approval }: {
  experience: OfficialExperienceDto
  run?: RunDto
  presentation: ResultPresentationDto | null
  issue: ResultPresentationIssueDto | null
  intent: ResultRelevantIntentDto | null
  approval: ResultIntentHistoryDto['revisions'][number] | null
}) {
  if (!run || !presentation) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前官方示例尚无正式检查结果；请退出展示模式，在正式产品中完成准备与检查。" />
  const trace = traceFor(issue, presentation)
  return <div className="presentation-page-body">
    <section className="presentation-permission-banner" aria-label="人确认的权限规则">
      <div><Typography.Text>人确认的业务规则</Typography.Text><Typography.Title level={3}>{permissionStatement(intent, issue)}</Typography.Title></div>
      <div className="presentation-permission-meta">
        <Tag color="red">{intent?.expectation ? expectationLabel(intent.expectation) : '预期未发布'}</Tag>
        <strong>{intentLabel(intent)} · 第 {intent?.revision ?? '—'} 版</strong>
        <span>{approval ? `${approval.approved_by} 已确认 · ${formatTimestamp(approval.approved_at_us)}` : '审批记录未随本次展示发布'}</span>
      </div>
    </section>
    {issue ? <ResultFactChain issue={issue} presentation /> : <Alert message="当前结果没有发布可展示的检查项" type="warning" showIcon />}
    <Typography.Text type="secondary">检查时间：{formatTimestamp(run.created_at_us ?? run.created_at)} · {lifecycleLabel(run.lifecycle ?? run.state)} · {integrityLabel(run.result_integrity)}</Typography.Text>
    <div className="presentation-fact-grid" aria-label="当次验证数字">
      <div><span>本轮覆盖权限项</span><strong>{presentation.checked_count}</strong></div>
      <div><span>已发布证据来源</span><strong>{issue?.evidence_sources.length ?? 0}</strong></div>
      <div><span>关联执行链节点</span><strong>{trace?.events.length ?? 0}</strong></div>
    </div>
    <Alert message={experience.active ? '这些内容来自当前官方示例的正式 Run。' : '官方示例已经停止，页面保留的是当前工作区正式事实。'} type="info" showIcon />
  </div>
}

function LivePage({ presentation, issue, intent, approval, onEvidence, onOpen }: {
  presentation: ResultPresentationDto | null
  issue: ResultPresentationIssueDto | null
  intent: ResultRelevantIntentDto | null
  approval: ResultIntentHistoryDto['revisions'][number] | null
  onEvidence: (title: string, explanations: ResultEvidenceExplanationDto[]) => void
  onOpen: () => void
}) {
  if (!presentation || !issue) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前还没有可供现场验证的完整正式结果。" />
  const trace = traceFor(issue, presentation)
  const relevance = issue.evidence_explanations.find((item) => item.relevance)?.relevance
  return <div className="presentation-page-body">
    <div className="presentation-live-grid">
      <section className="presentation-live-column" aria-labelledby="live-permission-title">
        <Typography.Text className="presentation-column-kicker">01 · 权限要求</Typography.Text>
        <Typography.Title id="live-permission-title" level={3}>{intentLabel(intent)}</Typography.Title>
        <Tag color="red">{intent?.expectation ? expectationLabel(intent.expectation) : '预期未发布'} · 第 {intent?.revision ?? '—'} 版</Tag>
        <Typography.Paragraph>{permissionStatement(intent, issue)}</Typography.Paragraph>
        <Typography.Text type="secondary">{approval ? `${approval.approved_by} 于 ${formatTimestamp(approval.approved_at_us)} 确认` : '本次展示未取得审批记录'}</Typography.Text>
      </section>
      <section className="presentation-live-column is-path" aria-labelledby="live-path-title">
        <Typography.Text className="presentation-column-kicker">02 · 实际执行</Typography.Text>
        <Typography.Title id="live-path-title" level={3}>403 之外，后台继续发生了什么</Typography.Title>
        <div className="presentation-surface-track"><span>表面响应轨</span><strong>{issue.surface_result}</strong></div>
        {trace ? <TracePath trace={trace} issue={issue} onEvidence={() => onEvidence('ZIP 为什么属于本轮', issue.evidence_explanations)} /> : <Alert message="当前结果没有发布完整执行链" type="warning" showIcon />}
      </section>
      <section className="presentation-live-column is-outcome" aria-labelledby="live-outcome-title">
        <Typography.Text className="presentation-column-kicker">03 · 真实后果</Typography.Text>
        <Typography.Title id="live-outcome-title" level={3}>{issue.actual_result}</Typography.Title>
        <Tag color={verdictTone(presentation.verdict)}>{verdictLabel(presentation.verdict ?? issue.verdict)}</Tag>
        <Typography.Paragraph>{issue.claim_boundary.supported_statement}</Typography.Paragraph>
        <dl className="presentation-diagnosis">
          <div><dt>断裂类型</dt><dd>{issue.diagnosis?.breakpoint_type ?? '未发布'}</dd></div>
          <div><dt>定位精度</dt><dd>{issue.diagnosis?.precision ?? '未发布'}</dd></div>
          <div><dt>授权连续性</dt><dd>{issue.diagnosis?.continuity_state ?? '未发布'}</dd></div>
        </dl>
      </section>
    </div>
    <Alert message="为什么 ZIP 属于本轮" description={relevance || '本次结果没有发布可展示的关联说明。'} type={relevance ? 'info' : 'warning'} showIcon />
    <div className="presentation-actions">
      <Button type="primary" onClick={() => onEvidence('ZIP 为什么属于本轮', issue.evidence_explanations)}>查看 ZIP 为什么属于本轮</Button>
      <Button onClick={onOpen}>进入正式产品核对完整结果</Button>
    </div>
    <Alert message="页面响应、后台任务、Worker 或 ZIP 都不能单独决定安全结论。" type="warning" showIcon />
  </div>
}

function TracePath({ trace, issue, onEvidence }: { trace: ExecutionTraceDto; issue: ResultPresentationIssueDto; onEvidence: () => void }) {
  const diagnosis = issue.diagnosis
  const start = trace.events.findIndex((item) => item.event_id === diagnosis?.range_start_event_id)
  const end = trace.events.findIndex((item) => item.event_id === diagnosis?.range_end_event_id)
  return <ol className="presentation-trace" aria-label="本轮后台执行链">
    {trace.events.map((event, index) => {
      const exact = event.event_id === diagnosis?.first_violation_event_id
      const ranged = diagnosis?.precision === 'RANGE' && start >= 0 && end >= start && index >= start && index <= end
      return <li className={exact ? 'is-breakpoint' : ranged ? 'is-range' : undefined} key={event.event_id}>
        <button type="button" aria-label={`查看“${traceLabels[event.kind]}”证据`} onClick={onEvidence}><span>{index + 1}</span></button>
        <div><strong>{traceLabels[event.kind]}</strong><small>{event.source_component}{event.authorization_decision ? ` · ${event.authorization_decision}` : ''}</small>{exact && <Tag color="red">首个可证明断裂</Tag>}{ranged && !exact && <Tag color="gold">断裂范围</Tag>}</div>
      </li>
    })}
    {!trace.complete && <li className="is-incomplete"><span>?</span><div><strong>后续路径未完整发布</strong><small>页面不会补画未知节点</small></div></li>}
  </ol>
}

function ComparisonPage({ presentation, sourcePresentation, issue, onEvidence }: {
  presentation: ResultPresentationDto | null
  sourcePresentation: ResultPresentationDto | null
  issue: ResultPresentationIssueDto | null
  onEvidence: (title: string, explanations: ResultEvidenceExplanationDto[]) => void
}) {
  if (!presentation) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前还没有正式的原考题复验结果。" />
  const verification = presentation.repair_verification
  if (!verification) return <div className="presentation-page-body"><Alert message="尚未形成原考题复验记录" description="本页不会根据一次问题检查推断修复已经完成。" type="warning" showIcon /><RepairResponsibilities /></div>
  const sourceIssue = sourcePresentation?.issues.find((item) => item.finding_id === verification.reference.source_finding_id) ?? sourcePresentation?.issues[0] ?? null
  const requirement = issue?.repair_requirement
  const sameIntent = presentation.relevant_intents.some((currentIntent) => sourcePresentation?.relevant_intents.some((sourceIntent) => (
    sourceIntent.intent_id === currentIntent.intent_id && sourceIntent.revision === currentIntent.revision && sourceIntent.intent_hash === currentIntent.intent_hash
  )))
  const verified = verification.status === 'VERIFIED'
  const orderedPaths = [
    'DENY_EFFECT_REMOVAL',
    'ALLOW_CONTROL',
    'REGRESSION_CONTROL',
  ].flatMap((kind) => verification.path_results.filter((item) => item.kind === kind))
  return <div className="presentation-page-body">
    <section className="presentation-repair-contract" aria-label="修复合同">
      <article><span>必须消失</span><strong>{requirement?.must_disappear || '原违规后果必须消失'}</strong></article>
      <article><span>必须保留</span><strong>{requirement?.must_remain || '合法业务能力必须保留'}</strong></article>
      <article><span>不能改变</span><strong>{requirement?.must_not_change.join('、') || '原权限和关键观察标准'}</strong></article>
    </section>
    <div className="presentation-before-after">
      <RepairRunCard label="修复前" presentation={sourcePresentation} issue={sourceIssue} />
      <div className="presentation-repair-arrow" aria-hidden="true">→</div>
      <RepairRunCard label="修复后" presentation={presentation} issue={issue} />
    </div>
    <section aria-labelledby="repair-paths-title">
      <Typography.Title id="repair-paths-title" level={3}>三条路径分别核对</Typography.Title>
      <div className="presentation-repair-paths">
        {orderedPaths.length > 0 ? orderedPaths.map((path) => (
          <RepairPath
            key={`${path.kind}:${path.action_id}:${path.subject_id}`}
            title={`${path.subject_display_name} ${path.action_display_name}`}
            status={path.status}
            detail={path.message}
          />
        )) : <>
          <RepairPath title="Bob 导出完整项目交付包" status={verification.status} detail={verified ? '原违规业务后果已被完整证明消失。' : verification.message} />
          <RepairPath title="Alice 导出完整项目交付包" status={verification.status} detail={verified ? 'Alice 的合法导出仍然正常完成。' : '当前复验尚未证明合法导出保持正常。'} />
          <RepairPath title="Bob 查看日常协作资料" status="PENDING" detail="旧结果没有发布这条独立非回归事实。" />
        </>}
      </div>
    </section>
    <div className="presentation-consistency-grid" aria-label="修复前后一致性">
      <div><span>权限规则版本</span><strong>{sameIntent ? '保持一致' : '未能确认一致'}</strong></div>
      <div><span>身份关系</span><strong>{verified ? '由修复合同保持' : '尚未确认'}</strong></div>
      <div><span>关键观察标准</span><strong>{verified ? '未降低' : '尚未确认'}</strong></div>
    </div>
    <Alert message={repairStatusLabel(verification.status)} description={verification.message} type={verified ? 'success' : verification.status === 'NOT_VERIFIED' ? 'error' : 'warning'} showIcon />
    {issue && <Button onClick={() => onEvidence('原考题复验证据', [...(sourceIssue?.evidence_explanations ?? []), ...issue.evidence_explanations])}>查看为什么这次通过不是因为关闭功能</Button>}
  </div>
}

function RepairResponsibilities() {
  return <div className="presentation-repair-paths"><RepairPath title="Bob 导出完整项目交付包" status="PENDING" detail="等待新的原考题复验记录。" /><RepairPath title="Alice 导出完整项目交付包" status="PENDING" detail="等待合法导出能力的对照事实。" /><RepairPath title="Bob 查看日常协作资料" status="PENDING" detail="等待独立的功能保持事实。" /></div>
}

function RepairRunCard({ label, presentation, issue }: { label: string; presentation: ResultPresentationDto | null; issue: ResultPresentationIssueDto | null }) {
  return <article className="presentation-repair-run"><span>{label}</span><Tag color={verdictTone(presentation?.verdict)}>{presentation?.verdict ? verdictLabel(presentation.verdict) : '事实不可用'}</Tag><strong>{issue?.actual_result || '未取得对应正式路径'}</strong><small>{presentation ? `检查记录 ${presentation.run_id}` : '原检查记录无法读取'}</small></article>
}

function RepairPath({ title, status, detail }: { title: string; status: 'VERIFIED' | 'NOT_VERIFIED' | 'INCONCLUSIVE' | 'PENDING'; detail: string }) {
  const tone = status === 'VERIFIED' ? 'success' : status === 'NOT_VERIFIED' ? 'error' : 'warning'
  const label = repairStatusLabel(status)
  return <article><div><strong>{title}</strong><Tag color={tone}>{label}</Tag></div><p>{detail}</p></article>
}

function repairStatusLabel(status: 'VERIFIED' | 'NOT_VERIFIED' | 'INCONCLUSIVE' | 'PENDING') {
  return status === 'VERIFIED' ? '已验证' : status === 'NOT_VERIFIED' ? '未通过' : status === 'INCONCLUSIVE' ? '证据不足' : '尚未证明'
}

function BoundariesPage({ latest, validation, onOpen }: { latest?: RunDto; validation: CompetitionValidationSummaryViewDto | null; onOpen: () => void }) {
  const summary = validation?.summary
  const fullWrong = summary ? summary.full_wrong_pass_vulnerable + summary.full_wrong_pass_evidence_gap : 0
  const httpWrong = summary ? summary.http_wrong_pass_vulnerable + summary.http_wrong_pass_evidence_gap : 0
  return <div className="presentation-page-body">
    <div className="presentation-source-strip" aria-label="两类数据来源">
      <div><span>官方样例事实</span><strong>{latest?.run_id ? '当前正式 Run' : '尚无正式 Run'}</strong></div>
      <div><span>方法验证数据</span><strong>{summary ? `sample-test ${summary.suite}` : '尚未发布'}</strong></div>
    </div>
    {!summary && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={validation?.unavailable_reason || '正在读取公开验证汇总'} />}
    {summary && <>
      <div className="presentation-fact-grid" aria-label="公开验证关键数字">
        <div><span>固定验证矩阵</span><strong>{summary.case_count} Case</strong></div>
        <div><span>完整方法与预期一致</span><strong>{summary.full_exact_match_count}/{summary.case_run_count}</strong></div>
        <div><span>HTTP-only 每轮 wrong PASS</span><strong>{summary.http_wrong_pass_per_matrix}</strong></div>
      </div>
      <section className="presentation-method-comparison" aria-labelledby="method-comparison-title">
        <Typography.Title id="method-comparison-title" level={3}>完整方法与只看 HTTP 的差别</Typography.Title>
        <div>
          <article className="is-safe"><span>界鉴完整方法</span><strong>{summary.full_exact_match_count}/{summary.case_run_count} 匹配</strong><p>漏洞错判 PASS：{summary.full_wrong_pass_vulnerable}；证据缺口错判 PASS：{summary.full_wrong_pass_evidence_gap}。</p></article>
          <article className="is-danger"><span>HTTP-only 基线</span><strong>{summary.http_exact_match_count}/{summary.case_run_count} 匹配</strong><p>共 {httpWrong} 个 wrong PASS：漏洞 {summary.http_wrong_pass_vulnerable}，证据缺口 {summary.http_wrong_pass_evidence_gap}。</p></article>
        </div>
        {fullWrong === 0 && <Alert message="完整方法没有把本矩阵中的漏洞或证据缺口判成 PASS。" type="success" showIcon />}
      </section>
      <section className="presentation-validation-scope" aria-labelledby="validation-scope-title">
        <Typography.Title id="validation-scope-title" level={3}>这些数字只适用于什么范围</Typography.Title>
        <p>{summary.application_count} 个应用 × {summary.mode_count} 种权限断裂模式 × {summary.state_count} 种状态；独立执行 {summary.repetitions} 轮，共 {summary.case_run_count} 次 Case 运行。</p>
        <p>生成时间：{formatTimestamp(summary.generated_at_us)} · 代码来源：{summary.source_revision ? summary.source_revision.slice(0, 12) : '未取得 Git 版本'}{summary.source_dirty === true ? '（含未提交改动）' : summary.source_dirty === false ? '（工作树干净）' : ''}</p>
      </section>
    </>}
    <section className="presentation-boundaries" aria-labelledby="boundaries-title">
      <Typography.Title id="boundaries-title" level={3}>不能据此宣称</Typography.Title>
      <ul><li>不能代表任意 Web 应用的漏洞检出率或现实世界漏洞发生比例。</li><li>不能证明所有权限漏洞、未知失效模式或未来 Target 都能被发现。</li><li>tests-only 应用不是生产应用；验证矩阵也不是 Coding Agent 的现实漏洞率。</li><li>不能宣称模型安全完全没有进步；这里只证明功能能力不能替代独立安全验证。</li></ul>
    </section>
    {latest && <Button onClick={onOpen}>返回正式产品查看完整结果</Button>}
  </div>
}
