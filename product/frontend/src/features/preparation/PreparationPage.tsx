// 动作级检查准备：展示现场材料，操作顺序与定位只消费最新 Workspace 主任务。
import { useLiveRead } from '../../app/useLiveRead'
import { WorkPageVisible } from '../../app/RetainedWorkPages'
import { useContext, useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Empty, Radio, Select, Space, Spin } from 'antd'
import { ApiError } from '../../api/http'
import type { ProjectDto } from '../../api/projects'
import { preparationApi, type AllowControlRequirement, type MaterialReference, type MaterialRecordingContext, type PreparationDraft, type PreparationView } from '../../api/preparation'
import { testIdentitiesApi, type IdentityPreparationDto } from '../../api/testIdentities'
import type { PrimaryTaskDto, WorkspaceViewDto } from '../../api/workspace'
import { AssistantPanel } from '../assistant/AssistantPanel'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { taskDestination } from '../../app/taskDestination'
import { TaskActionBar } from '../../shared/ui/TaskActionBar'
import { TestIdentityPage } from '../identities/TestIdentityPage'
import { RecordingPage } from '../recording/RecordingPage'
import { TaskReceipt, useTaskGuard } from '../../app/tasks/TaskContinuity'
import { MaterialOverview } from './MaterialOverview'
import { MaterialEditor, materialName } from './MaterialEditor'
import { EvidenceMaterials } from './EvidenceMaterials'

function matchesRecordingTask(task: PrimaryTaskDto | null | undefined, ref: MaterialReference) {
  if (!task?.can_execute || task.business_action_id !== ref.action_id || task.action_revision !== ref.action_revision) return false
  if (ref.kind === 'evidence') return (task.task_kind === 'COMPLETE_EFFECT_EVIDENCE' || (task.task_kind === 'REVIEW_RECORDING' && task.recording_purpose === 'OBSERVATION')) && task.effect_id === ref.member_id
  if (ref.kind === 'recovery') return task.task_kind === 'COMPLETE_RECOVERY' || (task.task_kind === 'REVIEW_RECORDING' && task.recording_purpose === 'RECOVERY')
  if (ref.kind === 'resource' && task.resource_owner_test_identity_id !== ref.member_id) return false
  return ['DEMONSTRATE_ACTION', 'PREPARE_ACTION_RESOURCE'].includes(task.task_kind) || (task.task_kind === 'REVIEW_RECORDING' && task.recording_purpose === 'TARGET')
}

export function PreparationPage({ project, workspace, onStateChanged, onError, onNavigate, onProvidedMaterials, onFeedback }: {
  project: ProjectDto
  onProvidedMaterials?: () => Promise<unknown>
  workspace: WorkspaceViewDto | null
  onStateChanged: () => Promise<WorkspaceViewDto | undefined>
  onError: (error: ApiError) => void
  onNavigate: (path: string) => void
  onFeedback?: (message: string) => void
}) {
  const visible = useContext(WorkPageVisible)
  const [preparation, setPreparation] = useState<PreparationView | null>(null)
  const [currentWorkspace, setCurrentWorkspace] = useState(workspace)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [syncError, setSyncError] = useState<string>()
  const [receipt, setReceipt] = useState<string>()
  const [selectedAction, setSelectedAction] = useState<string>()
  const [material, setMaterial] = useState<{ reference: MaterialReference; label: string }>()
  const [evidenceAction, setEvidenceAction] = useState<string>()
  const [focusSourceEntry, setFocusSourceEntry] = useState(false)
  const draftRef = useRef<PreparationDraft | undefined>(undefined)
  const [returnMaterial, setReturnMaterial] = useState<MaterialReference>()
  useTaskGuard(busy || Boolean(syncError))
  const feedback = (message: string) => { setReceipt(message); onFeedback?.(message) }
  const [mode, setMode] = useState<'materials' | 'identities' | 'recording'>('materials')
  const [recordingTask, setRecordingTask] = useState<PrimaryTaskDto>()
  const [materialRecording, setMaterialRecording] = useState<MaterialRecordingContext>()
  const recordingReturn = useRef<{ reference: MaterialReference; label: string } | undefined>(undefined)
  const [login, setLogin] = useState<IdentityPreparationDto>()
  const [choices, setChoices] = useState<Record<string, string>>({})
  // 后台刷新只更新事实，不滚动页面或夺走正在操作的焦点。
  const selecting = useRef(false)
  const projectRef = useRef(project.project_id)
  projectRef.current = project.project_id
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => { if (workspace?.project.project_id === project.project_id) setCurrentWorkspace(workspace) }, [workspace, project.project_id])
  useEffect(() => {
    let active = true
    setLoading(true); setPreparation(null); setChoices({}); setMode('materials'); setSyncError(undefined); setMaterial(undefined); setSelectedAction(undefined); setEvidenceAction(undefined)
    void Promise.all([preparationApi.get(project.project_id), preparationApi.draft(project.project_id)]).then(([value, draft]) => {
      if (!active) return
      if (value.project_id !== project.project_id) throw new ApiError('STATE_PRECONDITION', '材料所属应用不一致，请重新读取。')
      setPreparation(value); draftRef.current = draft
      const action = value.actions.find(item => item.action_id === draft.action_id && item.action_revision === draft.action_revision)
      if (action) {
        setSelectedAction(action.action_id)
        if (draft.material) setMaterial({ reference: draft.material, label: '上次处理的材料' })
      }
    })
      .catch((error) => { if (active) onError(error as ApiError) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [project.project_id, onError])

  // 写动作后先重读页面材料，再同步 Workspace；失败保留已完成动作并阻止使用旧任务。
  const reload = useCallback(async () => {
    const next = await preparationApi.get(project.project_id)
    if (next.project_id !== project.project_id) throw new ApiError('STATE_PRECONDITION', '材料所属应用不一致，请重新读取。')
    if (!alive.current || projectRef.current !== project.project_id) return
    setPreparation(next)
    const nextWorkspace = await onStateChanged().catch(() => undefined)
    if (!alive.current || projectRef.current !== project.project_id) return
    if (!nextWorkspace) { setSyncError('材料已刷新，但下一步尚未同步，请重试刷新。'); return }
    setCurrentWorkspace(nextWorkspace)
    setSyncError(undefined)
    return { preparation: next, workspace: nextWorkspace }
  }, [project.project_id, onStateChanged])
  const materialSync = useLiveRead(visible && !busy && mode === 'materials' ? project.project_id : undefined, async () => {
    if (syncError) {
      if (!await reload()) throw new Error('Preparation workspace synchronization unavailable')
      return
    }
    const id = project.project_id
    const next = await preparationApi.get(id)
    if (next.project_id !== id) throw new ApiError('STATE_PRECONDITION', '材料所属应用不一致，请重新读取。')
    if (alive.current && projectRef.current === id) setPreparation(next)
  }, 5000, false)
  const syncChild = async () => (await reload())?.workspace
  const showMaterials = async () => {
    try { await reload(); if (alive.current) { setMode('materials'); if (materialRecording && recordingReturn.current) setMaterial(recordingReturn.current); setMaterialRecording(undefined) } } catch (error) { if (alive.current) onError(error as ApiError) }
  }
  const refresh = async () => {
    setBusy(true)
    try { await reload() } catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) setBusy(false) }
  }
  const installProvidedMaterials = async () => {
    if (!onProvidedMaterials || selecting.current || busy || syncError) return
    selecting.current = true; setBusy(true)
    try {
      await onProvidedMaterials()
      if (!alive.current || projectRef.current !== project.project_id) return
      feedback('提供的测试材料已保存。准备材料不代表实际身份或安全结论。')
      setSyncError('材料已保存，正在同步下一步。')
      await reload()
    }
    catch (error) {
      if (alive.current && projectRef.current === project.project_id) {
        onError(error as ApiError)
        try { await reload() } catch { setSyncError('材料操作回执尚未确认，请刷新后核对；不要重复提交。') }
      }
    } finally { selecting.current = false; if (alive.current && projectRef.current === project.project_id) setBusy(false) }
  }
  const selectControl = async (control: AllowControlRequirement) => {
    const selected = control.candidate_allow_permissions.find((item) => item.intent_id === choices[control.selection_fingerprint])
    if (!selected || selecting.current || busy || syncError) return
    selecting.current = true; setBusy(true)
    try {
      // 服务端核对整组候选指纹；保存后先同步事实，不能把旧选择用于另一组考题。
      await preparationApi.selectAllowControl(project.project_id, control, selected)
      if (!alive.current || projectRef.current !== project.project_id) return
      setChoices({}); setSyncError('正常对照已保存，正在同步下一步。')
      feedback('正常对照已保存，原有权限规则保持不变。')
      await reload()
    } catch (error) { if (alive.current && projectRef.current === project.project_id) onError(error as ApiError) }
    finally { selecting.current = false; if (alive.current && projectRef.current === project.project_id) setBusy(false) }
  }
  const proceed = async () => {
    setBusy(true)
    try {
      const fresh = await reload()
      const task = fresh?.workspace.primary_task
      if (!fresh || !task || !alive.current) return
      if (task.route !== '/tests') { onNavigate(task.route); return }
      if (!task.can_execute) return
      if (task.task_kind === 'SELECT_ALLOW_CONTROL') return
      if (['RUN_CURRENT_CHECK', 'VIEW_CURRENT_RESULT', 'VERIFY_REPAIR'].includes(task.task_kind)) { onNavigate(taskDestination(task)); return }
      if (task.task_kind === 'PREPARE_TEST_IDENTITY') {
        const action = fresh.preparation.actions.find((item) => item.action_id === task.business_action_id)
        const slot = action?.identity_requirements.slots.find((item) => item.requirement.slot_id === task.identity_slot_id)
        if (!slot) return
        let identityId = task.test_identity_id
        if (!identityId) {
          const created = await testIdentitiesApi.create(project.project_id, slot.requirement.actor_id, slot.requirement.actor_revision,
            `${slot.actor_display_name}账号 ${slot.requirement.ordinal}`)
          identityId = created.identity_id
          // 创建已经是完成的事实；同步失败时留待刷新，不重复创建或继续使用旧任务。
          const updated = await reload()
          if (!updated || !alive.current) return
          const nextTask = updated.workspace.primary_task
          if (nextTask?.task_kind !== 'PREPARE_TEST_IDENTITY' || nextTask.identity_slot_id !== task.identity_slot_id || nextTask.test_identity_id !== identityId || !nextTask.can_execute) return
        }
        const session = await testIdentitiesApi.startPreparation(identityId)
        if (!alive.current) return
        setLogin(session); setMode('identities')
        await reload()
      } else {
        setRecordingTask(task); setMode('recording')
      }
    } catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) setBusy(false) }
  }

  const openMaterial = async (reference: MaterialReference, label: string) => {
    setFocusSourceEntry(false)
    setBusy(true)
    try {
      const draft = draftRef.current ?? await preparationApi.draft(project.project_id)
      if (draft.pending_operation_id) { setMaterial({ reference: draft.material!, label: '上次处理的材料' }); return }
      draftRef.current = await preparationApi.saveDraft(project.project_id, { ...draft, action_id: reference.action_id,
        action_revision: reference.action_revision, material: reference, candidate_recording_id: null, base_fingerprint: null, pending_operation_id: null })
      setMaterial({ reference, label })
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  const closeMaterial = async () => {
    if (!material) return
    try {
      const draft = draftRef.current ?? await preparationApi.draft(project.project_id)
      if (!draft.pending_operation_id) draftRef.current = await preparationApi.saveDraft(project.project_id, { ...draft, material: null,
        candidate_recording_id: null, base_fingerprint: null, action_id: null, action_revision: null })
    } catch (error) { onError(error as ApiError) }
    finally {
      setReturnMaterial(material.reference); setSelectedAction(material.reference.action_id); setMaterial(undefined)
      try { await reload() } catch (error) { onError(error as ApiError) }
      requestAnimationFrame(() => document.querySelector<HTMLButtonElement>(`[data-material-key="${material.reference.kind}:${material.reference.member_id ?? ''}"]`)?.focus())
    }
  }
  const selectAction = async (id: string) => {
    const action = preparation?.actions.find(item => item.action_id === id)
    if (!action) return
    setSelectedAction(id)
    try {
      const draft = draftRef.current ?? await preparationApi.draft(project.project_id)
      if (draft.pending_operation_id && draft.material) { setMaterial({ reference: draft.material, label: '上次处理的材料' }); return }
      draftRef.current = await preparationApi.saveDraft(project.project_id, { ...draft, action_id: id, action_revision: action.action_revision,
        material: null, candidate_recording_id: null, base_fingerprint: null, pending_operation_id: null })
    } catch (error) { onError(error as ApiError) }
  }
  if (evidenceAction) return <EvidenceMaterials projectId={project.project_id} actionId={evidenceAction} onBack={() => { setFocusSourceEntry(true); setEvidenceAction(undefined) }} />
  if (material) return <MaterialEditor key={JSON.stringify(material.reference)} projectId={project.project_id} reference={material.reference}
    onEvidence={() => setEvidenceAction(material.reference.action_id)}
    focusSourceEntry={focusSourceEntry}
    onRecordCandidate={context => { recordingReturn.current = material; setMaterialRecording(context); setRecordingTask(undefined); setMaterial(undefined); setMode('recording') }}
    labelForMaterial={ref => {
      const effect = currentWorkspace?.actions.find(action => action.action_id === ref.action_id)?.effect_catalog.find(item => item.effect_id === ref.member_id)
      const owner = preparation?.actions.find(action => action.action_id === ref.action_id)?.identity_requirements.slots.find(slot => slot.test_identity_id === ref.member_id)
      return effect ? `结果证明 · ${effect.business_label}` : ref.kind === 'resource' && owner ? `测试资源 · ${owner.actor_display_name}账号 ${owner.requirement.ordinal}` : materialName(ref)
    }}
    onDraftChange={value => { draftRef.current = value }}
    actionLabel={preparation?.actions.find(item => item.action_id === material.reference.action_id)?.display_name ?? '当前业务动作'}
    effectLabel={currentWorkspace?.actions.find(action => action.action_id === material.reference.action_id)?.effect_catalog.find(effect => effect.effect_id === material.reference.member_id)?.business_label ?? material.label} onError={onError} onBack={() => void closeMaterial()} onSaved={reload}
    onRecord={matchesRecordingTask(currentWorkspace?.primary_task, material.reference) ? () => { setMaterial(undefined); void proceed() } : undefined} />
  if (mode === 'identities') return <TestIdentityPage key={`${project.project_id}:${login?.preparation_id ?? 'accounts'}`} project={project} initialPreparation={login}
    onError={onError} onBack={() => void showMaterials()} onContinuePreparation={showMaterials} onStateChanged={syncChild} onPrepared={() => onFeedback?.('登录状态已保存，已有的其他材料继续保留。')} />
  if (mode === 'recording' && (recordingTask || materialRecording)) return <RecordingPage key={`${project.project_id}:${materialRecording?.context_id ?? recordingTask?.task_id}`} project={project} task={recordingTask} materialContext={materialRecording}
    effectName={currentWorkspace?.actions.find((item) => item.action_id === (materialRecording ?? recordingTask)?.business_action_id)?.effect_catalog.find((item) => item.effect_id === (materialRecording ?? recordingTask)?.effect_id)?.business_label}
    onError={onError} onBack={() => void showMaterials()} onContinuePreparation={showMaterials} onStateChanged={syncChild} />
  if (loading) return <EditorialPage><Spin />正在读取检查准备材料…</EditorialPage>
  if (!preparation) return <EditorialPage><EditorialHeader eyebrow="工作台 / 检查材料" title="暂时无法读取检查材料"/><p>尚未取得当前材料事实，重新读取后再继续。</p><Button loading={busy} onClick={() => void refresh()}>重新读取材料</Button></EditorialPage>
  const task = currentWorkspace?.primary_task
  const chosenActionId = preparation?.actions.find(action => action.action_id === selectedAction)?.action_id
    ?? preparation?.actions.find(action => action.action_id === task?.business_action_id)?.action_id ?? preparation?.actions[0]?.action_id
  const actorName = (id: string) => currentWorkspace?.actors.find((item) => item.actor_id === id)?.display_name ?? '业务主体'
  const taskStage: Record<string, number> = { PREPARE_TEST_IDENTITY: 0, DEMONSTRATE_ACTION: 1, PREPARE_ACTION_RESOURCE: 2, COMPLETE_EFFECT_EVIDENCE: 3, COMPLETE_RECOVERY: 4 }
  const currentStage = task?.task_kind === 'REVIEW_RECORDING' ? task.recording_purpose === 'OBSERVATION' ? 3 : task.recording_purpose === 'RECOVERY' ? 4 : 1 : task ? taskStage[task.task_kind] : undefined
  const providedAvailable = Boolean(onProvidedMaterials && !preparation?.preparation_complete && task?.route === '/tests' && currentStage !== undefined)
  const primaryButton = task && task.task_kind !== 'SELECT_ALLOW_CONTROL' ? <Button type={providedAvailable ? 'default' : 'primary'} loading={busy} disabled={Boolean(syncError) || materialSync.retrying || !task.can_execute} onClick={() => void proceed()}>
    {task.task_kind === 'PREPARE_TEST_IDENTITY' ? task.test_identity_id ? '打开登录浏览器' : '创建账号并登录' : task.route === '/tests' && currentStage !== undefined ? '继续准备这项材料' : task.action_label ?? '前往处理'}
  </Button> : null
  return <EditorialPage label="检查材料">
    <EditorialHeader eyebrow="工作台 / 检查材料" title="检查材料"><p className="editorial-muted">只更新需要处理的部分</p></EditorialHeader>
    {!!preparation?.actions.length && <Select className="materials-action-picker" aria-label="选择业务动作" disabled={busy}
      value={chosenActionId} onChange={id => void selectAction(id)}
      options={preparation.actions.map(action => ({ value: action.action_id, label: action.display_name }))} />}
    {(receipt || syncError) && <TaskReceipt message={receipt ?? '正在核对准备材料'} pending={syncError} onRetry={syncError ? () => void refresh() : undefined}/>}
    {materialSync.retrying && <Alert className="flow-feedback" type="warning" message="材料状态暂未同步" description={materialSync.stopped ? '当前读取未通过校验，请重新读取后再继续。' : '以下保留上次读取的内容，界鉴正在重新同步。继续操作前会再次核对。'} />}
    {!preparation?.actions.length && <Empty description="请先在业务边界中确认动作和权限" />}
    {preparation?.actions.filter(action => action.action_id === chosenActionId).map((action) => {
      const business = currentWorkspace?.actions.find((item) => item.action_id === action.action_id)
      const current = task?.business_action_id === action.action_id && task.action_revision === action.action_revision
      const permissionLabel = (id: string) => {
        const permission = action.permissions.find((item) => item.intent_id === id)
        if (!permission) return '当前已确认权限'
        const owner = permission.relation === 'OWNS' ? '自己' : permission.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `另一个${actorName(permission.resource_owner_actor_id)}账号` : actorName(permission.resource_owner_actor_id)
        const effects = permission.protected_effect_ids.map((effectId) => business?.effect_catalog.find((effect) => effect.effect_id === effectId)?.business_label ?? '已确认的业务结果').join('、')
        return `${actorName(permission.subject_actor_id)}对${owner}拥有的资源，${permission.expectation === 'ALLOW' ? '允许' : '拒绝'}“${action.display_name}”；业务结果：${effects}`
      }
      return <section key={action.action_id} className="preparation-action" aria-label={action.display_name}>
        {current && task?.task_kind === 'SELECT_ALLOW_CONTROL' && action.assurance_contract.allow_controls.filter((control) => !control.resolved_allow_permission && control.candidate_allow_permissions.length > 1).map((control) => <section key={control.selection_fingerprint} className="task-focus" aria-label="选择正常对照">
          <h3>选择正常对照</h3><p>{permissionLabel(control.deny_permission.intent_id)}</p><p>以下操作均符合正常对照条件。请选择本次用来确认业务功能正常的一项，现有权限规则保持不变。</p>
          <Radio.Group aria-label="正常对照候选" value={choices[control.selection_fingerprint]} disabled={busy || !task.can_execute || Boolean(syncError)} onChange={(event) => setChoices((values) => ({ ...values, [control.selection_fingerprint]: event.target.value }))}>
            <Space direction="vertical">{control.candidate_allow_permissions.map((candidate) => <Radio value={candidate.intent_id} key={candidate.intent_id}>{permissionLabel(candidate.intent_id)}</Radio>)}</Space>
          </Radio.Group><div className="confirmation-actions"><Button type="primary" loading={busy} disabled={!choices[control.selection_fingerprint] || !task.can_execute || Boolean(syncError)} onClick={() => void selectControl(control)}>确认正常对照</Button></div>
        </section>)}
        <MaterialOverview action={action} currentStage={current ? currentStage : undefined}
          outdated={materialSync.retrying}
          showFocus={!(current && task?.task_kind === 'SELECT_ALLOW_CONTROL')}
          effectName={id => business?.effect_catalog.find(effect => effect.effect_id === id)?.business_label ?? '已确认的业务结果'}
          taskTitle={syncError ? '材料已保存，正在同步下一步' : current ? task?.title : undefined} taskWhy={syncError ? '正在读取最新任务，不需要重新准备已经保存的材料。' : current ? task?.why_now : undefined}
          primary={current ? <>{primaryButton}{providedAvailable && <Button type="primary" loading={busy} disabled={Boolean(syncError) || materialSync.retrying || !task?.can_execute} onClick={() => void installProvidedMaterials()}>使用已提供的测试材料</Button>}</> : <Button type="primary" onClick={() => onNavigate('/tests')}>核对检查条件</Button>}
          onIdentity={() => { setLogin(undefined); setMode('identities') }} onMaterial={(reference, label) => void openMaterial(reference, label)} returnKind={returnMaterial?.action_id === action.action_id ? returnMaterial.kind : undefined}>
          <h3>已确认的权限</h3>{action.permissions.map(permission => <p key={permission.intent_id}>{permissionLabel(permission.intent_id ?? '')}</p>)}
          <AssistantPanel projectId={project.project_id} surface="preparation-explanation" focus={{ business_action_id: action.action_id }} title="理解这项动作的准备要求" actionLabel="解释准备缺口" />
        </MaterialOverview>
      </section>
    })}
    <TaskActionBar back={{ label: '返回检查总览', onClick: () => onNavigate('/tests'), disabled: busy }} refresh={{ label: '刷新准备材料', onClick: () => void refresh(), loading: busy }} />
  </EditorialPage>
}
