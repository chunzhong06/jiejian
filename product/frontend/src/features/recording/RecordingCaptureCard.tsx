/* 录制采集卡：显示浏览器采集阶段、控制开始/停止并恢复后台事件游标。 */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Popconfirm, Space, Tag, Typography } from 'antd'
import type { RecordingDto, RecordingJobDto } from '../../api/recordings'
import { runsApi, type JobEventDto } from '../../api/runs'
import { browserState } from '../../app/browserState'
import { lifecycleLabel } from '../../app/presentation'
import type { ApiError } from '../../api/http'

export function captureLabel(recording: RecordingDto | null) {
  if (!recording) return '尚未开始'
  if (recording.state === 'PENDING_REVIEW') return '等待确认'
  if (recording.state === 'COMPLETED') return '流程已保存'
  if (recording.state === 'CANCELLED') return '本次录制已取消'
  if (recording.state === 'FAILED' || recording.state === 'SAFETY_STOPPED') return '录制未完成'
  return ({ PREPARING_BROWSER: '正在准备浏览器', AWAITING_CAPTURE: '等待开始记录', CAPTURE_STARTING: '正在开始记录', CAPTURING: '正在记录业务动作', STOPPING: '正在整理流程', FINISHED: '正在整理结果' } as Record<string, string>)[String(recording.capture_phase)] ?? '正在准备录制'
}

export function RecordingCaptureCard({ recording, busy, canCancel, onRefresh, onControl, onError }: {
  recording: RecordingDto
  busy: boolean
  canCancel: boolean
  onRefresh: () => void
  onControl: (action: 'start' | 'stop') => void
  onError: (error: ApiError) => void
}) {
  const phase = String(recording.capture_phase ?? '')
  const actionName = recording.action?.display_name ?? '这个业务动作'
  const captureGuide = phase === 'AWAITING_CAPTURE'
    ? <div className="recording-capture-guide">
      <ol>
        <li><Tag color="green">1</Tag><div><Typography.Text strong>浏览器已打开</Typography.Text><Typography.Text type="secondary">请进入要执行操作的页面。</Typography.Text><Typography.Text type="secondary">现在的浏览和登录不会写进业务流程。</Typography.Text></div></li>
        <li><Tag color="blue">2</Tag><div><Typography.Text strong>准备开始记录</Typography.Text><Button type="primary" size="large" loading={busy} onClick={() => onControl('start')}>开始记录这个操作</Button></div></li>
        <li><Tag>3</Tag><div><Typography.Text strong>在浏览器里正常完成一次“{actionName}”</Typography.Text><Typography.Text type="secondary">完成后不要关闭浏览器。</Typography.Text></div></li>
        <li><Tag>4</Tag><div><Typography.Text strong>回到界鉴</Typography.Text><Typography.Text type="secondary">完成业务动作后，在这里确认。</Typography.Text></div></li>
      </ol>
    </div>
    : phase === 'CAPTURING'
      ? <Alert type="warning" showIcon message={`正在记录“${actionName}”`} description="请在浏览器里正常完成一次这个业务动作。完成后不要关闭浏览器，再回到界鉴点击“我已完成这个操作”。" />
      : null
  const phaseContent = phase === 'AWAITING_CAPTURE'
    ? captureGuide
    : phase === 'CAPTURING'
      ? captureGuide
      : <Alert type={recording.state === 'FAILED' || recording.state === 'SAFETY_STOPPED' ? 'error' : 'info'} showIcon message={captureLabel(recording)} description={phase === 'PREPARING_BROWSER' ? '正在启动有界 Chromium，请稍候。' : phase === 'STOPPING' ? `正在整理刚才的操作并寻找真正执行“${actionName}”的请求…` : recording.state === 'CANCELLED' ? '本次事件已丢弃，没有生成流程草稿。' : '界鉴会保留当前状态；关闭页面只会断开显示。'} />
  return <Card title={`录制「${actionName}」`} extra={<Button onClick={onRefresh}>刷新状态</Button>}><Space direction="vertical" className="full-width" size="middle">
    {phaseContent}
    <Space wrap>{phase === 'CAPTURING' && <Button type="primary" size="large" loading={busy} onClick={() => onControl('stop')}>我已完成这个操作</Button>}<RecordingProgress job={recording.job ?? undefined} canCancel={canCancel} onRefresh={onRefresh} onError={onError} /></Space>
  </Space></Card>
}

function RecordingProgress({ job, canCancel, onRefresh, onError }: { job?: RecordingJobDto; canCancel: boolean; onRefresh: () => void; onError: (error: ApiError) => void }) {
  const [event, setEvent] = useState<JobEventDto | null>(null)
  useEffect(() => {
    if (!job?.job_id || ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.state)) return
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
  }, [job?.job_id, job?.state])
  if (!job) return null
  return <Space wrap><Tag>后台状态：{lifecycleLabel(job.state)}</Tag>{event && <Typography.Text type="secondary">后台状态已更新</Typography.Text>}{canCancel && <Popconfirm title="取消并丢弃本次录制？" description="取消不会生成流程草稿。" onConfirm={() => runsApi.cancel(job.job_id).then(onRefresh).catch(onError)}><Button danger size="small">取消并丢弃</Button></Popconfirm>}</Space>
}
