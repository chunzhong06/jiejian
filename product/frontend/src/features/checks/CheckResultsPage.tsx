/* =============================================================================
 * 检查结果投影
 *
 * 定位
 *   把后端 ResultPresentation、ExecutionTrace 与已发布 Evidence 组织成单一可信结果故事。
 *
 * 职责
 *   依次说明权限预期、实际身份、表面响应、断裂见证、确认影响与最终结论
 *   ｜默认折叠完整执行路径｜按需展开证据和报告｜不在前端推断或重算安全结论
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Collapse, Segmented, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi, type EvidenceDto, type ExecutionTraceDto, type ResultDiagnosisDto, type ResultEvidenceSourceDto, type ResultPresentationDto, type ResultPresentationIssueDto } from '../../api/results'
import { runsApi, type RunDto } from '../../api/runs'
import { occurrenceStatusLabel, severityLabel } from '../../app/presentation'
import { AssistantPanel } from '../../components/AssistantPanel'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { TaskActionBar } from '../../components/TaskActionBar'
import { EvidenceTimeline } from './EvidenceTimeline'
import { ReportPanel } from './ReportPanel'
import './checks.css'

function fallbackHeadline(run: RunDto | undefined) {
  if (!run) return '等待检查结果'
  if (String(run.result_integrity) === 'VERIFIED') return '正在读取检查结果'
  return ['FAILED', 'CANCELLED'].includes(String(run.lifecycle)) ? '检查未完整结束' : '等待检查结果'
}

function resultTone(verdict: ResultPresentationIssueDto['verdict']) {
  return verdict === 'VULNERABLE' ? 'danger' : verdict === 'INCONCLUSIVE' ? 'warning' : 'safe'
}

function resultTagColor(verdict: ResultPresentationIssueDto['verdict']) {
  return verdict === 'VULNERABLE' ? 'red' : verdict === 'INCONCLUSIVE' ? 'gold' : 'green'
}

function plannedIdentityLabel(issue: ResultPresentationIssueDto) {
  return issue.planned_identity_label || '已安排一个测试账号'
}

function actualIdentityText(issue: ResultPresentationIssueDto) {
  if (issue.actual_identity_status === 'UNAVAILABLE') return '无法独立确认'
  return issue.actual_identity_label || '无法独立确认'
}

function sourceRoleLabel(role: ResultEvidenceSourceDto['role']) {
  return role === 'KEY' ? '关键来源' : '佐证来源'
}

function sourceStatusLabel(status: ResultEvidenceSourceDto['status']) {
  return ({ FOUND: '已发现', NOT_FOUND: '未发现', UNAVAILABLE: '无法确认' } as const)[status]
}

function sourceStatusColor(status: ResultEvidenceSourceDto['status']) {
  return status === 'FOUND' ? 'green' : status === 'UNAVAILABLE' ? 'gold' : 'blue'
}

export function CheckResultsPage({
  run,
  onError,
  onBack,
  onHistory,
  onNavigate,
  canVerifyFix = false,
  verifyingFix = false,
  onVerifyFix,
}: {
  run?: RunDto
  onError: (error: ApiError) => void
  onBack?: () => void
  onHistory?: () => void
  onNavigate?: (path: string) => void
  canVerifyFix?: boolean
  verifyingFix?: boolean
  onVerifyFix?: () => void
}) {
  const [current, setCurrent] = useState<RunDto | undefined>(run)
  const [presentation, setPresentation] = useState<ResultPresentationDto | null>(null)
  const [evidence, setEvidence] = useState<EvidenceDto[]>([])
  const [view, setView] = useState<'results' | 'report'>('results')
  const [selectedIssue, setSelectedIssue] = useState<ResultPresentationIssueDto | undefined>()
  const [refreshEpoch, setRefreshEpoch] = useState(0)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setCurrent(run)
    setPresentation(null)
    setEvidence([])
    setSelectedIssue(undefined)
    setView('results')
    if (!run?.run_id) return
    let active = true
    setLoading(true)
    void runsApi.run(String(run.run_id)).then(async (authoritative) => {
      if (!active) return
      setCurrent(authoritative)
      if (String(authoritative.result_integrity) !== 'VERIFIED') return
      const [resultView, publishedEvidence] = await Promise.all([
        resultsApi.presentation(String(run.run_id)),
        resultsApi.evidence(String(run.run_id)),
      ])
      if (!active) return
      setPresentation(resultView)
      setEvidence(publishedEvidence)
      setSelectedIssue(resultView.issues[0])
    }).catch((error) => { if (active) onError(error as ApiError) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [run?.run_id, refreshEpoch])

  const preferredEvidence = useMemo(() => selectedIssue?.evidence_refs ?? [], [selectedIssue])
  const headline = presentation?.headline ?? fallbackHeadline(current)
  const verified = String(current?.result_integrity) === 'VERIFIED'

  return <Space direction="vertical" size="large" className="full-width result-page">
    <PageTaskHeader title="检查结果" description="先看最终结论，再沿着同一条事实链理解界鉴为什么这样判断。" status={headline} />
    {!current && <Alert type="info" showIcon message="尚未选择检查结果。" />}
    {current && <section className={`result-overview result-overview-${presentation?.verdict?.toLowerCase() ?? 'pending'}`} aria-labelledby="result-headline">
      <div className="result-overview-copy">
        <Typography.Text className="result-eyebrow">本次检查结论</Typography.Text>
      <Typography.Title id="result-headline" level={2}>{headline}</Typography.Title>
      <Typography.Paragraph type="secondary">{presentation?.scope_statement ?? (verified ? '结果正在加载。' : '结果尚未通过完整性校验，暂不提供安全结论。')}</Typography.Paragraph>
      {presentation && <Space direction="vertical" size={2}>
        {presentation.change_verification && <>
          <Typography.Text>本次检查由最近一次代码修改触发</Typography.Text>
          <Typography.Text>使用你之前确认的 {presentation.change_verification.required_intents.length} 条权限要求重新检查</Typography.Text>
        </>}
      </Space>}
      </div>
      {presentation && <dl className="result-count-grid">
        <div><dt>实际检查</dt><dd>{presentation.checked_count} 项</dd></div>
        <div><dt>符合预期</dt><dd>{presentation.safe_count} 项</dd></div>
        <div><dt>权限问题</dt><dd>{presentation.problem_count} 项</dd></div>
        <div><dt>证据不足</dt><dd>{presentation.inconclusive_count} 项</dd></div>
        <div><dt>未覆盖</dt><dd>{presentation.uncovered_count} 项</dd></div>
      </dl>}
      {presentation?.execution_problem && <Alert type="error" showIcon message="检查执行未完整结束" description={presentation.execution_problem} />}
      {presentation?.repair_verification && <Alert
        type={presentation.repair_verification.status === 'VERIFIED' ? 'success' : presentation.repair_verification.status === 'NOT_VERIFIED' ? 'error' : 'warning'}
        showIcon
        message={presentation.repair_verification.status === 'VERIFIED' ? '修复要求已验证' : presentation.repair_verification.status === 'NOT_VERIFIED' ? '修复要求未通过' : '修复结果暂时无法确认'}
        description={presentation.repair_verification.message}
      />}
      {String(current.result_integrity) === 'INVALID' && <Alert type="warning" showIcon message="结果完整性校验未通过，不能形成安全结论。" />}
    </section>}
    {current && presentation && <AssistantPanel runId={String(current.run_id)} title="这个结果的因果说明" actionLabel="AI 解读这个结果" />}
    {current && <Segmented className="result-view-switch" value={view} onChange={(value) => setView(value as 'results' | 'report')} options={[{ label: '结论与证据', value: 'results' }, { label: '完整报告', value: 'report' }]} />}
    {view === 'results' && current && <>
      {presentation && presentation.execution_traces.length > 0 && <ExecutionPaths traces={presentation.execution_traces} />}
      <section className="result-section" aria-labelledby="result-stories-title">
        <div className="result-section-heading"><div><Typography.Title id="result-stories-title" level={3}>{presentation?.issues.some((issue) => issue.verdict !== 'SAFE') ? '需要处理的检查项' : '检查项说明'}</Typography.Title><Typography.Paragraph type="secondary">每一项都按照同一顺序展示权限预期、执行表象、真实影响和后端结论。</Typography.Paragraph></div></div>
        {presentation?.issues.length
          ? <div className="result-story-list">{presentation.issues.map((issue, index) => <ResultStory key={issue.finding_id} issue={issue} index={index} onEvidence={() => setSelectedIssue(issue)} onNavigate={onNavigate} />)}</div>
          : <div className="result-empty">{verified ? '当前结果没有需要单独说明的检查项。' : '结果尚未可用。'}</div>}
      </section>
      {presentation && presentation.limitations.length > 0 && <section className="result-section result-limitations" aria-labelledby="result-limitations-title"><Typography.Title id="result-limitations-title" level={3}>本次范围与限制</Typography.Title><ul>{presentation.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section>}
      <section id="published-evidence" className="result-evidence-section" aria-labelledby="result-evidence-title">
        <div className="result-section-heading"><div><Typography.Title id="result-evidence-title" level={3}>证据怎样支持结论</Typography.Title><Typography.Paragraph type="secondary">这里只展开已经发布的执行与观察事实；“已发现、未发现、无法确认”不会改变后端形成的结论。</Typography.Paragraph></div>{selectedIssue && <Tag>{selectedIssue.title}</Tag>}</div>
        <EvidenceTimeline runId={String(current.run_id)} evidence={evidence} preferredIds={preferredEvidence} onError={onError} />
      </section>
    </>}
    {view === 'report' && <ReportPanel run={current} onError={onError} />}
    <TaskActionBar back={onBack ? { label: '返回权限与检查', onClick: onBack } : undefined} refresh={current ? { label: '刷新已发布结果', onClick: () => setRefreshEpoch((value) => value + 1), loading } : undefined} restart={canVerifyFix && onVerifyFix ? { label: '验证修复后的行为', onClick: onVerifyFix, loading: verifyingFix } : undefined} primary={presentation && onHistory ? { label: '查看历史变化', onClick: onHistory } : undefined} />
  </Space>
}

function ExecutionPaths({ traces }: { traces: ExecutionTraceDto[] }) {
  const eventLabel = (kind: string) => ({ ENTRY: '请求进入目标应用', IDENTITY: '服务器识别实际账号', AUTHORIZATION: '应用作出权限判断', PERSISTENT_EFFECT: '业务状态发生变化', MESSAGE: '任务进入消息链路', DELEGATION: '后台任务继续处理', FINAL_EFFECT: '最终业务结果形成', RECOVERY: '测试现场得到恢复' } as Record<string, string>)[kind] ?? '记录到一个业务执行节点'
  return <section className="result-section" aria-labelledby="execution-path-title">
    <div className="result-section-heading"><div><Typography.Title id="execution-path-title" level={3}>执行路径</Typography.Title><Typography.Paragraph type="secondary">界鉴只从已发布证据还原实际发生的节点；这里的顺序不会改变后端安全结论。</Typography.Paragraph></div></div>
    <Collapse destroyOnHidden items={[{ key: 'execution-paths', label: '查看完整执行路径', children: <div className="execution-paths">{traces.map((trace, traceIndex) => <article className="execution-path" key={`${trace.case_id}-${trace.action_id}`} aria-label={traces.length > 1 ? `执行路径 ${traceIndex + 1}` : '执行路径详情'}>
      {!trace.complete && <Alert type="warning" showIcon message="当前只能确认部分执行路径" />}
      {trace.events.length > 0
        ? <ol className="execution-path-list">{trace.events.map((event) => <li key={event.event_id}><span className="execution-path-dot" aria-hidden="true" /><Typography.Text strong>{eventLabel(event.kind)}</Typography.Text></li>)}</ol>
        : <Typography.Text type="secondary">已发布证据暂时没有可展示的路径节点。</Typography.Text>}
    </article>)}</div> }]} />
  </section>
}

function ResultStory({ issue, index, onEvidence, onNavigate }: { issue: ResultPresentationIssueDto; index: number; onEvidence: () => void; onNavigate?: (path: string) => void }) {
  const steps = [
    { label: '原本应该怎样', value: issue.expectation },
    { label: '计划使用的账号', value: plannedIdentityLabel(issue), note: '来自本次检查开始前冻结的执行请求。' },
    { label: '目标实际识别的账号', value: actualIdentityText(issue), note: issue.actual_identity_status === 'UNAVAILABLE' ? '当前已发布证据没有目标服务器或可信记录提供的实际账号事实，界鉴不会把计划账号冒充为实际账号。' : undefined },
    { label: '页面或接口怎样回应', value: issue.surface_result },
    { label: '真实资源发生了什么', value: issue.actual_result },
    { label: '最终结论', value: issue.conclusion, note: issue.explanation },
  ]
  return <article className={`result-story result-story-${resultTone(issue.verdict)}`} aria-labelledby={`result-story-${index}`}>
    <header className="result-story-header"><div><Typography.Text className="result-context" type="secondary">{issue.subject_group} · {issue.action} · {issue.resource} · {issue.relation}</Typography.Text><Typography.Title id={`result-story-${index}`} level={4}>{issue.title}</Typography.Title></div><Space wrap><Tag color={resultTagColor(issue.verdict)}>{issue.conclusion}</Tag><Tag>{severityLabel(issue.severity)}</Tag></Space></header>
    <ol className="result-story-steps">{steps.map((step, stepIndex) => <li key={step.label}><span className="result-story-step-index" aria-hidden="true">{stepIndex + 1}</span><div className="result-story-step-copy"><Typography.Text type="secondary">{step.label}</Typography.Text><Typography.Text strong>{step.value}</Typography.Text>{step.note && <Typography.Paragraph type="secondary">{step.note}</Typography.Paragraph>}</div></li>)}</ol>
    <section className="result-source-summary" aria-label="真实结果证据来源">
      <div className="result-source-summary-copy"><Typography.Text strong>真实结果证据来源</Typography.Text><Typography.Paragraph type="secondary">关键来源共同约束真实结果能否确认；佐证来源补充执行过程，但不会单独改变结论。</Typography.Paragraph></div>
      {issue.evidence_sources.length > 0
        ? <ul className="result-source-list">{issue.evidence_sources.map((source) => <li key={`${source.observer_type}-${source.label}`}><div><Typography.Text strong>{source.label}</Typography.Text><Typography.Text type="secondary">{sourceRoleLabel(source.role)}</Typography.Text></div><Tag color={sourceStatusColor(source.status)}>{sourceStatusLabel(source.status)}</Tag></li>)}</ul>
        : <Typography.Text type="secondary">本次发布结果没有可展示的观察来源。</Typography.Text>}
    </section>
    {issue.diagnosis && <ResultDiagnosis diagnosis={issue.diagnosis} />}
    {issue.repair_requirement && <section className="result-repair-requirement" aria-label="修复要求">
      <Typography.Text strong>修复后必须满足</Typography.Text>
      <ul>
        <li>{issue.repair_requirement.must_disappear}</li>
        <li>{issue.repair_requirement.must_remain}</li>
        {issue.repair_requirement.must_not_change.map((item) => <li key={item}>{item}不能改变。</li>)}
      </ul>
    </section>}
    {issue.verdict === 'INCONCLUSIVE' && <Alert type="warning" showIcon message={issue.conclusion} description={<Space direction="vertical"><Typography.Text>{issue.explanation}</Typography.Text><Button onClick={() => onNavigate?.('/flows')}>完善真实结果确认方式</Button></Space>} />}
    <div className="result-story-actions"><Button type="link" onClick={onEvidence} aria-controls="published-evidence">查看对应证据</Button><Tag>{occurrenceStatusLabel(issue.occurrence_status)}</Tag></div>
  </article>
}

function ResultDiagnosis({ diagnosis }: { diagnosis: ResultDiagnosisDto }) {
  return <section className="result-diagnosis" aria-label="诊断">
    <div className="result-diagnosis-summary"><Typography.Text strong>问题出在哪里</Typography.Text><Typography.Paragraph>{diagnosis.summary}</Typography.Paragraph></div>
    <div><Typography.Text strong>为什么这样判断</Typography.Text><ol className="result-diagnosis-witness">{diagnosis.minimal_witness.map((witness, index) => <li key={`${witness.kind}-${index}`}><span className="result-story-step-index" aria-hidden="true">{index + 1}</span><div className="result-diagnosis-witness-copy"><Typography.Text type="secondary">{witness.label}</Typography.Text><Typography.Text strong>{witness.detail}</Typography.Text></div></li>)}</ol></div>
    {diagnosis.confirmed_impacts.length > 0 && <div><Typography.Text strong>已确认影响</Typography.Text><ul className="result-diagnosis-impact-list">{diagnosis.confirmed_impacts.map((impact) => <li key={impact.event_id}><Typography.Text strong>{impact.summary}</Typography.Text></li>)}</ul></div>}
  </section>
}
