// 展示模式把同一官方样例的正式权限、变化、证据和修复历史重排为四幕，不创建演示结论。

import { Alert, Button, Empty, Skeleton, Tag, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import type { OfficialExperienceDto } from '../../api/experience'
import {
  resultsApi,
  type ExecutionTraceDto,
  type HistoryViewDto,
  type ResultDiagnosisDto,
  type ResultEvidenceExplanationDto,
  type ResultIntentHistoryDto,
  type ResultPresentationDto,
  type ResultPresentationIssueDto,
  type ResultRelevantIntentDto,
} from '../../api/results'
import type { RunDto } from '../../api/runs'
import { sourceChangesApi, type SourceChangeViewDto } from '../../api/sourceChanges'
import { expectationLabel, formatTimestamp, integrityLabel, lifecycleLabel, traceEventLabel, verdictLabel } from '../../app/presentation'
import { EvidenceExplanationDrawer } from '../checks/EvidenceExplanationDrawer'
import './PresentationMode.css'

type PresentationAct = 'conflict' | 'change' | 'evidence' | 'repair'
type ProductRoute = '/changes' | '/results' | '/verification' | '/validation'
type EvidenceDrawerState = { title: string; explanations: ResultEvidenceExplanationDto[] } | null

const acts: Array<{ key: PresentationAct; index: string; label: string; summary: string; title: string }> = [
  { key: 'conflict', index: '01', label: '发现矛盾', summary: '403 与 ZIP 同时成立', title: 'Bob 收到 403，完整项目交付包却仍在后台生成' },
  { key: 'change', index: '02', label: '回看变化', summary: '核对提交来源与真实文件变化', title: '执行方式发生了变化，但人的权限规则没有改变' },
  { key: 'evidence', index: '03', label: '展开证据', summary: '定位首个可证明断裂', title: '403 只说明表面拒绝，证据链才说明真实后果' },
  { key: 'repair', index: '04', label: '验证修复', summary: '用原考题检查三条路径', title: '修复不是关闭功能，而是让同一权限规则重新贯穿执行链' },
]

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

function breakpointLabel(value: ResultDiagnosisDto['breakpoint_type'] | undefined) {
  const labels: Record<string, string> = {
    AUTHORIZATION_MISSING: '没有执行权限判断',
    AUTHORIZATION_LATE: '权限判断发生过晚',
    AUTHORIZATION_BYPASS: '绕过了权限判断',
    IDENTITY_SUBSTITUTION: '实际账号发生替换',
    AUTHORITY_EXPANSION: '后台权限范围被扩大',
    COMPENSATION_MASKING: '后续补偿掩盖了前序后果',
  }
  return value ? labels[value] ?? '断裂类型未识别' : '未发布'
}

function precisionLabel(value: ResultDiagnosisDto['precision'] | undefined) {
  return value === 'EXACT' ? '精确到单一节点' : value === 'RANGE' ? '只能定位到一段路径' : value === 'VIOLATION_ONLY' ? '仅确认存在断裂' : '未发布'
}

function continuityLabel(value: ResultDiagnosisDto['continuity_state'] | undefined) {
  return value === 'INTACT' ? '权限规则保持贯穿' : value === 'ORPHAN_EFFECT_CONFIRMED' ? '已确认存在未受权限约束的后果' : value === 'UNKNOWN' ? '现有证据不足以确认' : '未发布'
}

export function PresentationMode({ experience, projectName, runs, onExit, onOpenProductRoute }: {
  experience: OfficialExperienceDto
  projectName: string
  runs: RunDto[]
  onExit: () => void
  onOpenProductRoute: (path: ProductRoute) => void
}) {
  const [act, setAct] = useState<PresentationAct>('conflict')
  const [presentation, setPresentation] = useState<ResultPresentationDto | null>(null)
  const [sourcePresentation, setSourcePresentation] = useState<ResultPresentationDto | null>(null)
  const [storyChange, setStoryChange] = useState<SourceChangeViewDto | null>(null)
  const [repairChange, setRepairChange] = useState<SourceChangeViewDto | null>(null)
  const [history, setHistory] = useState<HistoryViewDto | null>(null)
  const [factsLoading, setFactsLoading] = useState(false)
  const [factsError, setFactsError] = useState<string | null>(null)
  const [retryEpoch, setRetryEpoch] = useState(0)
  const [drawer, setDrawer] = useState<EvidenceDrawerState>(null)
  const latest = useMemo(
    () => runs.find((item) => item.run_id && item.result_integrity === 'VERIFIED') ?? runs.find((item) => item.run_id),
    [runs],
  )
  const failurePresentation = sourcePresentation ?? (presentation?.verdict === 'BLOCK' ? presentation : null)
  const failureIssue = mainIssue(failurePresentation ?? presentation)
  const currentIssue = mainIssue(presentation)
  const intent = denyIntent(failurePresentation ?? presentation)
  const approval = approvalFor(intent, history)
  const current = acts.find((item) => item.key === act) ?? acts[0]
  const currentIndex = acts.findIndex((item) => item.key === act)

  useEffect(() => {
    const runId = latest?.run_id
    const projectId = experience.project_id
    if (!runId || !projectId) {
      setPresentation(null)
      setSourcePresentation(null)
      setStoryChange(null)
      setRepairChange(null)
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
        let source: ResultPresentationDto | null = null
        const sourceRunId = currentPresentation.repair_verification?.reference.source_run_id
        if (sourceRunId && sourceRunId !== runId) {
          try {
            source = await resultsApi.presentation(sourceRunId)
          } catch {
            source = null
          }
        }
        const failure = source ?? (currentPresentation.verdict === 'BLOCK' ? currentPresentation : null)
        const storyChangeId = failure?.change_verification?.change_id
        const repairChangeId = currentPresentation.repair_verification ? currentPresentation.change_verification?.change_id : null
        const [loadedStoryChange, loadedRepairChange] = await Promise.all([
          storyChangeId ? sourceChangesApi.show(projectId, storyChangeId).catch(() => null) : Promise.resolve(null),
          repairChangeId ? sourceChangesApi.show(projectId, repairChangeId).catch(() => null) : Promise.resolve(null),
        ])
        if (!active) return
        setPresentation(currentPresentation)
        setSourcePresentation(source)
        setStoryChange(loadedStoryChange)
        setRepairChange(loadedRepairChange)
        setHistory(currentHistory)
      } catch {
        if (active) {
          setPresentation(null)
          setSourcePresentation(null)
          setStoryChange(null)
          setRepairChange(null)
          setHistory(null)
          setFactsError('无法读取这个故事所需的正式权限、变化和运行事实。')
        }
      } finally {
        if (active) setFactsLoading(false)
      }
    })()
    return () => { active = false }
  }, [experience.project_id, latest?.run_id, retryEpoch])

  const openEvidence = (title: string, explanations: ResultEvidenceExplanationDto[]) => setDrawer({ title, explanations })
  const goTo = (index: number) => setAct(acts[Math.max(0, Math.min(acts.length - 1, index))].key)

  return <div className="presentation-mode">
    <header className="presentation-header">
      <div>
        <Typography.Text className="presentation-brand">界鉴 · 一例四幕</Typography.Text>
        <Typography.Title level={1}>校园数字展馆：一次权限断裂的完整复验</Typography.Title>
        <Typography.Text>{experience.display_name?.trim() || projectName} · 当前正式产品上下文</Typography.Text>
      </div>
      <div className="presentation-header-actions"><Tag className="presentation-data-tag">只读取正式事实</Tag><Button onClick={onExit}>返回工作台</Button></div>
    </header>

    <div className="presentation-shell">
      <nav className="presentation-navigation" aria-label="展示章节">
        {acts.map((item) => <button aria-current={act === item.key ? 'step' : undefined} className={act === item.key ? 'is-active' : undefined} id={`presentation-tab-${item.key}`} key={item.key} onClick={() => setAct(item.key)} type="button">
          <span>{item.index}</span><strong>{item.label}</strong><small>{item.summary}</small>
        </button>)}
      </nav>
      <main aria-labelledby={`presentation-tab-${act}`} className="presentation-content" id={`presentation-panel-${act}`}>
        <div className="presentation-page-heading"><Typography.Text className="presentation-kicker">{current.index} / 04</Typography.Text><Typography.Title level={2}>{current.title}</Typography.Title><Typography.Paragraph>{current.summary}</Typography.Paragraph></div>
        {factsLoading && <Skeleton active paragraph={{ rows: 7 }} />}
        {!factsLoading && factsError && <Alert action={<Button onClick={() => setRetryEpoch((value) => value + 1)}>重新读取</Button>} message={factsError} showIcon type="error" />}
        {!factsLoading && !factsError && act === 'conflict' && <ConflictAct run={sourcePresentation ? runs.find((item) => item.run_id === sourcePresentation.run_id) ?? latest : latest} presentation={failurePresentation ?? presentation} issue={failureIssue} intent={intent} approval={approval} onEvidence={openEvidence} />}
        {!factsLoading && !factsError && act === 'change' && <ChangeAct change={storyChange} intent={intent} issue={failureIssue} approval={approval} onOpen={() => onOpenProductRoute('/changes')} />}
        {!factsLoading && !factsError && act === 'evidence' && <EvidenceAct presentation={failurePresentation ?? presentation} issue={failureIssue} intent={intent} onEvidence={openEvidence} onOpen={() => onOpenProductRoute('/verification')} />}
        {!factsLoading && !factsError && act === 'repair' && <RepairAct presentation={presentation} sourcePresentation={sourcePresentation} issue={currentIssue} repairChange={repairChange} onEvidence={openEvidence} onOpenValidation={() => onOpenProductRoute('/validation')} />}
        <div className="presentation-act-actions" aria-label="展示章节操作">
          <Button disabled={currentIndex === 0} onClick={() => goTo(currentIndex - 1)}>上一幕</Button>
          <Typography.Text type="secondary">{current.label} · {currentIndex + 1}/{acts.length}</Typography.Text>
          {currentIndex < acts.length - 1 ? <Button type="primary" onClick={() => goTo(currentIndex + 1)}>下一幕：{acts[currentIndex + 1].label}</Button> : <Button type="primary" onClick={onExit}>返回正式工作台</Button>}
        </div>
      </main>
    </div>
    <EvidenceExplanationDrawer open={drawer !== null} title={drawer?.title} explanations={drawer?.explanations ?? []} onClose={() => setDrawer(null)} />
  </div>
}

function ConflictAct({ run, presentation, issue, intent, approval, onEvidence }: {
  run?: RunDto
  presentation: ResultPresentationDto | null
  issue: ResultPresentationIssueDto | null
  intent: ResultRelevantIntentDto | null
  approval: ResultIntentHistoryDto['revisions'][number] | null
  onEvidence: (title: string, explanations: ResultEvidenceExplanationDto[]) => void
}) {
  if (!run || !presentation || !issue) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前官方示例还没有形成可展示的正式问题 Run。" />
  return <div className="presentation-page-body">
    <section className="presentation-permission-banner" aria-label="人确认的权限规则">
      <div><Typography.Text>人确认的权限考题</Typography.Text><Typography.Title level={3}>{permissionStatement(intent, issue)}</Typography.Title></div>
      <div className="presentation-permission-meta"><Tag color="red">{intent?.expectation ? expectationLabel(intent.expectation) : '预期未发布'}</Tag><strong>{intentLabel(intent)} · 第 {intent?.revision ?? '—'} 版</strong><span>{approval ? `${approval.approved_by} 已确认 · ${formatTimestamp(approval.approved_at_us)}` : '审批记录未随本次展示发布'}</span></div>
    </section>
    <section className="presentation-conflict" aria-label="403 与 ZIP 的矛盾">
      <article><span>页面回应</span><strong>{issue.surface_result}</strong><p>用户看到请求已经被拒绝。</p></article>
      <div aria-hidden="true"><span>但是</span></div>
      <article className="is-danger"><span>后台真实后果</span><strong>{issue.actual_result}</strong><p>{issue.claim_boundary.supported_statement}</p></article>
    </section>
    <div className="presentation-conflict-conclusion"><Tag color={verdictTone(presentation.verdict)}>{verdictLabel(presentation.verdict ?? issue.verdict)}</Tag><Typography.Title level={3}>{issue.conclusion}</Typography.Title><Button type="primary" onClick={() => onEvidence('ZIP 为什么属于本轮', issue.evidence_explanations)}>为什么确定 ZIP 属于本轮？</Button></div>
    <Typography.Text type="secondary">{formatTimestamp(run.created_at_us ?? run.created_at)} · {lifecycleLabel(run.lifecycle ?? run.state)} · {integrityLabel(run.result_integrity)}</Typography.Text>
  </div>
}

function ChangeAct({ change, intent, issue, approval, onOpen }: {
  change: SourceChangeViewDto | null
  intent: ResultRelevantIntentDto | null
  issue: ResultPresentationIssueDto | null
  approval: ResultIntentHistoryDto['revisions'][number] | null
  onOpen: () => void
}) {
  if (!change) return <div className="presentation-page-body"><Alert message="当前问题 Run 没有可读取的关联变化" description="界鉴不会把最近一条无关变化拼接到这个故事中。" type="warning" showIcon /><Button onClick={onOpen}>查看正式变化记录</Button></div>
  const actualPaths = [...change.added_paths.map((path) => ({ label: '新增', path })), ...change.modified_paths.map((path) => ({ label: '修改', path })), ...change.removed_paths.map((path) => ({ label: '删除', path }))]
  const submittedThroughMcp = change.submitted_by.startsWith('MCP')
  return <div className="presentation-page-body">
    <section className="presentation-change-flow" aria-label="人的规则、提交变化与界鉴核对">
      <article><span>人的权限基线</span><strong>{permissionStatement(intent, issue)}</strong><small>{approval ? `${approval.approved_by} 已确认` : '审批记录未发布'}</small></article><div aria-hidden="true">→</div>
      <article className="is-agent"><span>变化提交记录</span><strong>{change.reason}</strong><small>{change.submitted_by} · {formatTimestamp(change.created_at_us)}</small></article><div aria-hidden="true">→</div>
      <article className="is-system"><span>界鉴独立核对</span><strong>实际变化 {change.actual_changed_path_count} 个文件</strong><small>直接影响 {change.directly_affected_count} 条权限规则</small></article>
    </section>
    <section className="presentation-change-receipt" aria-label="变化来源、回执与检查关联">
      <div><span>提交来源</span><strong>{change.submitted_by}</strong></div>
      <div><span>{submittedThroughMcp ? 'MCP 提交回执' : '变化登记回执'}</span><strong>界鉴已登记这次变化</strong><small>{change.change_id}</small></div>
      <div><span>检查关联</span><strong>由本次问题检查精确引用</strong><small>不使用“最近一条变化”推测</small></div>
    </section>
    <Alert type="info" showIcon message={change.summary} description="Agent 说明只解释修改意图；文件数量、真实路径和权限影响来自界鉴重新读取源码后的结果。" />
    <section className="presentation-change-detail" aria-label="声明变化与实际变化">
      <article><Typography.Text strong>Agent 声明会修改</Typography.Text>{change.claimed_paths.length ? <ul>{change.claimed_paths.map((path) => <li key={path}><Typography.Text code>{path}</Typography.Text></li>)}</ul> : <Typography.Paragraph type="secondary">Agent 没有声明具体路径。</Typography.Paragraph>}</article>
      <article><Typography.Text strong>界鉴实际确认</Typography.Text>{actualPaths.length ? <ul>{actualPaths.map((item) => <li key={`${item.label}:${item.path}`}><span>{item.label}</span><Typography.Text code>{item.path}</Typography.Text></li>)}</ul> : <Typography.Paragraph type="secondary">当前变化没有形成可比较的文件差异。</Typography.Paragraph>}</article>
    </section>
    <div className="presentation-actions"><Tag color={submittedThroughMcp ? 'blue' : 'default'}>{change.submitted_by}</Tag><Button onClick={onOpen}>查看完整变化记录</Button></div>
  </div>
}

function EvidenceAct({ presentation, issue, intent, onEvidence, onOpen }: {
  presentation: ResultPresentationDto | null
  issue: ResultPresentationIssueDto | null
  intent: ResultRelevantIntentDto | null
  onEvidence: (title: string, explanations: ResultEvidenceExplanationDto[]) => void
  onOpen: () => void
}) {
  if (!presentation || !issue) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前还没有可展开的正式证据链。" />
  const trace = traceFor(issue, presentation)
  const relevance = issue.evidence_explanations.find((item) => item.relevance)?.relevance
  return <div className="presentation-page-body">
    <section className="presentation-evidence-grid" aria-label="权限要求、实际执行与真实后果">
      <article><Typography.Text className="presentation-column-kicker">预期路径</Typography.Text><Typography.Title level={3}>识别 Bob → 权限拒绝 → 停止</Typography.Title><Tag color="red">{intent?.expectation ? expectationLabel(intent.expectation) : '预期未发布'}</Tag><Typography.Paragraph>{permissionStatement(intent, issue)}</Typography.Paragraph></article>
      <article className="is-path"><Typography.Text className="presentation-column-kicker">实际路径</Typography.Text><div className="presentation-surface-track"><span>表面响应轨</span><strong>{issue.surface_result}</strong></div>{trace ? <TracePath trace={trace} issue={issue} onEvidence={() => onEvidence('本轮证据怎样关联', issue.evidence_explanations)} /> : <Alert message="当前结果没有发布完整执行链" type="warning" showIcon />}</article>
      <article className="is-outcome"><Typography.Text className="presentation-column-kicker">真实后果</Typography.Text><Typography.Title level={3}>{issue.actual_result}</Typography.Title><Tag color={verdictTone(presentation.verdict)}>{verdictLabel(presentation.verdict ?? issue.verdict)}</Tag><dl className="presentation-diagnosis"><div><dt>断裂类型</dt><dd>{breakpointLabel(issue.diagnosis?.breakpoint_type)}</dd></div><div><dt>定位精度</dt><dd>{precisionLabel(issue.diagnosis?.precision)}</dd></div><div><dt>权限规则是否贯穿</dt><dd>{continuityLabel(issue.diagnosis?.continuity_state)}</dd></div></dl></article>
    </section>
    <Alert message="为什么这些事实属于本轮" description={relevance || '本次结果没有发布可展示的关联说明。'} type={relevance ? 'info' : 'warning'} showIcon />
    <div className="presentation-actions"><Button type="primary" onClick={() => onEvidence('本轮证据怎样关联', issue.evidence_explanations)}>展开每种证据能证明什么</Button><Button onClick={onOpen}>在正式产品中挑战证据不足</Button></div>
    <Typography.Text type="secondary">页面响应、后台任务、Worker 或 ZIP 都不能单独决定安全结论。</Typography.Text>
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
      return <li className={exact ? 'is-breakpoint' : ranged ? 'is-range' : undefined} key={event.event_id}><button type="button" aria-label={`查看“${traceEventLabel(event)}”证据`} onClick={onEvidence}><span>{index + 1}</span></button><div><strong>{traceEventLabel(event)}</strong><small>{event.source_component}{event.authorization_decision ? ` · ${event.authorization_decision}` : ''}</small>{exact && <Tag color="red">首个可证明断裂</Tag>}{ranged && !exact && <Tag color="gold">断裂范围</Tag>}</div></li>
    })}
    {!trace.complete && <li className="is-incomplete"><span>?</span><div><strong>后续路径未完整发布</strong><small>页面不会补画未知节点</small></div></li>}
  </ol>
}

function RepairAct({ presentation, sourcePresentation, issue, repairChange, onEvidence, onOpenValidation }: {
  presentation: ResultPresentationDto | null
  sourcePresentation: ResultPresentationDto | null
  issue: ResultPresentationIssueDto | null
  repairChange: SourceChangeViewDto | null
  onEvidence: (title: string, explanations: ResultEvidenceExplanationDto[]) => void
  onOpenValidation: () => void
}) {
  if (!presentation) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前还没有正式的原考题复验结果。" />
  const verification = presentation.repair_verification
  if (!verification) return <div className="presentation-page-body"><Alert message="尚未形成原考题复验记录" description="本幕不会根据一次问题检查推断修复已经完成。" type="warning" showIcon /><RepairResponsibilities /><Button type="primary" onClick={onOpenValidation}>进入正式产品准备复验</Button></div>
  const sourceIssue = sourcePresentation?.issues.find((item) => item.finding_id === verification.reference.source_finding_id) ?? sourcePresentation?.issues[0] ?? null
  const requirement = issue?.repair_requirement
  const sameIntent = presentation.relevant_intents.some((currentIntent) => sourcePresentation?.relevant_intents.some((sourceIntent) => sourceIntent.intent_id === currentIntent.intent_id && sourceIntent.revision === currentIntent.revision && sourceIntent.intent_hash === currentIntent.intent_hash))
  const verified = verification.status === 'VERIFIED'
  const orderedPaths = ['DENY_EFFECT_REMOVAL', 'ALLOW_CONTROL', 'REGRESSION_CONTROL'].flatMap((kind) => verification.path_results.filter((item) => item.kind === kind))
  return <div className="presentation-page-body">
    {repairChange && <div className="presentation-repair-change"><span>修复变化</span><strong>{repairChange.reason}</strong><small>{repairChange.submitted_by} · 实际修改 {repairChange.actual_changed_path_count} 个文件</small></div>}
    <section className="presentation-repair-contract" aria-label="修复合同"><article><span>必须消失</span><strong>{requirement?.must_disappear || '原违规后果必须消失'}</strong></article><article><span>必须保留</span><strong>{requirement?.must_remain || '合法业务能力必须保留'}</strong></article><article><span>不能改变</span><strong>{requirement?.must_not_change.join('、') || '原权限和关键观察标准'}</strong></article></section>
    <div className="presentation-before-after"><RepairRunCard label="修复前" presentation={sourcePresentation} issue={sourceIssue} /><div className="presentation-repair-arrow" aria-hidden="true">→</div><RepairRunCard label="修复后" presentation={presentation} issue={issue} /></div>
    <section aria-labelledby="repair-paths-title"><Typography.Title id="repair-paths-title" level={3}>三条路径分别核对</Typography.Title><div className="presentation-repair-paths">
      {orderedPaths.length > 0 ? orderedPaths.map((path) => <RepairPath key={`${path.kind}:${path.action_id}:${path.subject_id}`} title={`${path.subject_display_name} ${path.action_display_name}`} status={path.status} detail={path.message} />) : <><RepairPath title="Bob 导出完整项目交付包" status={verification.status} detail={verified ? '原违规业务后果已被完整证明消失。' : verification.message} /><RepairPath title="Alice 导出完整项目交付包" status={verification.status} detail={verified ? 'Alice 的合法导出仍然正常完成。' : '当前复验尚未证明合法导出保持正常。'} /><RepairPath title="Bob 查看日常协作资料" status="PENDING" detail="旧结果没有发布这条独立非回归事实。" /></>}
    </div></section>
    <div className="presentation-consistency-grid" aria-label="修复前后一致性"><div><span>权限规则版本</span><strong>{sameIntent ? '保持一致' : '未能确认一致'}</strong></div><div><span>身份关系</span><strong>{verified ? '由修复合同保持' : '尚未确认'}</strong></div><div><span>关键观察标准</span><strong>{verified ? '未降低' : '尚未确认'}</strong></div></div>
    <Alert message={repairStatusLabel(verification.status)} description={verification.message} type={verified ? 'success' : verification.status === 'NOT_VERIFIED' ? 'error' : 'warning'} showIcon />
    <div className="presentation-actions">{issue && <Button onClick={() => onEvidence('原考题复验证据', [...(sourceIssue?.evidence_explanations ?? []), ...issue.evidence_explanations])}>查看为什么这次通过不是因为关闭功能</Button>}<Button type="primary" onClick={onOpenValidation}>重新验证当前修复</Button></div>
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
  return <article><div><strong>{title}</strong><Tag color={tone}>{repairStatusLabel(status)}</Tag></div><p>{detail}</p></article>
}

function repairStatusLabel(status: 'VERIFIED' | 'NOT_VERIFIED' | 'INCONCLUSIVE' | 'PENDING') {
  return status === 'VERIFIED' ? '已验证' : status === 'NOT_VERIFIED' ? '未通过' : status === 'INCONCLUSIVE' ? '证据不足' : '尚未证明'
}
