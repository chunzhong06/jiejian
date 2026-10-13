// 动作级检查准备：展示现场材料，操作顺序与定位只消费最新 Workspace 主任务。
import { AgentAssistEntry } from '../../shared/ui/AgentAssistEntry'
import { LoadingState } from '../../shared/ui/LoadingState'
import { useLiveRead } from '../../shared/runtime/useLiveRead'
import { WorkPageVisible } from '../../shared/runtime/visibility'
import { useContext, useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Empty, Radio, Select, Space } from 'antd'
import { ApiError } from '../../api/http'
import type { ProjectDto } from '../../api/applications/projects'
import { preparationApi, type AllowControlRequirement, type MaterialReference, type MaterialRecordingContext, type PreparationDraft, type PreparationView } from '../../api/preparation/preparation'
import { testIdentitiesApi, type IdentityPreparationDto } from '../../api/preparation/testIdentities'
import type { PrimaryTaskDto, WorkspaceViewDto } from '../../api/workspace'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { taskDestination } from '../../shared/navigation/taskDestination'
import { TaskActionBar } from '../../shared/ui/TaskActionBar'
import { TestIdentityPage } from '../identities/TestIdentityPage'
import { RecordingPage } from '../recording/RecordingPage'
import { TaskReceipt } from '../../shared/ui/TaskReceipt'
import { useTaskGuard } from '../../shared/runtime/editGuard'
import { MaterialOverview } from './materials/MaterialOverview'
import { MaterialEditor, materialName } from './materials/MaterialEditor'
import { EvidenceMaterials } from './evidence/EvidenceMaterials'
import { ProvidedMaterialPreparation } from './proof-sources/ProvidedMaterialPreparation'
import { ProofSourcesPanel } from './proof-sources/ProofSourcesPanel'
import { proofSourcesApi } from '../../api/preparation/proofSources'
import { preparationSuggestionsApi } from '../../api/preparation/preparationSuggestions'
import { useMaterialSuggestions } from './materials/useMaterialSuggestions'
import { materialSuggestionEntries, UnboundMaterialSuggestions } from './materials/MaterialSuggestions'
import { PreparationProgress } from './materials/PreparationProgress'

function matchesRecordingTask(task: PrimaryTaskDto | null | undefined, ref: MaterialReference) {
  if (!task?.can_execute || task.business_action_id !== ref.action_id || task.action_revision !== ref.action_revision) return false
  if (ref.kind === 'evidence') return (task.task_kind === 'COMPLETE_EFFECT_EVIDENCE' || (task.task_kind === 'REVIEW_RECORDING' && task.recording_purpose === 'OBSERVATION')) && task.effect_id === ref.member_id
  if (ref.kind === 'recovery') return task.task_kind === 'COMPLETE_RECOVERY' || (task.task_kind === 'REVIEW_RECORDING' && task.recording_purpose === 'RECOVERY')
  if (ref.kind === 'resource' && task.resource_owner_test_identity_id !== ref.member_id) return false
  return ['DEMONSTRATE_ACTION', 'PREPARE_ACTION_RESOURCE'].includes(task.task_kind) || (task.task_kind === 'REVIEW_RECORDING' && task.recording_purpose === 'TARGET')
}

export function PreparationPage({ project, workspace, onStateChanged, onError, onNavigate, onProvidedMaterials, onFeedback, requestedProofSources, requestedProofSource, requestedActionId, requestedIdentities, assistReturnTo, requestedSuggestionId, requestedSuggestionRevision, requestedMaterialKind }: {
  project: ProjectDto
  onProvidedMaterials?: () => Promise<unknown>
  workspace: WorkspaceViewDto | null
  onStateChanged: () => Promise<WorkspaceViewDto | undefined>
  onError: (error: ApiError) => void
  onNavigate: (path: string) => void
  onFeedback?: (message: string) => void
  requestedProofSources?: boolean
  requestedProofSource?: string | null
  requestedActionId?: string | null
  requestedIdentities?: boolean
  assistReturnTo?: string
  requestedSuggestionId?: string | null
  requestedSuggestionRevision?: string | null
  requestedMaterialKind?: string | null
}) {
  const visible = useContext(WorkPageVisible)
  const [providedOpen,setProvidedOpen] = useState(false)
  const [preparation, setPreparation] = useState<PreparationView | null>(null)
  const [currentWorkspace, setCurrentWorkspace] = useState(workspace)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [syncError, setSyncError] = useState<string>()
  const [receipt, setReceipt] = useState<string>()
  const [guidanceEpoch, setGuidanceEpoch] = useState(0)
  const [selectedAction, setSelectedAction] = useState<string>()
  const [material, setMaterial] = useState<{ reference: MaterialReference; label: string }>()
  const [evidenceAction, setEvidenceAction] = useState<string>()
  const [focusSourceEntry, setFocusSourceEntry] = useState(false)
  const [opening, setOpening] = useState<string>()
  const [proofSources,setProofSources] = useState(Boolean(requestedProofSources))
  useEffect(() => { setProofSources(Boolean(requestedProofSources)) },[project.project_id,requestedProofSources])
  const draftRef = useRef<PreparationDraft | undefined>(undefined)
  const [returnMaterial, setReturnMaterial] = useState<MaterialReference>()
  useTaskGuard(!proofSources && (busy || Boolean(syncError)))
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
  const suggestions = useMaterialSuggestions(project.project_id, visible && (!onProvidedMaterials || Boolean(requestedSuggestionId)) && !busy && mode === 'materials' && !material && !proofSources && !evidenceAction,
    `${currentWorkspace?.primary_task?.task_id}:${currentWorkspace?.primary_task?.stale_fingerprint}:${guidanceEpoch}`, requestedSuggestionId, requestedSuggestionRevision)
  const guidance = suggestions.guidance
  const materialReturnPath = (actionId?: string | null) => {
    const query = new URLSearchParams(assistReturnTo?.split('?')[1])
    query.set('project_id', project.project_id); query.set('materials', '1')
    if (actionId) query.set('action_id', actionId)
    if (requestedSuggestionId != null) query.set('suggestion_id', requestedSuggestionId)
    if (requestedSuggestionRevision != null) query.set('suggestion_revision', requestedSuggestionRevision)
    if (requestedMaterialKind) query.set('material_kind', requestedMaterialKind)
    return `/tests?${query}`
  }
  useEffect(() => {
    let active = true
    setLoading(true); setPreparation(null); setChoices({}); setMode(requestedIdentities ? 'identities' : 'materials'); setSyncError(undefined); setMaterial(undefined); setSelectedAction(undefined); setEvidenceAction(undefined)
    void Promise.all([preparationApi.get(project.project_id), preparationApi.draft(project.project_id)]).then(([value, draft]) => {
      if (!active) return
      if (value.project_id !== project.project_id) throw new ApiError('STATE_PRECONDITION', '材料所属应用不一致，请重新读取。')
      setPreparation(value); draftRef.current = draft
      const action = value.actions.find(item => requestedActionId ? item.action_id === requestedActionId : item.action_id === draft.action_id && item.action_revision === draft.action_revision)
      if (action) {
        setSelectedAction(action.action_id)
        if (!requestedActionId && draft.material) setMaterial({ reference: draft.material, label: '上次处理的材料' })
      }
    })
      .catch((error) => { if (active) onError(error as ApiError) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [project.project_id, onError, requestedActionId, requestedIdentities])

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
    setGuidanceEpoch(value => value + 1)
    setSyncError(undefined)
    return { preparation: next, workspace: nextWorkspace }
  }, [project.project_id, onStateChanged])
  const materialSync = useLiveRead(visible && !busy && !proofSources && !evidenceAction && mode === 'materials' ? project.project_id : undefined, async () => {
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
    if (requestedIdentities) onNavigate(materialReturnPath(requestedActionId))
    // 返回先恢复原位置；同步期间收起旧的下一步许可，但不阻挡回看材料。
    setMode('materials'); if (materialRecording && recordingReturn.current) setMaterial(recordingReturn.current); setMaterialRecording(undefined)
    setSyncError('正在更新材料和下一步状态…')
    try { await reload() } catch (error) { if (alive.current) { setSyncError('材料尚未更新，请刷新后继续。'); onError(error as ApiError) } }
  }
  const refresh = async () => {
    setBusy(true)
    try { await reload() } catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) setBusy(false) }
  }
  const providedControl = (updated:()=>Promise<unknown> = refresh) => onProvidedMaterials ? <ProvidedMaterialPreparation projectId={project.project_id} onChanged={updated} prepared={Boolean(preparation?.preparation_complete) && !materialSync.retrying} currentPreparation={preparation ?? undefined} outdated={materialSync.retrying} onContinue={()=>onNavigate('/tests')} open={providedOpen} onOpenChange={setProvidedOpen}/> : undefined
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
    if (busy) return
    setBusy(true); setOpening('正在核对下一步准备')
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
          setOpening('正在准备测试账号')
          const created = await testIdentitiesApi.create(project.project_id, slot.requirement.actor_id, slot.requirement.actor_revision,
            `${slot.actor_display_name}账号 ${slot.requirement.ordinal}`)
          identityId = created.identity_id
          // 创建已经是完成的事实；同步失败时留待刷新，不重复创建或继续使用旧任务。
          const updated = await reload()
          if (!updated || !alive.current) return
          const nextTask = updated.workspace.primary_task
          if (nextTask?.task_kind !== 'PREPARE_TEST_IDENTITY' || nextTask.identity_slot_id !== task.identity_slot_id || nextTask.test_identity_id !== identityId || !nextTask.can_execute) return
        }
        setOpening('正在打开测试登录')
        const session = await testIdentitiesApi.startPreparation(identityId)
        if (!alive.current) return
        setLogin(session); setMode('identities'); setOpening(undefined)
        await reload()
      } else {
        setRecordingTask(task); setMode('recording')
      }
    } catch (error) { if (alive.current) onError(error as ApiError) }
    finally { if (alive.current) { setBusy(false); setOpening(undefined) } }
  }

  const openMaterial = async (reference: MaterialReference, label: string) => {
    if (busy) return
    setFocusSourceEntry(false)
    setBusy(true); setOpening(`正在打开${label}`)
    try {
      const draft = draftRef.current ?? await preparationApi.draft(project.project_id)
      if (draft.pending_operation_id) { setMaterial({ reference: draft.material!, label: '上次处理的材料' }); return }
      draftRef.current = await preparationApi.saveDraft(project.project_id, { ...draft, action_id: reference.action_id,
        action_revision: reference.action_revision, material: reference, candidate_recording_id: null, base_fingerprint: null, pending_operation_id: null })
      setMaterial({ reference, label })
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false); setOpening(undefined) }
  }
  const closeMaterial = async () => {
    if (!material) return
    // 返回位置先显示，草稿写回与材料同步继续进行；未确认前不放行旧的下一步。
    setReturnMaterial(material.reference); setSelectedAction(material.reference.action_id); setMaterial(undefined)
    setBusy(true); setSyncError('正在保存准备位置并更新材料…')
    let positionSaved = true
    requestAnimationFrame(() => document.querySelector<HTMLButtonElement>(`[data-material-key="${material.reference.kind}:${material.reference.member_id ?? ''}"]`)?.focus())
    try {
      const draft = draftRef.current ?? await preparationApi.draft(project.project_id)
      if (!draft.pending_operation_id) draftRef.current = await preparationApi.saveDraft(project.project_id, { ...draft, material: null,
        candidate_recording_id: null, base_fingerprint: null, action_id: null, action_revision: null })
    } catch (error) { positionSaved = false; onError(error as ApiError) }
    finally {
      try { await reload() } catch (error) { onError(error as ApiError) }
      if (!positionSaved) setSyncError('返回位置尚未保存，请刷新后继续；原操作定位仍保留。')
      setBusy(false)
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
  if (opening) return <EditorialPage width="summary"><EditorialHeader eyebrow={project.name || '当前应用'} title={opening}/><LoadingState>正在核对当前材料并保存准备位置，完成后会自动进入。</LoadingState><TaskActionBar back={{label:'返回当前工作',onClick:()=>onNavigate('/workspace')}}/></EditorialPage>
  if (proofSources) return <ProofSourcesPanel projectId={project.project_id} requestedSource={requestedProofSource} providedPreparation={updated=>providedControl(async()=>{await updated();await refresh()})} providedMaterials={Boolean(onProvidedMaterials)} onChanged={refresh} onNavigate={onNavigate} onBack={() => { setProofSources(false); if (requestedProofSources) onNavigate(materialReturnPath(requestedActionId)) }}/>
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
  if (loading) return <EditorialPage width="summary"><LoadingState>正在读取检查准备材料…</LoadingState><TaskActionBar back={{label:'返回当前工作',onClick:()=>onNavigate('/workspace')}}/></EditorialPage>
  if (requestedActionId && preparation && !preparation.actions.some(item=>item.action_id===requestedActionId)) return <EditorialPage width="summary"><EditorialHeader title="这项业务的材料已不在当前范围"/><p>原链接指向的动作已经变化，未替换成另一项业务。</p><TaskActionBar back={{label:'返回当前工作',onClick:()=>onNavigate('/workspace')}} primary={{label:'核对权限要求',onClick:()=>onNavigate('/permissions')}}/></EditorialPage>
  if (!preparation) return <EditorialPage width="summary"><EditorialHeader eyebrow={project.name || '当前应用'} title="暂时无法读取检查材料"/><p>尚未取得当前材料事实，重新读取后再继续。</p><TaskActionBar back={{label:'返回当前工作',onClick:()=>onNavigate('/workspace')}} primary={{label:'重新读取材料',loading:busy,onClick:()=>void refresh()}}/></EditorialPage>
  const task = currentWorkspace?.primary_task
  const nextAction = guidance?.state === 'CURRENT' && guidance.next_action?.task_id === task?.task_id ? guidance.next_action : undefined
  const chosenActionId = preparation?.actions.find(action => action.action_id === selectedAction)?.action_id
    ?? preparation?.actions.find(action => action.action_id === task?.business_action_id)?.action_id ?? preparation?.actions[0]?.action_id
  const actorName = (id: string) => currentWorkspace?.actors.find((item) => item.actor_id === id)?.display_name ?? '业务主体'
  const taskStage: Record<string, number> = { PREPARE_TEST_IDENTITY: 0, DEMONSTRATE_ACTION: 1, PREPARE_ACTION_RESOURCE: 2, COMPLETE_EFFECT_EVIDENCE: 3, COMPLETE_RECOVERY: 4 }
  const currentStage = task?.task_kind === 'REVIEW_RECORDING' ? task.recording_purpose === 'OBSERVATION' ? 3 : task.recording_purpose === 'RECOVERY' ? 4 : 1 : task ? taskStage[task.task_kind] : undefined
  const guidedProof = nextAction?.kind==='REVIEW_REFERENCE_RECOVERY' ? nextAction : task?.task_kind === 'COMPLETE_EFFECT_EVIDENCE' && nextAction?.kind !== task.task_kind ? nextAction : undefined
  const assistQuery = new URLSearchParams(materialReturnPath(chosenActionId).split('?')[1])
  const entries = materialSuggestionEntries(suggestions.view)
  const unbound = entries.filter(entry => entry.view.resolved_target.state !== 'APPROVED' || !preparation.actions.some(action => action.action_id === entry.view.resolved_target.action_id && action.action_revision === entry.view.resolved_target.action_revision))
  const readSuggestions = async () => {
    if (requestedSuggestionId != null && requestedSuggestionRevision != null) {
      const query = new URLSearchParams(assistQuery); query.delete('suggestion_revision')
      onNavigate(`/tests?${query}`)
    } else await suggestions.read()
  }
  const primaryButton = task && task.task_kind !== 'SELECT_ALLOW_CONTROL' ? guidedProof ? <Button type="primary" loading={busy} disabled={Boolean(syncError) || materialSync.retrying || !task.can_execute} onClick={() => onNavigate(guidedProof.gui_url.slice(1))}>核对证明来源</Button> : <Button type="primary" loading={busy} disabled={Boolean(syncError) || materialSync.retrying || !task.can_execute} onClick={() => void proceed()}>
    {task.task_kind === 'PREPARE_TEST_IDENTITY' ? task.test_identity_id ? '打开登录浏览器' : '创建账号并登录' : task.route === '/tests' && currentStage !== undefined ? '继续准备这项材料' : task.action_label ?? '前往处理'}
  </Button> : null
  return <EditorialPage label="检查材料" width="summary">
    <EditorialHeader eyebrow={project.name || '当前应用'} title="检查准备"/>
    {providedControl()}
    {guidance?.state === 'CURRENT' && guidance.progress && !materialSync.retrying && <PreparationProgress progress={guidance.progress}
      currentActionId={task?.business_action_id} selectedActionId={chosenActionId} onSelect={id => void selectAction(id)}/>}
    {!onProvidedMaterials && <AgentAssistEntry aside projectId={project.project_id} contextKey={`materials:${chosenActionId ?? ''}:${requestedSuggestionId ?? ''}:${requestedSuggestionRevision ?? ''}`}
      title="整理检查需要的材料" description="让原来的 Agent 核对已有材料，并说明缺少的账号、操作、测试资源、证明或恢复方式怎样准备。"
      heading={<div className="materials-context">
        {!!preparation.actions.length && <><label htmlFor="materials-action">当前业务动作</label><Select id="materials-action" className="materials-action-picker" aria-label="选择业务动作" disabled={busy}
          value={chosenActionId} onChange={id => void selectAction(id)}
          options={preparation.actions.map(action => ({ value: action.action_id, label: action.display_name }))}/></>}
        {suggestions.view && <span className="editorial-muted">材料建议 · 修订 {suggestions.view.suggestion.revision}</span>}
      </div>}
      actions={<Button loading={suggestions.loading} onClick={() => void readSuggestions()}>读取建议</Button>}
      returnTo={`/tests?${assistQuery}`}
      onNavigate={onNavigate}
      loadContext={async () => {
        const value = await proofSourcesApi.context(project.project_id)
        const context = value.suggestion_context
        if (context?.state !== 'CURRENT' || !context.basis_id) throw new Error('suggestion context unavailable')
        const view = requestedSuggestionId != null ? await preparationSuggestionsApi.show(project.project_id, requestedSuggestionId, requestedSuggestionRevision) : context.latest
        if (view && view.suggestion.project_id !== project.project_id) throw new Error('suggestion project mismatch')
        if (view && view.current_basis_id !== context.basis_id) throw new Error('suggestion context changed')
        return { projectId:value.project_id,revisionKey:`${context.basis_id}:${view?.suggestion.suggestion_id}:${view?.suggestion.revision}:${view?.latest_revision}`,
          requestText:[`请协助整理界鉴项目 ${value.project_id} 的检查材料。`,
            chosenActionId ? `本次动作：${chosenActionId}。` : '先检查当前规则及全部动作所需材料。',
            '调用 jiejian_preparation_context 读取最新材料、可用接口和缺口。逐项核对真实账号、动作录制、测试资源、结果证明、恢复方式，保留可用材料。',
            '没有运行环境或实际数据时，先给出建立办法；有应用开发授权后才协助补齐，再由界鉴核对。不要编造账号、资源、录制或证据。',
            '先执行你已经获授权且工具支持的材料准备，例如保存来源候选、提交已获读取授权的预检查；不要只留下建议让我逐项重做。不能自动处理的部分，说明具体缺少的账号、文件或决定。再按 suggestion_context.input_schema 通过 jiejian_preparation_suggestion_save 保存五类有限建议。代码位置使用已核验候选引用；其他办法明确标为假设。规则尚未批准时保留候选局部引用。',
            view ? `当前查看建议 ${view.suggestion.suggestion_id} 的修订 ${view.suggestion.revision}。先调用 jiejian_preparation_suggestion_show 核对该建议最新修订，再决定如何更新。` : '当前尚无指定建议，保存后返回建议的精确查看入口。',
            '登录、规则批准、读取范围和来源采用由用户完成。建议不能把实际材料改成已齐备。',
            `复制时的建议依据：${context.basis_id}；保存前重新读取。未知写入结果只调用 jiejian_preparation_suggestion_receipt 查询原 operation_id，不重复提交。`].join('\n') }
      }}/>}
    {suggestions.error && <Alert className="flow-feedback" type="warning" showIcon message={suggestions.error} action={requestedSuggestionId != null && <Button onClick={() => { const query = new URLSearchParams(assistQuery); query.delete('suggestion_id'); query.delete('suggestion_revision'); onNavigate(`/tests?${query}`) }}>返回当前材料</Button>}/>}
    {!suggestions.error && suggestions.context && suggestions.context.state !== 'CURRENT' && <Alert className="flow-feedback" type="warning" showIcon message={suggestions.context.note ?? '准备依据正在变化，请重新读取材料建议。'}/>}
    {!suggestions.error && suggestions.context?.state === 'CURRENT' && suggestions.view && suggestions.view.state !== 'CURRENT' && <Alert className="flow-feedback" type="warning" showIcon message={suggestions.view.state === 'SUPERSEDED' ? '这份建议已有新修订，可用“读取建议”查看。' : suggestions.view.state === 'PARTIAL' ? `${suggestions.view.current_count} 项建议可沿用，${suggestions.view.review_count} 项需要核对；原因列在对应材料中。` : '这份建议的依据需要重新核对，请查看各项原因。真实材料的准备状态仍以当前核对结果为准。'}/>}
    {suggestions.view && suggestions.view.suggestion.content.unresolved_questions.length > 0 && <details className="material-dependencies"><summary>整理时还未确定的事项</summary><ul>{suggestions.view.suggestion.content.unresolved_questions.map((question, index) => <li key={index}>{question}</li>)}</ul></details>}
    {!preparation.actions.length && (receipt || syncError) && <TaskReceipt message={receipt ?? '正在核对准备材料'} pending={syncError} onRetry={syncError ? () => void refresh() : undefined}/>}
    {materialSync.retrying && <Alert className="flow-feedback" type="warning" message="材料状态暂未同步" description={materialSync.stopped ? '当前读取未通过校验，请重新读取后再继续。' : '以下保留上次读取的内容，界鉴正在重新同步。继续操作前会再次核对。'} />}
    {!preparation?.actions.length && !unbound.length && <Empty description={suggestions.loaded ? '尚未确认业务动作。可以先让 Agent 整理规则与材料建立办法。' : '正在读取材料建议…'} />}
    <UnboundMaterialSuggestions entries={unbound} allEntries={entries} returnKind={requestedMaterialKind} projectId={project.project_id} onNavigate={onNavigate}/>
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
        <MaterialOverview feedback={(receipt || syncError) && <TaskReceipt message={receipt ?? '正在核对准备材料'} pending={syncError} onRetry={syncError ? () => void refresh() : undefined}/>} action={action} currentStage={current ? currentStage : undefined}
          suggestions={entries.filter(entry => entry.view.resolved_target.state === 'APPROVED' && entry.view.resolved_target.action_id === action.action_id && entry.view.resolved_target.action_revision === action.action_revision)} allSuggestions={entries}
          advice={guidance?.state === 'CURRENT' && !materialSync.retrying ? guidance.materials : undefined}
          outdated={materialSync.retrying}
          showFocus={!(current && task?.task_kind === 'SELECT_ALLOW_CONTROL')}
          effectName={id => business?.effect_catalog.find(effect => effect.effect_id === id)?.business_label ?? '已确认的业务结果'}
          taskTitle={syncError ? '材料已保存，正在同步下一步' : current ? nextAction?.title ?? task?.title : undefined} taskWhy={syncError ? '正在读取最新任务，不需要重新准备已经保存的材料。' : current ? nextAction?.reason ?? task?.why_now : undefined}
          primary={current ? primaryButton : <Button type="primary" onClick={() => onNavigate('/tests')}>核对检查条件</Button>}
          onProofSources={() => setProofSources(true)}
          fileEffectIds={business?.effect_catalog.filter(effect=>effect.effect_kind==='FILE_CONTENT_DELIVERY').map(effect=>effect.effect_id)}
          renderFileProof={business?.effect_catalog.length ? close=><ProofSourcesPanel key={`${action.action_id}:${action.action_revision}`} embedded actionId={action.action_id} providedMaterials={Boolean(onProvidedMaterials)} projectId={project.project_id} onBack={close} onChanged={refresh} onNavigate={onNavigate}/> : undefined}
          onIdentity={() => { setLogin(undefined); setMode('identities') }} onMaterial={(reference, label) => void openMaterial(reference, label)} returnKind={returnMaterial?.action_id === action.action_id ? returnMaterial.kind : requestedMaterialKind ?? undefined}>
          <h3>已确认的权限</h3>{action.permissions.map(permission => <p key={permission.intent_id}>{permissionLabel(permission.intent_id ?? '')}</p>)}
        </MaterialOverview>
      </section>
    })}
    <TaskActionBar back={{ label: '返回检查总览', onClick: () => onNavigate('/tests'), disabled: busy }} refresh={{ label: '刷新准备材料', onClick: () => void refresh(), loading: busy }} />
  </EditorialPage>
}
