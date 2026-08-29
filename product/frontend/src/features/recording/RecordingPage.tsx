/* =============================================================================
 * 流程录制页面
 *
 * 定位：编排录制准备、受控浏览器采集和 FlowDraft 审阅三个独立阶段。
 * 边界：普通流程不接收磁盘路径、headless 开关或原始 JSON；安全校验仍由后端完成。
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Card, Descriptions, Space, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { recordingsApi, type ActionSafetySetupViewDto, type ConfirmActionSafetySetupInput, type FlowDraftDto, type RecordingActionDto, type RecordingDto, type RecordingReviewCommand, type RecordingTestIdentityDto, type RecordingViewDto } from '../../api/recordings'
import { runsApi } from '../../api/runs'
import type { ProjectDto } from '../../api/projects'
import { browserState } from '../../app/browserState'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { AssistantPanel } from '../../components/AssistantPanel'
import { TaskActionBar } from '../../components/TaskActionBar'
import { AdvancedDetails } from '../../components/AdvancedDetails'
import { FlowDraftReview } from './FlowDraftReview'
import { RecordingCaptureCard, captureLabel } from './RecordingCaptureCard'
import { RecordingSetupCard } from './RecordingSetupCard'
import { ActionSafetySetupCard } from './ActionSafetySetupCard'
import './recording.css'

const finishedStates = new Set(['PENDING_REVIEW', 'COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'])

function recordedTargetLabel(draft: FlowDraftDto) {
  const step = draft.steps.find((item) => item.id === draft.target_step_id)
  if (!step?.method || !step.path) return '尚未确认'
  const candidate = step.resource_candidates.find((item) => item.candidate_id === draft.resource_candidate_id)
  let path = step.path
  if (candidate?.consumer === 'PATH') {
    const index = Number(candidate.location.replace(/^path\[/, '').replace(/\]$/, ''))
    const parts = path.split('/')
    const positions = parts.flatMap((value, position) => value ? [position] : [])
    const position = positions[index]
    if (Number.isInteger(index) && position !== undefined) parts[position] = '{测试资源}'
    path = parts.join('/')
  } else if (candidate?.consumer === 'QUERY') {
    const name = candidate.location.replace(/^query\./, '')
    const [pathname, query = ''] = path.split('?', 2)
    const items = query.split('&').filter(Boolean).map((item) => {
      const [key, ...rest] = item.split('=')
      return decodeURIComponent(key) === name ? `${key}={测试资源}` : [key, ...rest].join('=')
    })
    path = pathname + (items.length ? `?${items.join('&')}` : '')
  }
  return `${step.method} ${path}`
}

export function RecordingPage({ project, onError, onBack, onNext }: { project: ProjectDto; onError: (error: ApiError) => void; onBack: () => void; onNext?: () => void }) {
  const [recording, setRecording] = useState<RecordingDto | null>(null)
  const [actionOptions, setActionOptions] = useState<RecordingActionDto[]>([])
  const [actionId, setActionId] = useState<string>()
  const [identityOptions, setIdentityOptions] = useState<RecordingTestIdentityDto[]>([])
  const [testIdentityId, setTestIdentityId] = useState<string>()
  const [duration, setDuration] = useState(600)
  const [sources, setSources] = useState<Record<string, string>>({})
  const [renamingStep, setRenamingStep] = useState<string>()
  const [renameValue, setRenameValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string>()
  const [safetySetup, setSafetySetup] = useState<ActionSafetySetupViewDto>()

  const updateView = (view: RecordingViewDto | RecordingDto) => {
    setRecording((current) => {
      const nested = 'recording' in view ? view.recording : undefined
      const record = nested ?? view as RecordingDto
      const next: RecordingDto = {
        ...current,
        ...record,
        project_id: record.project_id ?? current?.project_id ?? project.project_id,
        recording_id: record.recording_id ?? current?.recording_id ?? '',
        state: record.state ?? current?.state ?? 'QUEUED',
        draft: 'draft' in view ? view.draft : current?.draft,
        job: 'job' in view ? view.job : current?.job,
        capture_phase: 'capture_phase' in view ? view.capture_phase : current?.capture_phase,
        flow_path: 'flow_path' in view ? view.flow_path : current?.flow_path,
        action: 'action' in view ? view.action : current?.action,
        test_identity: 'test_identity' in view ? view.test_identity : current?.test_identity,
      }
      browserState.writeRecording(next)
      return next
    })
  }

  const refresh = async (recordingId = recording?.recording_id) => {
    if (!recordingId) return
    try { updateView(await recordingsApi.recording(recordingId)) }
    catch (error) { onError(error as ApiError) }
  }

  const refreshSafetySetup = async (recordingId = recording?.recording_id) => {
    if (!recordingId) return
    try { setSafetySetup(await recordingsApi.safetySetup(recordingId)) }
    catch (error) { onError(error as ApiError) }
  }

  useEffect(() => {
    let active = true
    // 浏览器状态只负责页面定位；当前 Recording 必须先由服务端列表重新确认。
    setRecording(null)
    browserState.clearRecording()
    Promise.all([recordingsApi.setup(project.project_id), recordingsApi.recordings(project.project_id)]).then(([setup, items]) => {
      if (!active) return
      setActionOptions(setup.action_options)
      setActionId((current) => current && setup.action_options.some((item) => item.action_candidate_id === current) ? current : setup.action_options[0]?.action_candidate_id)
      setIdentityOptions(setup.test_identity_options)
      setTestIdentityId((current) => current && setup.test_identity_options.some((item) => item.test_identity_id === current) ? current : setup.test_identity_options[0]?.test_identity_id)
      if (items[0]?.recording_id) void refresh(items[0].recording_id)
    }).catch((error) => onError(error as ApiError))
    return () => { active = false }
  }, [project.project_id])

  useEffect(() => {
    const recordingId = recording?.recording_id
    if (!recordingId || finishedStates.has(recording.state)) return
    const timer = window.setInterval(() => { void refresh(recordingId) }, 1200)
    return () => window.clearInterval(timer)
  }, [recording?.recording_id, recording?.state])

  useEffect(() => {
    if (recording?.state !== 'COMPLETED' || !recording.recording_id) {
      setSafetySetup(undefined)
      return
    }
    void refreshSafetySetup(recording.recording_id)
  }, [recording?.recording_id, recording?.state])

  const draft = recording?.draft ?? undefined
  const steps = useMemo(() => draft?.steps ?? [], [draft?.revision])
  const variables = useMemo(() => draft?.variables ?? [], [draft?.revision])
  useEffect(() => {
    if (!draft) return
    setSources((current) => Object.fromEntries(variables.map((variable) => {
      const selected = variable.confirmed_source ?? variable.candidate_sources[0]
      return [variable.name, current[variable.name] ?? (selected ? `${selected.source_event_sequence}|${selected.json_path}` : '')]
    })))
  }, [draft?.revision])

  const createRecording = async () => {
    if (!actionId || !testIdentityId) return
    setBusy(true); setMessage(undefined)
    try { setSafetySetup(undefined); updateView({ ...(await recordingsApi.createRecording(project.project_id, actionId, testIdentityId, duration)), draft: null, capture_phase: 'PREPARING_BROWSER' }) }
    catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  const refreshPage = async () => {
    setBusy(true)
    try {
      const [setup, items] = await Promise.all([recordingsApi.setup(project.project_id), recordingsApi.recordings(project.project_id)])
      setActionOptions(setup.action_options)
      setIdentityOptions(setup.test_identity_options)
      setActionId((current) => current && setup.action_options.some((item) => item.action_candidate_id === current) ? current : setup.action_options[0]?.action_candidate_id)
      setTestIdentityId((current) => current && setup.test_identity_options.some((item) => item.test_identity_id === current) ? current : setup.test_identity_options[0]?.test_identity_id)
      const recordingId = recording?.recording_id ?? items[0]?.recording_id
      if (recordingId) updateView(await recordingsApi.recording(recordingId))
      else { setRecording(null); browserState.clearRecording() }
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  const cancelRecording = async () => {
    const jobId = recording?.job?.job_id
    const recordingId = recording?.recording_id
    if (!jobId || !recordingId) return
    setBusy(true)
    try { await runsApi.cancel(jobId); await refresh(recordingId) }
    catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  const controlCapture = async (action: 'start' | 'stop') => {
    if (!recording?.recording_id) return
    setBusy(true)
    try { updateView(action === 'start' ? await recordingsApi.startCapture(recording.recording_id) : await recordingsApi.stopCapture(recording.recording_id)) }
    catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  const review = async (command: RecordingReviewCommand) => {
    if (!recording?.recording_id) return
    setBusy(true); setMessage(undefined)
    try { updateView(await recordingsApi.reviewRecording(recording.recording_id, command)); setRenamingStep(undefined) }
    catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }

  const sourcesReady = variables.every((variable) => Boolean(sources[variable.name]))
  const hasLooseActions = steps.some((step) => !step.method)
  const canFinalize = Boolean(draft && steps.length && draft.target_step_id && draft.resource_candidate_id && sourcesReady && !hasLooseActions)
  const finalize = async () => {
    if (!recording?.recording_id || !draft || !canFinalize) return
    setBusy(true); setMessage(undefined)
    try {
      for (const variable of variables) {
        if (variable.status === 'CONFIRMED') continue
        const selected = sources[variable.name]
        const separator = selected.indexOf('|')
        updateView(await recordingsApi.reviewRecording(recording.recording_id, { schema_version: '1', operation: 'CONFIRM_VARIABLE_SOURCE', variable_name: variable.name, source_event_sequence: Number(selected.slice(0, separator)), source_json_path: selected.slice(separator + 1) }))
      }
      const finalized = await recordingsApi.finalizeRecording(recording.recording_id)
      updateView(finalized)
      setSafetySetup(await recordingsApi.safetySetup(recording.recording_id))
      setMessage('流程已经保存。请继续确认测试资源、真实观察和安全恢复。')
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }

  const confirmSafetySetup = async (input: ConfirmActionSafetySetupInput) => {
    if (!recording?.recording_id) return
    setBusy(true); setMessage(undefined)
    try {
      const confirmed = await recordingsApi.confirmSafetySetup(recording.recording_id, input)
      setSafetySetup(confirmed)
      setMessage(confirmed.automatic_execution_allowed ? '真实观察与安全恢复已经确认。' : '当前确认已保存；未补齐的内容会明确显示为尚未完成。')
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }

  const reviewable = recording?.state === 'PENDING_REVIEW' && Boolean(draft)
  const phase = String(recording?.capture_phase ?? '')
  const currentStage = !recording ? 1 : reviewable ? 3 : recording.state === 'COMPLETED' ? 4 : 2
  const sequence = ['选择动作和账号', '在浏览器完成操作', '确认录制步骤', '确认真实结果与恢复']
  const setupDisabled = Boolean(recording && !['COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'].includes(recording.state))
  const primaryAction = !recording
    ? { label: '打开浏览器并开始准备', onClick: () => void createRecording(), loading: busy, disabled: !actionId || !testIdentityId }
    : phase === 'AWAITING_CAPTURE'
      ? { label: '开始记录这个操作', onClick: () => void controlCapture('start'), loading: busy }
      : phase === 'CAPTURING'
        ? { label: '我已完成这个操作', onClick: () => void controlCapture('stop'), loading: busy }
        : reviewable
          ? { label: canFinalize ? '确认并保存流程' : '完成步骤确认后保存', onClick: () => void finalize(), loading: busy, disabled: !canFinalize }
          : recording.state === 'COMPLETED' && !safetySetup
            ? { label: '正在读取真实结果与恢复选项', disabled: true }
            : recording.state === 'COMPLETED' && safetySetup && !safetySetup.automatic_execution_allowed
              ? { label: '确认测试资源、观察与恢复', submitForm: 'recording-safety-setup', loading: busy, disabled: safetySetup.resource_candidates.length === 0 }
              : recording.state === 'COMPLETED' && safetySetup?.automatic_execution_allowed && onNext
                ? { label: '继续确认权限与检查', onClick: onNext }
                : undefined
  const restartAction = recording && !finishedStates.has(recording.state)
    ? {
      label: '取消并丢弃本次录制', onClick: () => void cancelRecording(), loading: busy, danger: true,
      confirm: { title: '取消并丢弃本次录制？', description: '界鉴会停止受控浏览器任务并丢弃尚未确认的本次录制；不会生成可用业务流程。', okText: '取消并丢弃', cancelText: '继续录制' },
    }
    : recording && ['COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'].includes(recording.state)
      ? {
        label: '重新录制当前选择', onClick: () => void createRecording(), loading: busy, disabled: !actionId || !testIdentityId,
        confirm: { title: '重新录制当前选择的业务动作？', description: '界鉴会打开一个新的受控浏览器任务；已经保存的旧流程不会删除，新录制会成为当前页面正在处理的流程。', okText: '开始新录制', cancelText: '取消' },
      }
      : undefined

  return <Space direction="vertical" size="large" className="full-width recording-page">
    <PageTaskHeader title="业务流程" description="在真实浏览器中完成一次操作，再把它整理为可重复使用的检查流程。" status={captureLabel(recording)} />
    <ol className="task-sequence" aria-label="业务流程准备进度">
      {sequence.map((label, index) => {
        const step = index + 1
        const state = step < currentStage ? 'complete' : step === currentStage ? 'current' : 'upcoming'
        return <li key={label} className={`task-sequence-step is-${state}`}><span>{step < currentStage ? '✓' : step}</span><div><strong>{label}</strong><small>{state === 'complete' ? '已完成' : state === 'current' ? '当前任务' : '随后进行'}</small></div></li>
      })}
    </ol>
    <RecordingSetupCard actions={actionOptions} identities={identityOptions} actionId={actionId} testIdentityId={testIdentityId} duration={duration} disabled={setupDisabled} onActionChange={setActionId} onIdentityChange={setTestIdentityId} onDurationChange={setDuration} />
    {recording && <RecordingCaptureCard recording={recording} onRefresh={() => void refresh()} />}
    {draft && <AssistantPanel projectId={project.project_id} surface="recording-review" title="这次录制的步骤用途" actionLabel="AI 解读这次录制" />}
    {reviewable && draft && <FlowDraftReview draft={draft as FlowDraftDto} actionName={recording.action?.display_name ?? actionOptions.find((item) => item.action_candidate_id === draft.action_candidate_id)?.display_name ?? '这个业务动作'} sources={sources} renamingStep={renamingStep} renameValue={renameValue} busy={busy} canFinalize={canFinalize} hasLooseActions={hasLooseActions} onSourcesChange={setSources} onRenameStart={(stepId, value) => { setRenamingStep(stepId); setRenameValue(value) }} onRenameValueChange={setRenameValue} onRenameCancel={() => setRenamingStep(undefined)} onReview={(command) => void review(command)} />}
    {message && <Alert type={safetySetup && !safetySetup.automatic_execution_allowed ? 'info' : 'success'} showIcon message={message} />}
    {recording?.state === 'COMPLETED' && draft && <Card className="recording-summary" title="已保存的业务流程"><Descriptions size="small" column={1}><Descriptions.Item label="业务动作">{recording.action?.display_name ?? actionOptions.find((item) => item.action_candidate_id === draft.action_candidate_id)?.display_name ?? '已确认动作'}</Descriptions.Item><Descriptions.Item label="用于录制的账号">{recording.test_identity?.label ?? '已准备测试账号'}{recording.test_identity?.role_display_name ? `（${recording.test_identity.role_display_name}）` : ''}</Descriptions.Item><Descriptions.Item label="状态">录制内容已保存</Descriptions.Item></Descriptions><AdvancedDetails label="高级：技术请求"><Typography.Text code>{recordedTargetLabel(draft)}</Typography.Text></AdvancedDetails></Card>}
    {recording?.state === 'COMPLETED' && safetySetup && <ActionSafetySetupCard setup={safetySetup} busy={busy} onConfirm={(input) => void confirmSafetySetup(input)} />}
    {recording && <AdvancedDetails label="高级信息"><Descriptions size="small" column={1}><Descriptions.Item label="录制标识"><Typography.Text code>{recording.recording_id}</Typography.Text></Descriptions.Item><Descriptions.Item label="内部状态">{recording.state} / {recording.capture_phase ?? 'UNKNOWN'}</Descriptions.Item>{recording.flow_path && <Descriptions.Item label="流程文件">{recording.flow_path}</Descriptions.Item>}</Descriptions></AdvancedDetails>}
    <TaskActionBar back={{ label: '返回测试账号', onClick: onBack }} refresh={{ label: '刷新流程状态', onClick: () => void refreshPage(), loading: busy }} restart={restartAction} primary={primaryAction} />
  </Space>
}
