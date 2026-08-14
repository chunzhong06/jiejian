/* =============================================================================
 * Job 进度观察
 *
 * 定位
 *   长时 Recording/Run Job 的 SSE 游标恢复与取消交互组件
 *
 * 职责
 *   续接事件流｜持久化最新游标｜提交取消并刷新终态
 *
 * 调用链
 *   Recording / Run UI → JobProgress → EventSource / runsApi.cancel
 * ============================================================================= */

import { useEffect, useState } from 'react'
import { Button, Collapse, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { runsApi } from '../../api/runs'
import { lifecycleLabel } from '../sharedStatus'

type Item = Record<string, any>
const cursorKey = 'jiejian.cursor'

function remember(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value))
}

function recalled<T>(key: string): T | null {
  try {
    return JSON.parse(localStorage.getItem(key) ?? 'null') as T
  } catch {
    return null
  }
}

export function JobProgress({ job, onRefresh, onError }: { job?: Item; onRefresh: () => void; onError: (e: ApiError) => void }) {
  const [event, setEvent] = useState<Item | null>(null)
  useEffect(() => {
    if (!job?.job_id || ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.state)) return
    const stored = recalled<number>(`${cursorKey}.${job.job_id}`) ?? 0
    const source = new EventSource(`/api/v1/jobs/${job.job_id}/events?after=${stored}`)
    source.onmessage = (message) => {
      const next = JSON.parse(message.data) as Item
      setEvent(next)
      remember(`${cursorKey}.${job.job_id}`, next.sequence)
      void onRefresh()
    }
    source.onerror = () => undefined
    return () => source.close()
  }, [job?.job_id, job?.state])
  if (!job) return null
  return (
    <Space>
      <Tag color={job.state === 'RUNNING' ? 'processing' : undefined}>
        后台状态：{lifecycleLabel(job.state)}
      </Tag>
      {event && <Typography.Text type="secondary">后台正在处理</Typography.Text>}
      {event && <Collapse ghost items={[{ key: 'job-event', label: '高级：后台事件细节', children: <Typography.Text type="secondary">事件 #{event.sequence}：{event.event_type}</Typography.Text> }]} />}
      {!['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.state) && (
        <Button
          danger
          size="small"
          onClick={() => runsApi.cancel(String(job.job_id)).then(onRefresh).catch(onError)}
        >
          主动取消
        </Button>
      )}
    </Space>
  )
}
