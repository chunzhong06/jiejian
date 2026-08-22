/* 只按事实顺序展示已发布 Evidence；Verdict 由后端确定，原始 JSON 仅供高级查看。 */

import { useEffect, useState, type ReactNode } from 'react'
import { Alert, Card, Collapse, Descriptions, List, Select, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi, type EvidenceCaseSnapshotDto, type EvidenceDto, type ExecutionFactDto, type ObservationFactDto, type SecurityEffectFactDto } from '../../api/results'
import { expectationLabel, productTermLabel, verdictLabel } from '../../app/presentation'

type TechnicalObservationDto = {
  observer_type?: string
  phase?: string
  target_id?: string
  correlation?: { resource_id?: string }
  completeness?: string
  causality?: string
  state?: { canonical_data?: unknown }
}
type TechnicalOutcomeDto = { observer_id?: string; required?: boolean; status?: string }
function text(value: unknown): string {
  if (value === undefined || value === null || value === '') return '未提供'
  if (Array.isArray(value)) return value.map(text).join('、') || '未提供'
  if (typeof value === 'object') return '未提供'
  return String(value)
}
function list(value: unknown) { return Array.isArray(value) && value.length > 0 ? value.map(text).join('、') : '未提供' }
function requirementLabel(value: unknown) { return ({ resource_state: '资源状态' } as Record<string, string>)[String(value)] ?? `观察要求：${text(value)}` }
function targetLabel(value: unknown) { return ({ WEB: 'Web 应用', PROCESS: '本地进程', MCP: 'MCP/Agent 服务', MCP_AGENT: 'MCP/Agent 服务' } as Record<string, string>)[String(value)] ?? `目标：${text(value)}` }
function outcomeLabel(value: unknown) { return ({ ACCEPTED: '执行已允许', DENIED: '执行已拒绝', FAILED: '执行失败', UNKNOWN: '执行结果无法确定' } as Record<string, string>)[String(value)] ?? `执行状态：${text(value)}` }
function effectLabel(value: unknown) { return ({ CONFIRMED: '资源状态发生变化', ABSENT: '资源状态未变化', UNKNOWN: '无法可靠获取资源状态' } as Record<string, string>)[String(value)] ?? `观察结果：${text(value)}` }
function securityEffectLabel(value: unknown) { return ({ STATE_MUTATION: '状态变更', DATA_DISCLOSURE: '受保护数据披露', OBJECT_CREATION: '对象创建', EXTERNAL_DISPATCH: '外部发送', RESTRICTED_FUNCTION_INVOCATION: '受限功能调用', CREDENTIAL_ACCESS: '凭据访问' } as Record<string, string>)[String(value)] ?? text(value) }
function effectStateLabel(value: unknown) { return ({ CONFIRMED: '已确认发生', ABSENT: '已确认未发生', UNKNOWN: '尚无法确定' } as Record<string, string>)[String(value)] ?? text(value) }
function closureLabel(value: unknown) { return ({ CLOSED: '证据窗口已闭合', OPEN: '仍可能出现后续影响', UNKNOWN: '闭合状态未知' } as Record<string, string>)[String(value)] ?? text(value) }
function twinRoleLabel(value: unknown) { return ({ ALLOW_CONTROL: '允许场景对照', DENY_VARIANT: '禁止场景检查' } as Record<string, string>)[String(value)] ?? '独立检查' }
function booleanLabel(value: unknown, positive: string, negative: string) { return value === true ? positive : negative }
function observerLabel(value: unknown) { return ({ HTTP: '接口响应', OWNER_API: '资源状态接口', READ_ONLY_SQLITE: '只读数据状态', STRUCTURED_AUDIT_LOG: '审计记录', ASYNC_TASK_STATUS: '异步任务状态', AZURE_QUEUE_PEEK: '队列状态', AZURE_BLOB_OBJECT: '文件状态' } as Record<string, string>)[String(value)] ?? '外部状态观察' }
function phaseLabel(value: unknown) { return ({ BEFORE: '请求前', AFTER: '请求后', EVENTUAL: '最终状态' } as Record<string, string>)[String(value)] ?? text(value) }
function completenessLabel(value: unknown) { return ({ COMPLETE: '完整', PARTIAL: '部分可用', INCOMPLETE: '未完成' } as Record<string, string>)[String(value)] ?? text(value) }
function causalityLabel(value: unknown) { return ({ CORRELATED: '已确认与本次请求相关', UNCORRELATED: '未确认关联', UNKNOWN: '关联尚不明确' } as Record<string, string>)[String(value)] ?? text(value) }
function facts(value: unknown) {
  if (!value || typeof value !== 'object') return []
  return Object.entries(value as Record<string, unknown>).flatMap(([key, item]) => {
    if (item === null || item === undefined || typeof item === 'object' && !Array.isArray(item)) return []
    return [{ key, value: Array.isArray(item) ? item.map(text).join('、') : text(item) }]
  }).slice(0, 8)
}

export function EvidenceTimeline({ runId, evidence, preferredIds = [], onError }: { runId?: string; evidence: EvidenceDto[]; preferredIds?: string[]; onError: (error: ApiError) => void }) {
  const [selectedId, setSelectedId] = useState<string>()
  const [detail, setDetail] = useState<EvidenceDto | null>(null)
  useEffect(() => { setSelectedId(preferredIds.find((id) => evidence.some((item) => String(item.evidence_id) === String(id))) ?? (evidence[0]?.evidence_id ? String(evidence[0].evidence_id) : undefined)) }, [evidence, preferredIds.join('|')])
  useEffect(() => {
    if (!runId || !selectedId) { setDetail(null); return }
    // 旧请求可能晚于当前选择返回，失效响应不得覆盖用户正在查看的 Evidence。
    let active = true
    setDetail(null)
    void resultsApi.evidenceDetail(runId, selectedId).then((value) => { if (active) setDetail(value) }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [runId, selectedId])
  const executionFact = detail?.execution_fact
  const observationFacts = Array.isArray(detail?.observation_facts) ? detail.observation_facts : []
  const securityEffectFacts = Array.isArray(detail?.security_effect_facts) ? detail.security_effect_facts : []
  return <Card title="证据时间线">
    {evidence.length === 0 && <Alert type="info" showIcon message="没有可展示的已发布证据。" />}
    {evidence.length > 0 && <Select aria-label="选择证据" className="full-width" value={selectedId} onChange={setSelectedId} options={evidence.map((item, index) => ({ value: String(item.evidence_id), label: `证据 ${index + 1}` }))} />}
    {detail && <div className="evidence-timeline">
      <TimelineStep title="检查对象"><CaseFacts value={detail.case_snapshot} /></TimelineStep>
      <TimelineStep title="对照与基线"><DifferentialFacts value={detail} /></TimelineStep>
      <TimelineStep title="执行事实"><ExecutionFacts value={executionFact} /></TimelineStep>
      <TimelineStep title="真实影响"><SecurityEffectFacts values={securityEffectFacts} /></TimelineStep>
      <TimelineStep title="真实观察"><ObservationFacts values={observationFacts} /></TimelineStep>
      <TimelineStep title="确定性结论"><Tag>{verdictLabel(detail.verdict)}</Tag></TimelineStep>
      <Collapse ghost items={[{ key: 'technical', label: '高级：技术详情', children: <TechnicalDetails detail={detail} /> }]} />
    </div>}
  </Card>
}

function CaseFacts({ value = {} }: { value?: EvidenceCaseSnapshotDto }) {
  const resources = Array.isArray(value.resource_ids) ? value.resource_ids : []
  const expectations = Array.isArray(value.expectations) ? value.expectations : []
  return <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
    <Descriptions.Item label="身份">{productTermLabel('identity', value.subject_id)}</Descriptions.Item>
    <Descriptions.Item label="动作">{productTermLabel('action', value.action_id)}</Descriptions.Item>
    <Descriptions.Item label="资源">{resources.map((item: unknown) => productTermLabel('resource', item)).join('、') || '未提供'}</Descriptions.Item>
    <Descriptions.Item label="预期">{expectations.map(expectationLabel).join('、') || '未提供'}</Descriptions.Item>
    <Descriptions.Item label="关系路径">{Array.isArray(value.relation_paths) ? value.relation_paths.map((path: unknown) => list(path)).join('；') : '未提供'}</Descriptions.Item>
    <Descriptions.Item label="必需观察">{Array.isArray(value.required_observations) && value.required_observations.length > 0 ? value.required_observations.map(requirementLabel).join('、') : '未提供'}</Descriptions.Item>
  </Descriptions>
}

function ExecutionFacts({ value = {} }: { value?: ExecutionFactDto }) {
  if (!value || Object.keys(value).length === 0) return <Typography.Text type="secondary">未提供执行事实</Typography.Text>
  return <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
    <Descriptions.Item label="检查目标">{targetLabel(value.target_type)}</Descriptions.Item>
    <Descriptions.Item label="动作">{productTermLabel('action', value.action_id)}</Descriptions.Item>
    <Descriptions.Item label="执行结果"><Tag>{outcomeLabel(value.outcome)}</Tag></Descriptions.Item>
    {Array.isArray(value.reason_codes) && value.reason_codes.length > 0 && <Descriptions.Item label="原因">{list(value.reason_codes)}</Descriptions.Item>}
  </Descriptions>
}

function DifferentialFacts({ value }: { value: EvidenceDto }) {
  return <Descriptions size="small" column={{ xs: 1, sm: 2 }}>
    <Descriptions.Item label="当前场景"><Tag color={value.twin_role === 'ALLOW_CONTROL' ? 'green' : value.twin_role === 'DENY_VARIANT' ? 'red' : undefined}>{twinRoleLabel(value.twin_role)}</Tag></Descriptions.Item>
    <Descriptions.Item label="允许场景对照">{booleanLabel(value.allow_control_valid, '有效', '无效或未完成')}</Descriptions.Item>
    <Descriptions.Item label="基线可比性">{booleanLabel(value.baseline_integrity, '基线一致', '基线无法确认')}</Descriptions.Item>
  </Descriptions>
}

function SecurityEffectFacts({ values }: { values: SecurityEffectFactDto[] }) {
  if (values.length === 0) return <Typography.Text type="secondary">未提供聚合后的真实影响</Typography.Text>
  return <List size="small" dataSource={values} renderItem={(item) => <List.Item className="observation-item"><Descriptions size="small" column={{ xs: 1, sm: 2 }} className="full-width">
    <Descriptions.Item label="影响类型">{securityEffectLabel(item.kind)}</Descriptions.Item>
    <Descriptions.Item label="资源">{productTermLabel('resource', item.resource_id)}</Descriptions.Item>
    <Descriptions.Item label="影响状态"><Tag color={item.state === 'CONFIRMED' ? 'red' : item.state === 'ABSENT' ? 'green' : 'gold'}>{effectStateLabel(item.state)}</Tag></Descriptions.Item>
    <Descriptions.Item label="证据闭合">{closureLabel(item.temporal_closure)}</Descriptions.Item>
    <Descriptions.Item label="证据质量">{item.complete && item.reliable && item.correlated ? '完整、可靠且已关联' : '仍有证据缺口'}</Descriptions.Item>
    <Descriptions.Item label="基线">{booleanLabel(item.baseline_integrity, '一致', '无法确认')}</Descriptions.Item>
    {Array.isArray(item.reason_codes) && item.reason_codes.length > 0 && <Descriptions.Item label="原因代码">{list(item.reason_codes)}</Descriptions.Item>}
  </Descriptions></List.Item>} />
}

function ObservationFacts({ values }: { values: ObservationFactDto[] }) {
  if (values.length === 0) return <Typography.Text type="secondary">未提供真实观察事实</Typography.Text>
  return <List size="small" dataSource={values} renderItem={(item) => <List.Item className="observation-item"><Descriptions size="small" column={{ xs: 1, sm: 2 }} className="full-width"><Descriptions.Item label="观察要求">{requirementLabel(item.requirement_id)}</Descriptions.Item><Descriptions.Item label="资源">{productTermLabel('resource', item.resource_id)}</Descriptions.Item><Descriptions.Item label="效果"><Tag>{effectLabel(item.effect)}</Tag></Descriptions.Item><Descriptions.Item label="完整性">{booleanLabel(item.complete, '完整', '未完成')}</Descriptions.Item><Descriptions.Item label="可靠性">{booleanLabel(item.reliable, '可靠', '不可靠')}</Descriptions.Item>{Array.isArray(item.reason_codes) && item.reason_codes.length > 0 && <Descriptions.Item label="原因代码">{list(item.reason_codes)}</Descriptions.Item>}</Descriptions></List.Item>} />
}

function TechnicalDetails({ detail }: { detail: EvidenceDto }) {
  const observations = Array.isArray(detail.observations) ? detail.observations as TechnicalObservationDto[] : []
  const outcomes = Array.isArray(detail.outcomes) ? detail.outcomes as TechnicalOutcomeDto[] : []
  return <Space direction="vertical" className="full-width">
    {observations.length > 0 && <List size="small" dataSource={observations} renderItem={(item) => <List.Item><Descriptions size="small" column={{ xs: 1, sm: 2 }} className="full-width"><Descriptions.Item label="观察来源">{observerLabel(item.observer_type)}</Descriptions.Item><Descriptions.Item label="时点">{phaseLabel(item.phase)}</Descriptions.Item><Descriptions.Item label="目标">{text(item.correlation?.resource_id ?? item.target_id)}</Descriptions.Item><Descriptions.Item label="完整性">{completenessLabel(item.completeness)}</Descriptions.Item><Descriptions.Item label="因果关联">{causalityLabel(item.causality)}</Descriptions.Item><Descriptions.Item label="观察状态">{item.state?.canonical_data ? <PlainFacts value={item.state.canonical_data} empty="已采集" /> : '未采集完整状态'}</Descriptions.Item></Descriptions></List.Item>} />}
    {outcomes.length > 0 && <Descriptions size="small" column={1}>{outcomes.map((item, index) => <Descriptions.Item key={`${item.observer_id ?? 'outcome'}-${index}`} label={`${observerLabel(item.observer_id === 'http' ? 'HTTP' : item.observer_id === 'owner_api' ? 'OWNER_API' : undefined)}${item.required ? '（必需）' : ''}`}>{text(item.status)}</Descriptions.Item>)}</Descriptions>}
    <pre className="report-view">{JSON.stringify(detail, null, 2)}</pre>
  </Space>
}

function PlainFacts({ value, empty }: { value: unknown; empty: string }) {
  const items = Array.isArray(value) ? value.flatMap(facts) : facts(value)
  if (items.length === 0) return <Typography.Text type="secondary">{empty}</Typography.Text>
  return <span>{items.map((item) => `${item.key}：${item.value}`).join('；')}</span>
}

function TimelineStep({ title, children }: { title: string; children: ReactNode }) {
  return <section className="evidence-timeline-item"><span className="evidence-timeline-dot" aria-hidden="true" /><Typography.Title level={5}>{title}</Typography.Title><div className="evidence-timeline-content">{children}</div></section>
}
