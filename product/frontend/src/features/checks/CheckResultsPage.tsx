/* 检查结果：结论优先，稳定 Finding、Evidence 和报告在同一任务页内切换。 */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Card, Collapse, Descriptions, List, Segmented, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi } from '../../api/results'
import { runsApi } from '../../api/runs'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { integrityLabel, lifecycleLabel, occurrenceStatusLabel, severityLabel, verdictLabel } from '../../app/presentation'
import { EvidenceTimeline } from './EvidenceTimeline'
import { ReportPanel } from './ReportPanel'

type Item = Record<string, any>
function requirementLabel(value: unknown) { return ({ resource_state: '资源状态' } as Record<string, string>)[String(value)] ?? `观察要求：${String(value ?? '未提供')}` }
function conclusion(run: Item | undefined) {
  if (!run) return '等待检查结果'
  if (!['COMPLETED', 'SAFETY_STOPPED'].includes(String(run.lifecycle))) return '等待检查结果'
  if (String(run.result_integrity) !== 'VERIFIED') return '结果不可用'
  if (run.verdict === 'BLOCK') return '发现权限问题'
  if (run.verdict === 'PASS') return '未发现确认问题'
  if (run.verdict === 'INCONCLUSIVE') return '证据不足'
  return '结果不可用'
}

function observerSummary(value: unknown) {
  if (!value || typeof value !== 'object') return '未提供'
  const health = value as Record<string, unknown>
  const required = Array.isArray(health.required_observations) ? health.required_observations.map(String) : []
  if (required.length === 0) return '未声明必需观察'
  return required.map((id) => {
    const item = health[id]
    const configured = Boolean(item && typeof item === 'object' && (item as Item).configured === true)
    return `${requirementLabel(id)} · ${configured ? '已配置' : '缺失'}`
  }).join('；')
}

function readableErrors(value: unknown) {
  if (!Array.isArray(value)) return []
  return value.map((item) => typeof item === 'object' && item ? String((item as Item).message ?? (item as Item).code ?? '执行失败') : String(item))
}

export function CheckResultsPage({ run, onError, onNext, initialView = 'results' }: { run?: Item; onError: (error: ApiError) => void; onNext?: () => void; initialView?: 'results' | 'report' }) {
  const [current, setCurrent] = useState<Item | undefined>(run)
  const [findings, setFindings] = useState<Item[]>([])
  const [evidence, setEvidence] = useState<Item[]>([])
  const [view, setView] = useState<'results' | 'report'>(initialView)
  const [selectedFinding, setSelectedFinding] = useState<Item | undefined>()
  useEffect(() => {
    setCurrent(run); setFindings([]); setEvidence([]); setSelectedFinding(undefined); setView(initialView)
    if (!run?.run_id) return
    let active = true
    void runsApi.run(String(run.run_id)).then(async (authoritative) => {
      if (!active) return
      setCurrent(authoritative)
      if (String(authoritative.result_integrity) !== 'VERIFIED') return
      try {
        const [stable, publishedEvidence] = await Promise.all([resultsApi.findings(String(run.run_id)), resultsApi.evidence(String(run.run_id))])
        if (active) { setFindings(stable); setEvidence(publishedEvidence) }
      } catch (error) { if (active) onError(error as ApiError) }
    }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [run?.run_id, initialView])
  const vulnerableCount = findings.filter((item) => ['BLOCK'].includes(String(item.occurrence?.verdict))).length
  const severities = findings.filter((item) => ['BLOCK'].includes(String(item.occurrence?.verdict))).map((item) => severityLabel(item.occurrence?.severity)).join('、') || '无'
  const observer = current?.observer_health as Item | undefined
  const executionErrors = readableErrors(current?.execution_errors)
  const reasonCodes = Array.isArray(current?.reason_codes) ? current.reason_codes.map(String) : []
  const preferredEvidence = useMemo(() => Array.isArray(selectedFinding?.occurrence?.evidence_refs) ? selectedFinding.occurrence.evidence_refs.map(String) : [], [selectedFinding])
  return <Space direction="vertical" size="large" className="full-width">
    <PageTaskHeader title="检查结果" description="先看当前安全检查结论，再查看稳定问题、证据事实和完整报告。" status={conclusion(current)} next={current?.result_integrity === 'VERIFIED' ? '结果已发布' : integrityLabel(current?.result_integrity)} actionLabel={current?.result_integrity === 'VERIFIED' ? '重新开始检查' : undefined} onAction={onNext} />
    {!current && <Alert type="info" showIcon message="尚未选择检查结果。" />}
    {current && <Card className="result-summary" title="结论摘要"><Space direction="vertical" className="full-width"><Space wrap><Tag color={conclusion(current) === '发现权限问题' ? 'red' : conclusion(current) === '未发现确认问题' ? 'green' : 'gold'}>{conclusion(current)}</Tag><Tag>检查状态：{lifecycleLabel(current.lifecycle)}</Tag><Tag>结果完整性：{integrityLabel(current.result_integrity)}</Tag></Space><Typography.Paragraph type="secondary">“未发现确认问题”仅限当前已执行规则与可用证据范围，不代表绝对安全。</Typography.Paragraph>{executionErrors.length > 0 && <Alert type="error" showIcon message="检查执行未完整结束" description={executionErrors.join('；')} />}{String(current.result_integrity) === 'INVALID' && <Alert type="warning" showIcon message="结果完整性校验未通过，不能形成安全结论。" />}<Descriptions size="small" column={{ xs: 1, sm: 2 }}><Descriptions.Item label="确认问题数">{vulnerableCount}</Descriptions.Item><Descriptions.Item label="严重度">{severities}</Descriptions.Item><Descriptions.Item label="证据数量">{evidence.length}</Descriptions.Item>{typeof current.coverage_record_count === 'number' && <Descriptions.Item label="覆盖记录">{current.coverage_record_count}</Descriptions.Item>}{typeof current.coverage_gap_count === 'number' && <Descriptions.Item label="覆盖缺口">{current.coverage_gap_count}</Descriptions.Item>}<Descriptions.Item label="必需观察状态">{observerSummary(observer)}</Descriptions.Item></Descriptions>{reasonCodes.length > 0 && <Collapse ghost items={[{ key: 'result-reasons', label: '高级：结果原因代码', children: <Typography.Text code>{reasonCodes.join('、')}</Typography.Text> }]} />}</Space></Card>}
    {current && <Segmented block value={view} onChange={(value) => setView(value as 'results' | 'report')} options={[{ label: '结论与证据', value: 'results' }, { label: '完整报告', value: 'report' }]} />}
    {view === 'results' && current && <>
      <Card title="稳定问题"><List dataSource={findings} locale={{ emptyText: current.result_integrity === 'VERIFIED' ? '当前结果没有已确认问题。' : '结果尚未可用。' }} renderItem={(item) => { const identity = item.finding?.identity ?? {}; const occurrence = item.occurrence ?? {}; return <List.Item onClick={() => setSelectedFinding(item)} className="finding-list-item" tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setSelectedFinding(item) }}><Space direction="vertical" className="full-width"><Space wrap><Typography.Text strong>{identity.permission_intent ?? identity.problem_category ?? '权限问题'}</Typography.Text><Tag>{severityLabel(occurrence.severity)}</Tag><Tag>{occurrenceStatusLabel(occurrence.status)}</Tag><Tag>{verdictLabel(occurrence.verdict)}</Tag></Space><Typography.Text type="secondary">{[identity.subject_class, identity.action, identity.resource_class, identity.resource_relation, identity.problem_category].filter(Boolean).join(' · ') || '身份与资源摘要未提供'}</Typography.Text><Collapse ghost items={[{ key: 'finding-details', label: '高级：问题标识', children: <Descriptions size="small"><Descriptions.Item label="finding_id">{String(item.finding?.finding_id ?? identity.finding_id ?? '未提供')}</Descriptions.Item><Descriptions.Item label="occurrence_id">{String(occurrence.occurrence_id ?? '未提供')}</Descriptions.Item></Descriptions> }]} /></Space></List.Item> }} /></Card>
      <EvidenceTimeline runId={String(current.run_id)} evidence={evidence} preferredIds={preferredEvidence} onError={onError} />
    </>}
    {view === 'report' && <ReportPanel run={current} onError={onError} />}
  </Space>
}
