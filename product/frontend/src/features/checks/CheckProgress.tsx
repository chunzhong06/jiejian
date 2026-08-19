/* 当前检查的真实过程状态、事件续读与取消边界。 */

import { useEffect, useState, type ReactNode } from 'react'
import { Button, Collapse, Progress, Space, Spin, Tag, Typography } from 'antd'
import { runsApi } from '../../api/runs'
import { ApiError } from '../../api/http'
import { integrityLabel, lifecycleLabel, verdictLabel } from '../../app/presentation'

type Item = Record<string, any>
const terminalStates = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'])

export function CheckProgress({ run, onRefresh, onError }: { run?: Item; onRefresh: () => void; onError: (error: ApiError) => void }) {
  const jobId = run?.job?.job_id ? String(run.job.job_id) : undefined
  const terminal = terminalStates.has(String(run?.lifecycle)) || ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(String(run?.job?.state))
  const [event, setEvent] = useState<Item | null>(null)
  useEffect(() => {
    if (!jobId || terminal || typeof EventSource === 'undefined') return
    const cursorKey = `jiejian.cursor.${jobId}`
    const stored = localStorage.getItem(cursorKey)
    let cursor = stored ?? '0'
    try { cursor = String(JSON.parse(stored ?? '0')) } catch { /* 兼容当前已保存的纯文本游标。 */ }
    const source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events?after=${encodeURIComponent(cursor)}`)
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as Item
        setEvent(payload)
        const nextCursor = payload.sequence ?? payload.cursor ?? payload.event_id ?? event.lastEventId
        if (nextCursor) localStorage.setItem(cursorKey, String(nextCursor))
      } catch { /* 事件正文不是页面判断依据，权威状态仍由刷新接口读取。 */ }
      onRefresh()
    }
    source.onerror = () => undefined
    return () => source.close()
  }, [jobId, terminal])

  if (!run) return null
  const progress = run.case_progress as Item | undefined
  const completed = typeof progress?.completed === 'number' ? progress.completed : undefined
  const total = typeof progress?.total === 'number' && progress.total > 0 ? progress.total : undefined
  const percent = completed !== undefined && total !== undefined ? Math.min(100, Math.round((completed / total) * 100)) : undefined
  const errors = Array.isArray(run.execution_errors) ? run.execution_errors : []
  return <Cardless>
    <Space wrap>
      <Tag color={run.lifecycle === 'RUNNING' ? 'processing' : undefined}>检查状态：{lifecycleLabel(run.lifecycle)}</Tag>
      {run.result_integrity && <Tag>结果完整性：{integrityLabel(run.result_integrity)}</Tag>}
      {run.verdict && <Tag>安全结论：{verdictLabel(run.verdict)}</Tag>}
      {!terminal && jobId && <Button danger size="small" onClick={() => runsApi.cancel(jobId).then(onRefresh).catch(onError)}>取消检查</Button>}
    </Space>
    {percent !== undefined
      ? <div className="check-progress-value"><Typography.Text>已完成 {completed}/{total} 个用例</Typography.Text><Progress percent={percent} size="small" aria-label={`检查进度 ${completed}/${total}`} /></div>
      : !terminal && <Space><Spin size="small" /><Typography.Text type="secondary">正在执行，暂时没有可确认的用例总量</Typography.Text></Space>}
    {errors.length > 0 && <Typography.Text type="danger">执行错误：{errors.map((item: unknown) => typeof item === 'object' ? String((item as Item).message ?? (item as Item).code ?? '执行失败') : String(item)).join('、')}</Typography.Text>}
    <Collapse ghost items={[{ key: 'progress-details', label: '高级：运行详情', children: <Space direction="vertical"><Typography.Text>事件序列：{String(event?.sequence ?? run.job?.event_sequence ?? run.event_sequence ?? '未提供')}</Typography.Text><Typography.Text>事件类型：{String(event?.event_type ?? '未提供')}</Typography.Text><Typography.Text>任务类型：{String(run.job?.job_type ?? '未提供')}</Typography.Text><Typography.Text>任务标识：{jobId ?? '未提供'}</Typography.Text></Space> }]} />
  </Cardless>
}

function Cardless({ children }: { children: ReactNode }) { return <div className="check-progress">{children}</div> }
