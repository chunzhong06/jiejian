/* =============================================================================
 * 检查结果投影
 *
 * 定位
 *   展示后端 ResultPresentation 与已发布 Evidence，不在前端重算安全结论。
 *
 * 职责
 *   呈现范围、三态结论、权限问题与限制｜按需打开证据和完整报告
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Collapse, Descriptions, List, Segmented, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi, type EvidenceDto, type ResultPresentationDto, type ResultPresentationIssueDto } from '../../api/results'
import { runsApi, type RunDto } from '../../api/runs'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { integrityLabel, lifecycleLabel, occurrenceStatusLabel, severityLabel, verdictLabel } from '../../app/presentation'
import { EvidenceTimeline } from './EvidenceTimeline'
import { ReportPanel } from './ReportPanel'
import './checks.css'

function requirementLabel(value: unknown) { return ({ resource_state: '资源状态' } as Record<string, string>)[String(value)] ?? `观察要求：${String(value ?? '未提供')}` }

function observerSummary(value: unknown) {
  if (!value || typeof value !== 'object') return '未提供'
  const health = value as Record<string, unknown>
  const required = Array.isArray(health.required_observations) ? health.required_observations.map(String) : []
  if (required.length === 0) return '未声明必需观察'
  return required.map((id) => {
    const item = health[id]
    const configured = Boolean(item && typeof item === 'object' && (item as { configured?: boolean }).configured === true)
    return `${requirementLabel(id)} · ${configured ? '已配置' : '缺失'}`
  }).join('；')
}

function fallbackHeadline(run: RunDto | undefined) {
  if (!run) return '等待检查结果'
  if (String(run.result_integrity) === 'VERIFIED') return '正在读取检查结果'
  return ['FAILED', 'CANCELLED'].includes(String(run.lifecycle)) ? '检查未完整结束' : '等待检查结果'
}

function issueTagColor(issue: ResultPresentationIssueDto) {
  return issue.verdict === 'VULNERABLE' ? 'red' : issue.verdict === 'INCONCLUSIVE' ? 'gold' : 'green'
}

export function CheckResultsPage({ run, onError, onNext, onNavigate, initialView = 'results' }: { run?: RunDto; onError: (error: ApiError) => void; onNext?: () => void; onNavigate?: (path: string) => void; initialView?: 'results' | 'report' }) {
  const [current, setCurrent] = useState<RunDto | undefined>(run)
  const [presentation, setPresentation] = useState<ResultPresentationDto | null>(null)
  const [evidence, setEvidence] = useState<EvidenceDto[]>([])
  const [view, setView] = useState<'results' | 'report'>(initialView)
  const [selectedIssue, setSelectedIssue] = useState<ResultPresentationIssueDto | undefined>()

  useEffect(() => {
    setCurrent(run)
    setPresentation(null)
    setEvidence([])
    setSelectedIssue(undefined)
    setView(initialView)
    if (!run?.run_id) return
    let active = true
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
    }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [run?.run_id, initialView])

  const preferredEvidence = useMemo(() => selectedIssue?.evidence_refs ?? [], [selectedIssue])
  const headline = presentation?.headline ?? fallbackHeadline(current)
  const verified = String(current?.result_integrity) === 'VERIFIED'

  return <Space direction="vertical" size="large" className="full-width">
    <PageTaskHeader title="检查结果" description="先判断有没有权限问题，再理解发生了什么，最后按需查看证据和完整报告。" status={presentation?.headline ?? fallbackHeadline(current)} next={verified ? '结果已发布' : integrityLabel(current?.result_integrity)} actionLabel={verified ? '重新开始检查' : undefined} onAction={onNext} />
    {!current && <Alert type="info" showIcon message="尚未选择检查结果。" />}
    {current && <Card className="result-summary"><Space direction="vertical" className="full-width" size="middle">
      <Typography.Title level={2} style={{ margin: 0 }}>{headline}</Typography.Title>
      <Typography.Paragraph type="secondary" style={{ margin: 0 }}>{presentation?.scope_statement ?? (verified ? '结果正在加载。' : '结果尚未通过完整性校验，暂不提供安全结论。')}</Typography.Paragraph>
      {presentation && <Space wrap><Tag color={presentation.verdict === 'BLOCK' ? 'red' : presentation.verdict === 'PASS' ? 'green' : 'gold'}>{presentation.headline}</Tag></Space>}
      {presentation?.execution_problem && <Alert type="error" showIcon message="检查执行未完整结束" description={presentation.execution_problem} />}
      {String(current.result_integrity) === 'INVALID' && <Alert type="warning" showIcon message="结果完整性校验未通过，不能形成安全结论。" />}
      {presentation && <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
        <Descriptions.Item label="本次检查">{presentation.checked_count} 项</Descriptions.Item>
        <Descriptions.Item label="符合预期">{presentation.safe_count} 项</Descriptions.Item>
        <Descriptions.Item label="权限问题">{presentation.problem_count} 项</Descriptions.Item>
        <Descriptions.Item label="证据不足">{presentation.inconclusive_count} 项</Descriptions.Item>
        <Descriptions.Item label="权限要求未覆盖">{presentation.uncovered_count} 项</Descriptions.Item>
      </Descriptions>}
      <Collapse ghost items={[{ key: 'result-technical', label: '高级：技术信息', children: <Descriptions size="small" column={{ xs: 1, sm: 2 }}><Descriptions.Item label="检查状态">{lifecycleLabel(current.lifecycle)}</Descriptions.Item><Descriptions.Item label="结果完整性">{integrityLabel(current.result_integrity)}</Descriptions.Item><Descriptions.Item label="必需观察状态">{observerSummary(current.observer_health)}</Descriptions.Item><Descriptions.Item label="执行 Schema">{String(current.execution_schema_version ?? '未提供')}</Descriptions.Item><Descriptions.Item label="原因代码">{Array.isArray(current.reason_codes) && current.reason_codes.length > 0 ? current.reason_codes.join('、') : '无'}</Descriptions.Item></Descriptions> }]} />
    </Space></Card>}
    {current && <Segmented block value={view} onChange={(value) => setView(value as 'results' | 'report')} options={[{ label: '结论与证据', value: 'results' }, { label: '完整报告', value: 'report' }]} />}
    {view === 'results' && current && <>
      <Card title={presentation?.issues.some((issue) => issue.verdict !== 'SAFE') ? '需要处理的问题' : '检查项说明'}><List dataSource={presentation?.issues ?? []} locale={{ emptyText: verified ? '当前结果没有需要单独说明的问题。' : '结果尚未可用。' }} renderItem={(issue) => {
        return <List.Item className="finding-list-item"><Card size="small" className="full-width" title={<Space wrap><Typography.Text strong>{issue.title}</Typography.Text><Tag color={issueTagColor(issue)}>{verdictLabel(issue.verdict)}</Tag><Tag>{severityLabel(issue.severity)}</Tag></Space>} extra={<Button type="link" onClick={() => setSelectedIssue(issue)}>查看对应证据</Button>}>
          <Descriptions size="small" column={{ xs: 1, md: 2 }}>
            <Descriptions.Item label="谁">{issue.subject_group}</Descriptions.Item>
            <Descriptions.Item label="做什么">{issue.action}</Descriptions.Item>
            <Descriptions.Item label="对什么资源">{issue.resource}</Descriptions.Item>
            <Descriptions.Item label="资源关系">{issue.relation}</Descriptions.Item>
            <Descriptions.Item label="预期">{issue.expectation}</Descriptions.Item>
            <Descriptions.Item label="表面结果">{issue.surface_result}</Descriptions.Item>
            <Descriptions.Item label="真实结果">{issue.actual_result}</Descriptions.Item>
            <Descriptions.Item label="结论">{issue.conclusion}</Descriptions.Item>
            <Descriptions.Item label="为什么" span={{ xs: 1, md: 2 }}>{issue.explanation}</Descriptions.Item>
          </Descriptions>
          {issue.verdict === 'INCONCLUSIVE' && <Alert style={{ marginTop: 12 }} type="warning" showIcon message={issue.conclusion} description={<Space direction="vertical"><Typography.Text>{issue.explanation}</Typography.Text><Button onClick={() => onNavigate?.('/apps/flows')}>完善真实结果确认方式</Button></Space>} />}
          <Space wrap style={{ marginTop: 12 }}><Tag>{occurrenceStatusLabel(issue.occurrence_status)}</Tag><Collapse ghost items={[{ key: 'finding-details', label: '高级：问题标识', children: <Descriptions size="small"><Descriptions.Item label="finding_id">{issue.finding_id}</Descriptions.Item><Descriptions.Item label="occurrence_status">{issue.occurrence_status ?? '未提供'}</Descriptions.Item><Descriptions.Item label="evidence_refs">{issue.evidence_refs.join('、') || '无'}</Descriptions.Item></Descriptions> }]} /></Space>
        </Card></List.Item>
      }} /></Card>
      {presentation && presentation.limitations.length > 0 && <Card title="范围与限制"><List dataSource={presentation.limitations} renderItem={(item) => <List.Item>{item}</List.Item>} /></Card>}
      <Collapse ghost items={[{ key: 'evidence', label: '查看证据', children: <EvidenceTimeline runId={String(current.run_id)} evidence={evidence} preferredIds={preferredEvidence} onError={onError} /> }]} />
    </>}
    {view === 'report' && <ReportPanel run={current} onError={onError} />}
  </Space>
}
