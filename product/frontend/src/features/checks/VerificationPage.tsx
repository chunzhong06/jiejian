/* =============================================================================
 * 现场验证
 *
 * 定位
 *   把一次已发布 Run 的权限考题、实际业务路径与可支持主张并列展示。
 *
 * 职责
 *   只读取 ResultPresentation/ExecutionTrace/ResultDiagnosis｜按断点精度限制视觉主张
 *   ｜展示证据边界与修复前后对照｜把 AI 解释放在确定性事实之后。
 *
 * 边界
 *   不读取 live Ledger，不从时间或文本重算 Verdict，不制造示例结果。
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Collapse, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi, type ExecutionTraceDto, type ResultDiagnosisDto, type ResultPresentationDto, type ResultPresentationIssueDto } from '../../api/results'
import { runsApi, type RunDto } from '../../api/runs'
import { expectationLabel } from '../../app/presentation'
import { AssistantPanel } from '../../components/AssistantPanel'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { TaskActionBar } from '../../components/TaskActionBar'
import { EvidenceExplanationDrawer } from './EvidenceExplanationDrawer'
import './checks.css'

const eventLabels: Record<string, string> = {
  ENTRY: '请求进入目标应用',
  IDENTITY: '目标应用识别账号',
  AUTHORIZATION: '应用作出权限判断',
  PERSISTENT_EFFECT: '业务状态发生变化',
  MESSAGE: '任务进入消息链路',
  DELEGATION: '后台任务继续处理',
  FINAL_EFFECT: '最终业务结果形成',
  RECOVERY: '测试现场得到恢复',
}

function claimValue(value: string | null) {
  return ({
    ACCEPTED: '页面或接口接受了操作', DENIED: '页面或接口拒绝了操作', FAILED: '操作执行失败', UNKNOWN: '表面响应无法确认',
    CONFIRMED: '已确认受保护业务后果发生', ABSENT: '未发现受保护业务后果',
    UNAVAILABLE: '实际执行身份无法独立确认', EXACT: '已定位唯一断裂点', RANGE: '只能定位断裂区间',
    VIOLATION_ONLY: '已确认违规，但不能定位断裂点', VERIFIED: '原考题复验已通过', NOT_VERIFIED: '原考题复验未通过',
    INCONCLUSIVE: '原考题复验证据仍不足',
  } as Record<string, string>)[String(value)] ?? '当前没有形成这项事实'
}

function traceFor(issue: ResultPresentationIssueDto, presentation: ResultPresentationDto) {
  if (!issue.diagnosis) return undefined
  return presentation.execution_traces.find((item) => item.case_id === issue.diagnosis?.case_id && item.action_id === issue.diagnosis?.action_id)
}

function eventState(issue: ResultPresentationIssueDto, diagnosis: ResultDiagnosisDto | null, trace: ExecutionTraceDto, eventId: string) {
  if (!diagnosis || issue.verdict === 'INCONCLUSIVE') return ''
  if (diagnosis.precision === 'EXACT' && diagnosis.first_violation_event_id === eventId) return 'is-exact-break'
  if (diagnosis.precision === 'RANGE') {
    const current = trace.events.findIndex((event) => event.event_id === eventId)
    const start = trace.events.findIndex((event) => event.event_id === diagnosis.range_start_event_id)
    const end = trace.events.findIndex((event) => event.event_id === diagnosis.range_end_event_id)
    if (start >= 0 && end >= start && current >= start && current <= end) {
      return `is-range-segment ${current === start || current === end ? 'is-range-boundary' : ''}`.trim()
    }
  }
  return ''
}

function VerificationPath({ issue, trace, compact = false, onEvidence }: { issue: ResultPresentationIssueDto; trace?: ExecutionTraceDto; compact?: boolean; onEvidence?: () => void }) {
  const diagnosis = issue.diagnosis
  return <section className={`verification-path ${compact ? 'is-compact' : ''}`} aria-label={compact ? '对照业务路径' : '实际业务路径'}>
    {!trace && <Alert type="warning" showIcon message="当前没有可可靠关联的执行路径" description="界鉴不会用其他检查项的路径补齐这段事实。" />}
    {trace && <>
      {!trace.complete && <Alert type="warning" showIcon message="当前只能确认部分业务路径" />}
      {diagnosis?.precision === 'EXACT' && issue.verdict !== 'INCONCLUSIVE' && <Typography.Text type="danger">红色边表示首个可证明断裂。</Typography.Text>}
      {diagnosis?.precision === 'RANGE' && issue.verdict !== 'INCONCLUSIVE' && <Typography.Text type="warning">只能确认断裂发生在两个边界之间，不能声称唯一断点。</Typography.Text>}
      {diagnosis?.precision === 'VIOLATION_ONLY' && <Alert type="warning" showIcon message="违规已确认，但当前证据不足以定位具体断裂点" />}
      <ol className="verification-path-list">{trace.events.map((event, index) => <li className={eventState(issue, diagnosis, trace, event.event_id)} key={event.event_id}>
        <span className="verification-path-edge" aria-hidden="true" />
        {onEvidence
          ? <button type="button" className="verification-path-node" aria-label={`查看“${eventLabels[event.kind] ?? '已发布业务节点'}”证据`} onClick={onEvidence}><span aria-hidden="true">{index + 1}</span></button>
          : <span className="verification-path-node" aria-hidden="true"><span>{index + 1}</span></span>}
        <div><Typography.Text strong>{eventLabels[event.kind] ?? '已发布业务节点'}</Typography.Text></div>
      </li>)}</ol>
    </>}
  </section>
}

function PermissionExam({ presentation }: { presentation: ResultPresentationDto }) {
  return <section className="verification-column verification-exam" aria-labelledby="verification-exam-title">
    <Typography.Text className="verification-kicker">被检查的业务规则</Typography.Text>
    <Typography.Title id="verification-exam-title" level={3}>权限考题已锁定</Typography.Title>
    <Tag color="green">已由用户确认</Tag>
    {presentation.relevant_intents.length === 0 && <Alert type="warning" showIcon message="这次检查没有可展示的权限规则版本" />}
    <div className="verification-intents">{presentation.relevant_intents.map((intent) => <article key={intent.intent_id}>
      <Space wrap><Tag color="blue">{intent.display_label ?? '权限要求'}</Tag><Typography.Text strong>第 {intent.revision} 版</Typography.Text></Space>
      <Typography.Paragraph>{intent.business_statement ?? '这次较早运行没有保存完整业务语义，界鉴不补猜权限句。'}</Typography.Paragraph>
      <Collapse ghost items={[{ key: 'technical', label: '查看技术标识', children: <Space direction="vertical"><Typography.Text code>{intent.intent_hash}</Typography.Text><Typography.Text type="secondary">权限规则版本 {presentation.policy_epoch}</Typography.Text></Space> }]} />
    </article>)}</div>
    <Typography.Text type="secondary">本页始终读取本次检查锁定的权限版本。</Typography.Text>
  </section>
}

function ClaimBoundary({ issue }: { issue: ResultPresentationIssueDto }) {
  const boundary = issue.claim_boundary
  const dimensions = [
    ['表面响应', boundary.surface_response_status],
    ['真实业务后果', boundary.business_effect_status],
    ['实际执行身份', boundary.actual_identity_status],
    ['断裂定位精度', boundary.breakpoint_precision],
    ['原考题复验', boundary.repair_status],
  ] as const
  return <section id="verification-limitations" tabIndex={-1} className="verification-column verification-claims" aria-labelledby="verification-claims-title">
    <Typography.Text className="verification-kicker">证据允许说到哪里</Typography.Text>
    <Typography.Title id="verification-claims-title" level={3}>现有证据能够确认什么</Typography.Title>
    <dl className="verification-claim-grid">{dimensions.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{claimValue(value)}</dd></div>)}</dl>
    <Alert type="success" showIcon message="当前证据支持" description={boundary.supported_statement} />
    {boundary.unsupported_statements.length > 0 && <div><Typography.Text strong>当前不能宣称</Typography.Text><ul>{boundary.unsupported_statements.map((item) => <li key={item}>{item}</li>)}</ul></div>}
  </section>
}

function ActualPathColumn({ issue, presentation, onEvidence }: { issue: ResultPresentationIssueDto; presentation: ResultPresentationDto; onEvidence: () => void }) {
  return <section className="verification-column verification-actual" aria-labelledby="verification-actual-title">
    <Typography.Text className="verification-kicker">权限语义与已发布执行事实</Typography.Text>
    <Typography.Title id="verification-actual-title" level={3}>预期与实际业务路径</Typography.Title>
    <article className="verification-expected-path"><Typography.Text strong>预期业务路径</Typography.Text>{presentation.relevant_intents.length === 0
      ? <Alert type="warning" showIcon message="本次检查没有可读取的权限语义" />
      : presentation.relevant_intents.map((intent) => <div key={intent.intent_id}><Typography.Paragraph className="verification-expected-statement" title={intent.business_statement ?? undefined}>{intent.business_statement ?? '较早检查没有保存完整业务语义，界鉴不补猜权限路径。'}</Typography.Paragraph><Space wrap><Tag>{intent.display_label ?? '权限要求'}</Tag>{intent.expectation && <Tag color={intent.expectation === 'DENY' ? 'red' : 'green'}>{expectationLabel(intent.expectation)}</Tag>}<Tag>{intent.expectation === 'DENY' ? '应当停止' : intent.expectation === 'ALLOW' ? '应当继续' : '预期方向不可用'}</Tag></Space></div>)}</article>
    <Typography.Text strong>实际业务路径</Typography.Text>
    <Typography.Paragraph>{issue.actual_result}</Typography.Paragraph>
    <VerificationPath compact issue={issue} trace={traceFor(issue, presentation)} onEvidence={onEvidence} />
    {issue.diagnosis?.continuity_state === 'ORPHAN_EFFECT_CONFIRMED' && <article className="verification-orphan-card">
      <Typography.Text strong>已确认没有合法授权来源的业务后果</Typography.Text>
      <Typography.Paragraph>{issue.actual_result}</Typography.Paragraph>
      <Typography.Text type="secondary">{Array.from(new Set(issue.diagnosis.confirmed_impacts.map((impact) => impact.summary))).join('、')}</Typography.Text>
    </article>}
  </section>
}

export function VerificationPage({
  run,
  onError,
  onBack,
  onHistory,
  onRetest,
  retestBusy = false,
  onObservationGap,
  observationGapBusy = false,
}: {
  run?: RunDto
  onError: (error: ApiError) => void
  onBack?: () => void
  onHistory?: () => void
  onRetest?: () => void
  retestBusy?: boolean
  onObservationGap?: () => void
  observationGapBusy?: boolean
}) {
  const [presentation, setPresentation] = useState<ResultPresentationDto | null>(null)
  const [sourcePresentation, setSourcePresentation] = useState<ResultPresentationDto | null>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [unavailableReason, setUnavailableReason] = useState<string>()
  const [refreshEpoch, setRefreshEpoch] = useState(0)

  useEffect(() => {
    setPresentation(null)
    setSourcePresentation(null)
    setSelectedIndex(0)
    setUnavailableReason(undefined)
    if (!run?.run_id) return
    let active = true
    setLoading(true)
    void runsApi.run(String(run.run_id)).then(async (authoritative) => {
      if (String(authoritative.result_integrity) !== 'VERIFIED') {
        if (active) setUnavailableReason('当前检查尚未形成可验证的已发布结果。')
        return null
      }
      const current = await resultsApi.presentation(String(run.run_id))
      if (!active) return null
      setPresentation(current)
      const sourceRunId = current.repair_verification?.reference.source_run_id
      if (sourceRunId && sourceRunId !== current.run_id) return resultsApi.presentation(sourceRunId)
      return null
    }).then((source) => { if (active && source) setSourcePresentation(source) }).catch((error) => { if (active) onError(error as ApiError) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [run?.run_id, refreshEpoch])

  const issue = presentation?.issues[selectedIndex]
  const sourceIssue = useMemo(() => {
    const sourceFinding = presentation?.repair_verification?.reference.source_finding_id
    return sourcePresentation?.issues.find((item) => item.finding_id === sourceFinding)
  }, [presentation, sourcePresentation])
  const openEvidence = () => setDrawerOpen(true)
  const focusLimitations = () => document.getElementById('verification-limitations')?.focus()

  if (!run) return <Space direction="vertical" size="large" className="full-width verification-page">
    <PageTaskHeader title="现场验证" description="把权限考题、实际路径和证据边界放到同一现场核对。" status="等待一次检查" />
    <Alert type="info" showIcon message="先完成一次检查" description="现场验证只展示真实 Run 已发布的结果，不提供演示占位数据。" />
    <TaskActionBar back={onBack ? { label: '返回检查结果', onClick: onBack } : undefined} />
  </Space>

  return <Space direction="vertical" size="large" className="full-width verification-page">
    <PageTaskHeader title="现场验证" description="把权限考题、实际路径和证据边界放到同一现场核对。" status={presentation?.headline ?? unavailableReason ?? '正在读取已发布结果'} />
    {presentation && <Space wrap><Tag>当前应用：{presentation.project_name}</Tag><Collapse ghost items={[{ key: 'run', label: '查看本次检查标识', children: <Typography.Text code>{presentation.run_id}</Typography.Text> }]} /></Space>}
    {!loading && unavailableReason && <Alert type="warning" showIcon message="当前没有可用于现场验证的发布结果" description={unavailableReason} />}
    {presentation && presentation.issues.length > 1 && <Space wrap>{presentation.issues.map((item, index) => <Button type={index === selectedIndex ? 'primary' : 'default'} key={item.finding_id} onClick={() => setSelectedIndex(index)}>检查项 {index + 1}</Button>)}</Space>}
    {presentation && !issue && <Alert type="info" showIcon message="本次检查没有需要单独展示的现场问题" description={presentation.scope_statement} />}
    {presentation && issue && <>
      {issue.verdict === 'INCONCLUSIVE' && <Alert type="warning" showIcon message="证据不足，现场不标记红色断裂点" description={issue.explanation} />}
      <section className={`verification-board is-${issue.verdict.toLowerCase()}`} aria-label="现场验证三栏视图">
        <PermissionExam presentation={presentation} />
        <ActualPathColumn issue={issue} presentation={presentation} onEvidence={openEvidence} />
        <ClaimBoundary issue={issue} />
      </section>
      <section className="verification-evidence-actions">
        <div><Typography.Title level={3}>证据说明</Typography.Title><Typography.Paragraph type="secondary">来源、步骤、可证明和不可证明边界按固定顺序展示。</Typography.Paragraph></div>
        <Space wrap><Button onClick={openEvidence}>查看为什么</Button><Button onClick={focusLimitations}>查看限制</Button></Space>
      </section>
      {presentation.repair_verification && <section className="verification-repair" aria-labelledby="verification-repair-title">
        <Typography.Title id="verification-repair-title" level={3}>修复前后沿同一业务路径核对</Typography.Title>
        {issue.repair_requirement && <ul><li>必须消失：{issue.repair_requirement.must_disappear}</li><li>必须保留：{issue.repair_requirement.must_remain}</li><li>不能改变：{issue.repair_requirement.must_not_change.join('、')}</li></ul>}
        <div className="verification-repair-grid">
          <article><Typography.Text strong>修复前</Typography.Text>{sourceIssue ? <VerificationPath compact issue={sourceIssue} trace={sourcePresentation ? traceFor(sourceIssue, sourcePresentation) : undefined} onEvidence={openEvidence} /> : <Alert type="warning" showIcon message="修复前路径不可用" />}</article>
          <article><Typography.Text strong>修复后</Typography.Text><VerificationPath compact issue={issue} trace={traceFor(issue, presentation)} onEvidence={openEvidence} /></article>
        </div>
        <Alert type={presentation.repair_verification.status === 'VERIFIED' ? 'success' : presentation.repair_verification.status === 'NOT_VERIFIED' ? 'error' : 'warning'} showIcon message={claimValue(presentation.repair_verification.status)} description={presentation.repair_verification.message} />
      </section>}
      {(onRetest || onObservationGap) && <Space wrap>{onRetest && <Button type="primary" loading={retestBusy} onClick={onRetest}>使用原考题复验</Button>}{onObservationGap && <Button loading={observationGapBusy} onClick={onObservationGap}>验证关键结果不可读取时会怎样</Button>}</Space>}
      <section className="verification-ai-boundary"><Typography.Text type="secondary">仅辅助解释，不参与安全判定</Typography.Text><AssistantPanel runId={String(run.run_id)} title="解释这次现场验证" actionLabel="生成辅助解释" /></section>
      <EvidenceExplanationDrawer open={drawerOpen} title={issue.title} explanations={issue.evidence_explanations} onClose={() => setDrawerOpen(false)} />
    </>}
    <TaskActionBar back={onBack ? { label: '返回检查结果', onClick: onBack } : undefined} refresh={{ label: '刷新现场事实', onClick: () => setRefreshEpoch((value) => value + 1), loading }} primary={presentation && onHistory ? { label: '查看历史变化', onClick: onHistory } : undefined} />
  </Space>
}
