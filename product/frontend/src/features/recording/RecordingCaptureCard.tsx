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
  return ({ PREPARING_BROWSER: '正在准备浏览器', AWAITING_CAPTURE: '等待登录准备', CAPTURE_STARTING: '正在开始录制', CAPTURING: '正在录制', STOPPING: '正在生成流程', FINISHED: '正在整理结果' } as Record<string, string>)[String(recording.capture_phase)] ?? '正在准备录制'
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
  return <Card title="录制进度" extra={<Button onClick={onRefresh}>刷新状态</Button>}><Space direction="vertical" className="full-width" size="middle">
    <Alert type={phase === 'CAPTURING' ? 'warning' : recording.state === 'FAILED' || recording.state === 'SAFETY_STOPPED' ? 'error' : 'info'} showIcon message={captureLabel(recording)} description={phase === 'PREPARING_BROWSER' ? '正在启动有界 Chromium，请稍候。' : phase === 'AWAITING_CAPTURE' ? '浏览器已经打开。请先完成登录并进入要录制的页面；这些准备操作不会写入流程。' : phase === 'CAPTURING' ? '现在开始记录你的操作。完成业务流程后，点击“停止录制并生成流程”。' : phase === 'STOPPING' ? '正在停止采集、整理事件并生成步骤草稿。' : recording.state === 'CANCELLED' ? '本次事件已丢弃，没有生成流程草稿。' : '界鉴会保留当前状态；关闭页面只会断开显示。'} />
    <Space wrap>{phase === 'AWAITING_CAPTURE' && <Button type="primary" size="large" loading={busy} onClick={() => onControl('start')}>开始录制</Button>}{phase === 'CAPTURING' && <Button type="primary" danger size="large" loading={busy} onClick={() => onControl('stop')}>停止录制并生成流程</Button>}<RecordingProgress job={recording.job ?? undefined} canCancel={canCancel} onRefresh={onRefresh} onError={onError} /></Space>
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
