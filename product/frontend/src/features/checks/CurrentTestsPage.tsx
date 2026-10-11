// 当前检查工作区：准备、显式提交、有限状态刷新和只读故事共享同一项目事实。
import { LoadingState } from '../../shared/ui/LoadingState'
import { Alert, Button, Typography } from 'antd'
import { useCallback, useContext, useEffect, useRef, useState, type ComponentProps } from 'react'
import { useLiveRead } from '../../shared/runtime/useLiveRead'
import { WorkPageVisible } from '../../shared/runtime/visibility'
import { ApiError } from '../../api/http'
import { currentChecksApi, type CheckPreview, type CheckStatus, type ResultStory } from '../../api/checks/currentChecks'
import { lifecycleLabel } from '../../shared/presentation/execution'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { TaskActionBar } from '../../shared/ui/TaskActionBar'
import { RequirementNotice } from '../../shared/ui/RequirementNotice'
import {RequirementScopeSummary} from '../../shared/ui/RequirementScopeSummary'
import { useTaskGuard } from '../../shared/runtime/editGuard'
import { PreparationPage } from '../preparation/PreparationPage'
import { CurrentResultStory } from '../results/CurrentResultStory'
import { ResultAgentHandoff } from '../results/ResultAgentHandoff'
import { CheckProgressPanel } from './CheckProgressPanel'
import { ResultOverviewHeader, ResultScope } from '../results/overview/ResultOverview'
import { SourceIdentityPanel } from '../changes/delivery/SourceIdentityPanel'

const active = (status: CheckStatus) => ['QUEUED', 'RUNNING'].includes(status.run.lifecycle)

export function CurrentTestsPage(props: ComponentProps<typeof PreparationPage> & { requestedMaterials?: boolean; requestedTaskId?: string | null; requestedRunId?: string | null; requestedCaseId?: string | null; requestedTab?:string|null; requestedEvidenceId?:string|null; requestedRecordId?:string|null; changeId?: string | null; onBackToHistory?: () => void }) {
  const { project, onError, onNavigate, requestedRunId, requestedTaskId, requestedMaterials } = props
  const visible = useContext(WorkPageVisible)
  const [materials, setMaterials] = useState(Boolean(requestedTaskId || requestedMaterials))
  const [resultView, setResultView] = useState<'result' | 'source'>('result')
  const [preview, setPreview] = useState<CheckPreview | null>(null)
  const [runs, setRuns] = useState<CheckStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [submissionStage, setSubmissionStage] = useState<'checking' | 'submitting'>()
  const [readFailed, setReadFailed] = useState(false)
  const [submissionUncertain, setSubmissionUncertain] = useState(false)
  const [selected, setSelected] = useState<string>()
  // 普通检查和复验都承接工作台明确选定的改动批次；不按最近检查猜测关联。
  // 已提交后固定本轮上下文，工作台的后续任务不得切换当前运行。
  const repairContext = useRef<{ projectId: string; changeId?: string }>({ projectId: project.project_id })
  if (repairContext.current.projectId !== project.project_id) repairContext.current = { projectId: project.project_id }
  if (!requestedRunId && !selected && !busy && !repairContext.current.changeId && props.workspace?.project.project_id === project.project_id && props.workspace.primary_task?.route === '/tests') repairContext.current.changeId = props.workspace.primary_task.change_id ?? undefined
  const changeId = props.changeId ?? (!requestedRunId ? repairContext.current.changeId : undefined)
  const navigateCheck = (path: string) => {
    const [route, search] = path.split('?')
    const query = new URLSearchParams(search)
    if (route === '/tests' && changeId && !query.has('run_id')) query.set('change_id', changeId)
    onNavigate(route + (query.size ? `?${query}` : ''))
  }
  const [status, setStatus] = useState<CheckStatus | null>(null)
  const [story, setStory] = useState<ResultStory | null>(null)
  const [openedResult, setOpenedResult] = useState<string>()
  const observedRunning = useRef(new Set<string>())
  const completionPending = Boolean(story && observedRunning.current.has(story.run_id) && openedResult !== story.run_id)
  useTaskGuard(Boolean(status && active(status)) || completionPending || busy || submissionUncertain)
  const [runFailed, setRunFailed] = useState(false)
  const [runLoading, setRunLoading] = useState(false)
  const [pollPaused, setPollPaused] = useState(false)
  const [workspaceSyncFailed, setWorkspaceSyncFailed] = useState(false)
  const [refreshEpoch, setRefreshEpoch] = useState(0)
  const submitting = useRef(false)
  const pending = useRef<{ fingerprint: string; key: string } | undefined>(undefined)
  const alive = useRef(true)
  const loadEpoch = useRef(0)
  const pendingRefreshes = useRef(0)
  const currentProject = useRef(project.project_id)
  currentProject.current = project.project_id
  const workspaceRefresh = useRef(props.onStateChanged)
  workspaceRefresh.current = props.onStateChanged
  const workspaceSynced = useRef<string | undefined>(undefined)
  const workspaceContext = useRef('')
  workspaceContext.current = `${project.project_id}:${selected ?? 'overview'}`
  const syncWorkspace = useCallback(async (key: string) => {
    if (workspaceSynced.current === key) return
    const context = workspaceContext.current
    try {
      const next = await workspaceRefresh.current()
      if (!alive.current || currentProject.current !== project.project_id || workspaceContext.current !== context) return
      if (!next || next.project.project_id !== project.project_id) { setWorkspaceSyncFailed(true); return }
      workspaceSynced.current = key; setWorkspaceSyncFailed(false)
    } catch { if (alive.current && currentProject.current === project.project_id && workspaceContext.current === context) setWorkspaceSyncFailed(true) }
  }, [project.project_id])

  useEffect(() => { alive.current = true; return () => { alive.current = false; loadEpoch.current += 1 } }, [])
  const refresh = useCallback(async (quiet = false) => {
    // 后台轮询不能不断废弃较慢的首次读取，否则材料齐备也会一直显示加载中。
    if (quiet && pendingRefreshes.current > 0) return
    pendingRefreshes.current += 1
    const epoch = ++loadEpoch.current
    if (!quiet) { setLoading(true); setReadFailed(false) }
    try {
      const [nextPreview, nextRuns] = await Promise.all([currentChecksApi.preview(project.project_id, changeId), currentChecksApi.list(project.project_id, true)])
      if (nextPreview.project_id !== project.project_id || nextRuns.some((item) => item.run.project_id !== project.project_id)) throw new ApiError('STATE_PRECONDITION', '检查信息所属项目不一致。')
      if (alive.current && epoch === loadEpoch.current) { setPreview(nextPreview); setRuns(nextRuns); setReadFailed(false) }
    } catch (error) { if (alive.current && epoch === loadEpoch.current) { setReadFailed(true); if (!quiet) { setPreview(null); onError(error as ApiError) } }; if (quiet) throw error }
    finally { pendingRefreshes.current -= 1; if (alive.current && epoch === loadEpoch.current) setLoading(false) }
  }, [project.project_id, onError, changeId])
  useLiveRead(visible && !selected && !materials && !busy ? project.project_id + (changeId ?? '') : undefined, () => refresh(true), 5000, false)
  useEffect(() => {
    setSelected(requestedRunId ?? undefined); setStatus(null); setStory(null); setRuns([]); setMaterials(Boolean(requestedTaskId || requestedMaterials)); setResultView('result')
    pending.current = undefined; setSubmissionUncertain(false); setOpenedResult(undefined); observedRunning.current.clear()
    // 本页提交后进入同一 Run 深链时 selected 不变；清空结果后仍须重新触发权威读取。
    setRefreshEpoch(value => value + 1)
  }, [refresh, requestedRunId, requestedTaskId, requestedMaterials])

  useEffect(() => {
    // 材料和历史结果拥有自己的读取；隐藏页面不并发编译用不到的检查计划。
    if (visible && !requestedRunId && !requestedTaskId && !requestedMaterials) void refresh()
  }, [refresh, visible, requestedRunId, requestedTaskId, requestedMaterials])

  useEffect(() => {
    setWorkspaceSyncFailed(false)
    if (!selected || materials || !visible) return
    let valid = true
    let timer: ReturnType<typeof setTimeout> | undefined
    let failures = 0, pendingRead = false
    // 同一轮刷新保留已读取的展示节点，进度条才能从旧值衔接；切换记录仍清除旧事实。
    setStatus(previous => previous?.run.run_id === selected && previous.run.project_id === project.project_id ? previous : null)
    setStory(previous => previous?.run_id === selected && previous.project_id === project.project_id ? previous : null)
    setRunFailed(false); setPollPaused(false); setRunLoading(true)
    const read = async () => {
      if (!valid || pendingRead || document.visibilityState === 'hidden') return
      clearTimeout(timer); pendingRead = true
      try {
        const next = await currentChecksApi.status(selected)
        if (next.run.project_id !== project.project_id || next.run.run_id !== selected) throw new ApiError('STATE_PRECONDITION', '检查记录所属项目不一致。')
        if (!valid) return
        if (active(next)) observedRunning.current.add(next.run.run_id)
        failures = 0; setRunFailed(false); setPollPaused(false)
        setStatus(next); setRuns((items) => items.map((item) => item.run.run_id === selected ? next : item))
        // 进度不代表结论，必须先通过完整性读取；失效时撤下旧故事。
        if (next.result_integrity === 'VALID') {
          const nextStory = await currentChecksApi.story(selected)
          if (nextStory.run_id !== selected || nextStory.project_id !== project.project_id || nextStory.verdict !== next.run.verdict) throw new ApiError('ARTIFACT_MANIFEST', '结果关联信息不一致。')
          if (valid) { setStory(nextStory); window.dispatchEvent(new Event('jiejian:check-updated')) }
        } else {
          setStory(null)
          if (active(next) || (next.run.lifecycle === 'COMPLETED' && next.result_integrity === 'NOT_PUBLISHED')) {
            timer = setTimeout(() => void read(), 2000)
          }
        }
        // 已发布事实保持只读；终态以后另行刷新唯一 Workspace，不能让工作台继续保留旧缺口。
        if (valid && !active(next)) void syncWorkspace(`${selected}:${next.run.lifecycle}:${next.result_integrity}:${next.run.finished_at_us}`)
      } catch (error) { if (valid) {
        if (error instanceof ApiError && ['STATE_PRECONDITION','ARTIFACT_MANIFEST','API_VERSION_UNSUPPORTED'].includes(error.code)) { setStatus(null); setStory(null); setRunFailed(true); onError(error) }
        else { setPollPaused(true); failures += 1; timer = setTimeout(() => void read(), Math.min(30000, 2000 * 2 ** Math.min(failures,3))) }
      } } finally { pendingRead = false; if (valid) setRunLoading(false) }
    }
    const resume = () => { if (document.visibilityState === 'visible') void read() }
    window.addEventListener('online', resume); window.addEventListener('focus', resume)
    document.addEventListener('visibilitychange', resume)
    void read()
    return () => { valid = false; if (timer) clearTimeout(timer); window.removeEventListener('online',resume); window.removeEventListener('focus',resume); document.removeEventListener('visibilitychange',resume) }
  }, [selected, materials, project.project_id, refreshEpoch, onError, syncWorkspace, visible])

  const start = async () => {
    if (submitting.current || !preview?.can_execute || readFailed) return
    submitting.current = true; setBusy(true); setSubmissionStage('checking')
    const projectId = project.project_id
    const recoveringUnknown = Boolean(pending.current)
    try {
      // 未知提交回执先查运行记录，重试只复用原幂等键，不能新建请求来试探。
      const freshRuns = await currentChecksApi.list(projectId, true)
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
      setSubmissionStage('submitting')
      const submitted = await currentChecksApi.submit(projectId, pending.current.fingerprint, pending.current.key, changeId)
      if (!alive.current || currentProject.current !== projectId) return
      pending.current = undefined; setSubmissionUncertain(false)
      props.onFeedback?.('检查请求已确认，可以离开此页后再查看结果。')
      setSelected(submitted.run.run_id)
      // 回执已确定精确运行，进度页自行读取；不再让第二次计划计算挡住进入。
      void syncWorkspace(`submitted:${submitted.run.run_id}`)
    } catch (error) { if (alive.current && currentProject.current === projectId) {
      // 首次请求被写入前门禁明确拒绝，不是回执丢失；已有未知请求则继续保留原幂等键。
      const rejectedBeforeWrite = error instanceof ApiError && ['STATE_PRECONDITION', 'INPUT_INVALID', 'PROJECT_NOT_FOUND'].includes(error.code)
      if (!recoveringUnknown && rejectedBeforeWrite) pending.current = undefined
      setSubmissionUncertain(Boolean(pending.current))
      onError(error as ApiError)
    } }
    finally { submitting.current = false; if (alive.current && currentProject.current === projectId) { setBusy(false); setSubmissionStage(undefined) } }
  }
  const showMaterials = () => { setMaterials(true); setSelected(undefined); navigateCheck('/tests?materials=1') }
  // 点击即进入明确的提交阶段；没有运行回执时不能提前展示任务或执行进度。
  if (submissionStage) return <EditorialPage label="正在提交检查" width="summary">
    <EditorialHeader eyebrow={project.name || '当前应用'} title={submissionStage === 'checking' ? '正在核对本轮检查范围' : '正在创建本轮检查'}/>
    <LoadingState>{submissionStage === 'checking' ? '正在确认准备条件与是否已有检查。核对完成后会继续提交。' : '正在等待服务端确认。收到回执后会自动显示检查进度。'}</LoadingState>
    <p className="editorial-muted">本次操作正在处理，无需再次点击。返回后仍可在当前检查中查看。</p>
    <TaskActionBar back={{label:'返回当前工作',onClick:()=>onNavigate('/workspace')}}/>
  </EditorialPage>
  // 显式切换准备任务只重置页面局部模式；同一任务刷新继续保留当前输入和服务端材料。
  if (materials) return <PreparationPage key={`${project.project_id}:${requestedTaskId ?? "materials"}`} {...props} assistReturnTo={`/tests?materials=1${changeId ? `&change_id=${encodeURIComponent(changeId)}` : ''}${props.requestedActionId ? `&action_id=${encodeURIComponent(props.requestedActionId)}` : ''}${requestedTaskId ? `&task_id=${encodeURIComponent(requestedTaskId)}` : ''}`} onNavigate={(path) => {
    if (path.split('?')[0] === '/tests' && !new URLSearchParams(path.split('?')[1]).has('task_id')) {
      const keepMaterials = new URLSearchParams(path.split('?')[1]).get('materials') === '1'
      setMaterials(keepMaterials); if (!keepMaterials) void refresh()
    }
    navigateCheck(path)
  }} />
  const running = runs.find(active)
  const selectedMode = Boolean(selected)
  const needsBoundary = Boolean(preview?.boundary_review_gaps?.length) || Boolean(props.workspace && props.workspace.actions.every(action=>action.current_permissions.length===0))
  const headline = selectedMode ? (completionPending ? '本轮检查已完成' : story?.judgement) ?? (runFailed || pollPaused && !story ? '暂时无法读取本次检查' : status?.result_integrity === 'INVALID' ? '结果完整性校验失败，不能展示安全结论' : status ? lifecycleLabel(status.run.lifecycle) : '正在读取检查记录')
    : loading ? '正在读取当前检查条件' : running ? '有一项检查正在执行' : preview?.can_execute ? '当前准备条件允许开始检查' : readFailed ? '暂时无法确认当前检查条件' : needsBoundary ? '请先核对权限要求与未覆盖范围' : '请先补齐本次检查所需材料'
  const primaryAction = selectedMode ? undefined : running ? { label: '查看当前进度', onClick: () => setSelected(running.run.run_id) }
    : preview?.can_execute ? { label: submissionUncertain ? '确认上次提交' : '开始检查', loading: busy, disabled: loading || readFailed, onClick: () => void start() }
    : needsBoundary ? { label:'核对权限要求',disabled:loading || busy,onClick:()=>onNavigate('/permissions?view=candidates') } : { label: '准备检查材料', disabled: loading || busy, onClick: showMaterials }
  return <EditorialPage label="权限验证工作区" width={!story ? 'summary' : undefined}>
    {selectedMode && !(story && !completionPending) && <div className="result-return"><Button type="link" onClick={() => { if (props.onBackToHistory) props.onBackToHistory(); else onNavigate('/history') }}>← 返回检查记录</Button></div>}
    {selectedMode && story && !completionPending ? <>
      <div className="result-location"><Button type="link" onClick={() => { if (props.onBackToHistory) props.onBackToHistory(); else onNavigate('/history') }}>检查历史</Button><span>/</span><span>本轮结果</span></div>
      <ResultOverviewHeader story={story} onNavigate={onNavigate} action={story.verdict === 'INCONCLUSIVE' ? { label: '查看准备条件', onClick: () => onNavigate('/tests?materials=1' + (story.change_context ? '&change_id=' + encodeURIComponent(story.change_context.change_id) : '')) } : undefined}/>
    </> : <EditorialHeader eyebrow={selectedMode ? '检查记录 / 本轮结果' : project.name || '当前应用'} title={headline}/>}
    {!selectedMode && <section className={`task-focus${!preview?.can_execute && !running ? ' check-preparation-summary' : ''}`} aria-label="当前检查判断"><div className="task-focus-layout"><div className="task-focus-copy"><h2>{preview?.can_execute || running ? '本轮检查范围' : '本轮准备情况'}</h2>
      {props.workspace?.source_change && (!changeId || props.workspace.source_change.change_id === changeId) && <p className="editorial-muted">最近代码变化：{props.workspace.source_change.reason} · {props.workspace.source_change.submitted_by || '来源未提供'}</p>}
      {preview && <><p>本次范围包含 {preview.action_count} 项业务动作、{preview.case_count} 项验证。开始前会重新核对准备条件。</p><ul className="check-scope-list">{preview.actions.map((action) => <li key={action.action_id}><strong>{props.workspace?.actions.find((item) => item.action_id === action.action_id && item.action_revision === action.action_revision)?.display_name ?? '本轮已确认的业务动作'}</strong><span>正常对照与拒绝验证</span></li>)}</ul></>}
      </div>
      {primaryAction && <div className="task-focus-actions"><Button type="primary" size="large" loading={busy} disabled={primaryAction.disabled} onClick={primaryAction.onClick}>{primaryAction.label}</Button></div>}</div>
    </section>}
    {selectedMode && status && (status.progress || active(status)) && status.result_integrity !== 'VALID' && !story && <CheckProgressPanel status={status} paused={pollPaused}>
      {active(status) && status.job && <Button danger disabled={busy || status.job.cancel_requested} onClick={async () => {
      setBusy(true)
      try { await currentChecksApi.cancel(status.job!.job_id); setRefreshEpoch(value => value + 1) } catch (error) { onError(error as ApiError) } finally { setBusy(false) }
    }}>{status.job.cancel_requested ? '正在停止检查' : '停止本次检查'}</Button>}
    </CheckProgressPanel>}
    {selectedMode && workspaceSyncFailed && <p role="status">检查记录已读取，工作台状态暂未同步。<Button onClick={() => void syncWorkspace(`retry:${selected}:${refreshEpoch}`)}>重新同步工作台</Button></p>}
    {!selectedMode && loading && <LoadingState>正在读取检查状态…</LoadingState>}
    {!selectedMode && readFailed && <Alert className="flow-feedback" type="warning" showIcon message="检查条件读取失败。刷新成功后才能开始检查。" />}
    {!selectedMode && <RequirementNotice gaps={preview?.boundary_review_gaps ?? []} purpose="check" onOpen={gap=>onNavigate((gap.next_url??gap.review_url).replace(/^#/,''))}/>}
    {!selectedMode && <RequirementScopeSummary scopes={preview?.requirement_scope??[]}/>}
    {!selectedMode && submissionUncertain && <Alert className="flow-feedback" type="warning" showIcon message="检查请求已发出，但尚未收到确认。请先读取检查记录；再次确认会使用同一次请求。" />}
    {selectedMode && pollPaused && <Alert className="flow-feedback" type="info" showIcon message={status?.result_integrity === 'VALID' && !story ? '检查已完成，但结果暂时无法读取，正在自动重试。不会重新执行检查。' : '暂时无法获取最新进度，正在自动重试。保留上次读取的状态。'} />}
    {selectedMode && !story && status && !active(status) && status.result_integrity === 'NOT_PUBLISHED' && <Alert className="flow-feedback" type="info" showIcon message="本次没有发布可用安全结论。执行停止或失败不代表发现权限问题。" />}
    {changeId && !selectedMode && <p className="editorial-muted">本轮对应所选修改批次，覆盖完整当前权限要求。</p>}
    {completionPending && story && <section className="task-focus check-completion" aria-label="本轮检查完成"><div className="agent-task-main">
      <p className="editorial-eyebrow task-focus-label" role="status">检查已完成，结果已保存。</p>
      <h2>{story.judgement}</h2>
      <p>{story.verdict === 'BLOCK' && story.actions.some(action => action.repair_requirement) ? '下一步：核对原问题与必须保留的正常业务，查看修复依据。' : '查看本轮结果与证据，了解检查结论及适用范围。'}</p>
      <div className="task-focus-actions">
        <Button type={story.verdict === 'BLOCK' && story.actions.some(action => action.repair_requirement) ? 'default' : 'primary'} onClick={() => setOpenedResult(story.run_id)}>查看本轮结果</Button>
        {story.verdict === 'BLOCK' && story.actions.some(action => action.repair_requirement) && <Button type="primary" onClick={() => onNavigate('/changes?repair_reference=' + encodeURIComponent(story.actions.find(action => action.repair_requirement)!.repair_requirement!.repair_fingerprint))}>查看修复依据</Button>}
      </div>
    </div><ResultAgentHandoff compact story={story} onNavigate={onNavigate}/></section>}
    {selectedMode && story && !completionPending && <>
      <nav className="result-review-views" aria-label="本轮结果视图"><button aria-current={resultView === 'result' ? 'page' : undefined} onClick={() => setResultView('result')}>检查结果 <span>{story.actions.length}</span></button><button aria-current={resultView === 'source' ? 'page' : undefined} onClick={() => setResultView('source')}>源码对应</button><ResultScope story={story}/></nav>
      {resultView === 'source' && <SourceIdentityPanel key={story.run_id} projectId={project.project_id} recordId={story.run_id} kind="runs" onIntegrityError={(error) => { setStory(null); setRunFailed(true); setStatus(null); onError(error) }}/>}
      <div hidden={resultView !== 'result'}><WorkPageVisible.Provider value={visible && resultView === 'result'}><CurrentResultStory key={story.run_id} embedded story={story} requestedCaseId={props.requestedCaseId} requestedTab={props.requestedTab} requestedEvidenceId={props.requestedEvidenceId} requestedRecordId={props.requestedRecordId} onCaseChange={caseId => onNavigate(`/tests?run_id=${encodeURIComponent(story.run_id)}${caseId ? '&case_id=' + encodeURIComponent(caseId) : ''}`)} onNavigate={onNavigate} onError={(error) => { setStory(null); setRunFailed(true); setStatus(null); onError(error) }}/></WorkPageVisible.Provider></div>
      {resultView==='result' && status?.result_integrity==='VALID' && <details className="check-process-history"><summary>查看本轮检查过程</summary><CheckProgressPanel status={status} paused={false}/></details>}
      <div className="result-record-actions">{resultView === 'source' && <Button onClick={() => onNavigate('/changes')}>查看当前代码变化</Button>}<Button loading={runLoading} onClick={() => setRefreshEpoch(value => value + 1)}>刷新检查结果</Button></div>
    </>}
    {!selectedMode && <>
      {preview && !preview.can_execute && !needsBoundary && <Typography.Paragraph type="secondary">请在准备材料中核对账号、动作演示、资源、结果证明与恢复条件；材料齐备后仍需服务端确认执行配置。</Typography.Paragraph>}
    </>}
    {!(selectedMode && story && !completionPending) && <div className="check-footer">{!selectedMode && <nav className="check-related-actions" aria-label="检查相关内容">{(running || preview?.can_execute) && <Button type="link" onClick={showMaterials} disabled={busy}>管理准备材料</Button>}</nav>}<TaskActionBar back={{ label: props.onBackToHistory ? '返回检查历史' : changeId ? '返回本批交付' : '返回当前工作', disabled: busy, onClick: () => { if (props.onBackToHistory) props.onBackToHistory(); else if (selectedMode) { setSelected(undefined); void refresh() } else onNavigate(changeId ? '/changes?change_id=' + encodeURIComponent(changeId) : '/workspace') } }}
      refresh={{ label: selectedMode ? '刷新检查结果' : '刷新检查条件', loading: (selectedMode ? runLoading : loading) || busy, onClick: () => { if (selectedMode) setRefreshEpoch((value) => value + 1); else void refresh() } }}
      /></div>}
  </EditorialPage>
}
