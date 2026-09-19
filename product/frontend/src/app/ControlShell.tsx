/* 当前产品壳：只接入动作级 Workspace、应用接入、业务边界和明确不可用区域。 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Layout, Modal, Result } from 'antd'
import { HashRouter, useLocation, useNavigate } from 'react-router-dom'
import { experienceApi, type OfficialExperienceDto } from '../api/experience'
import { ApiError } from '../api/http'
import { mcpAccessApi, type MCPAccessView } from '../api/mcp'
import { projectsApi, type ProjectDto } from '../api/projects'
import { systemApi } from '../api/system'
import { DesktopModuleNavigation, MobileModuleNavigation } from '../components/ModuleNavigation'
import { ErrorRecovery } from '../components/ErrorRecovery'
import { AccessPage } from '../features/access/AccessPage'
import { CurrentTestsPage } from '../features/testing/CurrentTestsPage'
import { CheckHistoryPage } from '../features/testing/CheckHistoryPage'
import { ChangesPage } from '../features/changes/ChangesPage'
import { OfficialSamplePanel } from '../features/workspace/OfficialSamplePanel'
import { BusinessBoundaryPage } from '../features/boundaries/BusinessBoundaryPage'
import LLMSettingsDrawer from '../features/settings/LLMSettingsDrawer'
import { RuntimePage } from '../features/system/RuntimePage'
import { ToolsPage } from '../features/tools/ToolsPage'
import { WorkbenchContext, WorkbenchPage } from '../features/workspace/WorkbenchPage'
import { aiStatusLabel, AppHeader } from './AppHeader'
import { NotificationCenter, enqueueNotification, useNotificationExpiry, type NotificationItem } from './NotificationCenter'
import { normalizeRoute, type AppRoute } from './presentation'
import { useProjectWorkspace } from './useProjectWorkspace'
import { useSystemStatus } from './useSystemStatus'
import { useCheckActivity } from './useCheckActivity'
import { RetainedWorkPages } from './RetainedWorkPages'
import { TaskGuardContext, TaskJourney } from '../components/TaskContinuity'
import type { WorkspaceViewDto } from '../api/workspace'
import '../styles.css'

function MissingApplication({ onNavigate }: { onNavigate: () => void }) {
  return <Result status="info" title="先选择要维护的应用" subTitle="选择应用后才能查看这里的内容。" extra={<Button type="primary" onClick={onNavigate}>去应用接入</Button>} />
}

function CurrentUnavailableArea({ title, description, onBack }: { title: string; description: string; onBack: () => void }) {
  return <Result status="info" title={title} subTitle={description} extra={<Button onClick={onBack}>返回工作台</Button>} />
}

export default function ControlShell() { return <HashRouter><ControlShellContent /></HashRouter> }

function ControlShellContent() {
  const location = useLocation()
  const navigate = useNavigate()
  const route = normalizeRoute(location.pathname)
  const [error, setError] = useState<ApiError | null>(null)
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [retryEpoch, setRetryEpoch] = useState(0)
  const [shutdownConfirmOpen, setShutdownConfirmOpen] = useState(false)
  const [shutdownRequested, setShutdownRequested] = useState(false)
  const [removeConfirmOpen, setRemoveConfirmOpen] = useState(false)
  const [removeBusy, setRemoveBusy] = useState(false)
  const [experience, setExperience] = useState<OfficialExperienceDto | null>(null)
  const [mcpStatus, setMcpStatus] = useState<MCPAccessView | null>(null)
  const [mcpStatusFailed, setMcpStatusFailed] = useState(false)
  const [workReceipt, setWorkReceipt] = useState<string | null>(null)
  const updateNotifications = useCallback((updater: (items: NotificationItem[]) => NotificationItem[]) => setNotifications(updater), [])
  const showBlockingError = useCallback((nextError: ApiError) => setError(nextError), [])
  const notifyError = useCallback((nextError: ApiError) => {
    setNotifications((items) => enqueueNotification(items, nextError, Date.now()))
  }, [])
  const updateMcpStatus = useCallback((next: MCPAccessView) => {
    setMcpStatus(next)
    setMcpStatusFailed(false)
  }, [])
  const clearError = useCallback(() => setError(null), [])
  const dismissNotification = useCallback((key: string) => setNotifications((items) => items.filter((item) => item.key !== key)), [])
  useNotificationExpiry(updateNotifications)

  const workspaceState = useProjectWorkspace(showBlockingError)
  const systemState = useSystemStatus()
  const { projects, selected, workspace: latestWorkspace } = workspaceState
  const [guards, setGuards] = useState<Record<string, boolean>>({})
  const updateGuard = useCallback((key: string, blocked: boolean) => setGuards(current => {
    if (Boolean(current[key]) === blocked) return current
    const next = { ...current }; if (blocked) next[key] = true; else delete next[key]; return next
  }), [])
  const heldWorkspace = useRef<WorkspaceViewDto | null>(null)
  const editing = Object.values(guards).some(Boolean)
  // 页面正在编辑时保留任务输入上下文；最新事实继续回读，切换项目立即释放旧快照。
  if (!editing || heldWorkspace.current?.project.project_id !== selected?.project_id) heldWorkspace.current = latestWorkspace
  const workspace = editing && heldWorkspace.current?.project.project_id === selected?.project_id ? heldWorkspace.current : latestWorkspace
  const pendingTask = editing && workspace?.primary_task?.task_id !== latestWorkspace?.primary_task?.task_id
  const receiptTask = useRef<string | undefined>(undefined)
  const rememberReceipt = (message: string) => { receiptTask.current = workspace?.primary_task?.task_id; setWorkReceipt(message) }
  const checkActivity = useCheckActivity(selected?.project_id, latestWorkspace?.active_check, workspaceState.refreshCurrentWorkspace, latestWorkspace?.latest_result?.run_id, Boolean(latestWorkspace))
  const { profiles: llmProfiles, profilesFailed: llmLoadFailed, aiSettings, setAiSettings, aiSettingsFailed, status: systemStatus } = systemState
  const assistantStatus = aiStatusLabel(llmProfiles, aiSettings, llmLoadFailed, aiSettingsFailed)

  useEffect(() => {
    let active = true
    void experienceApi.status().then((value) => {
      if (active) setExperience(value)
    }).catch((experienceError) => {
      if (active) notifyError(experienceError as ApiError)
    })
    return () => { active = false }
  }, [notifyError])

  useEffect(() => {
    let active = true
    const refresh = () => void mcpAccessApi.status().then((value) => {
      if (active) updateMcpStatus(value)
    }).catch(() => {
      if (active) setMcpStatusFailed(true)
    })
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') refresh()
    }
    refresh()
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      active = false
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [updateMcpStatus])

  useEffect(() => {
    const state = mcpStatus?.connection_state
    if (!state || !['CREDENTIAL_READY', 'AUTHENTICATED', 'CONNECTED'].includes(state)) return
    let active = true, pending = false, reads = 0
    const timer = window.setInterval(() => {
      if (pending || document.visibilityState !== 'visible') return
      if (reads >= 150) { window.clearInterval(timer); return }
      reads += 1; pending = true
      void mcpAccessApi.status().then((value) => {
        if (active) updateMcpStatus(value)
      }).catch(() => {
        if (active) setMcpStatusFailed(true)
      }).finally(() => { pending = false })
    }, 2_000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [mcpStatus?.connection_state, updateMcpStatus])

  useEffect(() => {
    if (location.pathname === '/settings/models') {
      setSettingsOpen(true)
      navigate('/workspace', { replace: true })
      return
    }
    if (location.pathname !== route) navigate(route, { replace: true })
  }, [location.pathname, navigate, route])

  const choose = (project: ProjectDto) => { setWorkReceipt(null); workspaceState.selectProject(project); navigate('/workspace') }
  const connectForAccess = (project: ProjectDto) => { workspaceState.selectProject(project); clearError() }
  const retryCurrentPage = () => {
    clearError()
    setRetryEpoch((epoch) => epoch + 1)
    void workspaceState.refreshProjects()
    void workspaceState.refreshCurrentWorkspace()
  }
  const navigateRecoveryTarget = useCallback((path: string) => {
    if (path === '/settings/models') {
      setSettingsOpen(true)
      navigate('/workspace')
      return
    }
    const [pathname, query] = path.split('?')
    navigate(normalizeRoute(pathname) + (query ? `?${query}` : ''))
  }, [navigate])
  const removeCurrentProject = async () => {
    if (!selected) return
    setRemoveBusy(true)
    try {
      await projectsApi.remove(selected.project_id)
      setRemoveConfirmOpen(false)
      await workspaceState.refreshProjects()
      navigate('/workspace')
    } catch (removeError) {
      notifyError(removeError as ApiError)
    } finally {
      setRemoveBusy(false)
    }
  }

  // Agent 可以在页面外登记或执行；自由导航期间仍有界回读，更新事实但不切换页面。
  useEffect(() => {
    if (!selected || mcpStatus?.connection_state !== 'CONNECTED') return
    let active = true, pending = false, reads = 0
    const timer = window.setInterval(async () => {
      if (!active || pending || document.visibilityState !== 'visible') return
      if (reads >= 60) { window.clearInterval(timer); return }
      pending = true; reads += 1
      try { await workspaceState.refreshCurrentWorkspace() } finally { pending = false }
    }, 5_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [route, selected?.project_id, mcpStatus?.connection_state, workspaceState.refreshCurrentWorkspace])

  const renderChecks = (runId?: string | null, taskId?: string | null, changeId?: string | null, onBackToHistory?: () => void) => selected && <CurrentTestsPage
    key={`checks-${selected.project_id}-${retryEpoch}-${changeId ?? ''}`} project={selected} workspace={workspace} onError={notifyError}
    onStateChanged={workspaceState.refreshCurrentWorkspace} onBackToHistory={onBackToHistory} onFeedback={rememberReceipt}
    onProvidedMaterials={experience?.active && experience.project_id === selected.project_id ? async () => { const value = await experienceApi.prepare(); setExperience(value); return value } : undefined}
    onNavigate={path => { if (onBackToHistory && path.startsWith('/tests?run_id=')) navigate(path.replace('/tests?', '/history?')); else navigateRecoveryTarget(path) }}
    requestedTaskId={taskId} requestedRunId={runId} requestedCaseId={new URLSearchParams(location.search).get('case_id')} changeId={changeId} />
  const renderPermissions = () => selected && <BusinessBoundaryPage key={`permissions-${selected.project_id}-${retryEpoch}`} project={selected}
    onError={notifyError} onStateChanged={workspaceState.refreshCurrentWorkspace} onFeedback={rememberReceipt}
    onProvidedProposal={experience?.active && experience.project_id === selected.project_id ? experienceApi.boundaryProposal : undefined} onBack={() => navigate('/workspace')} />
  const currentTaskContent = () => {
    const task = workspace?.primary_task
    if (!selected || !task) return undefined
    if (task.route === '/permissions') return renderPermissions()
    if (task.route === '/tests') {
      const preparing = !['RUN_CURRENT_CHECK', 'VIEW_CURRENT_RESULT', 'VERIFY_REPAIR'].includes(task.task_kind)
      return renderChecks(workspace?.active_check?.run.run_id ?? task.run_id, preparing ? task.task_id : null, task.change_id)
    }
    if (task.route === '/application') return <AccessPage selected={selected} endpointStatus={workspace?.connection.endpoint_status} officialSampleAvailable={false} onProvidedBoundary={experience?.active && experience.project_id === selected?.project_id ? () => navigate('/permissions') : undefined} onConnected={connectForAccess} onUnderstandingChanged={() => { void workspaceState.refreshCurrentWorkspace() }} onBack={() => navigate('/workspace')} onContinue={() => navigate('/permissions')} />
    return undefined
  }

  const samplePanel = <OfficialSamplePanel value={experience} onError={notifyError} onChanged={async (value) => {
      setExperience(value)
      const items = await workspaceState.refreshProjects()
      const project = value.active ? items.find(item => item.project_id === value.project_id) : null
      if (project) { workspaceState.selectProject(project); await workspaceState.refreshCurrentWorkspace(project) }
    }} />
  const directTask = route === '/workspace' ? currentTaskContent() : undefined

  const content = () => {
    // 当前任务与自由入口使用相同组件位置，避免从当前工作进入权限页时丢失草稿。
    if (directTask) return directTask
    if (route === '/workspace') return <WorkbenchPage selected={selected} workspace={workspace} systemStatus={systemStatus} experience={experience} mcpStatus={mcpStatusFailed ? null : mcpStatus} onNavigate={(path) => navigate(path)} samplePanel={samplePanel} />
    if (route === '/tools') return <ToolsPage projects={projects} onError={notifyError} onStatusChange={updateMcpStatus} />
    if (route === '/application') return <AccessPage selected={selected} endpointStatus={workspace?.connection.endpoint_status} officialSampleAvailable={false} onProvidedBoundary={experience?.active && experience.project_id === selected?.project_id ? () => navigate('/permissions') : undefined} onConnected={connectForAccess} onUnderstandingChanged={() => { void workspaceState.refreshCurrentWorkspace() }} onBack={() => navigate('/workspace')} onContinue={() => navigate('/permissions')} />
    if (route === '/settings/system') return <RuntimePage status={systemStatus} profiles={llmProfiles} failed={llmLoadFailed} />
    if (!selected) return <MissingApplication onNavigate={() => navigate('/application')} />
    if (route === '/permissions') return renderPermissions()
    if (route === '/history') return <CheckHistoryPage key={`history-${selected.project_id}-${retryEpoch}`} project={selected} onError={notifyError} onNavigate={navigateRecoveryTarget} requestedRunId={new URLSearchParams(location.search).get('run_id')} renderRun={(runId, onBack) => renderChecks(runId, null, null, onBack)} />
    if (route === '/changes') return <ChangesPage key={`changes-${selected.project_id}-${retryEpoch}`} project={selected} onError={notifyError} onNavigate={navigate} onStateChanged={workspaceState.refreshCurrentWorkspace} requestedRepair={new URLSearchParams(location.search).get('repair_reference')} />
    if (route === '/tests') { const query = new URLSearchParams(location.search); return renderChecks(query.get('run_id'), query.get('task_id'), query.get('change_id')) }
    return <CurrentUnavailableArea title="此历史入口当前不可用" description="请从工作台进入当前可用的业务边界或检查准备。" onBack={() => navigate('/workspace')} />
  }

  const retainedRoute = route === '/workspace' && workspace?.primary_task && ['/permissions', '/tests', '/application'].includes(workspace.primary_task.route) ? workspace.primary_task.route : route
  const retainedKey = ['/workspace', '/permissions', '/history', '/tests', '/changes', '/application'].includes(retainedRoute) ? retainedRoute : null

  if (shutdownRequested) return <Result status="success" title="界鉴正在安全退出" subTitle="服务清理完成后，可以关闭此页面。" />
  return <TaskGuardContext.Provider value={updateGuard}><Layout className="app-shell">
    <DesktopModuleNavigation systemStatus={systemStatus} route={route} areas={workspace?.areas ?? null} onNavigate={(path: AppRoute) => navigate(path)} />
    <Layout className="product-main">
      <MobileModuleNavigation systemStatus={systemStatus} route={route} areas={workspace?.areas ?? null} onNavigate={(path: AppRoute) => navigate(path)} />
      <AppHeader projects={projects} selected={selected} mcpStatus={mcpStatus} mcpStatusFailed={mcpStatusFailed} systemStatus={systemStatus} onSelectProject={choose} onConnectNew={() => navigate('/application')} onRemoveCurrent={() => setRemoveConfirmOpen(true)} onNavigate={navigate} aiLabel={assistantStatus} onOpenAI={() => setSettingsOpen(true)} onRequestShutdown={() => setShutdownConfirmOpen(true)} />
      <Layout.Content className="content"><div className="content-frame">
        {route === '/workspace' && <TaskJourney workspace={workspace} pending={pendingTask} />}
        {workReceipt && route === '/workspace' && receiptTask.current !== workspace?.primary_task?.task_id && <div className="work-receipt" role="status"><span>{workReceipt}</span><Button type="text" aria-label="关闭操作完成提示" onClick={() => setWorkReceipt(null)}>×</Button></div>}
        {checkActivity.completed && !['/tests','/workspace'].includes(route) && <div className="check-activity-notice" role="status"><span>{checkActivity.completed.label}</span><Button type="link" onClick={() => navigate(`/history?run_id=${encodeURIComponent(checkActivity.completed!.runId)}`)}>查看结果</Button><Button type="text" aria-label="关闭检查完成提示" onClick={checkActivity.dismiss}>×</Button></div>}
        {!checkActivity.completed && checkActivity.activeRunId && route !== '/tests' && route !== '/workspace' && <div className="check-activity-notice"><span>{checkActivity.paused ? '检查进度暂未同步' : '有一项检查正在执行'}</span><Button type="link" onClick={() => navigate(`/tests?run_id=${encodeURIComponent(checkActivity.activeRunId!)}`)}>查看当前进度</Button></div>}
        {error && <ErrorRecovery error={error} onRetry={retryCurrentPage} onNavigate={(path) => { clearError(); navigateRecoveryTarget(path) }} onClose={clearError} />}<RetainedWorkPages key={`${selected?.project_id ?? 'new'}-${retryEpoch}`} activeKey={retainedKey}>{content()}</RetainedWorkPages>{directTask && <WorkbenchContext workspace={workspace} onNavigate={navigate} />}{(directTask || route === "/changes") && experience?.active && experience.project_id === selected?.project_id && <div className="work-sample-tools">{samplePanel}</div>}</div></Layout.Content>
    </Layout>
    <NotificationCenter items={notifications} onDismiss={dismissNotification} onNavigate={(path, key) => { dismissNotification(key); clearError(); navigateRecoveryTarget(path) }} />
    <Modal open={removeConfirmOpen} title="移除当前应用？" okText="确认移除" cancelText="取消" okButtonProps={{ danger: true, loading: removeBusy }} onCancel={() => setRemoveConfirmOpen(false)} onOk={() => { void removeCurrentProject() }}>
      界鉴会从普通应用列表中移除当前应用，并清理当前测试账号的安全凭据；不会删除应用源码和历史事实。
    </Modal>
    <Modal open={shutdownConfirmOpen} title="退出界鉴？" okText="安全退出" cancelText="继续使用" cancelButtonProps={{ id: 'shutdown-cancel-button' }} afterOpenChange={(open) => { if (open) document.getElementById('shutdown-cancel-button')?.focus() }} onCancel={() => setShutdownConfirmOpen(false)} focusTriggerAfterClose onOk={async () => {
      try {
        await systemApi.shutdown()
        setShutdownConfirmOpen(false)
        setShutdownRequested(true)
      } catch (shutdownError) {
        notifyError(shutdownError as ApiError)
      }
    }}>界鉴会先停止当前本地服务并保存可恢复事实。</Modal>
    <LLMSettingsDrawer open={settingsOpen} profiles={llmProfiles} aiSettings={aiSettings} onClose={() => setSettingsOpen(false)} onChanged={systemState.setProfiles} onSettingsChanged={setAiSettings} onError={notifyError} />
  </Layout></TaskGuardContext.Provider>
}
