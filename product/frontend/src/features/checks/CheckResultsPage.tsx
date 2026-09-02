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
import { Alert, Button, Collapse, Segmented, Space, Typography } from 'antd'
import { ApiError } from '../../api/http'
import type { ProductStatusDto } from '../../api/projects'
import { resultsApi, type EvidenceDto, type ExecutionTraceDto, type ResultPresentationDto, type ResultPresentationIssueDto } from '../../api/results'
import { runsApi, type RunDto } from '../../api/runs'
import { traceEventLabel } from '../../app/presentation'
import { AssistantPanel } from '../../components/AssistantPanel'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { TaskActionBar } from '../../components/TaskActionBar'
import { EvidenceTimeline } from './EvidenceTimeline'
import { EvidenceExplanationDrawer } from './EvidenceExplanationDrawer'
import { ReportPanel } from './ReportPanel'
import { ResultDecisionNarrative } from './ResultDecisionNarrative'
import './checks.css'

function fallbackHeadline(run: RunDto | undefined) {
  if (!run) return '等待检查结果'
  if (String(run.result_integrity) === 'VERIFIED') return '正在读取检查结果'
  return ['FAILED', 'CANCELLED'].includes(String(run.lifecycle)) ? '检查未完整结束' : '等待检查结果'
}

export function CheckResultsPage({
  run,
  onError,
  onBack,
  onHistory,
  onVerification,
  onNavigate,
  repair,
  inconclusiveRecovery,
}: {
  run?: RunDto
  onError: (error: ApiError) => void
  onBack?: () => void
  onHistory?: () => void
  onVerification?: () => void
  onNavigate?: (path: string) => void
  repair?: ProductStatusDto['repair']
  inconclusiveRecovery?: ProductStatusDto['inconclusive_recovery']
}) {
  const [current, setCurrent] = useState<RunDto | undefined>(run)
  const [presentation, setPresentation] = useState<ResultPresentationDto | null>(null)
  const [evidence, setEvidence] = useState<EvidenceDto[]>([])
  const [view, setView] = useState<'results' | 'report'>('results')
  const [activeIssueIndex, setActiveIssueIndex] = useState(0)
  const [drawerIssue, setDrawerIssue] = useState<ResultPresentationIssueDto | undefined>()
  const [refreshEpoch, setRefreshEpoch] = useState(0)
  const [loading, setLoading] = useState(false)
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false)

  useEffect(() => {
    setCurrent(run)
    setPresentation(null)
    setEvidence([])
    setActiveIssueIndex(0)
    setDrawerIssue(undefined)
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
    }).catch((error) => { if (active) onError(error as ApiError) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [run?.run_id, refreshEpoch])

  const activeIssue = presentation?.issues[activeIssueIndex] ?? presentation?.issues[0]
  const preferredEvidence = useMemo(() => activeIssue?.evidence_refs ?? [], [activeIssue])
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
          <Typography.Text>{presentation.change_verification.required_intents.length > 0
            ? `这次变化直接关联 ${presentation.change_verification.required_intents.length} 条已确认权限要求`
            : '这次变化未直接关联单条权限要求；仍按当前完整权限范围检查'}</Typography.Text>
        </>}
      </Space>}
      </div>
      {presentation && <dl className="result-count-summary">
        <div><dt>已检查</dt><dd>{presentation.checked_count} 项</dd></div>
        <div><dt>符合规则</dt><dd>{presentation.safe_count} 项</dd></div>
        <div><dt>需要处理</dt><dd>{presentation.problem_count + presentation.inconclusive_count} 项</dd></div>
        {presentation.uncovered_count > 0 && <div><dt>未覆盖</dt><dd>{presentation.uncovered_count} 项</dd></div>}
      </dl>}
      {presentation?.execution_problem && <Alert type="error" showIcon message="检查执行未完整结束" description={presentation.execution_problem} />}
      {presentation?.repair_verification && <Alert
        type={presentation.repair_verification.status === 'VERIFIED' ? 'success' : presentation.repair_verification.status === 'NOT_VERIFIED' ? 'error' : 'warning'}
        showIcon
        message={presentation.repair_verification.status === 'VERIFIED' ? '原考题复验已通过' : presentation.repair_verification.status === 'NOT_VERIFIED' ? '原考题复验未通过' : '原考题复验暂时无法确认'}
        description={presentation.repair_verification.message}
      />}
      {String(current.result_integrity) === 'INVALID' && <Alert type="warning" showIcon message="结果完整性校验未通过，不能形成安全结论。" />}
    </section>}
    {inconclusiveRecovery && <Alert
      type="warning"
      showIcon
      message="本次检查的证据不足结论会永久保留"
      description={<Space direction="vertical" size={2}><Typography.Text>界鉴不会在运行结束后补写旧证据或修改这次结论。</Typography.Text><Typography.Text>{inconclusiveRecovery.summary}</Typography.Text></Space>}
      action={<Button type="primary" onClick={() => onNavigate?.(inconclusiveRecovery.next_path)}>{inconclusiveRecovery.next_label}</Button>}
    />}
    {repair && repair.status !== 'NONE' && <ProjectRepairPanel repair={repair} onNavigate={onNavigate} showRequirements={!presentation?.issues.some((issue) => issue.repair_requirement)} />}
    {current && <Segmented className="result-view-switch" value={view} onChange={(value) => setView(value as 'results' | 'report')} options={[{ label: '结论与证据', value: 'results' }, { label: '完整报告', value: 'report' }]} />}
    {view === 'results' && current && <>
      <section className="result-section" aria-labelledby="result-stories-title">
        <div className="result-section-heading"><div><Typography.Title id="result-stories-title" level={3}>{presentation?.issues.length === 1 ? '关键发现' : '本次检查项'}</Typography.Title><Typography.Paragraph type="secondary">最终判定只在页面顶部出现一次；这里说明决定判定的事实、位置和定位结果。</Typography.Paragraph></div></div>
        {presentation && presentation.issues.length > 1 && <div className="result-issue-switcher" role="group" aria-label="选择检查项">{presentation.issues.map((issue, index) => <Button key={issue.finding_id} type={index === activeIssueIndex ? 'primary' : 'default'} onClick={() => setActiveIssueIndex(index)}>检查项 {index + 1}</Button>)}</div>}
        {activeIssue
          ? <ResultDecisionNarrative issue={activeIssue} onEvidence={() => { setDrawerIssue(activeIssue); setEvidenceDrawerOpen(true) }} />
          : <div className="result-empty">{verified ? '当前结果没有需要单独说明的检查项。' : '结果尚未可用。'}</div>}
      </section>
      <Collapse className="result-audit-details" destroyOnHidden items={[{
        key: 'audit',
        label: '查看完整执行路径、已发布证据与本次范围',
        children: <div className="result-audit-content">
          {presentation && presentation.execution_traces.length > 0 && <ExecutionPaths traces={presentation.execution_traces} />}
          <section id="published-evidence" className="result-evidence-section" aria-labelledby="result-evidence-title">
            <div className="result-section-heading"><div><Typography.Title id="result-evidence-title" level={3}>全部已发布证据</Typography.Title><Typography.Paragraph type="secondary">这里保留完整执行与观察事实，不根据列表数量重新计算安全结论。</Typography.Paragraph></div>{activeIssue && <span className="semantic-state">{activeIssue.title}</span>}</div>
            <EvidenceTimeline runId={String(current.run_id)} evidence={evidence} preferredIds={preferredEvidence} onError={onError} />
          </section>
          {presentation && presentation.limitations.length > 0 && <section className="result-limitations" aria-labelledby="result-limitations-title"><Typography.Title id="result-limitations-title" level={3}>本次范围与限制</Typography.Title><ul>{presentation.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section>}
        </div>,
      }]} />
      {presentation && <section className="verification-ai-boundary"><Typography.Text type="secondary">仅辅助解释，不参与安全判定</Typography.Text><AssistantPanel runId={String(current.run_id)} title="这个结果的因果说明" actionLabel="AI 解读这个结果" /></section>}
    </>}
    {view === 'report' && <ReportPanel run={current} onError={onError} />}
    {presentation && onHistory && <Button className="result-history-link" onClick={onHistory}>查看历史变化</Button>}
    <TaskActionBar back={onBack ? { label: '返回验证运行', onClick: onBack } : undefined} refresh={current ? { label: '刷新已发布结果', onClick: () => setRefreshEpoch((value) => value + 1), loading } : undefined} primary={presentation && onVerification ? { label: '进入现场验证', onClick: onVerification } : undefined} />
    <EvidenceExplanationDrawer open={evidenceDrawerOpen} title={drawerIssue?.title} explanations={drawerIssue?.evidence_explanations ?? []} onClose={() => setEvidenceDrawerOpen(false)} />
  </Space>
}

function ProjectRepairPanel({ repair, onNavigate, showRequirements }: { repair: NonNullable<ProductStatusDto['repair']>; onNavigate?: (path: string) => void; showRequirements: boolean }) {
  const task = repair.tasks.find((item) => item.status !== 'VERIFIED') ?? repair.tasks[0]
  const presentation = {
    NONE: ['info', '当前没有待处理修复', '当前项目没有待处理的正式修复任务。'],
    REPAIR_REQUIRED: ['warning', '等待 Coding Agent 提交修复', '修复要求已经准备好。连接的 Coding Agent 可以通过界鉴 MCP 读取；Agent 不能宣布修复完成。'],
    CHANGE_SUBMITTED: ['info', 'Agent 已提交代码变化', `当前需要：${repair.next_label ?? '继续完成修复准备'}`],
    READY_TO_VERIFY: ['success', '当前修复已经可以独立复验', '当前修复代码与准备事实已就绪；复验仍由正式检查形成三态结果。'],
    VERIFIED: ['success', '修复已经通过独立复验', '当前修复满足原权限要求，旧结果和新结果都会保留。'],
    NOT_VERIFIED: ['error', '修复没有满足原要求', '请让 Coding Agent 继续修改；用户不能把当前状态手工标记为已修复。'],
    INCONCLUSIVE: ['warning', '本次复验证据不足', '旧结果不会改写，请按当前恢复提示继续。'],
    STALE: ['warning', '修复引用或代码变化已经失效', '请按当前提示重新建立可核验的修复变化。'],
  } as const
  const [type, message, description] = presentation[repair.status]
  const action = repair.next_path && ['CHANGE_SUBMITTED', 'READY_TO_VERIFY', 'INCONCLUSIVE', 'STALE'].includes(repair.status)
    ? <Button type={repair.status === 'READY_TO_VERIFY' ? 'primary' : 'default'} onClick={() => onNavigate?.(repair.next_path!)}>{repair.status === 'READY_TO_VERIFY' ? '复验这次修复' : repair.next_label ?? '继续处理'}</Button>
    : undefined
  return <section className="result-section result-repair-status" aria-labelledby="project-repair-status-title">
    <Typography.Title id="project-repair-status-title" level={3}>当前修复状态</Typography.Title>
    <Alert type={type} showIcon message={message} description={description} action={action} />
    {repair.status === 'REPAIR_REQUIRED' && <Typography.Paragraph type="secondary">可交给 Coding Agent 的简短指令：修复界鉴当前发现的权限问题。</Typography.Paragraph>}
    {showRequirements && task && <div className="result-repair-requirement"><Typography.Text strong>修复后必须满足</Typography.Text><ul><li>{task.must_disappear}</li><li>{task.must_remain}</li>{task.must_not_change.map((item) => <li key={item}>{item}不能改变。</li>)}</ul></div>}
  </section>
}

function ExecutionPaths({ traces }: { traces: ExecutionTraceDto[] }) {
  return <section className="result-execution-paths" aria-labelledby="execution-path-title">
    <div className="result-section-heading"><div><Typography.Title id="execution-path-title" level={3}>执行路径</Typography.Title><Typography.Paragraph type="secondary">界鉴只从已发布证据还原实际发生的节点；这里的顺序不会改变后端安全结论。</Typography.Paragraph></div></div>
    <Collapse destroyOnHidden items={[{ key: 'execution-paths', label: '查看完整执行路径', children: <div className="execution-paths">{traces.map((trace, traceIndex) => <article className="execution-path" key={`${trace.case_id}-${trace.action_id}`} aria-label={traces.length > 1 ? `执行路径 ${traceIndex + 1}` : '执行路径详情'}>
      {!trace.complete && <Alert type="warning" showIcon message="当前只能确认部分执行路径" />}
      {trace.events.length > 0
        ? <ol className="execution-path-list">{trace.events.map((event) => <li key={event.event_id}><span className="execution-path-dot" aria-hidden="true" /><Typography.Text strong>{traceEventLabel(event)}</Typography.Text></li>)}</ol>
        : <Typography.Text type="secondary">已发布证据暂时没有可展示的路径节点。</Typography.Text>}
    </article>)}</div> }]} />
  </section>
}
