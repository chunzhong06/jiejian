// 动作级检查准备：展示现场材料，操作顺序与定位只消费最新 Workspace 主任务。
import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Empty, Radio, Space, Spin, Typography } from 'antd'
import { ApiError } from '../../api/http'
import type { ProjectDto } from '../../api/projects'
import { preparationApi, type AllowControlRequirement, type PreparationItem, type PreparationView } from '../../api/preparation'
import { testIdentitiesApi, type IdentityPreparationDto } from '../../api/testIdentities'
import type { PrimaryTaskDto, WorkspaceViewDto } from '../../api/workspace'
import { AssistantPanel } from '../../components/AssistantPanel'
import { EditorialHeader, EditorialPage, FlowSpine, type FlowStep } from '../../shared/ui/Editorial'
import { taskDestination } from '../../app/taskDestination'
import { TaskActionBar } from '../../components/TaskActionBar'
import { TestIdentityPage } from '../identities/TestIdentityPage'
import { RecordingPage } from '../recording/RecordingPage'
import { TaskReceipt, useTaskGuard } from '../../components/TaskContinuity'

const states = {
  SATISFIED: ['已准备', 'green'], NEEDS_USER: ['需要准备', 'orange'],
  STALE: ['需要更新', 'orange'], BLOCKED: ['需要先确认', 'red'], NOT_REQUIRED: ['不需要', 'default'],
} as const
function Material({ name, item }: { name: string; item: PreparationItem }) {
  const [label] = states[item.status]
  return <div className="preparation-list-item"><Typography.Text>{name}</Typography.Text><span>{label}</span></div>
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
  const [preparation, setPreparation] = useState<PreparationView | null>(null)
  const [currentWorkspace, setCurrentWorkspace] = useState(workspace)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [syncError, setSyncError] = useState<string>()
  const [receipt, setReceipt] = useState<string>()
  useTaskGuard(busy || Boolean(syncError))
  const feedback = (message: string) => { setReceipt(message); onFeedback?.(message) }
  const [mode, setMode] = useState<'materials' | 'identities' | 'recording'>('materials')
  const [recordingTask, setRecordingTask] = useState<PrimaryTaskDto>()
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
    setLoading(true); setPreparation(null); setChoices({}); setMode('materials'); setSyncError(undefined)
    void preparationApi.get(project.project_id).then((value) => { if (active) setPreparation(value) })
      .catch((error) => { if (active) onError(error as ApiError) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [project.project_id, onError])

  // 写动作后先重读页面材料，再同步 Workspace；失败保留已完成动作并阻止使用旧任务。
  const reload = useCallback(async () => {
    const next = await preparationApi.get(project.project_id)
    if (!alive.current || projectRef.current !== project.project_id) return
    setPreparation(next)
    const nextWorkspace = await onStateChanged().catch(() => undefined)
    if (!alive.current || projectRef.current !== project.project_id) return
    if (!nextWorkspace) { setSyncError('材料已刷新，但下一步尚未同步，请重试刷新。'); return }
    setCurrentWorkspace(nextWorkspace)
    setSyncError(undefined)
    return { preparation: next, workspace: nextWorkspace }
  }, [project.project_id, onStateChanged])
  const syncChild = async () => (await reload())?.workspace
  const showMaterials = async () => {
    try { await reload(); if (alive.current) setMode('materials') } catch (error) { if (alive.current) onError(error as ApiError) }
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

  if (mode === 'identities') return <TestIdentityPage key={`${project.project_id}:${login?.preparation_id ?? 'accounts'}`} project={project} initialPreparation={login}
    onError={onError} onBack={() => void showMaterials()} onContinuePreparation={showMaterials} onStateChanged={syncChild} onPrepared={() => onFeedback?.('登录状态已保存，已有的其他材料继续保留。')} />
  if (mode === 'recording' && recordingTask) return <RecordingPage key={`${project.project_id}:${recordingTask.task_id}`} project={project} task={recordingTask}
    effectName={currentWorkspace?.actions.find((item) => item.action_id === recordingTask.business_action_id)?.effect_catalog.find((item) => item.effect_id === recordingTask.effect_id)?.business_label}
    onError={onError} onBack={() => void showMaterials()} onContinuePreparation={showMaterials} onStateChanged={syncChild} />
  if (loading) return <EditorialPage><Spin />正在读取检查准备材料…</EditorialPage>
  const task = currentWorkspace?.primary_task
  const actorName = (id: string) => currentWorkspace?.actors.find((item) => item.actor_id === id)?.display_name ?? '业务主体'
  const taskStage: Record<string, number> = { PREPARE_TEST_IDENTITY: 0, DEMONSTRATE_ACTION: 1, PREPARE_ACTION_RESOURCE: 2, COMPLETE_EFFECT_EVIDENCE: 3, COMPLETE_RECOVERY: 4 }
  const currentStage = task?.task_kind === 'REVIEW_RECORDING' ? task.recording_purpose === 'OBSERVATION' ? 3 : task.recording_purpose === 'RECOVERY' ? 4 : 1 : task ? taskStage[task.task_kind] : undefined
  const providedAvailable = Boolean(onProvidedMaterials && !preparation?.preparation_complete && task?.route === '/tests' && currentStage !== undefined)
  const primaryButton = task && task.task_kind !== 'SELECT_ALLOW_CONTROL' ? <Button type={providedAvailable ? 'default' : 'primary'} loading={busy} disabled={Boolean(syncError) || !task.can_execute} onClick={() => void proceed()}>
    {task.task_kind === 'PREPARE_TEST_IDENTITY' ? task.test_identity_id ? '打开登录浏览器' : '创建账号并登录' : task.route === '/tests' && currentStage !== undefined ? '继续准备这项材料' : '前往处理'}
  </Button> : null
  return <EditorialPage label="当前准备缺口">
    <EditorialHeader eyebrow="当前工作 / 检查准备" title="继续准备本轮检查"><p className="editorial-muted">完成眼前这一项，界鉴会根据最新材料衔接下一步。</p></EditorialHeader>
    {(receipt || syncError) && <TaskReceipt message={receipt ?? '正在核对准备材料'} pending={syncError} onRetry={syncError ? () => void refresh() : undefined}/>}
    {preparation?.preparation_complete && <p role="status">测试材料已准备完成，请返回检查总览核对执行条件。</p>}
    {task && currentStage === undefined && task.task_kind !== 'SELECT_ALLOW_CONTROL' && <section className="task-focus"><p>{task.user_responsibility}</p>{primaryButton}</section>}
    {!preparation?.actions.length && <Empty description="请先在业务边界中确认动作和权限" />}
    {preparation?.actions.map((action) => {
      const business = currentWorkspace?.actions.find((item) => item.action_id === action.action_id)
      const slots = action.identity_requirements.slots
      const slotName = (id: string) => { const slot = slots.find((item) => item.requirement.slot_id === id); return slot ? `${slot.actor_display_name}账号 ${slot.requirement.ordinal}` : '资源所有者账号' }
      const current = task?.business_action_id === action.action_id
      const permissionLabel = (id: string) => {
        const permission = action.permissions.find((item) => item.intent_id === id)
        if (!permission) return '当前已确认权限'
        const owner = permission.relation === 'OWNS' ? '自己' : permission.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `另一个${actorName(permission.resource_owner_actor_id)}账号` : actorName(permission.resource_owner_actor_id)
        const effects = permission.protected_effect_ids.map((effectId) => business?.effect_catalog.find((effect) => effect.effect_id === effectId)?.business_label ?? '已确认的业务结果').join('、')
        return `${actorName(permission.subject_actor_id)}对${owner}拥有的资源，${permission.expectation === 'ALLOW' ? '允许' : '拒绝'}“${action.display_name}”；业务结果：${effects}`
      }
      const groups = [
        { key: 'identity', title: '真实账号', items: slots.map((slot) => ({ name: slotName(slot.requirement.slot_id), item: slot })) },
        { key: 'execution', title: '业务动作', items: [{ name: '正常完成一次业务操作', item: action.execution }] },
        { key: 'resource', title: '测试资源', items: action.resources.map((item) => ({ name: `${slotName(item.owner_slot_id)}拥有的资源`, item })) },
        { key: 'proof', title: '结果证明', items: action.effect_evidence.map((item) => ({ name: business?.effect_catalog.find((effect) => effect.effect_id === item.effect_id)?.business_label ?? '已确认的业务结果', item })) },
        { key: 'recovery', title: '恢复现场', items: [{ name: action.recovery.status === 'NOT_REQUIRED' ? '只读动作不需要恢复' : '恢复本次操作改变的状态', item: action.recovery }] },
      ]
      const steps: FlowStep[] = groups.map((group, index) => ({ key: group.key,
        title: group.items.length > 0 && group.items.every(({item}) => item.status === 'NOT_REQUIRED') ? `${group.title} · 无需准备` : group.items.length > 0 && group.items.every(({item}) => ['SATISFIED','NOT_REQUIRED'].includes(item.status)) ? `${group.title} · 已准备` : current && currentStage === index ? `${group.title} · 当前处理` : `随后核对${group.title}`,
        state: current && currentStage === index ? 'current' : group.items.length > 0 && group.items.every(({item}) => ['SATISFIED','NOT_REQUIRED'].includes(item.status)) ? 'complete' : 'future',
        detail: <><p>{task?.user_responsibility}</p>{index === 0 && <p className="editorial-muted">保存登录状态不等于确认实际执行身份；实际身份在检查中核验。</p>}
          {group.items.map(({name,item},i) => <Material key={i} name={name} item={item} />)}
          {index === 3 && <p>必须独立确认上述业务结果；页面回应不能替代结果证明。当前无法取得决定性事实时，界鉴不会宣布安全。</p>}
          {index === 1 && <p>同一种业务动作复用已有执行方法；本次只补当前缺失的演示或账号/资源。</p>}
          {providedAvailable && <><p>这个项目已提供可导入的账号、动作、资源和证明材料；导入会核对当前权限，保持已有有效材料。</p><Button type="primary" loading={busy} disabled={Boolean(syncError) || !task?.can_execute} onClick={() => void installProvidedMaterials()}>使用已提供的测试材料</Button></>}
          <div className="task-focus-actions">{primaryButton}</div><p className="task-next"><span>完成后</span>{task?.system_will_do}</p></>,
      }))
      if (!current) return <details key={action.action_id} className="preparation-other-actions"><summary>{action.display_name} · 查看已有材料</summary><FlowSpine label={`${action.display_name}的准备过程`} steps={steps} />{groups.map(group => <div key={group.key}><h3>{group.title}</h3>{group.items.map(({name,item},i) => <Material key={i} name={name} item={item}/>)}</div>)}</details>
      const currentStep = steps.find(step => step.state === 'current')
      const retained = groups.filter(group => group.items.some(({item}) => item.status === 'SATISFIED') && group.items.every(({item}) => ['SATISFIED','NOT_REQUIRED'].includes(item.status)))
      return <section key={action.action_id} className="preparation-action" aria-label={action.display_name}>
        <div className="preparation-heading"><h2>{action.display_name}</h2><details><summary>回看已确认的权限</summary>{action.permissions.map((permission) => <p key={permission.intent_id}>{permissionLabel(permission.intent_id ?? '')}</p>)}</details></div>
        <p className="preparation-progress editorial-muted">{retained.length ? `${retained.length} 类有效材料继续保留。` : '按当前缺口逐项准备。'}后续要求可在下方展开查看。</p>
        {current && task?.task_kind === 'SELECT_ALLOW_CONTROL' && action.assurance_contract.allow_controls.filter((control) => !control.resolved_allow_permission && control.candidate_allow_permissions.length > 1).map((control) => <section key={control.selection_fingerprint} className="task-focus" aria-label="选择正常对照">
          <h3>选择正常对照</h3><p>{permissionLabel(control.deny_permission.intent_id)}</p><p>以下操作均符合正常对照条件。请选择本次用来确认业务功能正常的一项，现有权限规则保持不变。</p>
          <Radio.Group aria-label="正常对照候选" value={choices[control.selection_fingerprint]} disabled={busy || !task.can_execute || Boolean(syncError)} onChange={(event) => setChoices((values) => ({ ...values, [control.selection_fingerprint]: event.target.value }))}>
            <Space direction="vertical">{control.candidate_allow_permissions.map((candidate) => <Radio value={candidate.intent_id} key={candidate.intent_id}>{permissionLabel(candidate.intent_id)}</Radio>)}</Space>
          </Radio.Group><div><Button type="primary" loading={busy} disabled={!choices[control.selection_fingerprint] || !task.can_execute || Boolean(syncError)} onClick={() => void selectControl(control)}>确认正常对照</Button></div>
        </section>)}
        {currentStep && <section className="task-focus preparation-current" aria-label="当前需要处理的材料"><p className="editorial-eyebrow">当前需要你处理</p><h2>{task?.title}</h2><p className="editorial-muted">{task?.why_now}</p>{currentStep.detail}</section>}
        {retained.length > 0 && <details className="preparation-saved"><summary>已保存的材料<span>{retained.length} 类材料继续保留</span></summary><div className="preparation-retained" aria-label="仍然有效的材料">{retained.map(group => <span key={group.key}><strong aria-hidden="true">✓</strong>{group.title}已保留</span>)}</div>{retained.map(group => <div key={group.key}><h3>{group.title}</h3>{group.items.map(({name,item},i) => <Material key={i} name={name} item={item}/>)}</div>)}</details>}
        <details className="preparation-remaining"><summary>查看全部测试条件</summary><FlowSpine label={`${action.display_name}的准备过程`} steps={steps.map(step => ({...step,detail:undefined}))} />{groups.map(group => <div key={group.key}><h3>{group.title}</h3>{group.items.map(({name,item},i) => <Material key={i} name={name} item={item}/>)}</div>)}</details>
        <details className="preparation-remaining"><summary>解释这项准备要求</summary><AssistantPanel projectId={project.project_id} surface="preparation-explanation" focus={{ business_action_id: action.action_id }} title="理解这项动作的准备要求" actionLabel="解释准备缺口" /></details>
      </section>
    })}
    <details><summary>其他测试账号</summary><Button disabled={busy} onClick={() => { setLogin(undefined); setMode('identities') }}>管理测试账号</Button></details>
    <TaskActionBar back={{ label: '返回检查总览', onClick: () => onNavigate('/tests'), disabled: busy }} refresh={{ label: '刷新准备材料', onClick: () => void refresh(), loading: busy }} />
  </EditorialPage>
}
