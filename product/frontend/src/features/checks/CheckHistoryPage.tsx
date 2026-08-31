/* =============================================================================
 * 历史变化
 *
 * 定位
 *   默认按长期 PermissionIntent 展示 revision 与可靠关联的 Run。
 *
 * 职责
 *   区分精确单意图关联与策略快照成员关系｜展示变化重验和修复状态
 *   ｜把 Finding 聚合保留为次级视图｜不因缺失记录推断问题已经解决。
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Collapse, Select, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi, type HistoryChangeDto, type HistoryViewDto, type ResultIntentHistoryDto } from '../../api/results'
import { formatTimestamp, verdictLabel } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { TaskActionBar } from '../../components/TaskActionBar'
import './checks.css'

function statusColor(status: HistoryChangeDto['status']) {
  if (status === 'NEW' || status === 'PERSISTENT') return 'red'
  if (status === 'FIXED') return 'green'
  if (status === 'INCONCLUSIVE') return 'gold'
  return 'default'
}

function repairLabel(value: string | null) {
  return ({ VERIFIED: '原考题复验通过', NOT_VERIFIED: '原考题复验未通过', INCONCLUSIVE: '原考题复验证据不足' } as Record<string, string>)[String(value)] ?? null
}

function IntentHistory({ intent }: { intent: ResultIntentHistoryDto }) {
  const latest = intent.revisions.at(-1)
  return <article className="history-intent" aria-labelledby={`history-${intent.display_label}`}>
    <header className="history-group-header"><div><Space wrap><Tag color="blue">{intent.display_label}</Tag><Typography.Text strong>{latest ? `当前第 ${latest.revision} 版` : '没有版本'}</Typography.Text></Space><Typography.Title id={`history-${intent.display_label}`} level={4}>{latest?.business_statement ?? '权限业务语义不可用'}</Typography.Title></div>{latest && <Tag color={latest.effective_state === 'ACTIVE' ? 'green' : 'default'}>{latest.effective_state === 'ACTIVE' ? '当前生效' : '已退休'}</Tag>}</header>
    <ol className="history-intent-runs">{intent.runs.map((run) => <li key={run.run_id}>
      <span className={`history-marker history-marker-${run.association_status === 'EXACT' ? 'fixed' : 'inconclusive'}`} aria-hidden="true" />
      <div className="history-event">
        <Space wrap><Typography.Text strong>{formatTimestamp(run.checked_at_us)}</Typography.Text><Tag color={run.association_status === 'EXACT' ? 'green' : 'gold'}>{run.association_status === 'EXACT' ? '可可靠关联' : '仅确认属于本轮策略'}</Tag>{run.change_revalidation && <Tag color="blue">代码变化重验</Tag>}{repairLabel(run.repair_status) && <Tag color={run.repair_status === 'VERIFIED' ? 'green' : 'gold'}>{repairLabel(run.repair_status)}</Tag>}</Space>
        <Typography.Paragraph type="secondary">{run.association_note}</Typography.Paragraph>
        {run.association_status === 'EXACT' && run.verdict && <Typography.Text>{verdictLabel(run.verdict)}</Typography.Text>}
        {run.association_status === 'EXACT' && run.diagnosis_summary && <Typography.Text>{run.diagnosis_summary}</Typography.Text>}
        <Collapse ghost items={[{ key: 'technical', label: '查看技术标识', children: <Space direction="vertical"><Typography.Text code>{run.run_id}</Typography.Text><Typography.Text code>{run.intent_hash}</Typography.Text></Space> }]} />
      </div>
    </li>)}</ol>
    <Collapse items={[{ key: 'revisions', label: `查看 ${intent.revisions.length} 个权限版本`, children: <ol className="history-revision-list">{intent.revisions.map((revision) => <li key={revision.revision}><Space wrap><Typography.Text strong>第 {revision.revision} 版</Typography.Text><Tag>{revision.effective_state === 'ACTIVE' ? '生效' : '退休'}</Tag><Typography.Text type="secondary">{formatTimestamp(revision.approved_at_us)} 由 {revision.approved_by} 确认</Typography.Text></Space><Typography.Paragraph>{revision.business_statement}</Typography.Paragraph><Collapse ghost items={[{ key: 'hash', label: '查看技术标识', children: <Typography.Text code>{revision.intent_hash}</Typography.Text> }]} /></li>)}</ol> }]} />
  </article>
}

function FindingSummary({ history }: { history: HistoryViewDto }) {
  const changes = history.comparisons.flatMap((comparison) => comparison.changes.map((change) => ({ ...change, run_id: comparison.run_id, checked_at_us: comparison.checked_at_us, change_verification: comparison.change_verification })))
  const grouped = [...changes.reduce<Map<string, typeof changes>>((map, item) => { const current = map.get(item.finding_id) ?? []; current.push(item); map.set(item.finding_id, current); return map }, new Map()).values()]
  if (grouped.length === 0) return <Alert type="info" showIcon message="没有可展示的问题聚合" />
  return <div className="history-group-list">{grouped.map((items) => <article className="history-group" key={items[0].finding_id}><Typography.Title level={5}>{items[0].title}</Typography.Title><Typography.Text className="result-context" type="secondary">{items[0].subject_group} · {items[0].action} · {items[0].resource} · {items[0].relation}</Typography.Text><ol className="history-timeline">{items.map((item) => <li key={`${item.run_id}-${item.finding_id}`}><span className={`history-marker history-marker-${item.status.toLowerCase()}`} aria-hidden="true" /><div className="history-event"><Space wrap><Typography.Text strong>{formatTimestamp(item.checked_at_us)}</Typography.Text><Tag color={statusColor(item.status)}>{item.status_label}</Tag></Space>{item.change_verification && <><Typography.Text>本次检查由最近一次代码修改触发</Typography.Text><Typography.Text>使用你之前确认的 {item.change_verification.required_intents.length} 条权限要求重新检查</Typography.Text></>}<Typography.Paragraph>{item.explanation}</Typography.Paragraph></div></li>)}</ol></article>)}</div>
}

export function CheckHistoryPage({ projectId, onError, onBack }: { projectId?: string; onError: (error: ApiError) => void; onBack?: () => void }) {
  const [history, setHistory] = useState<HistoryViewDto | null>(null)
  const [loading, setLoading] = useState(false)
  const [intentId, setIntentId] = useState<string>()
  const [refreshEpoch, setRefreshEpoch] = useState(0)

  useEffect(() => {
    setHistory(null)
    setIntentId(undefined)
    if (!projectId) return
    let active = true
    setLoading(true)
    void resultsApi.history(projectId).then((value) => { if (active) setHistory(value) }).catch((error) => { if (active) onError(error as ApiError) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [projectId, refreshEpoch])

  const intents = history?.intents ?? []
  const visible = useMemo(() => intentId ? intents.filter((item) => item.intent_id === intentId) : intents, [intentId, intents])
  const runCount = intents.reduce((total, item) => total + item.runs.length, 0)

  return <Space direction="vertical" size="large" className="full-width history-page">
    <PageTaskHeader title="历史变化" description="默认按人确认的权限要求，查看版本、重验与可靠关联的检查结果。" status={intents.length > 0 ? `${intents.length} 条权限要求 · ${runCount} 次关联` : '暂无权限历史'} />
    {!projectId && <Alert type="info" showIcon message="先选择应用后才能查看历史变化。" />}
    {projectId && loading && <section className="history-section"><Typography.Paragraph type="secondary">正在读取后端整理的历史变化。</Typography.Paragraph></section>}
    {projectId && !loading && <section className="history-section" aria-labelledby="history-intent-title">
      <div className="history-section-heading"><div><Typography.Title id="history-intent-title" level={3}>按权限要求查看</Typography.Title><Typography.Paragraph type="secondary">只有单条权限规则版本与本轮检查完整匹配时，才把结论和诊断归到该权限要求；其他情况只标明它属于当轮规则集合。</Typography.Paragraph></div><Select allowClear placeholder="筛选权限要求" value={intentId} onChange={setIntentId} options={intents.map((item) => ({ value: item.intent_id, label: item.display_label }))} /></div>
      {visible.length === 0 && <Alert type="info" showIcon message="还没有可展示的权限要求历史。" />}
      <div className="history-intent-list">{visible.map((intent) => <IntentHistory intent={intent} key={intent.intent_id} />)}</div>
      {history && (intents.length === 0 ? <FindingSummary history={history} /> : <Collapse items={[{ key: 'finding-summary', label: '按权限问题查看次级聚合', children: <FindingSummary history={history} /> }]} />)}
    </section>}
    <TaskActionBar back={onBack ? { label: '返回检查结果', onClick: onBack } : undefined} refresh={projectId ? { label: '刷新历史', onClick: () => setRefreshEpoch((value) => value + 1), loading } : undefined} />
  </Space>
}
