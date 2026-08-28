/* =============================================================================
 * 历史变化
 *
 * 定位
 *   展示后端 HistoryView 已确认的跨次变化，不重复结果页的完整证据故事。
 *
 * 职责
 *   按权限问题归组｜只表达新发现、仍存在、已解决、证据不足和本次未覆盖
 *   ｜缺失记录不推断已解决
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Descriptions, Select, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi, type HistoryChangeDto, type HistoryViewDto } from '../../api/results'
import { formatTimestamp, severityLabel } from '../../app/presentation'
import { AdvancedDetails } from '../../components/AdvancedDetails'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { TaskActionBar } from '../../components/TaskActionBar'
import './checks.css'

function statusColor(status: HistoryChangeDto['status']) {
  if (status === 'NEW' || status === 'PERSISTENT') return 'red'
  if (status === 'FIXED') return 'green'
  if (status === 'INCONCLUSIVE') return 'gold'
  return 'default'
}

export function CheckHistoryPage({ projectId, onError, onBack }: { projectId?: string; onError: (error: ApiError) => void; onBack?: () => void }) {
  const [history, setHistory] = useState<HistoryViewDto | null>(null)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<string>()
  const [findingId, setFindingId] = useState<string>()
  const [refreshEpoch, setRefreshEpoch] = useState(0)

  useEffect(() => {
    setHistory(null)
    if (!projectId) return
    let active = true
    setLoading(true)
    void resultsApi.history(projectId).then((value) => {
      if (active) setHistory(value)
    }).catch((error) => {
      if (active) onError(error as ApiError)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [projectId, refreshEpoch])

  const changes = useMemo(() => (history?.comparisons ?? []).flatMap((comparison) => comparison.changes.map((change) => ({ ...change, run_id: comparison.run_id, previous_run_id: comparison.previous_run_id, checked_at_us: comparison.checked_at_us }))), [history])
  const statuses = [...new Map(changes.map((change) => [change.status, change.status_label])).entries()]
  const findingIds = [...new Set(changes.map((change) => change.finding_id))]
  const filtered = changes.filter((change) => (!status || change.status === status) && (!findingId || change.finding_id === findingId))
  const grouped: Array<[string, typeof filtered]> = [...filtered.reduce<Map<string, typeof filtered>>((map, item) => { const current = map.get(item.finding_id) ?? []; current.push(item); map.set(item.finding_id, current); return map }, new Map<string, typeof filtered>()).entries()]

  return <Space direction="vertical" size="large" className="full-width history-page">
    <PageTaskHeader title="历史变化" description="查看同一权限问题在多次检查中是新出现、仍存在、已经解决，还是暂时无法确认。" status={changes.length > 0 ? `已记录 ${changes.length} 次变化` : '暂无可比较变化'} />
    {!projectId && <Alert type="info" showIcon message="先选择应用后才能查看历史变化。" />}
    {projectId && loading && <section className="history-section"><Typography.Paragraph type="secondary">正在读取后端整理的历史变化。</Typography.Paragraph></section>}
    {projectId && !loading && <section className="history-section" aria-labelledby="history-list-title">
      <div className="history-section-heading"><div><Typography.Title id="history-list-title" level={3}>权限问题的变化轨迹</Typography.Title><Typography.Paragraph type="secondary">这里不重复每次检查的完整证据，只说明问题相对上一次发生了什么变化。</Typography.Paragraph></div><div className="history-filters"><Select allowClear placeholder="按变化状态筛选" value={status} onChange={setStatus} options={statuses.map(([value, label]) => ({ value, label }))} /><Select allowClear placeholder="按问题筛选" value={findingId} onChange={setFindingId} options={findingIds.map((value, index) => ({ value, label: `问题 ${index + 1}` }))} /></div></div>
      {grouped.length === 0 && <Alert type="info" showIcon message="还没有可比较的历史变化。" />}
      <div className="history-group-list">{grouped.map(([key, items]) => <article className="history-group" key={key}>
        <header className="history-group-header"><div><Typography.Title level={4}>{items[0].title}</Typography.Title><Typography.Text className="result-context" type="secondary">{items[0].subject_group} · {items[0].action} · {items[0].resource} · {items[0].relation}</Typography.Text></div><Typography.Text type="secondary">{items.length} 次记录</Typography.Text></header>
        <ol className="history-timeline">{items.map((item) => <li key={`${item.run_id}-${item.finding_id}-${item.status}`}><div className={`history-marker history-marker-${item.status.toLowerCase()}`} aria-hidden="true" /><div className="history-event"><Typography.Text type="secondary">{formatTimestamp(item.checked_at_us)}</Typography.Text><div><Tag color={statusColor(item.status)}>{item.status_label}</Tag></div><Typography.Paragraph>{item.explanation}</Typography.Paragraph><AdvancedDetails label="高级：本次检查标识"><Descriptions size="small" column={{ xs: 1, sm: 2 }}><Descriptions.Item label="运行标识">{item.run_id}</Descriptions.Item><Descriptions.Item label="前次运行">{item.previous_run_id ?? '无'}</Descriptions.Item><Descriptions.Item label="问题标识">{item.finding_id}</Descriptions.Item><Descriptions.Item label="严重程度">{severityLabel(item.severity)}</Descriptions.Item><Descriptions.Item label="Occurrence">{item.occurrence_status ?? '未提供'}</Descriptions.Item><Descriptions.Item label="Evidence">{item.evidence_refs.join('、') || '无'}</Descriptions.Item></Descriptions></AdvancedDetails></div></li>)}</ol>
      </article>)}</div>
    </section>}
    <TaskActionBar back={onBack ? { label: '返回检查结果', onClick: onBack } : undefined} refresh={projectId ? { label: '刷新历史变化', onClick: () => setRefreshEpoch((value) => value + 1), loading } : undefined} />
  </Space>
}
