// 当前检查工作区：准备、显式提交、有限状态刷新和只读故事共享同一项目事实。
import { Alert, Button, Space, Spin, Typography } from 'antd'
import { useCallback, useEffect, useRef, useState, type ComponentProps } from 'react'
import { ApiError } from '../../api/http'
import { currentChecksApi, type CheckPreview, type CheckStatus, type ResultStory } from '../../api/currentChecks'
import { lifecycleLabel } from '../../app/presentation'
import { EditorialHeader, EditorialPage, FlowSpine } from '../../shared/ui/Editorial'
import { TaskActionBar } from '../../components/TaskActionBar'
import { PreparationPage } from '../preparation/PreparationPage'
import { CurrentResultStory } from './CurrentResultStory'

const verdictLabels = { PASS: '本次权限要求已得到验证', BLOCK: '已确认不应发生的业务后果', INCONCLUSIVE: '现有证据不足以完成判断' }
const progressLabels = { PREPARING: '正在准备本次执行', EXECUTING: '正在执行并观察业务结果', FINALIZING: '正在核验并保存结果' }
const active = (status: CheckStatus) => ['QUEUED', 'RUNNING'].includes(status.run.lifecycle)

export function CurrentTestsPage(props: ComponentProps<typeof PreparationPage> & { requestedTaskId?: string | null; requestedRunId?: string | null; requestedCaseId?: string | null; changeId?: string | null; onBackToHistory?: () => void }) {
  const { project, onError, onNavigate, requestedRunId, requestedTaskId, changeId } = props
  const [materials, setMaterials] = useState(Boolean(requestedTaskId))
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
  const [workspaceSyncFailed, setWorkspaceSyncFailed] = useState(false)
  const [refreshEpoch, setRefreshEpoch] = useState(0)
  const submitting = useRef(false)
  const pending = useRef<{ fingerprint: string; key: string } | undefined>(undefined)
  const alive = useRef(true)
  const loadEpoch = useRef(0)
  const currentProject = useRef(project.project_id)
  currentProject.current = project.project_id
  const workspaceRefresh = useRef(props.onStateChanged)
  workspaceRefresh.current = props.onStateChanged
  const workspaceSynced = useRef<string | undefined>(undefined)
  const syncWorkspace = useCallback(async (key: string) => {
    if (workspaceSynced.current === key) return
    try {
      const next = await workspaceRefresh.current()
      if (!alive.current || currentProject.current !== project.project_id) return
      if (!next || next.project.project_id !== project.project_id) { setWorkspaceSyncFailed(true); return }
      workspaceSynced.current = key; setWorkspaceSyncFailed(false)
    } catch { if (alive.current && currentProject.current === project.project_id) setWorkspaceSyncFailed(true) }
  }, [project.project_id])

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
    setSelected(requestedRunId ?? undefined); setStatus(null); setStory(null); setRuns([]); setMaterials(Boolean(requestedTaskId))
    pending.current = undefined; setSubmissionUncertain(false)
    void refresh()
  }, [refresh, requestedRunId, requestedTaskId])

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
        // 已发布事实保持只读；终态以后另行刷新唯一 Workspace，不能让工作台继续保留旧缺口。
        if (valid && !active(next)) void syncWorkspace(`${selected}:${next.run.lifecycle}:${next.result_integrity}:${next.run.finished_at_us}`)
      } catch (error) { if (valid) { setStatus(null); setStory(null); setRunFailed(true); onError(error as ApiError) } }
    }
    void read()
    return () => { valid = false; if (timer) clearTimeout(timer) }
  }, [selected, materials, project.project_id, refreshEpoch, onError, syncWorkspace])

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
      props.onFeedback?.('检查请求已确认，可以离开此页后再查看结果。')
      setSelected(submitted.run.run_id)
      await refresh()
      void syncWorkspace(`submitted:${submitted.run.run_id}`)
    } catch (error) { if (alive.current && currentProject.current === projectId) onError(error as ApiError) }
    finally { submitting.current = false; if (alive.current && currentProject.current === projectId) setBusy(false) }
  }
  const showMaterials = () => { setMaterials(true); setSelected(undefined) }
  // 显式切换准备任务只重置页面局部模式；同一任务刷新继续保留当前输入和服务端材料。
  if (materials) return <PreparationPage key={`${project.project_id}:${requestedTaskId ?? "materials"}`} {...props} onNavigate={(path) => {
    if (path === '/tests') { setMaterials(false); void refresh() } else onNavigate(path)
  }} />
  const running = runs.find(active)
  const selectedMode = Boolean(selected)
  const headline = selectedMode ? story?.judgement ?? (runFailed ? '暂时无法读取本次检查' : status?.result_integrity === 'INVALID' ? '结果完整性校验失败，不能展示安全结论' : status ? lifecycleLabel(status.run.lifecycle) : '正在读取检查记录')
    : loading ? '正在读取当前检查条件' : running ? '有一项检查正在执行' : preview?.can_execute ? '当前准备条件允许开始检查' : readFailed ? '暂时无法确认当前检查条件' : '请先补齐本次检查所需材料'
  const currentVerdict = story?.verdict
  const primaryAction = selectedMode ? undefined : running ? { label: '查看当前进度', onClick: () => setSelected(running.run.run_id) }
    : preview?.can_execute ? { label: submissionUncertain ? '确认上次提交' : '开始检查', loading: busy, disabled: loading || readFailed, onClick: () => void start() }
    : { label: '准备检查材料', disabled: loading || busy, onClick: showMaterials }
  return <EditorialPage label="权限验证工作区">
    {selectedMode && <div className="result-return"><Button type="link" onClick={() => { if (props.onBackToHistory) props.onBackToHistory(); else onNavigate('/history') }}>← 返回检查记录</Button></div>}
    <EditorialHeader eyebrow={selectedMode ? '检查历史 / 本轮结果' : '当前工作 / 权限检查'} title={headline}>
      {currentVerdict && <span className={`semantic-state ${currentVerdict === 'PASS' ? 'is-safe' : currentVerdict === 'BLOCK' ? 'is-danger' : 'is-warning'}`}>{currentVerdict === 'PASS' ? '验证通过' : currentVerdict === 'BLOCK' ? '发现权限问题' : '证据不足'}</span>}
    </EditorialHeader>
    {!selectedMode && <section className="task-focus" aria-label="当前检查判断"><p className="editorial-eyebrow task-focus-label">当前需要你做</p><h2>{running ? '查看本轮检查进展' : preview?.can_execute ? '确认范围，开始本轮检查' : '准备本轮验证材料'}</h2>
      {props.workspace?.source_change && <p className="editorial-muted">最近代码变化：{props.workspace.source_change.reason} · {props.workspace.source_change.submitted_by || '来源未提供'}</p>}
      {preview && <><p>本次范围包含 {preview.action_count} 项业务动作、{preview.case_count} 项验证。开始前会重新核对准备条件。</p><ul className="check-scope-list">{preview.actions.map((action) => <li key={action.action_id}><strong>{props.workspace?.actions.find((item) => item.action_id === action.action_id && item.action_revision === action.action_revision)?.display_name ?? '本轮已确认的业务动作'}</strong><span>正常对照与拒绝验证</span></li>)}</ul></>}
      <p className="editorial-muted">只有显式开始检查才会执行目标操作；材料齐备本身不是安全结论。</p>
      {primaryAction && <div className="task-focus-actions"><Button type="primary" size="large" loading={busy} disabled={primaryAction.disabled} onClick={primaryAction.onClick}>{primaryAction.label}</Button></div>}
      <p className="task-next"><span>接下来</span>{running ? '执行结束后，查看已发布的结果与证据。' : preview?.can_execute ? '界鉴将执行本轮检查，并把结果保存在检查历史中。' : '按当前缺口准备材料，再核对本轮检查条件。'}</p>
    </section>}
    {selectedMode && status?.progress && !story && <FlowSpine label="本轮权限验证过程" steps={[
      {key:'prepare',title:'冻结本轮权限与测试材料',state:status.progress.phase === 'PREPARING' ? 'current' : 'complete',detail:<p>正在准备本次执行，尚无安全结论。</p>},
      {key:'execute',title:'执行正常对照与拒绝验证，观察真实业务结果',state:status.progress.phase === 'EXECUTING' ? 'current' : status.progress.phase === 'FINALIZING' ? 'complete' : 'future',detail:<>
        <p role="status">{progressLabels[status.progress.phase]} · 已处理 {status.progress.completed_cases} / {status.progress.planned_cases} 项验证。进度不代表安全结论。</p>
        {/* 最近进度只定位冻结的计划题目；不能把计划账号或计数补成实际执行事实。 */}
        {status.progress.current_case ? <section aria-label="当前处理的权限考题">
          <h3>{status.progress.current_case.expectation === 'ALLOW' ? '正常对照' : '拒绝验证'} · {status.progress.current_case.action_label}</h3>
          <p>计划操作账号：{status.progress.current_case.planned_subject_label}；资源所有者：{status.progress.current_case.planned_resource_owner_label}。</p>
          <p>本题将观察：{status.progress.current_case.effect_labels.join('、') || '本题冻结的业务结果'}。</p>
          <details><summary>核对本题资源引用</summary><code>{status.progress.current_case.resource_id}</code></details>
        </section> : <p className="editorial-muted">当前考题说明暂不可用，执行进度仍以服务端为准。</p>}
        <ol className="editorial-muted" aria-label="尚待发布的观察事实"><li>页面响应：未确认</li><li>后台执行：未确认</li><li>最终业务结果：未确认</li></ol>
        <p className="editorial-muted">这里显示最近进度对应的计划考题；实际账号、请求回应和业务结果将在本轮证据发布后说明。</p>
      </>},
      {key:'publish',title:'核验并发布本轮证据与结论',state:status.progress.phase === 'FINALIZING' ? 'current' : 'future',detail:<p>正在核验已取得的事实，发布完成后才展示判断。</p>},
    ]} />}
    {workspaceSyncFailed && <p role="alert">本次检查事实已保留，但下一步任务尚未同步。<Button onClick={() => void syncWorkspace(`retry:${selected ?? "overview"}:${refreshEpoch}`)}>重新同步工作台</Button></p>}
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
    {selectedMode && story && <CurrentResultStory key={story.run_id} story={story} requestedCaseId={props.requestedCaseId} onNavigate={onNavigate} onError={(error) => { setStory(null); setRunFailed(true); setStatus(null); onError(error) }} />}
    {!selectedMode && <>
      <Button onClick={showMaterials} disabled={busy}>管理准备材料</Button>
      {preview && !preview.can_execute && <Typography.Paragraph type="secondary">请在准备材料中核对账号、动作演示、资源、结果证明与恢复条件；材料齐备后仍需服务端确认执行配置。</Typography.Paragraph>}
      <Button type="link" onClick={() => onNavigate('/history')}>查看全部检查历史</Button>
    </>}
    <TaskActionBar back={{ label: props.onBackToHistory ? '返回检查历史' : '返回当前工作', disabled: busy, onClick: () => { if (props.onBackToHistory) props.onBackToHistory(); else if (selectedMode) { setSelected(undefined); void refresh() } else onNavigate('/workspace') } }}
      refresh={{ label: selectedMode ? '刷新检查结果' : '刷新检查条件', loading: loading || busy, onClick: () => { if (selectedMode) setRefreshEpoch((value) => value + 1); else void refresh() } }}
      />
  </EditorialPage>
}
