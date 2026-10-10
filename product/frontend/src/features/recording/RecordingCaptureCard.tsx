/* 录制采集过程：显示浏览器采集阶段、控制开始/停止并恢复后台事件游标。 */

import { useContext, useEffect, useState } from 'react'
import { WorkPageVisible } from '../../shared/runtime/visibility'
import { Alert, Space, Typography } from 'antd'
import type { RecordingDto, RecordingJobDto } from '../../api/preparation/recordings'
import type { JobEventDto } from '../../api/preparation/jobs'
import { browserState } from '../../shared/runtime/browserState'
import { lifecycleLabel } from '../../shared/presentation/execution'
import { StatusBadge } from '../../shared/ui/StatusBadge'

export function captureLabel(recording: RecordingDto | null) {
  if (!recording) return '尚未开始'
  if (recording.state === 'PENDING_REVIEW') return '等待确认'
  if (recording.state === 'COMPLETED') return '流程已保存'
  if (recording.state === 'CANCELLED') return '本次录制已取消'
  if (recording.state === 'FAILED' || recording.state === 'SAFETY_STOPPED') return '录制未完成'
  return ({ PREPARING_BROWSER: '正在准备浏览器', AWAITING_CAPTURE: '等待开始记录', CAPTURE_STARTING: '正在开始记录', CAPTURING: '正在记录业务动作', STOPPING: '正在整理流程', FINISHED: '正在整理结果' } as Record<string, string>)[String(recording.capture_phase)] ?? '正在准备录制'
}

export function RecordingCaptureCard({ recording, onRefresh }: {
  recording: RecordingDto
  onRefresh: () => void
}) {
  const phase = String(recording.capture_phase ?? '')
  const actionName = recording.action?.display_name ?? '这个业务动作'
  const captureGuide = phase === 'AWAITING_CAPTURE' || phase === 'CAPTURING'
    ? <div className="recording-capture-guide"><h2>{phase === 'CAPTURING' ? `到录制窗口完成一次“${actionName}”` : '在录制窗口确认账号与资源'}</h2>
      <p>{phase === 'CAPTURING' ? '操作完成后回到这里，点击“我已完成这个操作”结束记录。' : '准备好后在下方开始记录。开始前的登录与页面准备不会被采集。'}</p>
      <p className="editorial-muted">请保持录制窗口打开。</p></div> : null
  const phaseContent = phase === 'AWAITING_CAPTURE'
    ? captureGuide
    : phase === 'CAPTURING'
      ? captureGuide
      : <Alert type={recording.state === 'FAILED' || recording.state === 'SAFETY_STOPPED' ? 'error' : 'info'} showIcon message={captureLabel(recording)} description={phase === 'PREPARING_BROWSER' ? '正在打开用于演示业务的独立浏览器，请稍候。' : phase === 'STOPPING' ? `正在整理刚才的操作，确认哪一步完成了“${actionName}”…` : recording.state === 'CANCELLED' ? '本次录制已丢弃，没有生成可用的业务流程。' : '界鉴会保留当前状态；关闭页面只会断开显示。'} />
  return <section className="recording-capture"><Space direction="vertical" className="full-width" size="middle">
    {phaseContent}
    <RecordingProgress job={recording.job ?? undefined} onRefresh={onRefresh} />
  </Space></section>
}

function RecordingProgress({ job, onRefresh }: { job?: RecordingJobDto; onRefresh: () => void }) {
  const visible = useContext(WorkPageVisible)
  const [event, setEvent] = useState<JobEventDto | null>(null)
  useEffect(() => {
    if (!visible || !job?.job_id || ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.state)) return
    const stored = browserState.readJobCursor(job.job_id)
    const source = new EventSource(`/api/jobs/${job.job_id}/events?after=${stored}`)
    source.onmessage = (message) => {
      const next = JSON.parse(message.data) as JobEventDto
      setEvent(next)
      browserState.writeJobCursor(job.job_id, next.sequence)
      onRefresh()
    }
    source.onerror = () => undefined
    return () => source.close()
  }, [job?.job_id, job?.state, visible])
  if (!job) return null
  return <Space wrap><StatusBadge kind="lifecycle">处理状态：{lifecycleLabel(job.state)}</StatusBadge>{event && <Typography.Text type="secondary">状态已更新</Typography.Text>}</Space>
}
