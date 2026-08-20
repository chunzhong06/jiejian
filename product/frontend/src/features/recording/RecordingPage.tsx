/* =============================================================================
 * 流程录制页面
 *
 * 定位：编排录制准备、受控浏览器采集和 FlowDraft 审阅三个独立阶段。
 * 边界：普通流程不接收磁盘路径、headless 开关或原始 JSON；安全校验仍由后端完成。
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Collapse, Descriptions, Space, Typography } from 'antd'
import { executionProfilesApi, type ExecutionProfileDto } from '../../api/executionProfiles'
import { ApiError } from '../../api/http'
import { recordingsApi, type FlowDraftDto, type RecordingDto, type RecordingIdentityDto, type RecordingReviewCommand, type RecordingViewDto } from '../../api/recordings'
import type { ProjectDto } from '../../api/projects'
import { browserState } from '../../app/browserState'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { FlowDraftReview, type RecordingBinding } from './FlowDraftReview'
import { RecordingCaptureCard, captureLabel } from './RecordingCaptureCard'
import { RecordingSetupCard } from './RecordingSetupCard'

const finishedStates = new Set(['PENDING_REVIEW', 'COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'])

export function RecordingPage({ project, onError, onNext }: { project: ProjectDto; onError: (error: ApiError) => void; onNext?: () => void }) {
  const stored = browserState.readRecording()
  const [recording, setRecording] = useState<RecordingDto | null>(stored?.project_id === project.project_id ? stored : null)
  const [profiles, setProfiles] = useState<ExecutionProfileDto[]>([])
  const [profileId, setProfileId] = useState<string>()
  const [identityOptions, setIdentityOptions] = useState<RecordingIdentityDto[]>([])
  const [identityId, setIdentityId] = useState<string>()
  const [duration, setDuration] = useState(600)
  const [bindings, setBindings] = useState<Record<string, RecordingBinding>>({})
  const [sources, setSources] = useState<Record<string, string>>({})
  const [renamingStep, setRenamingStep] = useState<string>()
  const [renameValue, setRenameValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string>()

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
        identity_options: 'identity_options' in view ? view.identity_options : current?.identity_options,
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

  useEffect(() => {
    let active = true
    setRecording((current) => current?.project_id === project.project_id ? current : null)
    Promise.all([executionProfilesApi.profiles(project.project_id), recordingsApi.recordings(project.project_id)]).then(([profileItems, items]) => {
      if (!active) return
      setProfiles(profileItems)
      setProfileId((current) => current && profileItems.some((item) => item.profile_id === current) ? current : profileItems[0]?.profile_id)
      if (items[0]?.recording_id) void refresh(items[0].recording_id)
    }).catch((error) => onError(error as ApiError))
    return () => { active = false }
  }, [project.project_id])

  useEffect(() => {
    if (!profileId) { setIdentityOptions([]); setIdentityId(undefined); return }
    let active = true
    recordingsApi.setup(project.project_id, profileId).then((setup) => {
      if (!active) return
      const options = setup.identity_options
      setIdentityOptions(options)
      setIdentityId((current) => current && options.some((item) => item.identity_id === current) ? current : options[0]?.identity_id)
    }).catch((error) => onError(error as ApiError))
    return () => { active = false }
  }, [project.project_id, profileId])

  useEffect(() => {
    const recordingId = recording?.recording_id
    if (!recordingId || finishedStates.has(recording.state)) return
    const timer = window.setInterval(() => { void refresh(recordingId) }, 1200)
    return () => window.clearInterval(timer)
  }, [recording?.recording_id, recording?.state])

  const draft = recording?.draft ?? undefined
  const steps = useMemo(() => draft?.steps ?? [], [draft?.revision])
  const variables = useMemo(() => draft?.variables ?? [], [draft?.revision])
  useEffect(() => {
    if (!draft) return
    setBindings((current) => Object.fromEntries(steps.filter((step) => step.method).map((step) => {
      const previous = current[step.id]
      const alternate = identityOptions.find((item) => item.identity_id !== step.identity_id)
      return [step.id, {
        alternate_identity_id: previous?.alternate_identity_id ?? step.alternate_identity_id ?? alternate?.identity_id ?? '',
        resource_id: previous?.resource_id ?? step.resource_id ?? '',
        alternate_resource_id: previous?.alternate_resource_id ?? step.alternate_resource_id ?? '',
      }]
    })))
    setSources((current) => Object.fromEntries(variables.map((variable) => {
      const selected = variable.confirmed_source ?? variable.candidate_sources[0]
      return [variable.name, current[variable.name] ?? (selected ? `${selected.source_event_sequence}|${selected.json_path}` : '')]
    })))
  }, [draft?.revision, identityOptions.map((item) => item.identity_id).join('|')])

  const createRecording = async () => {
    if (!profileId || !identityId) return
    setBusy(true); setMessage(undefined)
    try { updateView({ ...(await recordingsApi.createRecording(project.project_id, profileId, identityId, duration)), draft: null, capture_phase: 'PREPARING_BROWSER' }) }
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

  const networkSteps = steps.filter((step) => step.method)
  const bindingsReady = networkSteps.every((step) => { const binding = bindings[step.id]; return binding && Object.values(binding).every((value) => value.trim()) })
  const sourcesReady = variables.every((variable) => Boolean(sources[variable.name]))
  const hasLooseActions = steps.some((step) => !step.method)
  const canFinalize = Boolean(draft && steps.length && bindingsReady && sourcesReady && !hasLooseActions)
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
      updateView(await recordingsApi.finalizeRecording(recording.recording_id, bindings))
      setMessage('流程已经保存，可以用于后续检查。')
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }

  const reviewable = recording?.state === 'PENDING_REVIEW' && Boolean(draft)
  return <Space direction="vertical" size="large" className="full-width">
    <PageTaskHeader title="流程录制" description="在真实浏览器中完成一次操作，再把它整理为可重复使用的检查流程。" status={captureLabel(recording)} next={recording?.state === 'COMPLETED' ? '流程已保存，可以继续完善权限规则' : '先选择身份，再准备登录和录制'} actionLabel={recording?.state === 'COMPLETED' ? '去权限规则' : undefined} onAction={recording?.state === 'COMPLETED' ? onNext : undefined} />
    <RecordingSetupCard profiles={profiles} identities={identityOptions} profileId={profileId} identityId={identityId} duration={duration} busy={busy} disabled={Boolean(recording && !finishedStates.has(recording.state))} onProfileChange={setProfileId} onIdentityChange={setIdentityId} onDurationChange={setDuration} onCreate={() => void createRecording()} />
    {recording && <RecordingCaptureCard recording={recording} busy={busy} canCancel={!finishedStates.has(recording.state)} onRefresh={() => void refresh()} onControl={(action) => void controlCapture(action)} onError={onError} />}
    {reviewable && draft && <FlowDraftReview draft={draft as FlowDraftDto} identities={identityOptions} bindings={bindings} sources={sources} renamingStep={renamingStep} renameValue={renameValue} busy={busy} canFinalize={canFinalize} bindingsReady={bindingsReady} hasLooseActions={hasLooseActions} onBindingsChange={setBindings} onSourcesChange={setSources} onRenameStart={(stepId, value) => { setRenamingStep(stepId); setRenameValue(value) }} onRenameValueChange={setRenameValue} onRenameCancel={() => setRenamingStep(undefined)} onReview={(command) => void review(command)} onFinalize={() => void finalize()} />}
    {message && <Alert type="success" showIcon message={message} />}
    {recording && <Collapse ghost items={[{ key: 'advanced-recording', label: '高级信息', children: <Space direction="vertical" className="full-width"><Descriptions size="small" column={1}><Descriptions.Item label="录制标识"><Typography.Text code>{recording.recording_id}</Typography.Text></Descriptions.Item><Descriptions.Item label="内部状态">{recording.state} / {recording.capture_phase ?? 'UNKNOWN'}</Descriptions.Item>{recording.flow_path && <Descriptions.Item label="流程文件">{recording.flow_path}</Descriptions.Item>}</Descriptions>{draft && <Collapse size="small" items={[{ key: 'raw-draft', label: '查看原始流程草稿（FlowDraft，只读）', children: <pre className="recording-raw-draft">{JSON.stringify(draft, null, 2)}</pre> }]} />}</Space> }]} />}
  </Space>
}
