/* =============================================================================
 * 流程录制页面
 *
 * 定位：编排录制准备、受控浏览器采集和 FlowDraft 审阅三个独立阶段。
 * 边界：普通流程不接收磁盘路径、headless 开关或原始 JSON；安全校验仍由后端完成。
 * ============================================================================= */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Checkbox, Radio, Space } from 'antd'
import { ApiError } from '../../api/http'
import { recordingsApi, type FlowDraftDto, type RecordingActionDto, type RecordingDto, type RecordingReviewCommand, type RecordingTestIdentityDto, type RecordingViewDto } from '../../api/recordings'
import { jobsApi } from '../../api/jobs'
import type { ProjectDto } from '../../api/projects'
import type { PrimaryTaskDto, WorkspaceViewDto } from '../../api/workspace'
import { browserState } from '../../app/browserState'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { AssistantPanel } from '../../components/AssistantPanel'
import { TaskActionBar } from '../../components/TaskActionBar'
import { FlowDraftReview } from './FlowDraftReview'
import { RecordingCaptureCard, captureLabel } from './RecordingCaptureCard'
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
  const [identityOptions, setIdentityOptions] = useState<RecordingTestIdentityDto[]>([])
  const [ownerConfirmed, setOwnerConfirmed] = useState(false)
  const duration = 600
  const subjectId = task?.subject_test_identity_id
  const ownerId = task?.resource_owner_test_identity_id
  const distinctOwner = Boolean(subjectId && ownerId && subjectId !== ownerId)
  const validAssignment = Boolean(task?.can_execute && task.action_revision && task.subject_slot_id && task.resource_owner_slot_id && subjectId && ownerId)
  const creating = useRef(false)
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
    setOwnerConfirmed(false)
    browserState.clearRecording()
    Promise.all([recordingsApi.setup(project.project_id), recordingsApi.recordings(project.project_id)]).then(([setup, items]) => {
      if (!active) return
      setActionOptions(setup.action_options)
      setIdentityOptions(setup.test_identity_options)
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
    const action = actionOptions.find((item) => item.business_action_id === task?.business_action_id && item.action_revision === task.action_revision)
    if (!task || !action || !validAssignment || !subjectId || !ownerId || !task.subject_slot_id || !task.resource_owner_slot_id || (distinctOwner && !ownerConfirmed) || busy || creating.current) return
    creating.current = true; setBusy(true); setMessage(undefined)
    try {
      const current = await onStateChanged()
      if (!alive.current) return
      const fresh = current?.primary_task
      if (!fresh || fresh.task_id !== task.task_id || !fresh.can_execute || fresh.subject_test_identity_id !== subjectId || fresh.resource_owner_test_identity_id !== ownerId || fresh.subject_slot_id !== task.subject_slot_id || fresh.resource_owner_slot_id !== task.resource_owner_slot_id) {
        setSyncError('准备要求已变化，请返回检查准备，按最新任务继续。'); return
      }
      // 组合只来自最新主任务；资源归属确认不会改变登录主体，也不允许自由拼接账号。
      const created = await recordingsApi.createRecording(project.project_id, {
        business_action_id: action.business_action_id, action_revision: task.action_revision!,
        subject_test_identity_id: subjectId, resource_owner_test_identity_id: ownerId,
        subject_slot_id: task.subject_slot_id, resource_owner_slot_id: task.resource_owner_slot_id,
        resource_owner_confirmed: !distinctOwner || ownerConfirmed, duration_seconds: duration,
        purpose: task.recording_purpose ?? 'TARGET', parent_recording_id: task.parent_recording_id ?? null, effect_id: task.effect_id ?? null,
      })
      updateView(created)
      if (!alive.current) return
      const id = created.recording?.recording_id
      if (id) await refresh(id)
      if (alive.current) await syncWorkspace('录制已创建')
    }
    catch (error) { if (alive.current) onError(error as ApiError) }
    finally { creating.current = false; if (alive.current) setBusy(false) }
  }
  const refreshPage = async () => {
    setBusy(true)
    try {
      const [setup, items] = await Promise.all([recordingsApi.setup(project.project_id), recordingsApi.recordings(project.project_id)])
      if (!alive.current) return
      setActionOptions(setup.action_options)
      setIdentityOptions(setup.test_identity_options)
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
    try { await jobsApi.cancel(jobId); if (alive.current) await refresh(recordingId); if (alive.current) await syncWorkspace('取消请求已提交') }
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
  const identityName = (id?: string | null) => identityOptions.find((item) => item.test_identity_id === id)?.label ?? '当前任务指定的账号'
  const primaryAction = !recording
    ? task ? { label: '打开浏览器并开始准备', onClick: () => void createRecording(), loading: busy, disabled: !validAssignment || !actionOptions.some((item) => item.business_action_id === task.business_action_id && item.action_revision === task.action_revision) || !identityOptions.some((item) => item.test_identity_id === subjectId) || !identityOptions.some((item) => item.test_identity_id === ownerId) || (distinctOwner && !ownerConfirmed) } : undefined
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
    : undefined

  return <EditorialPage label="演示当前业务动作">
    <EditorialHeader eyebrow={`验证 · ${captureLabel(recording)}`} title={task?.title ?? '演示一次业务操作'}><p>{task?.user_responsibility ?? '在真实浏览器中完成一次操作，再整理为可复用的业务演示。'}</p></EditorialHeader>
    {task?.recording_purpose === 'OBSERVATION' && <Alert type="info" showIcon message={`请演示一次：你通常在哪里确认“${effectName ?? '这项已确认的业务结果'}”是否发生。`} />}
    {task?.recording_purpose === 'RECOVERY' && <Alert type="info" showIcon message="请演示一次：你通常怎样恢复这项业务操作改变的状态。" />}
    {task ? <section className="task-focus"><h2>本次演示</h2><p>{task.why_now}</p><p className="editorial-muted">{task.system_will_do}</p>
      <p>业务动作：{actionOptions.find((item) => item.business_action_id === task.business_action_id)?.display_name ?? '当前业务动作'}</p>
      <dl className="preparation-account-pair"><div><dt>操作账号</dt><dd>{identityName(subjectId)}</dd></div><div><dt>资源所属账号</dt><dd>{identityName(ownerId)}</dd></div></dl>
      {!recording && distinctOwner && <Checkbox checked={ownerConfirmed} disabled={busy} onChange={(event) => setOwnerConfirmed(event.target.checked)}>我确认本次演示的测试资源属于“{identityName(ownerId)}”</Checkbox>}
      {!recording && primaryAction && <div className="task-focus-actions"><Button type="primary" size="large" loading={busy} disabled={Boolean(syncError) || busy || ('disabled' in primaryAction && Boolean(primaryAction.disabled))} onClick={primaryAction.onClick}>{primaryAction.label}</Button></div>}</section>
      : <Alert type="info" showIcon message="要准备新的业务演示，请返回检查准备，按当前任务选择的账号和资源继续。" />}
    {recording && <RecordingCaptureCard recording={recording} onRefresh={() => void refreshPage()} />}
    {reviewable && recording && <details><summary>解释这次录制</summary><AssistantPanel projectId={project.project_id} surface="recording-review" focus={{ recording_id: recording.recording_id }} title="这次录制的步骤用途" actionLabel="解读这次录制" /></details>}
    {reviewable && draft && recordingPurpose === 'TARGET' && <FlowDraftReview draft={draft as FlowDraftDto} actionName={recording.action?.display_name ?? actionOptions.find((item) => item.business_action_id === draft.business_action_id)?.display_name ?? '这个业务动作'} sources={sources} canFinalize={canFinalize} onSourcesChange={setSources} onReview={(command) => void review(command)} />}
    {reviewable && draft && recordingPurpose !== 'TARGET' && <section><h2>{recordingPurpose === 'OBSERVATION' ? '哪一步用于确认业务结果？' : '哪一步用于恢复业务状态？'}</h2>
      {supplementChoices.length > 1 && <Radio.Group value={draft.target_step_id} disabled={busy} onChange={(event) => void review({ schema_version: '1', operation: 'CONFIRM_TARGET_STEP', step_id: event.target.value })}>
        <Space direction="vertical">{supplementChoices.map((item) => <Radio key={item.step_id} value={item.step_id}>{item.label}</Radio>)}</Space>
      </Radio.Group>}
      <Alert type={canFinalize ? 'success' : 'warning'} showIcon message={canFinalize ? '业务含义已确认，可以保存本次补录' : supplementChoices.length ? '请选择符合这次业务目的的步骤' : '本次补录没有可用的业务步骤，请返回检查准备并重新演示'} />
    </section>}
    {message && <Alert type="success" showIcon message={message} />}
    {syncError && <Alert type="warning" showIcon message={syncError} />}
    {recording?.state === 'COMPLETED' && draft && <section className="recording-summary"><h2>已保存的业务流程</h2><p>{recording.action?.display_name ?? '已确认动作'} · 账号：{recording.test_identity?.label ?? '已准备测试账号'}</p><p>录制内容已保存</p></section>}
    <TaskActionBar back={{ label: '返回检查准备', onClick: onBack, disabled: busy }} refresh={{ label: '刷新流程状态', onClick: () => void refreshPage(), loading: busy }} restart={restartAction} primary={recording && primaryAction ? { ...primaryAction, disabled: Boolean(syncError) || busy || ('disabled' in primaryAction && Boolean(primaryAction.disabled)) } : undefined} />
  </EditorialPage>
}
