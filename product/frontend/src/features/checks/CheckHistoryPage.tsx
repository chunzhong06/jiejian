/* 历史变化：只读取已验证运行中的稳定 Finding/Occurrence，不推断缺失点。 */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Card, Collapse, Select, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { resultsApi } from '../../api/results'
import { formatTimestamp, occurrenceStatusLabel, severityLabel } from '../../app/presentation'

type Item = Record<string, any>

export function CheckHistoryPage({ runs, onError }: { runs: Item[]; onError: (error: ApiError) => void }) {
  const [events, setEvents] = useState<Item[]>([])
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [status, setStatus] = useState<string>()
  const [findingId, setFindingId] = useState<string>()
  const readableRuns = useMemo(() => runs.filter((run) => ['COMPLETED', 'SAFETY_STOPPED'].includes(String(run.lifecycle)) && String(run.result_integrity) === 'VERIFIED').sort((left, right) => Number(left.created_at_us ?? left.created_at ?? 0) - Number(right.created_at_us ?? right.created_at ?? 0)), [runs])
  useEffect(() => {
    if (readableRuns.length < 2) { setEvents([]); setLoaded(true); return }
    let active = true
    setLoading(true); setLoaded(false); setEvents([])
    void (async () => {
      const collected: Item[] = []
      for (const run of readableRuns) {
        const result = await resultsApi.findings(String(run.run_id))
        if (!active) return
        for (const item of result) collected.push({ ...item, run_id: run.run_id, run_created_at_us: run.created_at_us ?? run.created_at })
      }
      if (active) { setEvents(collected); setLoaded(true); setLoading(false) }
    })().catch((error) => { if (active) { setLoaded(false); setLoading(false); onError(error as ApiError) } })
    return () => { active = false }
  }, [readableRuns.map((run) => run.run_id).join('|')])
  const identities = [...new Set(events.map((item) => String(item.finding?.finding_id ?? item.finding?.identity?.finding_id ?? '')))].filter(Boolean)
  const filtered = events.filter((item) => (!status || String(item.occurrence?.status) === status) && (!findingId || String(item.finding?.finding_id) === findingId))
  const grouped: Array<[string, Item[]]> = [...filtered.reduce<Map<string, Item[]>>((map, item) => { const key = String(item.finding?.finding_id ?? 'unknown'); const current = map.get(key) ?? []; current.push(item); map.set(key, current); return map }, new Map<string, Item[]>()).entries()]
  return <Card title="历史变化">
    {readableRuns.length < 2 && <Typography.Paragraph type="secondary">还没有两次已完成且结果完整的检查可供比较。</Typography.Paragraph>}
    {readableRuns.length >= 2 && loading && <Typography.Paragraph type="secondary">正在按检查时间读取真实问题变化。</Typography.Paragraph>}
    {readableRuns.length >= 2 && loaded && <Space direction="vertical" className="full-width"><Space wrap><Select allowClear placeholder="按变化状态筛选" value={status} onChange={setStatus} options={['APPEARED', 'PRESENT', 'DISAPPEARED', 'REAPPEARED', 'CHANGED'].map((value) => ({ value, label: occurrenceStatusLabel(value) }))} /><Select allowClear placeholder="按问题筛选" value={findingId} onChange={setFindingId} options={identities.map((value, index) => ({ value, label: `问题 ${index + 1}` }))} /></Space>{grouped.length === 0 && <Alert type="info" showIcon message="没有符合筛选条件的真实变化记录。" />}{grouped.map(([key, items]) => <Card size="small" key={key} title={items[0].finding?.identity?.permission_intent ?? items[0].finding?.identity?.problem_category ?? '权限问题'}><Typography.Paragraph type="secondary">{[items[0].finding?.identity?.subject_class, items[0].finding?.identity?.action, items[0].finding?.identity?.resource_class, items[0].finding?.identity?.resource_relation].filter(Boolean).join(' · ') || '身份与资源摘要未提供'}</Typography.Paragraph><ol className="history-timeline">{items.map((item) => <li key={`${item.run_id}-${item.occurrence?.occurrence_id ?? item.occurrence?.status}`}><div className="history-marker" aria-hidden="true" /><div className="history-event"><Typography.Text type="secondary">{formatTimestamp(item.run_created_at_us)}</Typography.Text><Space wrap><Tag>{occurrenceStatusLabel(item.occurrence?.status)}</Tag><Tag>{severityLabel(item.occurrence?.severity)}</Tag></Space><Collapse ghost items={[{ key: 'history-details', label: '高级：检查标识', children: <Typography.Text code>{String(item.run_id)}</Typography.Text> }]} /></div></li>)}</ol></Card>)}</Space>}
  </Card>
}
