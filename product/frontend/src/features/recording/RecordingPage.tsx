/* =============================================================================
 * 流程录制页面
 *
 * 定位：编排录制准备、受控浏览器采集和 FlowDraft 审阅三个独立阶段。
 * 边界：普通流程不接收磁盘路径、headless 开关或原始 JSON；安全校验仍由后端完成。
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Collapse, Descriptions, Space, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { recordingsApi, type ActionSafetySetupViewDto, type ConfirmActionSafetySetupInput, type FlowDraftDto, type RecordingActionDto, type RecordingDto, type RecordingReviewCommand, type RecordingTestIdentityDto, type RecordingViewDto } from '../../api/recordings'
import type { ProjectDto } from '../../api/projects'
import { browserState } from '../../app/browserState'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { FlowDraftReview } from './FlowDraftReview'
import { RecordingCaptureCard, captureLabel } from './RecordingCaptureCard'
import { RecordingSetupCard } from './RecordingSetupCard'
import { ActionSafetySetupCard } from './ActionSafetySetupCard'

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

export function RecordingPage({ project, onError, onNext }: { project: ProjectDto; onError: (error: ApiError) => void; onNext?: () => void }) {
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
      setMessage(confirmed.automatic_execution_allowed ? '真实观察与安全恢复已经确认。' : '当前确认已保存，未补齐的内容会作为覆盖缺口保留。')
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }

  const reviewable = recording?.state === 'PENDING_REVIEW' && Boolean(draft)
  return <Space direction="vertical" size="large" className="full-width">
    <PageTaskHeader title="流程录制" description="在真实浏览器中完成一次操作，再把它整理为可重复使用的检查流程。" status={captureLabel(recording)} next={recording?.state === 'COMPLETED' ? safetySetup?.automatic_execution_allowed ? '真实观察与安全恢复已确认，可以继续完善权限规则' : '继续确认测试资源、真实观察和安全恢复' : '先选择身份，再准备登录和录制'} actionLabel={safetySetup?.automatic_execution_allowed ? '去权限规则' : undefined} onAction={safetySetup?.automatic_execution_allowed ? onNext : undefined} />
    <RecordingSetupCard actions={actionOptions} identities={identityOptions} actionId={actionId} testIdentityId={testIdentityId} duration={duration} busy={busy} disabled={Boolean(recording && !finishedStates.has(recording.state))} onActionChange={setActionId} onIdentityChange={setTestIdentityId} onDurationChange={setDuration} onCreate={() => void createRecording()} />
    {recording && <RecordingCaptureCard recording={recording} busy={busy} canCancel={!finishedStates.has(recording.state)} onRefresh={() => void refresh()} onControl={(action) => void controlCapture(action)} onError={onError} />}
    {reviewable && draft && <FlowDraftReview draft={draft as FlowDraftDto} actionName={recording.action?.display_name ?? actionOptions.find((item) => item.action_candidate_id === draft.action_candidate_id)?.display_name ?? '这个业务动作'} sources={sources} renamingStep={renamingStep} renameValue={renameValue} busy={busy} canFinalize={canFinalize} hasLooseActions={hasLooseActions} onSourcesChange={setSources} onRenameStart={(stepId, value) => { setRenamingStep(stepId); setRenameValue(value) }} onRenameValueChange={setRenameValue} onRenameCancel={() => setRenamingStep(undefined)} onReview={(command) => void review(command)} onFinalize={() => void finalize()} />}
    {message && <Alert type="success" showIcon message={message} />}
    {recording?.state === 'COMPLETED' && draft && <Descriptions bordered size="small" title="已录制业务流程" column={1}><Descriptions.Item label="业务动作">{recording.action?.display_name ?? actionOptions.find((item) => item.action_candidate_id === draft.action_candidate_id)?.display_name ?? '已确认动作'}</Descriptions.Item><Descriptions.Item label="录制状态">已录制</Descriptions.Item><Descriptions.Item label="目标请求">{recordedTargetLabel(draft)}</Descriptions.Item><Descriptions.Item label="录制身份">{recording.test_identity?.label ?? '已准备测试身份'}{recording.test_identity?.role_display_name ? `（${recording.test_identity.role_display_name}）` : ''}</Descriptions.Item></Descriptions>}
    {recording?.state === 'COMPLETED' && safetySetup && <ActionSafetySetupCard setup={safetySetup} busy={busy} onConfirm={(input) => void confirmSafetySetup(input)} />}
    {recording && <Collapse ghost items={[{ key: 'advanced-recording', label: '高级信息', children: <Descriptions size="small" column={1}><Descriptions.Item label="录制标识"><Typography.Text code>{recording.recording_id}</Typography.Text></Descriptions.Item><Descriptions.Item label="内部状态">{recording.state} / {recording.capture_phase ?? 'UNKNOWN'}</Descriptions.Item>{recording.flow_path && <Descriptions.Item label="流程文件">{recording.flow_path}</Descriptions.Item>}</Descriptions> }]} />}
  </Space>
}
