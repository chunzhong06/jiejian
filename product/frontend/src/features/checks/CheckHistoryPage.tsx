/* 历史变化：直接展示后端 HistoryView，不按缺失记录推断已修复。 */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Card, Collapse, Select, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi, type HistoryViewDto } from '../../api/results'
import { formatTimestamp, severityLabel } from '../../app/presentation'
import './checks.css'

export function CheckHistoryPage({ projectId, onError }: { projectId?: string; onError: (error: ApiError) => void }) {
  const [history, setHistory] = useState<HistoryViewDto | null>(null)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<string>()
  const [findingId, setFindingId] = useState<string>()

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
  }, [projectId])

  const changes = useMemo(() => (history?.comparisons ?? []).flatMap((comparison) => comparison.changes.map((change) => ({ ...change, run_id: comparison.run_id, previous_run_id: comparison.previous_run_id, checked_at_us: comparison.checked_at_us }))), [history])
  const statuses = [...new Map(changes.map((change) => [change.status, change.status_label])).entries()]
  const findingIds = [...new Set(changes.map((change) => change.finding_id))]
  const filtered = changes.filter((change) => (!status || change.status === status) && (!findingId || change.finding_id === findingId))
  const grouped: Array<[string, typeof filtered]> = [...filtered.reduce<Map<string, typeof filtered>>((map, item) => { const current = map.get(item.finding_id) ?? []; current.push(item); map.set(item.finding_id, current); return map }, new Map<string, typeof filtered>()).entries()]

  return <Card title="历史变化">
    {!projectId && <Typography.Paragraph type="secondary">先选择应用后才能查看历史变化。</Typography.Paragraph>}
    {projectId && loading && <Typography.Paragraph type="secondary">正在读取后端整理的历史变化。</Typography.Paragraph>}
    {projectId && !loading && <Space direction="vertical" className="full-width">
      <Space wrap>
        <Select allowClear placeholder="按变化状态筛选" value={status} onChange={setStatus} options={statuses.map(([value, label]) => ({ value, label }))} />
        <Select allowClear placeholder="按问题筛选" value={findingId} onChange={setFindingId} options={findingIds.map((value, index) => ({ value, label: `问题 ${index + 1}` }))} />
      </Space>
      {grouped.length === 0 && <Alert type="info" showIcon message="还没有可比较的历史变化。" />}
      {grouped.map(([key, items]) => <Card size="small" key={key} title={items[0].title}>
        <Typography.Paragraph type="secondary">{items[0].subject_group} · {items[0].action} · {items[0].resource} · {items[0].relation}</Typography.Paragraph>
        <ol className="history-timeline">{items.map((item) => <li key={`${item.run_id}-${item.finding_id}-${item.status}`}><div className="history-marker" aria-hidden="true" /><div className="history-event"><Typography.Text type="secondary">{formatTimestamp(item.checked_at_us)}</Typography.Text><Space wrap><Tag>{item.status_label}</Tag><Tag>{severityLabel(item.severity)}</Tag></Space><Typography.Paragraph>{item.explanation}</Typography.Paragraph><Collapse ghost items={[{ key: `history-details-${item.run_id}`, label: '高级：检查标识', children: <Typography.Text code>运行标识：{item.run_id}；前次运行：{item.previous_run_id ?? '无'}；Occurrence：{item.occurrence_status ?? '未提供'}</Typography.Text> }]} /></div></li>)}</ol>
      </Card>)}
    </Space>}
  </Card>
}
