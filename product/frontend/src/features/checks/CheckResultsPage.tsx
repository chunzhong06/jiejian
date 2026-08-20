/* =============================================================================
 * 检查结果投影
 *
 * 把已发布 Finding 与 Evidence 解释为预期、表面结果和真实影响；不重算后端 Verdict。
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Collapse, Descriptions, List, Segmented, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi, type EvidenceDto, type FindingDto, type ObservationFactDto } from '../../api/results'
import { runsApi, type RunDto } from '../../api/runs'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { integrityLabel, lifecycleLabel, occurrenceStatusLabel, productTermLabel, severityLabel, verdictLabel } from '../../app/presentation'
import { EvidenceTimeline } from './EvidenceTimeline'
import { ReportPanel } from './ReportPanel'
import './checks.css'

const issueVerdicts = new Set(['BLOCK', 'VULNERABLE'])

function requirementLabel(value: unknown) { return ({ resource_state: '资源状态' } as Record<string, string>)[String(value)] ?? `观察要求：${String(value ?? '未提供')}` }
function expectationText(value: unknown) {
  const items = Array.isArray(value) ? value.map(String) : []
  if (items.includes('DENY')) return '不应允许这次操作，资源也不应发生变化'
  if (items.includes('ALLOW')) return '应允许这次操作，并完成预期的资源变化'
  return '按当前权限规则执行'
}
function surfaceText(value: unknown) {
  return ({ DENIED: '页面或接口显示已拒绝', ACCEPTED: '页面或接口显示已接受', FAILED: '操作执行失败', UNKNOWN: '表面结果无法确定' } as Record<string, string>)[String(value)] ?? '表面结果未提供'
}
function actualText(value: unknown) {
  const facts = Array.isArray(value) ? value : []
  const effects = new Set((facts as ObservationFactDto[]).map((item) => String(item.effect)))
  if (effects.has('CONFIRMED')) return '真实资源已经发生变化'
  if (effects.size > 0 && [...effects].every((item) => item === 'ABSENT')) return '真实资源没有发生变化'
  return '真实资源状态尚不能可靠确认'
}
function explanation(detail: EvidenceDto | undefined, verdict: unknown) {
  const outcome = String(detail?.execution_fact?.outcome ?? '')
  const facts = Array.isArray(detail?.observation_facts) ? detail.observation_facts : []
  const changed = facts.some((item) => String(item.effect) === 'CONFIRMED')
  if (issueVerdicts.has(String(verdict)) && outcome === 'DENIED' && changed) return '界面虽然显示拒绝，但外部观察确认资源已被改变；表面拒绝没有阻止真实副作用，因此构成权限问题。'
  if (issueVerdicts.has(String(verdict)) && changed) return '这次操作产生了权限规则不允许的真实资源变化，因此构成权限问题。'
  if (String(verdict) === 'INCONCLUSIVE') return '必需观察不完整或不可靠，当前证据不足以确认资源是否按权限规则变化。'
  return '表面执行结果与真实资源观察共同支持当前结论。'
}
function conclusion(run: RunDto | undefined) {
  if (!run) return '等待检查结果'
  if (!['COMPLETED', 'SAFETY_STOPPED'].includes(String(run.lifecycle))) return '等待检查结果'
  if (String(run.result_integrity) !== 'VERIFIED') return '结果不可用'
  if (issueVerdicts.has(String(run.verdict))) return '发现权限问题'
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
    const configured = Boolean(item && typeof item === 'object' && (item as { configured?: boolean }).configured === true)
    return `${requirementLabel(id)} · ${configured ? '已配置' : '缺失'}`
  }).join('；')
}
function readableErrors(value: unknown) {
  if (!Array.isArray(value)) return []
  return value.map((item) => typeof item === 'object' && item ? String((item as { message?: string; code?: string }).message ?? (item as { code?: string }).code ?? '执行失败') : String(item))
}

export function CheckResultsPage({ run, onError, onNext, initialView = 'results' }: { run?: RunDto; onError: (error: ApiError) => void; onNext?: () => void; initialView?: 'results' | 'report' }) {
  const [current, setCurrent] = useState<RunDto | undefined>(run)
  const [findings, setFindings] = useState<FindingDto[]>([])
  const [evidence, setEvidence] = useState<EvidenceDto[]>([])
  const [details, setDetails] = useState<Record<string, EvidenceDto>>({})
  const [view, setView] = useState<'results' | 'report'>(initialView)
  const [selectedFinding, setSelectedFinding] = useState<FindingDto | undefined>()
  useEffect(() => {
    setCurrent(run); setFindings([]); setEvidence([]); setDetails({}); setSelectedFinding(undefined); setView(initialView)
    if (!run?.run_id) return
    let active = true
    void runsApi.run(String(run.run_id)).then(async (authoritative) => {
      if (!active) return
      setCurrent(authoritative)
      if (String(authoritative.result_integrity) !== 'VERIFIED') return
      try {
        const [stable, publishedEvidence] = await Promise.all([resultsApi.findings(String(run.run_id)), resultsApi.evidence(String(run.run_id))])
        if (!active) return
        setFindings(stable); setEvidence(publishedEvidence); setSelectedFinding(stable[0])
        const evidenceIds = [...new Set(stable.flatMap((item) => {
          const occurrence = item.occurrence
          return Array.isArray(occurrence?.evidence_refs) ? occurrence.evidence_refs.map(String) : []
        }).filter(Boolean))]
        const loaded = await Promise.allSettled(evidenceIds.map(async (evidenceId) => [evidenceId, await resultsApi.evidenceDetail(String(run.run_id), evidenceId)] as const))
        if (!active) return
        setDetails(Object.fromEntries(loaded.flatMap((item) => item.status === 'fulfilled' ? [item.value] : [])))
        const failed = loaded.find((item) => item.status === 'rejected')
        if (failed?.status === 'rejected') onError(failed.reason as ApiError)
      } catch (error) { if (active) onError(error as ApiError) }
    }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [run?.run_id, initialView])
  const issueFindings = findings.filter((item) => issueVerdicts.has(String(item.occurrence?.verdict)))
  const inconclusiveCount = findings.filter((item) => String(item.occurrence?.verdict) === 'INCONCLUSIVE').length
  const severities = issueFindings.map((item) => severityLabel(item.occurrence?.severity)).join('、') || '无'
  const observer = current?.observer_health
  const executionErrors = readableErrors(current?.execution_errors)
  const reasonCodes = Array.isArray(current?.reason_codes) ? current.reason_codes.map(String) : []
  const preferredEvidence = useMemo(() => Array.isArray(selectedFinding?.occurrence?.evidence_refs) ? selectedFinding.occurrence.evidence_refs.map(String) : [], [selectedFinding])
  const headline = conclusion(current) === '发现权限问题'
    ? `发现 ${issueFindings.length} 个权限问题`
    : conclusion(current) === '证据不足'
      ? `${inconclusiveCount || 1} 项检查证据不足`
      : conclusion(current) === '未发现确认问题'
        ? '当前范围内未发现已确认的权限问题'
        : conclusion(current)
  return <Space direction="vertical" size="large" className="full-width">
    <PageTaskHeader title="检查结果" description="先判断有没有权限问题，再理解发生了什么，最后按需查看证据和完整报告。" status={conclusion(current)} next={current?.result_integrity === 'VERIFIED' ? '结果已发布' : integrityLabel(current?.result_integrity)} actionLabel={current?.result_integrity === 'VERIFIED' ? '重新开始检查' : undefined} onAction={onNext} />
    {!current && <Alert type="info" showIcon message="尚未选择检查结果。" />}
    {current && <Card className="result-summary"><Space direction="vertical" className="full-width" size="middle">
      <Typography.Title level={2} style={{ margin: 0 }}>{headline}</Typography.Title>
      <Typography.Paragraph type="secondary" style={{ margin: 0 }}>{conclusion(current) === '未发现确认问题' ? '这个结论仅覆盖本次实际执行的规则和可用证据，不代表绝对安全。' : conclusion(current) === '证据不足' ? '请先补齐缺失的观察能力，再重新检查；证据不足不等于安全。' : '先处理下面列出的真实权限影响，再查看证据细节。'}</Typography.Paragraph>
      <Space wrap><Tag color={conclusion(current) === '发现权限问题' ? 'red' : conclusion(current) === '未发现确认问题' ? 'green' : 'gold'}>{conclusion(current)}</Tag><Tag>检查状态：{lifecycleLabel(current.lifecycle)}</Tag><Tag>结果完整性：{integrityLabel(current.result_integrity)}</Tag></Space>
      {executionErrors.length > 0 && <Alert type="error" showIcon message="检查执行未完整结束" description={executionErrors.join('；')} />}
      {String(current.result_integrity) === 'INVALID' && <Alert type="warning" showIcon message="结果完整性校验未通过，不能形成安全结论。" />}
      <Descriptions size="small" column={{ xs: 1, sm: 2 }}><Descriptions.Item label="确认问题数">{issueFindings.length}</Descriptions.Item><Descriptions.Item label="严重度">{severities}</Descriptions.Item><Descriptions.Item label="证据数量">{evidence.length}</Descriptions.Item>{typeof current.coverage_record_count === 'number' && <Descriptions.Item label="覆盖记录">{current.coverage_record_count}</Descriptions.Item>}{typeof current.coverage_gap_count === 'number' && <Descriptions.Item label="覆盖缺口">{current.coverage_gap_count}</Descriptions.Item>}<Descriptions.Item label="必需观察状态">{observerSummary(observer)}</Descriptions.Item></Descriptions>
      {reasonCodes.length > 0 && <Collapse ghost items={[{ key: 'result-reasons', label: '高级：结果原因代码', children: <Typography.Text code>{reasonCodes.join('、')}</Typography.Text> }]} />}
    </Space></Card>}
    {current && <Segmented block value={view} onChange={(value) => setView(value as 'results' | 'report')} options={[{ label: '结论与证据', value: 'results' }, { label: '完整报告', value: 'report' }]} />}
    {view === 'results' && current && <>
      <Card title={issueFindings.length > 0 ? '需要处理的问题' : '检查项说明'}><List dataSource={findings} locale={{ emptyText: current.result_integrity === 'VERIFIED' ? '当前结果没有已确认问题。' : '结果尚未可用。' }} renderItem={(item) => {
        const identity = item.finding?.identity ?? {}
        const occurrence = item.occurrence ?? {}
        const evidenceId = Array.isArray(occurrence.evidence_refs) ? String(occurrence.evidence_refs[0] ?? '') : ''
        const detail = details[evidenceId]
        const snapshot = detail?.case_snapshot ?? {}
        return <List.Item className="finding-list-item"><Card size="small" className="full-width" title={<Space wrap><Typography.Text strong>{identity.permission_intent ?? identity.problem_category ?? '权限检查项'}</Typography.Text><Tag color={issueVerdicts.has(String(occurrence.verdict)) ? 'red' : String(occurrence.verdict) === 'INCONCLUSIVE' ? 'gold' : 'green'}>{verdictLabel(occurrence.verdict)}</Tag><Tag>{severityLabel(occurrence.severity)}</Tag></Space>} extra={<Button type="link" onClick={() => setSelectedFinding(item)}>查看对应证据</Button>}>
          <Descriptions size="small" column={{ xs: 1, md: 2 }}>
            <Descriptions.Item label="谁">{productTermLabel('identity', snapshot.subject_id ?? identity.subject_class)}</Descriptions.Item>
            <Descriptions.Item label="做什么">{productTermLabel('action', snapshot.action_id ?? identity.action)}</Descriptions.Item>
            <Descriptions.Item label="对什么资源">{Array.isArray(snapshot.resource_ids) ? snapshot.resource_ids.map((value: unknown) => productTermLabel('resource', value)).join('、') : productTermLabel('resource', identity.resource_class)}</Descriptions.Item>
            <Descriptions.Item label="规则预期">{expectationText(snapshot.expectations)}</Descriptions.Item>
            <Descriptions.Item label="表面结果">{surfaceText(detail?.execution_fact?.outcome)}</Descriptions.Item>
            <Descriptions.Item label="真实结果">{actualText(detail?.observation_facts)}</Descriptions.Item>
          </Descriptions>
          <Alert style={{ marginTop: 12 }} type={issueVerdicts.has(String(occurrence.verdict)) ? 'error' : String(occurrence.verdict) === 'INCONCLUSIVE' ? 'warning' : 'success'} showIcon message="为什么得到这个结论" description={explanation(detail, occurrence.verdict)} />
          <Space wrap style={{ marginTop: 12 }}><Tag>{occurrenceStatusLabel(occurrence.status)}</Tag><Collapse ghost items={[{ key: 'finding-details', label: '高级：问题标识', children: <Descriptions size="small"><Descriptions.Item label="finding_id">{String(item.finding?.finding_id ?? identity.finding_id ?? '未提供')}</Descriptions.Item><Descriptions.Item label="occurrence_id">{String(occurrence.occurrence_id ?? '未提供')}</Descriptions.Item></Descriptions> }]} /></Space>
        </Card></List.Item>
      }} /></Card>
      <EvidenceTimeline runId={String(current.run_id)} evidence={evidence} preferredIds={preferredEvidence} onError={onError} />
    </>}
    {view === 'report' && <ReportPanel run={current} onError={onError} />}
  </Space>
}
