// 当前检查工作区：准备、显式提交、有限状态刷新和只读故事共享同一项目事实。
import { Alert, Button, Empty, List, Space, Spin, Typography } from 'antd'
import { useCallback, useEffect, useRef, useState, type ComponentProps } from 'react'
import { ApiError } from '../../api/http'
import { currentChecksApi, type CheckPreview, type CheckStatus, type ResultStory } from '../../api/currentChecks'
import { formatTimestamp, lifecycleLabel } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { TaskActionBar } from '../../components/TaskActionBar'
import { PreparationPage } from '../preparation/PreparationPage'
import { CurrentResultStory } from './CurrentResultStory'

const verdictLabels = { PASS: '本次权限要求已得到验证', BLOCK: '已确认不应发生的业务后果', INCONCLUSIVE: '现有证据不足以完成判断' }
const progressLabels = { PREPARING: '正在准备本次执行', EXECUTING: '正在执行并观察业务结果', FINALIZING: '正在核验并保存结果' }
const active = (status: CheckStatus) => ['QUEUED', 'RUNNING'].includes(status.run.lifecycle)

export function CurrentTestsPage(props: ComponentProps<typeof PreparationPage> & { requestedRunId?: string | null; changeId?: string | null }) {
  const { project, onError, onNavigate, requestedRunId, changeId } = props
  const [materials, setMaterials] = useState(false)
  const [preview, setPreview] = useState<CheckPreview | null>(null)
  const [runs, setRuns] = useState<CheckStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [readFailed, setReadFailed] = useState(false)
  const [submissionUncertain, setSubmissionUncertain] = useState(false)
  const [selected, setSelected] = useState<string>()
  const [status, setStatus] = useState<CheckStatus | null>(null)
  const [story, setStory] = useState<ResultStory | null>(null)
  const [runFailed, setRunFailed] = useState(false)
  const [pollPaused, setPollPaused] = useState(false)
  const [refreshEpoch, setRefreshEpoch] = useState(0)
  const submitting = useRef(false)
  const pending = useRef<{ fingerprint: string; key: string } | undefined>(undefined)
  const alive = useRef(true)
  const loadEpoch = useRef(0)
  const currentProject = useRef(project.project_id)
  currentProject.current = project.project_id
  useEffect(() => { alive.current = true; return () => { alive.current = false; loadEpoch.current += 1 } }, [])
  const refresh = useCallback(async () => {
    const epoch = ++loadEpoch.current
    setLoading(true); setReadFailed(false)
    try {
      const [nextPreview, nextRuns] = await Promise.all([currentChecksApi.preview(project.project_id, changeId), currentChecksApi.list(project.project_id)])
      if (nextPreview.project_id !== project.project_id || nextRuns.some((item) => item.run.project_id !== project.project_id)) throw new ApiError('STATE_PRECONDITION', '检查信息所属项目不一致。')
      if (alive.current && epoch === loadEpoch.current) { setPreview(nextPreview); setRuns(nextRuns) }
    } catch (error) { if (alive.current && epoch === loadEpoch.current) { setPreview(null); setReadFailed(true); onError(error as ApiError) } }
    finally { if (alive.current && epoch === loadEpoch.current) setLoading(false) }
  }, [project.project_id, onError, changeId])
  useEffect(() => {
    setSelected(requestedRunId ?? undefined); setStatus(null); setStory(null); setRuns([]); setMaterials(false)
    pending.current = undefined; setSubmissionUncertain(false)
    void refresh()
  }, [refresh, requestedRunId])

  useEffect(() => {
    if (!selected || materials) return
    let valid = true
    let timer: ReturnType<typeof setTimeout> | undefined
    let polls = 0
    setStatus(null); setStory(null); setRunFailed(false); setPollPaused(false)
    const read = async () => {
      try {
        const next = await currentChecksApi.status(selected)
        if (next.run.project_id !== project.project_id || next.run.run_id !== selected) throw new ApiError('STATE_PRECONDITION', '检查记录所属项目不一致。')
        if (!valid) return
        setStatus(next); setRuns((items) => items.map((item) => item.run.run_id === selected ? next : item))
        // 进度不代表结论，必须先通过完整性读取；失效时撤下旧故事。
        if (next.result_integrity === 'VALID') {
          const nextStory = await currentChecksApi.story(selected)
          if (nextStory.run_id !== selected || nextStory.project_id !== project.project_id || nextStory.verdict !== next.run.verdict) throw new ApiError('ARTIFACT_MANIFEST', '结果关联信息不一致。')
          if (valid) setStory(nextStory)
        } else {
          setStory(null)
          if (active(next)) {
            if (++polls < 150) timer = setTimeout(() => void read(), 2000)
            else setPollPaused(true)
          }
        }
      } catch (error) { if (valid) { setStatus(null); setStory(null); setRunFailed(true); onError(error as ApiError) } }
    }
    void read()
    return () => { valid = false; if (timer) clearTimeout(timer) }
  }, [selected, materials, project.project_id, refreshEpoch, onError])

  const start = async () => {
    if (submitting.current || !preview?.can_execute || readFailed) return
    submitting.current = true; setBusy(true)
    const projectId = project.project_id
    try {
      // 未知提交回执先查运行记录，重试只复用原幂等键，不能新建请求来试探。
      const freshRuns = await currentChecksApi.list(projectId)
      if (!alive.current || currentProject.current !== projectId) return
      setRuns(freshRuns)
      const running = freshRuns.find(active)
      if (running) { setSelected(running.run.run_id); return }
      const fresh = await currentChecksApi.preview(projectId, changeId)
      if (!alive.current || currentProject.current !== projectId) return
      setPreview(fresh)
      if (!fresh.can_execute || fresh.plan_fingerprint !== preview.plan_fingerprint) throw new ApiError('STATE_PRECONDITION', '准备条件已变化，请核对最新检查范围。')
      if (pending.current && pending.current.fingerprint !== fresh.plan_fingerprint) throw new ApiError('STATE_PRECONDITION', '上次提交尚未确认，且检查范围已变化，请先刷新检查记录。')
      pending.current ??= { fingerprint: fresh.plan_fingerprint, key: crypto.randomUUID() }
      setSubmissionUncertain(true)
      const submitted = await currentChecksApi.submit(projectId, pending.current.fingerprint, pending.current.key, changeId)
      if (!alive.current || currentProject.current !== projectId) return
      pending.current = undefined; setSubmissionUncertain(false)
      setSelected(submitted.run.run_id)
      await refresh()
    } catch (error) { if (alive.current && currentProject.current === projectId) onError(error as ApiError) }
    finally { submitting.current = false; if (alive.current && currentProject.current === projectId) setBusy(false) }
  }
  const showMaterials = () => { setMaterials(true); setSelected(undefined) }
  if (materials) return <PreparationPage {...props} onNavigate={(path) => {
    if (path === '/tests') { setMaterials(false); void refresh() } else onNavigate(path)
  }} />
  const running = runs.find(active)
  const selectedMode = Boolean(selected)
  const headline = selectedMode ? story?.judgement ?? (runFailed ? '暂时无法读取本次检查' : status?.result_integrity === 'INVALID' ? '结果完整性校验失败，不能展示安全结论' : status ? lifecycleLabel(status.run.lifecycle) : '正在读取检查记录')
    : loading ? '正在读取当前检查条件' : running ? '有一项检查正在执行' : preview?.can_execute ? '当前准备条件允许开始检查' : readFailed ? '暂时无法确认当前检查条件' : '请先补齐本次检查所需材料'
  const currentVerdict = story?.verdict
  return <Space direction="vertical" size="large" style={{ width: '100%' }}>
    <PageTaskHeader title="检查与结果" description="按已确认的权限运行正常对照与拒绝验证，观察实际发生的业务后果。" />
    <section className="testing-overview" aria-label="当前检查判断">
      <Typography.Title level={3}>{headline}</Typography.Title>
      {currentVerdict && <span className={`semantic-state ${currentVerdict === 'PASS' ? 'is-safe' : currentVerdict === 'BLOCK' ? 'is-danger' : 'is-warning'}`}>{currentVerdict === 'PASS' ? '验证通过' : currentVerdict === 'BLOCK' ? '发现权限问题' : '证据不足'}</span>}
      {!selectedMode && preview && <Typography.Paragraph type="secondary">本次范围包含 {preview.action_count} 项业务动作、{preview.case_count} 项验证。开始前会重新核对准备条件。</Typography.Paragraph>}
      {selectedMode && status?.progress && !story && <Typography.Paragraph role="status">{progressLabels[status.progress.phase]} · 已处理 {status.progress.completed_cases} / {status.progress.planned_cases} 项验证。进度不代表安全结论。</Typography.Paragraph>}
    </section>
    {!selectedMode && loading && <Spin />}
    {!selectedMode && readFailed && <Alert type="warning" showIcon message="检查条件读取失败。刷新成功后才能开始检查。" />}
    {submissionUncertain && <Alert type="warning" showIcon message="上次提交尚未确认。请先刷新检查记录；再次确认提交会复用同一次请求。" />}
    {selectedMode && pollPaused && <Alert type="info" showIcon message="已暂停自动刷新；检查仍由服务端执行，可手动刷新查看进展。" />}
    {selectedMode && !story && status && !active(status) && status.result_integrity === 'NOT_PUBLISHED' && <Alert type="info" showIcon message="本次没有发布可用安全结论。执行停止或失败不代表发现权限问题。" />}
    {changeId && !selectedMode && <Alert type="info" showIcon message="本次检查关联所选代码变化，将执行完整当前权限考题。" />}
    {selectedMode && status && active(status) && status.job && <Button disabled={busy || status.job.cancel_requested} onClick={async () => {
      setBusy(true)
      try { await currentChecksApi.cancel(status.job!.job_id); setRefreshEpoch(value => value + 1) } catch (error) { onError(error as ApiError) } finally { setBusy(false) }
    }}>{status.job.cancel_requested ? '正在停止检查' : '停止本次检查'}</Button>}
    {selectedMode && story && <CurrentResultStory key={story.run_id} story={story} onNavigate={onNavigate} onError={(error) => { setStory(null); setRunFailed(true); setStatus(null); onError(error) }} />}
    {!selectedMode && <>
      <Button onClick={showMaterials} disabled={busy}>管理准备材料</Button>
      {preview && !preview.can_execute && <Typography.Paragraph type="secondary">请在准备材料中核对账号、动作演示、资源、结果证明与恢复条件；材料齐备后仍需服务端确认执行配置。</Typography.Paragraph>}
      <section aria-label="检查记录"><Typography.Title level={4}>检查记录</Typography.Title>
        <List dataSource={runs} locale={{ emptyText: <Empty description="尚无检查记录" /> }} renderItem={(item) => <List.Item actions={[<Button key="open" onClick={() => setSelected(item.run.run_id)}>查看{active(item) ? '进度' : '结果'}</Button>]}>
          <List.Item.Meta title={item.result_integrity === 'VALID' && item.run.verdict ? verdictLabels[item.run.verdict] : item.result_integrity === 'INVALID' ? '结果完整性校验失败' : lifecycleLabel(item.run.lifecycle)} description={`${formatTimestamp(item.run.created_at_us)} · 权限版本 ${item.run.policy_epoch}`} />
        </List.Item>} />
      </section>
    </>}
    <TaskActionBar back={{ label: selectedMode ? '返回检查总览' : '返回工作台', disabled: busy, onClick: () => { if (selectedMode) { setSelected(undefined); void refresh() } else onNavigate('/workspace') } }}
      refresh={{ label: selectedMode ? '刷新检查结果' : '刷新检查条件', loading: loading || busy, onClick: () => { if (selectedMode) setRefreshEpoch((value) => value + 1); else void refresh() } }}
      primary={selectedMode ? undefined : running ? { label: '查看当前进度', onClick: () => setSelected(running.run.run_id) }
        : preview?.can_execute ? { label: submissionUncertain ? '确认上次提交' : '开始检查', loading: busy, disabled: loading || readFailed, onClick: () => void start() }
        : { label: '准备检查材料', disabled: loading || busy, onClick: showMaterials }} />
  </Space>
}
