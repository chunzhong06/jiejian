// 动作级检查准备：展示现场材料，操作顺序与定位只消费最新 Workspace 主任务。
import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Empty, Space, Spin, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import type { ProjectDto } from '../../api/projects'
import { preparationApi, type PreparationItem, type PreparationView } from '../../api/preparation'
import { testIdentitiesApi, type IdentityPreparationDto } from '../../api/testIdentities'
import type { PrimaryTaskDto, WorkspaceViewDto } from '../../api/workspace'
import { AssistantPanel } from '../../components/AssistantPanel'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { TaskActionBar } from '../../components/TaskActionBar'
import { TestIdentityPage } from '../identities/TestIdentityPage'
import { RecordingPage } from '../recording/RecordingPage'

const states = {
  SATISFIED: ['已准备', 'green'], NEEDS_USER: ['需要准备', 'orange'],
  STALE: ['需要更新', 'orange'], BLOCKED: ['需要先确认', 'red'], NOT_REQUIRED: ['不需要', 'default'],
} as const
function Material({ name, item }: { name: string; item: PreparationItem }) {
  const [label, color] = states[item.status]
  return <div className="preparation-list-item"><Typography.Text>{name}</Typography.Text><Tag color={color}>{label}</Tag></div>
}

export function PreparationPage({ project, workspace, onStateChanged, onError, onNavigate }: {
  project: ProjectDto
  workspace: WorkspaceViewDto | null
  onStateChanged: () => Promise<WorkspaceViewDto | undefined>
  onError: (error: ApiError) => void
  onNavigate: (path: string) => void
}) {
  const [preparation, setPreparation] = useState<PreparationView | null>(null)
  const [currentWorkspace, setCurrentWorkspace] = useState(workspace)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [syncError, setSyncError] = useState<string>()
  const [mode, setMode] = useState<'materials' | 'identities' | 'recording'>('materials')
  const [recordingTask, setRecordingTask] = useState<PrimaryTaskDto>()
  const [login, setLogin] = useState<IdentityPreparationDto>()
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => { if (workspace?.project.project_id === project.project_id) setCurrentWorkspace(workspace) }, [workspace, project.project_id])
  useEffect(() => {
    let active = true
    void preparationApi.get(project.project_id).then((value) => { if (active) setPreparation(value) })
      .catch((error) => { if (active) onError(error as ApiError) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [project.project_id, onError])

  // 写动作后先重读页面材料，再同步 Workspace；失败保留已完成动作并阻止使用旧任务。
  const reload = useCallback(async () => {
    const next = await preparationApi.get(project.project_id)
    if (!alive.current) return
    setPreparation(next)
    const nextWorkspace = await onStateChanged()
    if (!alive.current) return
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
  const proceed = async () => {
    setBusy(true)
    try {
      const fresh = await reload()
      const task = fresh?.workspace.primary_task
      if (!fresh || !task || !alive.current) return
      if (task.route !== '/tests') { onNavigate(task.route); return }
      if (!task.can_execute) return
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
    onError={onError} onBack={() => void showMaterials()} onContinuePreparation={showMaterials} onStateChanged={syncChild} />
  if (mode === 'recording' && recordingTask) return <RecordingPage key={`${project.project_id}:${recordingTask.task_id}`} project={project} task={recordingTask}
    effectName={currentWorkspace?.actions.find((item) => item.action_id === recordingTask.business_action_id)?.effect_catalog.find((item) => item.effect_id === recordingTask.effect_id)?.business_label}
    onError={onError} onBack={() => void showMaterials()} onContinuePreparation={showMaterials} onStateChanged={syncChild} />
  if (loading) return <Card><Spin /> 正在读取检查准备材料…</Card>
  const task = currentWorkspace?.primary_task
  const actorName = (id: string) => currentWorkspace?.actors.find((item) => item.actor_id === id)?.display_name ?? '业务主体'
  return <Space direction="vertical" size="large" style={{ width: '100%' }}>
    <PageTaskHeader title="检查准备" description="按当前权限要求，准备真实账号、业务演示和结果证明。" status={preparation?.preparation_complete ? '材料已准备' : '材料准备中'} />
    <Alert showIcon type={preparation?.preparation_complete ? 'success' : 'info'} message={preparation?.preparation_complete ? '测试材料已准备完成；当前尚不支持正式权限检查' : '这里只准备检查材料，不运行正式权限检查'} />
    {syncError && <Alert type="warning" showIcon message={syncError} />}
    <Button disabled={busy} onClick={() => { setLogin(undefined); setMode('identities') }}>管理测试账号</Button>
    {task && <Card title={task.title}><Typography.Paragraph>{task.why_now}</Typography.Paragraph><Typography.Paragraph>{task.user_responsibility}</Typography.Paragraph>
      {task.route === '/tests' && !task.can_execute && <Button onClick={() => onNavigate('/permissions')}>查看业务边界</Button>}
    </Card>}
    {!preparation?.actions.length && <Empty description="请先在业务边界中确认动作和权限" />}
    {preparation?.actions.map((action) => {
      const business = currentWorkspace?.actions.find((item) => item.action_id === action.action_id)
      const slots = action.identity_requirements.slots
      const slotName = (id: string) => { const slot = slots.find((item) => item.requirement.slot_id === id); return slot ? `${slot.actor_display_name}账号 ${slot.requirement.ordinal}` : '资源所有者账号' }
      return <Card key={action.action_id} title={action.display_name} extra={<Tag color={action.preparation_complete ? 'green' : 'orange'}>{action.preparation_complete ? '材料已准备' : '需要准备'}</Tag>}>
        <Typography.Title level={5}>当前权限考题</Typography.Title>
        {business?.current_permissions.map((permission) => <Typography.Paragraph key={permission.intent_id}>
          {actorName(permission.subject_actor_id)}对{permission.relation === 'OWNS' ? '自己' : permission.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? '同类主体的其他账号' : actorName(permission.resource_owner_actor_id)}拥有的资源，{permission.expectation === 'ALLOW' ? '应当允许' : '应当拒绝'}“{action.display_name}”。
          受保护的业务结果：{permission.protected_effect_ids.map((id) => business.effect_catalog.find((effect) => effect.effect_id === id)?.business_label ?? '已确认的业务结果').join('、')}。
        </Typography.Paragraph>)}
        <Typography.Title level={5}>真实身份需求</Typography.Title>
        {slots.map((slot) => <Material key={slot.requirement.slot_id} name={slotName(slot.requirement.slot_id)} item={slot} />)}
        <Typography.Title level={5}>业务动作演示</Typography.Title><Material name="正常完成一次业务操作" item={action.execution} />
        <Typography.Title level={5}>具体测试资源</Typography.Title>
        {action.resources.map((item) => <Material key={item.owner_slot_id} name={`${slotName(item.owner_slot_id)}拥有的资源`} item={item} />)}
        <Typography.Title level={5}>业务结果证明</Typography.Title>
        {action.effect_evidence.map((item) => <Material key={item.effect_id} name={business?.effect_catalog.find((effect) => effect.effect_id === item.effect_id)?.business_label ?? '已确认的业务结果'} item={item} />)}
        <Typography.Title level={5}>恢复方式</Typography.Title><Material name={action.recovery.status === 'NOT_REQUIRED' ? '只读动作不需要恢复' : '恢复本次操作改变的状态'} item={action.recovery} />
        <AssistantPanel projectId={project.project_id} surface="preparation-explanation" focus={{ business_action_id: action.action_id }} title="理解这项动作的准备要求" actionLabel="解释准备缺口" />
      </Card>
    })}
    <TaskActionBar back={{ label: '返回工作台', onClick: () => onNavigate('/workspace'), disabled: busy }} refresh={{ label: '刷新准备材料', onClick: () => void refresh(), loading: busy }} primary={task ? {
      label: task.task_kind === 'PREPARE_TEST_IDENTITY' ? (task.test_identity_id ? '打开登录浏览器' : '创建账号并登录') : task.route === '/tests' ? '继续准备这项材料' : '前往处理',
      onClick: () => void proceed(), loading: busy, disabled: Boolean(syncError) || !task.can_execute,
    } : undefined} />
  </Space>
}
