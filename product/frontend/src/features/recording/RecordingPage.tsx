/* =============================================================================
 * 流程录制页面
 *
 * 定位：编排录制准备、受控浏览器采集和 FlowDraft 审阅三个独立阶段。
 * 边界：普通流程不接收磁盘路径、headless 开关或原始 JSON；安全校验仍由后端完成。
 * ============================================================================= */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Card, Descriptions, Radio, Space } from 'antd'
import { ApiError } from '../../api/http'
import { recordingsApi, type FlowDraftDto, type RecordingActionDto, type RecordingDto, type RecordingReviewCommand, type RecordingTestIdentityDto, type RecordingViewDto } from '../../api/recordings'
import { runsApi } from '../../api/runs'
import type { ProjectDto } from '../../api/projects'
import type { PrimaryTaskDto, WorkspaceViewDto } from '../../api/workspace'
import { browserState } from '../../app/browserState'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { AssistantPanel } from '../../components/AssistantPanel'
import { TaskActionBar } from '../../components/TaskActionBar'
import { FlowDraftReview } from './FlowDraftReview'
import { RecordingCaptureCard, captureLabel } from './RecordingCaptureCard'
import { RecordingSetupCard } from './RecordingSetupCard'
import './recording.css'

const finishedStates = new Set(['PENDING_REVIEW', 'COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'])

async function sourceChoiceId(value: string) {
  const [stepId, sequence, ...path] = value.split('|')
  const payload = `${stepId}\0${sequence}\0${path.join('|')}`
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(payload))
  return `choice-${Array.from(new Uint8Array(digest)).map((item) => item.toString(16).padStart(2, '0')).join('').slice(0, 16)}`
}

export function RecordingPage({ project, task, effectName, onError, onBack, onStateChanged, onContinuePreparation }: { project: ProjectDto; task?: PrimaryTaskDto; effectName?: string; onError: (error: ApiError) => void; onBack: () => void; onStateChanged: () => Promise<WorkspaceViewDto | undefined>; onContinuePreparation: () => Promise<void> | void }) {
  const [recording, setRecording] = useState<RecordingDto | null>(null)
  const [actionOptions, setActionOptions] = useState<RecordingActionDto[]>([])
  const [actionId, setActionId] = useState<string>()
  const [identityOptions, setIdentityOptions] = useState<RecordingTestIdentityDto[]>([])
  const [testIdentityId, setTestIdentityId] = useState<string>()
  const [duration, setDuration] = useState(600)
  const [sources, setSources] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string>()
  const [syncError, setSyncError] = useState<string>()
  const alive = useRef(true)
  const terminalSynced = useRef<string | undefined>(undefined)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])

  const syncWorkspace = async (savedMessage: string) => {
    if (!alive.current) return
    const snapshot = await onStateChanged()
    if (!alive.current) return
    if (snapshot) {
      setSyncError(undefined)
      return
    }
    setSyncError(`${savedMessage}，但工作区状态刷新失败，请重试“刷新流程状态”。`)
  }

  const updateView = (view: RecordingViewDto | RecordingDto) => {
    if (!alive.current) return
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
        supplement_choices: view.supplement_choices ?? current?.supplement_choices,
      }
      browserState.writeRecording(next)
      return next
    })
  }

  const refresh = async (recordingId = recording?.recording_id) => {
    if (!recordingId) return
    updateView(await recordingsApi.recording(recordingId))
  }

  useEffect(() => {
    let active = true
    // 浏览器状态只负责页面定位；当前 Recording 必须先由服务端列表重新确认。
    setRecording(null)
    browserState.clearRecording()
    Promise.all([recordingsApi.setup(project.project_id), recordingsApi.recordings(project.project_id)]).then(([setup, items]) => {
      if (!active) return
      setActionOptions(setup.action_options)
      setActionId(task ? task.business_action_id ?? undefined : setup.action_options[0]?.business_action_id)
      setIdentityOptions(setup.test_identity_options)
      setTestIdentityId(task ? task.test_identity_id ?? undefined : setup.test_identity_options[0]?.test_identity_id)
      // 有主任务时只恢复它指定的录制，不能拿项目最后一条录制替代当前材料。
      const id = task ? task.recording_id : items[0]?.recording_id
      if (id) return recordingsApi.recording(id).then((view) => { if (active) updateView(view) })
    }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [project.project_id, task?.task_id])

  useEffect(() => {
    const recordingId = recording?.recording_id
    if (!recordingId || finishedStates.has(recording.state)) return
    let active = true
    let pending = false
    const timer = window.setInterval(async () => {
      if (pending) return
      pending = true
      try {
        const view = await recordingsApi.recording(recordingId)
        if (active) updateView(view)
      } catch (error) { if (active) onError(error as ApiError) }
      finally { pending = false }
    }, 1200)
    return () => { active = false; window.clearInterval(timer) }
  }, [recording?.recording_id, recording?.state])

  useEffect(() => {
    if (!recording || !finishedStates.has(recording.state)) return
    const key = `${recording.recording_id}:${recording.state}`
    if (terminalSynced.current === key) return
    terminalSynced.current = key
    void syncWorkspace('录制状态已更新').catch((error) => { if (alive.current) onError(error as ApiError) })
  }, [recording?.recording_id, recording?.state])


  const draft = recording?.draft ?? undefined
  const steps = useMemo(() => draft?.steps ?? [], [draft?.revision])
  const variables = useMemo(() => draft?.variables ?? [], [draft?.revision])
  useEffect(() => {
    if (!draft) return
    setSources((current) => Object.fromEntries(variables.map((variable) => {
      const selected = variable.confirmed_source ?? variable.candidate_sources[0]
      return [variable.name, current[variable.name] ?? (selected ? `${selected.source_step_id}|${selected.source_event_sequence}|${selected.json_path}` : '')]
    })))
  }, [draft?.revision])

  const createRecording = async () => {
    const action = actionOptions.find((item) => item.business_action_id === actionId)
    if (!action || !testIdentityId || busy) return
    setBusy(true); setMessage(undefined)
    try {
      if (task) {
        const current = await onStateChanged()
        if (!alive.current) return
        if (!current || current.primary_task?.task_id !== task.task_id || !current.primary_task.can_execute) {
          setSyncError('准备要求已变化，请返回检查准备，按最新任务继续。'); return
        }
      }
      const created = await recordingsApi.createRecording(project.project_id, action.business_action_id, task?.action_revision ?? action.action_revision, testIdentityId, duration,
        task?.recording_purpose ?? 'TARGET', task?.parent_recording_id ?? undefined, task?.effect_id ?? undefined)
      updateView(created)
      if (!alive.current) return
      const id = created.recording?.recording_id
      if (id) await refresh(id)
      if (alive.current) await syncWorkspace('录制已创建')
    }
    catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) setBusy(false) }
  }
  const refreshPage = async () => {
    setBusy(true)
    try {
      const [setup, items] = await Promise.all([recordingsApi.setup(project.project_id), recordingsApi.recordings(project.project_id)])
      if (!alive.current) return
      setActionOptions(setup.action_options)
      setIdentityOptions(setup.test_identity_options)
      setActionId((current) => current && setup.action_options.some((item) => item.business_action_id === current) ? current : setup.action_options[0]?.business_action_id)
      setTestIdentityId((current) => current && setup.test_identity_options.some((item) => item.test_identity_id === current) ? current : setup.test_identity_options[0]?.test_identity_id)
      const recordingId = recording?.recording_id ?? (task ? task.recording_id : items[0]?.recording_id)
      if (recordingId) updateView(await recordingsApi.recording(recordingId))
      else { setRecording(null); browserState.clearRecording() }
      await syncWorkspace('流程状态已刷新')
    } catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) setBusy(false) }
  }
  const cancelRecording = async () => {
    const jobId = recording?.job?.job_id
    const recordingId = recording?.recording_id
    if (!jobId || !recordingId) return
    setBusy(true)
    try { await runsApi.cancel(jobId); if (alive.current) await refresh(recordingId); if (alive.current) await syncWorkspace('取消请求已提交') }
    catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) setBusy(false) }
  }
  const discardReview = async () => {
    if (!recording || recording.state !== 'PENDING_REVIEW' || busy) return
    setBusy(true)
    try {
      updateView(await recordingsApi.discard(recording.recording_id))
      if (alive.current) await refresh(recording.recording_id)
      if (alive.current) await syncWorkspace('未采用的录制已放弃')
    } catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) setBusy(false) }
  }
  const controlCapture = async (action: 'start' | 'stop') => {
    if (!recording?.recording_id) return
    setBusy(true)
    try { updateView(action === 'start' ? await recordingsApi.startCapture(recording.recording_id) : await recordingsApi.stopCapture(recording.recording_id)); if (alive.current) await refresh(); if (alive.current) await syncWorkspace('采集状态已更新') }
    catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) setBusy(false) }
  }
  const review = async (command: RecordingReviewCommand) => {
    if (!recording?.recording_id) return
    setBusy(true); setMessage(undefined)
    try { updateView(await recordingsApi.reviewRecording(recording.recording_id, command)); if (alive.current) await refresh(); if (alive.current) await syncWorkspace('业务选择已保存') }
    catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) setBusy(false) }
  }

  const sourcesReady = variables.every((variable) => Boolean(sources[variable.name]))
  const recordingPurpose = recording?.purpose ?? 'TARGET'
  const supplementChoices = recording?.supplement_choices ?? []
  const canFinalize = Boolean(draft && (recordingPurpose !== 'TARGET'
    ? supplementChoices.length === 1 || supplementChoices.some((item) => item.step_id === draft.target_step_id)
    : steps.length && draft.target_step_id && draft.resource_candidate_id && sourcesReady))
  const finalize = async () => {
    if (!recording?.recording_id || !draft || !canFinalize) return
    setBusy(true); setMessage(undefined)
    try {
      if ((recording.purpose ?? 'TARGET') === 'TARGET') for (const variable of variables) {
        if (!alive.current) return
        if (variable.status === 'CONFIRMED') continue
        updateView(await recordingsApi.reviewRecording(recording.recording_id, { schema_version: '1', operation: 'CONFIRM_VARIABLE_CHOICE', variable_name: variable.name, choice_id: await sourceChoiceId(sources[variable.name]) }))
      }
      if (!alive.current) return
      const finalized = await recordingsApi.finalizeRecording(recording.recording_id)
      updateView(finalized)
      if (!alive.current) return
      await refresh(recording.recording_id)
      setMessage(recordingPurpose === 'TARGET' ? '业务流程已保存。' : '本次补录已保存。')
      await syncWorkspace(recordingPurpose === 'TARGET' ? '业务流程已保存' : '补录事实已保存')
    } catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) setBusy(false) }
  }

  const reviewable = recording?.state === 'PENDING_REVIEW' && Boolean(draft)
  const phase = String(recording?.capture_phase ?? '')
  const setupDisabled = Boolean(recording && !['COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'].includes(recording.state))
  const primaryAction = !recording
    ? { label: '打开浏览器并开始准备', onClick: () => void createRecording(), loading: busy, disabled: !actionId || !testIdentityId }
    : phase === 'AWAITING_CAPTURE'
      ? { label: '开始记录这个操作', onClick: () => void controlCapture('start'), loading: busy }
      : phase === 'CAPTURING'
        ? { label: '我已完成这个操作', onClick: () => void controlCapture('stop'), loading: busy }
        : reviewable
          ? { label: canFinalize ? (recordingPurpose === 'TARGET' ? '保存业务流程' : '保存本次补录') : '完成业务选择后保存', onClick: () => void finalize(), loading: busy, disabled: !canFinalize }
          : recording.state === 'COMPLETED'
            ? { label: '继续准备', onClick: onContinuePreparation }
            : undefined
  const restartAction = reviewable
    ? { label: '放弃这次录制', onClick: () => void discardReview(), loading: busy, danger: true,
      confirm: { title: '放弃这次未采用的录制？', description: '本次录制将不再作为待审材料，已保存的其他业务演示和权限保持不变。返回检查准备后可重新演示。', okText: '放弃录制', cancelText: '继续审阅' } }
    : recording && !finishedStates.has(recording.state)
    ? {
      label: '取消并丢弃本次录制', onClick: () => void cancelRecording(), loading: busy, danger: true,
      confirm: { title: '取消并丢弃本次录制？', description: '界鉴会停止受控浏览器任务并丢弃尚未确认的本次录制；不会生成可用业务流程。', okText: '取消并丢弃', cancelText: '继续录制' },
    }
    : !task && recording && ['COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'].includes(recording.state)
      ? {
        label: '重新录制当前选择', onClick: () => void createRecording(), loading: busy, disabled: !actionId || !testIdentityId,
        confirm: { title: '重新录制当前选择的业务动作？', description: '界鉴会打开一个新的受控浏览器任务；已经保存的旧流程不会删除，新录制会成为当前页面正在处理的流程。', okText: '开始新录制', cancelText: '取消' },
      }
      : undefined

  return <Space direction="vertical" size="large" className="full-width recording-page">
    <PageTaskHeader title={task?.title ?? '业务流程'} description={task?.user_responsibility ?? '在真实浏览器中完成一次操作，再整理为可重复使用的业务演示。'} status={captureLabel(recording)} />
    {task?.recording_purpose === 'OBSERVATION' && <Alert type="info" showIcon message={`请演示一次：你通常在哪里确认“${effectName ?? '这项已确认的业务结果'}”是否发生。`} />}
    {task?.recording_purpose === 'RECOVERY' && <Alert type="info" showIcon message="请演示一次：你通常怎样恢复这项业务操作改变的状态。" />}
    {task ? <Card title="本次演示"><p>{task.why_now}</p><p>{task.system_will_do}</p><Descriptions size="small" column={1}><Descriptions.Item label="业务动作">{actionOptions.find((item) => item.business_action_id === task.business_action_id)?.display_name ?? '当前业务动作'}</Descriptions.Item><Descriptions.Item label="演示账号">{identityOptions.find((item) => item.test_identity_id === task.test_identity_id)?.label ?? '当前任务指定的账号'}</Descriptions.Item></Descriptions></Card>
      : <RecordingSetupCard actions={actionOptions} identities={identityOptions} actionId={actionId} testIdentityId={testIdentityId} duration={duration} disabled={setupDisabled} onActionChange={setActionId} onIdentityChange={setTestIdentityId} onDurationChange={setDuration} />}
    {recording && <RecordingCaptureCard recording={recording} onRefresh={() => void refreshPage()} />}
    {reviewable && recording && <AssistantPanel projectId={project.project_id} surface="recording-review" focus={{ recording_id: recording.recording_id }} title="这次录制的步骤用途" actionLabel="解读这次录制" />}
    {reviewable && draft && recordingPurpose === 'TARGET' && <FlowDraftReview draft={draft as FlowDraftDto} actionName={recording.action?.display_name ?? actionOptions.find((item) => item.business_action_id === draft.business_action_id)?.display_name ?? '这个业务动作'} sources={sources} canFinalize={canFinalize} onSourcesChange={setSources} onReview={(command) => void review(command)} />}
    {reviewable && draft && recordingPurpose !== 'TARGET' && <Card title={recordingPurpose === 'OBSERVATION' ? '哪一步用于确认业务结果？' : '哪一步用于恢复业务状态？'}>
      {supplementChoices.length > 1 && <Radio.Group value={draft.target_step_id} disabled={busy} onChange={(event) => void review({ schema_version: '1', operation: 'CONFIRM_TARGET_STEP', step_id: event.target.value })}>
        <Space direction="vertical">{supplementChoices.map((item) => <Radio key={item.step_id} value={item.step_id}>{item.label}</Radio>)}</Space>
      </Radio.Group>}
      <Alert type={canFinalize ? 'success' : 'warning'} showIcon message={canFinalize ? '业务含义已确认，可以保存本次补录' : supplementChoices.length ? '请选择符合这次业务目的的步骤' : '本次补录没有可用的业务步骤，请返回检查准备并重新演示'} />
    </Card>}
    {message && <Alert type="success" showIcon message={message} />}
    {syncError && <Alert type="warning" showIcon message={syncError} />}
    {recording?.state === 'COMPLETED' && draft && <Card className="recording-summary" title="已保存的业务流程"><Descriptions size="small" column={1}><Descriptions.Item label="业务动作">{recording.action?.display_name ?? actionOptions.find((item) => item.business_action_id === draft.business_action_id)?.display_name ?? '已确认动作'}</Descriptions.Item><Descriptions.Item label="用于录制的账号">{recording.test_identity?.label ?? '已准备测试账号'}{recording.test_identity?.actor_display_name ? `（${recording.test_identity.actor_display_name}）` : ''}</Descriptions.Item><Descriptions.Item label="状态">录制内容已保存</Descriptions.Item></Descriptions></Card>}
    <TaskActionBar back={{ label: '返回检查准备', onClick: onBack, disabled: busy }} refresh={{ label: '刷新流程状态', onClick: () => void refreshPage(), loading: busy }} restart={restartAction} primary={primaryAction && { ...primaryAction, disabled: Boolean(syncError) || busy || ('disabled' in primaryAction && Boolean(primaryAction.disabled)) }} />
  </Space>
}
