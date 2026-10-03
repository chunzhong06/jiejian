/* 当前产品壳：只接入动作级 Workspace、应用接入、业务边界和明确不可用区域。 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Layout, Modal, Result } from 'antd'
import { HashRouter, useLocation, useNavigate } from 'react-router-dom'
import { experienceApi } from '../../api/applications/experience'
import { ApiError } from '../../api/http'
import { mcpAccessApi, type MCPAccessView } from '../../api/system/mcp'
import { projectsApi, type ProjectDto } from '../../api/applications/projects'
import { systemApi } from '../../api/system/system'
import { DesktopModuleNavigation, MobileModuleNavigation } from '../navigation/ModuleNavigation'
import { ErrorRecovery } from './ErrorRecovery'
import { AccessPage } from '../../features/access/AccessPage'
import { CurrentTestsPage } from '../../features/checks/CurrentTestsPage'
import { CheckHistoryPage } from '../../features/history/CheckHistoryPage'
import { ChangesPage } from '../../features/changes/ChangesPage'
import { OfficialSamplePanel } from '../../features/environment/OfficialSamplePanel'
import { OfficialDevelopmentJourney } from '../../features/environment/OfficialDevelopmentJourney'
import { EnvironmentPage } from '../../features/environment/EnvironmentPage'
import { BusinessBoundaryPage } from '../../features/boundaries/BusinessBoundaryPage'
import LLMSettingsDrawer from '../../features/settings/LLMSettingsDrawer'
import { RuntimePage } from '../../features/system/RuntimePage'
import { ToolsPage } from '../../features/tools/ToolsPage'
import { WorkbenchPage } from '../../features/workspace/WorkbenchPage'
import { aiStatusLabel, AppHeader } from './AppHeader'
import { NotificationCenter, enqueueNotification, useNotificationExpiry, type NotificationItem } from '../notifications/NotificationCenter'
import { normalizeRoute, type AppRoute } from '../navigation/routes'
import { useProjectWorkspace } from '../state/useProjectWorkspace'
import { useSystemStatus } from '../state/useSystemStatus'
import { FrontendBuildNotice } from '../notifications/FrontendBuildNotice'
import { useCheckActivity } from '../state/useCheckActivity'
import { RetainedWorkPages } from './RetainedWorkPages'
import { TaskGuardContext } from '../../shared/runtime/editGuard'
import type { WorkspaceViewDto } from '../../api/workspace'
import '../../styles.css'

function MissingApplication({ onNavigate }: { onNavigate: () => void }) {
  return <Result status="info" title="先选择要维护的应用" subTitle="选择应用后才能查看这里的内容。" extra={<Button type="primary" onClick={onNavigate}>去应用接入</Button>} />
}

function CurrentUnavailableArea({ title, description, onBack }: { title: string; description: string; onBack: () => void }) {
  return <Result status="info" title={title} subTitle={description} extra={<Button onClick={onBack}>返回概览</Button>} />
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
  const [mcpStatus, setMcpStatus] = useState<MCPAccessView | null>(null)
  const [mcpStatusFailed, setMcpStatusFailed] = useState(false)
  const [workReceipt, setWorkReceipt] = useState<{ message: string; projectId: string; locationKey: string } | null>(null)
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
  const { projects, selected, experience, setExperience, workspace: latestWorkspace } = workspaceState
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
  const rememberReceipt = (message: string) => { if (selected) setWorkReceipt({ message, projectId: selected.project_id, locationKey: location.key }) }
  // 短期操作回执只属于发出操作的页面和项目；持久进度由真实 Run 单独呈现。
  useEffect(() => { setWorkReceipt(null) }, [selected?.project_id, location.key])
  useEffect(() => { if (!workReceipt) return; const timer = window.setTimeout(() => setWorkReceipt(null), 6000); return () => window.clearTimeout(timer) }, [workReceipt])
  const checkActivity = useCheckActivity(selected?.project_id, latestWorkspace?.active_check, workspaceState.refreshCurrentWorkspace, latestWorkspace?.latest_result?.run_id, Boolean(latestWorkspace))
  const { profiles: llmProfiles, profilesFailed: llmLoadFailed, aiSettings, setAiSettings, aiSettingsFailed, status: systemStatus } = systemState
  const assistantStatus = aiStatusLabel(llmProfiles, aiSettings, llmLoadFailed, aiSettingsFailed)

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
      setWorkReceipt(null)
      workspaceState.selectProject(null)
      if (experience?.project_id === selected.project_id) setExperience(null)
      await workspaceState.refreshProjects()
      navigate('/workspace')
      // 移除 API 已停止属于该项目的官方实例；只回读环境，不再发一次停止请求。
      try { setExperience(await experienceApi.status()) } catch (error) { setExperience(null); notifyError(error as ApiError) }
    } catch (removeError) {
      notifyError(removeError as ApiError)
    } finally {
      setRemoveBusy(false)
    }
  }

  const renderChecks = (runId?: string | null, taskId?: string | null, changeId?: string | null, onBackToHistory?: () => void) => selected && <CurrentTestsPage
    key={`checks-${selected.project_id}-${retryEpoch}-${changeId ?? ''}`} project={selected} workspace={workspace} onError={notifyError}
    onStateChanged={workspaceState.refreshCurrentWorkspace} onBackToHistory={onBackToHistory} onFeedback={rememberReceipt}
    onProvidedMaterials={experience?.active && experience.project_id === selected.project_id ? async () => { const value = await experienceApi.prepare(); setExperience(value); return value } : undefined}
    onNavigate={path => { if (onBackToHistory && path.startsWith('/tests?run_id=')) navigate(path.replace('/tests?', '/history?')); else navigateRecoveryTarget(path) }}
    requestedProofSources={new URLSearchParams(location.search).get('proof_sources') === '1'} requestedProofSource={new URLSearchParams(location.search).get('source')}
    requestedActionId={new URLSearchParams(location.search).get('action_id')}
    requestedIdentities={new URLSearchParams(location.search).get('identities') === '1'}
    requestedMaterials={new URLSearchParams(location.search).get('materials') === '1'} requestedTaskId={taskId} requestedRunId={runId} requestedCaseId={new URLSearchParams(location.search).get('case_id')} changeId={changeId} />
  const renderPermissions = () => {
    const params = new URLSearchParams(location.search)
    const candidateProject = params.get('project_id')
    if ((params.has('candidate') || params.has('intent_id')) && candidateProject && candidateProject !== selected?.project_id) {
      const target = projects.find(item => item.project_id === candidateProject)
      return <Result status="info" title="这条规则属于另一个应用" subTitle={target ? `切换到${target.name}后继续审阅，当前应用不受影响。` : '该应用尚未读取或已不可用，请从应用列表核对。'}
        extra={target && <Button type="primary" onClick={() => workspaceState.selectProject(target)}>切换并查看规则</Button>}/>
    }
    const candidateRevision = Number(params.get('revision'))
    if (params.has('intent_id') && params.has('revision') && (!Number.isInteger(candidateRevision) || candidateRevision < 1)) return <Result status="warning" title="规则修订无效" subTitle="请从权限列表打开准确的规则修订。" extra={<Button onClick={()=>navigate('/permissions')}>返回权限列表</Button>}/>
    return selected && <BusinessBoundaryPage requestedActionId={params.get('action_id')} key={`permissions-${selected.project_id}-${retryEpoch}`} project={selected}
    requestedIntentId={params.get('intent_id')} requestedIntentRevision={params.has('revision') ? candidateRevision : undefined} onNavigate={navigateRecoveryTarget}
    onRuleRoute={(id,revision)=>navigate(id ? `/permissions?project_id=${selected.project_id}&intent_id=${id}&revision=${revision}` : '/permissions')}
    requestedCandidateId={params.get('candidate')} requestedCandidateRevision={Number.isInteger(candidateRevision) && candidateRevision > 0 ? candidateRevision : undefined}
    candidateRecoveryOperation={params.get('rule_operation_id')}
    onCandidateRoute={(id, revision, operation) => { const next = new URLSearchParams(location.search); next.set('project_id', selected.project_id); if(id) {next.set('candidate', id); next.set('revision', String(revision))} else {next.delete('candidate'); next.delete('revision')} if (operation) next.set('rule_operation_id', operation); else next.delete('rule_operation_id'); navigate(`/permissions?${next.toString()}`, {replace:true}) }}
    requestedProposalId={route === '/workspace' ? workspace?.primary_task?.proposal_id : new URLSearchParams(location.search).get('proposal_id')}
    onError={notifyError} onStateChanged={workspaceState.refreshCurrentWorkspace} onFeedback={rememberReceipt}
    onProvidedProposal={experience?.active && experience.project_id === selected.project_id ? experienceApi.boundaryProposal : undefined} onBack={() => navigate('/workspace')} />
  }

  const samplePanel = <OfficialSamplePanel value={experience} onError={notifyError} onChanged={async (value) => {
      setExperience(value)
      const items = await workspaceState.refreshProjects()
      const project = value.active ? items.find(item => item.project_id === value.project_id) : null
      if (project) { workspaceState.selectProject(project); await workspaceState.refreshCurrentWorkspace(project) }
    }} />

  const content = () => {
    // 当前任务与自由入口使用相同组件位置，避免从当前工作进入权限页时丢失草稿。
    if (route === '/workspace') return <WorkbenchPage workspaceSyncFailed={workspaceState.synchronization?.retrying} selected={selected} workspace={latestWorkspace} systemStatus={systemStatus} experience={experience} mcpStatus={mcpStatusFailed ? null : mcpStatus} onNavigate={(path) => navigate(path)} samplePanel={samplePanel} />
    if (route === '/tools') return <ToolsPage onNavigate={navigateRecoveryTarget} projects={projects} onError={notifyError} onStatusChange={updateMcpStatus} />
    if (route === '/environment') return <EnvironmentPage onRemoveCurrent={() => setRemoveConfirmOpen(true)} project={selected} workspace={workspace} systemStatus={systemStatus} onError={notifyError} onNavigate={navigateRecoveryTarget} onChanged={async value => { setExperience(value); const items = await workspaceState.refreshProjects(); const next = value.active ? items.find(item => item.project_id === value.project_id) : undefined; if (next) { workspaceState.selectProject(next); await workspaceState.refreshCurrentWorkspace(next) } }}/>
    if (route === '/application') return <AccessPage selected={selected} endpointStatus={workspace?.connection.endpoint_status} officialSampleAvailable={false} onProvidedBoundary={experience?.active && experience.project_id === selected?.project_id ? () => navigate('/permissions') : undefined} onConnected={connectForAccess} onUnderstandingChanged={async () => { const next = await workspaceState.refreshCurrentWorkspace(); if (!next) throw new ApiError('STATE_PRECONDITION', '下一步任务尚未同步。') }} onBack={() => navigate('/workspace')} onContinue={() => navigate('/permissions')} />
    if (route === '/settings/system') return <RuntimePage status={systemStatus} profiles={llmProfiles} failed={llmLoadFailed} />
    if (!selected) return <MissingApplication onNavigate={() => navigate('/application')} />
    if (route === '/permissions') return renderPermissions()
    if (route === '/history') return <CheckHistoryPage key={`history-${selected.project_id}-${retryEpoch}`} project={selected} onError={notifyError} onNavigate={navigateRecoveryTarget} requestedRunId={new URLSearchParams(location.search).get('run_id')} renderRun={(runId, onBack) => renderChecks(runId, null, null, onBack)} />
    if (route === '/changes') return <ChangesPage key={`changes-${selected.project_id}-${retryEpoch}`} project={selected} onError={notifyError} onNavigate={navigate} onStateChanged={workspaceState.refreshCurrentWorkspace} requestedRepair={new URLSearchParams(location.search).get('repair_reference')}
      requestedView={new URLSearchParams(location.search).get('view')} requestedChange={new URLSearchParams(location.search).get('change_id')} developmentJourney={experience?.active && experience.project_id === selected.project_id ? <OfficialDevelopmentJourney key={selected.project_id} value={experience} onError={notifyError} onNavigate={navigateRecoveryTarget} onChanged={async next => { setExperience(next); await workspaceState.refreshCurrentWorkspace() }}/> : undefined}/>
    if (route === '/tests') {
      const query = new URLSearchParams(location.search), projectId = query.get('project_id')
      if (projectId && projectId !== selected.project_id) {
        const target = projects.find(item => item.project_id === projectId)
        return <Result status="info" title="这项证明准备属于另一个应用" subTitle={target ? `切换到${target.name}后继续核对。` : '该应用尚未读取或已不可用。'} extra={target && <Button type="primary" onClick={() => workspaceState.selectProject(target)}>切换并查看来源</Button>}/>
      }
      return renderChecks(query.get('run_id'), query.get('task_id'), query.get('change_id'))
    }
    return <CurrentUnavailableArea title="此历史入口当前不可用" description="请从概览进入当前可用的业务边界或检查准备。" onBack={() => navigate('/workspace')} />
  }

  const retainedRoute = route
  const retainedKey = ['/workspace', '/permissions', '/history', '/tests', '/changes', '/application'].includes(retainedRoute) ? retainedRoute : null

  useEffect(() => { document.getElementById('main-content')?.focus({preventScroll:true}) }, [route])

  if (shutdownRequested) return <Result status="success" title="界鉴正在安全退出" subTitle="服务清理完成后，可以关闭此页面。" />
  return <TaskGuardContext.Provider value={updateGuard}><Layout className="app-shell"><a className="skip-to-content" href="#main-content" onClick={event=>{event.preventDefault();document.getElementById('main-content')?.focus()}}>跳到主要内容</a>
    <DesktopModuleNavigation systemStatus={systemStatus} route={route} areas={workspace?.areas ?? null} onNavigate={(path: AppRoute) => navigate(path)} />
    <Layout className="product-main">
      <MobileModuleNavigation systemStatus={systemStatus} route={route} areas={workspace?.areas ?? null} onNavigate={(path: AppRoute) => navigate(path)} />
      <AppHeader projects={projects} selected={selected} mcpStatus={mcpStatus} mcpStatusFailed={mcpStatusFailed} systemStatus={systemStatus} onSelectProject={choose} onConnectNew={() => navigate('/application')} onNavigate={navigate} aiLabel={assistantStatus} onOpenAI={() => setSettingsOpen(true)} onRequestShutdown={() => setShutdownConfirmOpen(true)} />
      <Layout.Content className="content"><div className="content-frame" id="main-content" tabIndex={-1}>
        {workReceipt && selected?.project_id === workReceipt.projectId && location.key === workReceipt.locationKey && <div className="work-receipt" role="status"><span>{workReceipt.message}</span><Button type="text" aria-label="关闭操作完成提示" onClick={() => setWorkReceipt(null)}>×</Button></div>}
        {error && <ErrorRecovery error={error} onRetry={retryCurrentPage} onNavigate={(path) => { clearError(); navigateRecoveryTarget(path) }} onClose={clearError} />}<RetainedWorkPages key={`${selected?.project_id ?? 'new'}-${retryEpoch}`} activeKey={retainedKey}>{content()}</RetainedWorkPages></div></Layout.Content>
    </Layout>
    <NotificationCenter resourceNotice={<FrontendBuildNotice identity={systemStatus.frontend_identity} blocked={editing || Boolean(checkActivity.activeRunId)}/>} activity={!['/tests','/workspace'].includes(route) ? checkActivity.completed ? {
      label:checkActivity.completed.label,actionLabel:'查看结果',onDismiss:checkActivity.dismiss,
      onView:()=>{const run=checkActivity.completed!.runId;checkActivity.dismiss();navigate(`/history?run_id=${encodeURIComponent(run)}`)},
    } : checkActivity.activeRunId && !checkActivity.progressDismissed ? {
      label:checkActivity.paused?'进度暂未同步，正在重试':'有一项检查正在执行',actionLabel:'查看当前进度',
      onDismiss:checkActivity.dismissProgress,
      onView:()=>navigate(`/tests?run_id=${encodeURIComponent(checkActivity.activeRunId!)}`),
    } : null : null} items={notifications} onDismiss={dismissNotification} onNavigate={(path, key) => { dismissNotification(key); clearError(); navigateRecoveryTarget(path) }} />
    <Modal open={removeConfirmOpen} title="移除当前应用？" okText="确认移除" cancelText="取消" okButtonProps={{ danger: true, loading: removeBusy }} onCancel={() => setRemoveConfirmOpen(false)} onOk={() => { void removeCurrentProject() }}>
      界鉴会从应用列表中移除当前应用，并清理当前测试账号的安全凭据。属于该应用的官方示例实例会一并停止，无需再次操作；应用源码和历史事实保留。普通应用的外部进程不会被停止。
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
