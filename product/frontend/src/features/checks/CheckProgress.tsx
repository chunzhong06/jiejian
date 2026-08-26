/* 当前检查的真实过程状态、事件续读与取消边界。 */

import { useEffect, useState, type ReactNode } from 'react'
import { Alert, Button, Card, Collapse, List, Progress, Space, Spin, Tag, Typography } from 'antd'
import { runsApi, type JobEventDto, type RunDto, type RunnerProgressEventDto } from '../../api/runs'
import type { CheckPreviewActionDto } from '../../api/checks'
import { ApiError } from '../../api/http'
import { integrityLabel, lifecycleLabel, verdictLabel } from '../../app/presentation'
import { browserState } from '../../app/browserState'

const terminalStates = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'])

export function CheckProgress({ run, actions = [], onRefresh, onError, onNavigate }: { run?: RunDto; actions?: CheckPreviewActionDto[]; onRefresh: () => void; onError: (error: ApiError) => void; onNavigate?: (path: string) => void }) {
  const jobId = run?.job?.job_id ? String(run.job.job_id) : undefined
  const terminal = terminalStates.has(String(run?.lifecycle)) || ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(String(run?.job?.state))
  const running = String(run?.lifecycle) === 'RUNNING' && String(run?.job?.state) === 'RUNNING'
  const [event, setEvent] = useState<JobEventDto | null>(null)
  const [progressEvents, setProgressEvents] = useState<RunnerProgressEventDto[]>([])
  useEffect(() => {
    if (!jobId || terminal || typeof EventSource === 'undefined') return
    const cursor = browserState.readJobCursor(jobId)
    const source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events?after=${encodeURIComponent(cursor)}`)
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as JobEventDto
        setEvent(payload)
        const nextCursor = payload.sequence || Number(event.lastEventId)
        if (nextCursor) browserState.writeJobCursor(jobId, nextCursor)
      } catch { /* 事件正文不是页面判断依据，权威状态仍由刷新接口读取。 */ }
      onRefresh()
    }
    source.onerror = () => undefined
    return () => source.close()
  }, [jobId, terminal])
  useEffect(() => {
    if (!jobId || !running || typeof runsApi.progress !== 'function') {
      setProgressEvents([])
      return
    }
    let active = true
    const read = () => {
      void runsApi.progress(jobId).then((value) => {
        if (active) setProgressEvents(value.events)
      }).catch((error) => { if (active) onError(error as ApiError) })
    }
    read()
    const timer = globalThis.setInterval(read, 1000)
    return () => { active = false; globalThis.clearInterval(timer) }
  }, [jobId, running, onError])

  if (!run) return null
  const progress = run.case_progress
  const completed = typeof progress?.completed === 'number' ? progress.completed : undefined
  const total = typeof progress?.total === 'number' && progress.total > 0 ? progress.total : undefined
  const percent = completed !== undefined && total !== undefined ? Math.min(100, Math.round((completed / total) * 100)) : undefined
  const errors = ['FAILED', 'CANCELLED'].includes(String(run.lifecycle)) && Array.isArray(run.execution_errors) ? run.execution_errors : []
  const progressLabel = (item: RunnerProgressEventDto) => {
    if (item.phase === 'PREPARE' || item.phase === 'BASELINE') return '准备检查环境'
    if (item.phase === 'TARGET' && item.twin_role === 'ALLOW_CONTROL') return '验证正常允许的操作'
    if (item.phase === 'TARGET' && item.twin_role === 'DENY_VARIANT') return '尝试不应允许的操作'
    if (item.phase === 'OBSERVE' || item.phase === 'VERIFY') return '确认真实资源结果'
    if (item.phase === 'RECOVERY') return '恢复测试数据'
    return '准备检查环境'
  }
  const actionRows = actions.filter((item) => item.ready).map((action) => {
    const events = progressEvents.filter((item) => item.action_id === action.action_candidate_id)
    const completedCases = new Set(events.filter((item) => item.phase === 'RECOVERY' && item.state === 'COMPLETED').map((item) => item.case_id)).size
    const expectedCases = Math.max(action.checks.filter((item) => item.ready).length, 1)
    const state = events.length === 0 ? 'WAITING' : completedCases >= expectedCases ? 'COMPLETED' : 'RUNNING'
    return { key: action.action_candidate_id, name: action.action_display_name, state, latest: events.at(-1) }
  })
  const knownActionIds = new Set(actions.map((item) => item.action_candidate_id))
  const unknownEvents = progressEvents.filter((item) => !knownActionIds.has(item.action_id))
  if (unknownEvents.length > 0) {
    const latest = unknownEvents.at(-1)!
    const completed = unknownEvents.some((item) => item.case_id === latest.case_id && item.phase === 'RECOVERY' && item.state === 'COMPLETED')
    actionRows.push({ key: 'unknown-action', name: '当前业务动作', state: completed ? 'COMPLETED' : 'RUNNING', latest })
  }
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
    {running && actionRows.length > 0 && <Card size="small" title="真实检查步骤" className="check-progress-steps">
      <List size="small" dataSource={actionRows} renderItem={(item) => <List.Item>
        <Space><Tag color={item.state === 'COMPLETED' ? 'green' : item.state === 'RUNNING' ? 'processing' : undefined}>{item.state === 'COMPLETED' ? '已完成' : item.state === 'RUNNING' ? '进行中' : '等待中'}</Tag><Typography.Text>{item.name} · {item.latest ? progressLabel(item.latest) : '等待开始'}</Typography.Text></Space>
      </List.Item>} />
    </Card>}
    {errors.map((item, index) => typeof item === 'object'
      ? <Alert key={`${item.code ?? 'error'}-${index}`} type="error" showIcon message={item.diagnosis?.headline ?? `${item.stage ?? '后台执行'}失败`} description={<Space direction="vertical">
          <Typography.Text>{item.diagnosis?.short_message ?? item.message ?? '任务未能完整结束。'}</Typography.Text>
          {item.diagnosis?.cleanup_warnings.map((warning) => <Typography.Text key={warning} type="warning">{warning}</Typography.Text>)}
          {item.diagnosis?.route && onNavigate && <Button onClick={() => onNavigate(item.diagnosis!.route)}>前往处理页面</Button>}
          <Collapse ghost items={[{ key: 'execution-error-details', label: '高级：执行错误详情', children: <Space direction="vertical">
            {item.message && <Typography.Text>{item.message}</Typography.Text>}
            {item.log_path && <Typography.Text>日志：<Typography.Text copyable>{item.log_path}</Typography.Text></Typography.Text>}
            {item.recovery && <Typography.Text>下一步：{item.recovery}</Typography.Text>}
            {item.copy_text && <Typography.Paragraph copyable={{ text: item.copy_text }} code>复制诊断信息</Typography.Paragraph>}
          </Space> }]} />
        </Space>} />
      : <Alert key={`error-${index}`} type="error" showIcon message="检查执行失败" description={String(item)} />)}
    <Collapse ghost items={[{ key: 'progress-details', label: '高级：运行详情', children: <Space direction="vertical"><Typography.Text>事件序列：{String(event?.sequence ?? run.job?.event_sequence ?? run.event_sequence ?? '未提供')}</Typography.Text><Typography.Text>事件类型：{String(event?.event_type ?? '未提供')}</Typography.Text><Typography.Text>任务类型：{String(run.job?.job_type ?? '未提供')}</Typography.Text><Typography.Text>任务标识：{jobId ?? '未提供'}</Typography.Text></Space> }]} />
  </Cardless>
}

function Cardless({ children }: { children: ReactNode }) { return <div className="check-progress">{children}</div> }
