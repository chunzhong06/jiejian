/* 当前检查的真实过程状态与事件续读；取消等副作用由页面底部统一动作区负责。 */

import { useEffect, useState, type ReactNode } from 'react'
import { Alert, Button, Card, List, Progress, Space, Spin, Tag, Typography } from 'antd'
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
  const [progressEvents, setProgressEvents] = useState<RunnerProgressEventDto[]>([])
  const [streamDisconnected, setStreamDisconnected] = useState(false)
  useEffect(() => {
    setStreamDisconnected(false)
    if (!jobId || terminal || typeof EventSource === 'undefined') return
    const cursor = browserState.readJobCursor(jobId)
    const source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events?after=${encodeURIComponent(cursor)}`)
    source.onmessage = (event) => {
      setStreamDisconnected(false)
      try {
        const payload = JSON.parse(event.data) as JobEventDto
        const nextCursor = payload.sequence || Number(event.lastEventId)
        if (nextCursor) browserState.writeJobCursor(jobId, nextCursor)
      } catch { /* 事件正文不是页面判断依据，权威状态仍由刷新接口读取。 */ }
      onRefresh()
    }
    source.onerror = () => setStreamDisconnected(true)
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
  const stageDefinitions = [
    { label: '准备检查环境', detail: '等待隔离任务和测试资源就绪' },
    { label: '验证合法路径', detail: '等待应当允许的业务操作完成' },
    { label: '尝试禁止路径', detail: '等待不应允许的业务操作结束' },
    { label: '确认真实业务后果', detail: '等待独立观察资源最终状态' },
    { label: '恢复测试现场', detail: '等待恢复完成并进入正式终态' },
  ]
  const stageIndex = (item: RunnerProgressEventDto | undefined) => {
    if (!item || item.phase === 'PREPARE' || item.phase === 'BASELINE') return 0
    if (item.phase === 'TARGET' && item.twin_role === 'ALLOW_CONTROL') return 1
    if (item.phase === 'TARGET' && item.twin_role === 'DENY_VARIANT') return 2
    if (item.phase === 'OBSERVE' || item.phase === 'VERIFY') return 3
    if (item.phase === 'RECOVERY') return 4
    return 0
  }
  const currentStage = stageIndex(progressEvents.at(-1))
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
    </Space>
    {percent !== undefined
      ? <div className="check-progress-value"><Typography.Text>已完成 {completed}/{total} 个用例</Typography.Text><Progress percent={percent} size="small" aria-label={`检查进度 ${completed}/${total}`} /></div>
      : !terminal && <Space><Spin size="small" /><Typography.Text type="secondary">正在执行，暂时没有可确认的用例总量</Typography.Text></Space>}
    {streamDisconnected && <Alert type="warning" showIcon message="实时视图暂时断开，正式检查仍在后台运行" description="界鉴会继续尝试恢复事件视图；请以服务端运行状态和最终发布结果为准。" />}
    {running && <ol className="check-stage-track" aria-label="真实检查阶段">
      {stageDefinitions.map((stage, index) => {
        const state = index < currentStage ? 'complete' : index === currentStage ? 'current' : 'waiting'
        return <li className={`is-${state}`} key={stage.label}><span className="check-stage-marker" aria-hidden="true">{state === 'complete' ? '✓' : index + 1}</span><div><Typography.Text strong>{stage.label}</Typography.Text><Typography.Text type="secondary">{state === 'current' ? stage.detail : state === 'complete' ? '已形成运行事实' : '等待前一阶段完成'}</Typography.Text></div></li>
      })}
    </ol>}
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
        </Space>} />
      : <Alert key={`error-${index}`} type="error" showIcon message="检查执行失败" description={String(item)} />)}
  </Cardless>
}

function Cardless({ children }: { children: ReactNode }) { return <div className="check-progress">{children}</div> }
