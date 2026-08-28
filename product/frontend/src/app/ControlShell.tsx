/* 产品工作台壳：集中处理任务导航、项目恢复、状态展示和错误恢复。 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Layout, Modal, Result } from 'antd'
import { HashRouter, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/http'
import { experienceApi, type OfficialExperienceDto, type OfficialExperienceMode } from '../api/experience'
import { projectsApi, type ProjectDto } from '../api/projects'
import { systemApi } from '../api/system'
import { ErrorRecovery } from '../components/ErrorRecovery'
import { JudgeGuideBar } from '../components/JudgeGuideBar'
import { DesktopProcessNavigation, MobileProcessNavigation } from '../components/ProcessNavigation'
import { AccessPage } from '../features/access/AccessPage'
import { TestIdentityPage } from '../features/identities/TestIdentityPage'
import { CheckHistoryPage } from '../features/checks/CheckHistoryPage'
import { PermissionCheckPage } from '../features/checks/PermissionCheckPage'
import { CheckResultsPage } from '../features/checks/CheckResultsPage'
import { RecordingPage } from '../features/recording/RecordingPage'
import { ModelServicePage } from '../features/settings/ModelServicePage'
import LLMSettingsDrawer from '../features/settings/LLMSettingsDrawer'
import { RuntimePage } from '../features/system/RuntimePage'
import { WorkbenchPage } from '../features/workspace/WorkbenchPage'
import { AppHeader } from './AppHeader'
import { NotificationCenter, enqueueNotification, useNotificationExpiry, type NotificationItem } from './NotificationCenter'
import { normalizeRoute, type AppRoute } from './presentation'
import { useProjectWorkspace } from './useProjectWorkspace'
import { useSystemStatus } from './useSystemStatus'
import '../styles.css'

function MissingApplication({ onNavigate }: { onNavigate: () => void }) {
  return <Result status="info" title="先选择要检查的应用" subTitle="选择应用后才能查看这里的内容。" extra={<Button type="primary" onClick={onNavigate}>去应用接入</Button>} />
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
  const [experienceBusy, setExperienceBusy] = useState(false)
  const updateNotifications = useCallback((updater: (items: NotificationItem[]) => NotificationItem[]) => setNotifications(updater), [])
  // 工作区加载失败会阻断整个控制面；页面内操作失败只进入通知，避免同一错误重复覆盖页面。
  const showBlockingError = useCallback((nextError: ApiError) => setError(nextError), [])
  const notifyError = useCallback((nextError: ApiError) => {
    setNotifications((items) => enqueueNotification(items, nextError, Date.now()))
  }, [])
  const clearError = useCallback(() => setError(null), [])
  const resolveRouteErrors = useCallback((routes: string[]) => {
    setError((current) => current?.diagnosis?.route && routes.includes(current.diagnosis.route) ? null : current)
    setNotifications((items) => items.filter((item) => !item.diagnosis?.route || !routes.includes(item.diagnosis.route)))
  }, [])
  const dismissNotification = useCallback((key: string) => setNotifications((items) => items.filter((item) => item.key !== key)), [])
  useNotificationExpiry(updateNotifications)
  const workspace = useProjectWorkspace(showBlockingError)
  const systemState = useSystemStatus()
  const { projects, selected, status, readiness, runs } = workspace
  const { profiles: llmProfiles, profilesFailed: llmLoadFailed, aiSettings, setAiSettings, aiSettingsFailed, status: systemStatus } = systemState

  useEffect(() => {
    let active = true
    void experienceApi.status().then((value) => {
      if (active) setExperience(value)
    }).catch((experienceError) => {
      if (active) notifyError(experienceError as ApiError)
    })
    return () => { active = false }
  }, [notifyError])

  const choose = (project: ProjectDto) => { workspace.selectProject(project); navigate('/workspace') }
  const connectForAccess = (project: ProjectDto) => { workspace.selectProject(project); clearError() }
  const refreshRuns = workspace.refreshCurrent
  const retryCurrentPage = () => { clearError(); setRetryEpoch((epoch) => epoch + 1); void workspace.refreshProjects(); void workspace.refreshCurrent() }
  const requestShutdown = () => setShutdownConfirmOpen(true)
  const removeCurrentProject = async () => {
    if (!selected) return
    setRemoveBusy(true)
    try {
      await projectsApi.remove(selected.project_id)
      setRemoveConfirmOpen(false)
      await workspace.refreshProjects()
      navigate('/application')
    } catch (removeError) {
      notifyError(removeError as ApiError)
    } finally {
      setRemoveBusy(false)
    }
  }
  const activeRun = useMemo(() => runs[0], [runs])
  const startOfficialExperience = async (mode: OfficialExperienceMode) => {
    setExperienceBusy(true)
    try {
      const started = await experienceApi.start(mode)
      setExperience(started)
      const currentProjects = await workspace.refreshProjects()
      const project = currentProjects.find((item) => item.project_id === started.project_id)
      if (project) workspace.selectProject(project)
      navigate('/application')
      return true
    } catch (experienceError) {
      notifyError(experienceError as ApiError)
      return false
    } finally {
      setExperienceBusy(false)
    }
  }
  const prepareOfficialIdentities = async () => {
    setExperienceBusy(true)
    try {
      setExperience(await experienceApi.prepareIdentities())
      await workspace.refreshCurrent()
    } catch (experienceError) {
      notifyError(experienceError as ApiError)
    } finally {
      setExperienceBusy(false)
    }
  }
  const verifyOfficialFix = async () => {
    if (!activeRun?.run_id) return
    setExperienceBusy(true)
    try {
      setExperience(await experienceApi.verifyFixedBehavior(String(activeRun.run_id)))
      await workspace.refreshCurrent()
      navigate('/check')
    } catch (experienceError) {
      notifyError(experienceError as ApiError)
    } finally {
      setExperienceBusy(false)
    }
  }
  useEffect(() => {
    if (location.pathname !== route) navigate(route, { replace: true })
  }, [location.pathname, navigate, route])
  useEffect(() => {
    if (!selected?.project_id || (route !== '/results' && route !== '/history')) return
    // Run 可能由 Worker、CLI 或其他会话形成，进入结果相关页面时必须重新读取权威工作区状态。
    void refreshRuns()
  }, [refreshRuns, route, selected?.project_id])

  const navigateTo = (path: AppRoute) => navigate(path)
  const content = () => {
    if (route === '/workspace') return <WorkbenchPage selected={selected} readiness={readiness} nextAction={status?.next_action ?? null} runs={runs} systemStatus={systemStatus} experience={experience} experienceBusy={experienceBusy} onStartExperience={startOfficialExperience} onNavigate={(path) => navigate(path)} />
    if (route === '/application') return <AccessPage selected={selected} endpointStatus={readiness?.endpoint_status} onConnected={connectForAccess} onUnderstandingChanged={() => { void workspace.refreshCurrent() }} onBack={() => navigate('/workspace')} onContinue={() => navigate('/identities')} />
    if (route === '/settings/models') return <ModelServicePage profiles={llmProfiles} onManage={() => setSettingsOpen(true)} />
    if (route === '/settings/system') return <RuntimePage status={systemStatus} profiles={llmProfiles} failed={llmLoadFailed} />
    if (!selected) return <MissingApplication onNavigate={() => navigate('/application')} />
    if (route === '/identities') return <TestIdentityPage key={`identities-${selected.project_id}-${retryEpoch}`} project={selected} onError={notifyError} onBack={() => navigate('/application')} onNext={() => navigate('/flows')} />
    if (route === '/flows') return <RecordingPage key={`recording-${retryEpoch}`} project={selected} onError={notifyError} onBack={() => navigate('/identities')} onNext={() => navigate('/check')} />
    if (route === '/check') return <PermissionCheckPage key={`check-${retryEpoch}`} project={selected} runs={runs} onRefresh={refreshRuns} onError={notifyError} onResolved={() => resolveRouteErrors(['/check'])} onNavigate={(path) => navigate(normalizeRoute(path))} onBack={() => navigate('/flows')} onNext={() => navigate('/results')} />
    if (route === '/history') return <CheckHistoryPage projectId={selected.project_id} onError={notifyError} onBack={() => navigate('/results')} />
    return <CheckResultsPage key={`results-${retryEpoch}`} run={activeRun} onError={notifyError} onBack={() => navigate('/check')} onHistory={() => navigate('/history')} onNavigate={(path) => navigate(normalizeRoute(path))} canVerifyFix={Boolean(experience?.active && experience.experience_mode === 'GUIDED' && experience.project_id === selected.project_id && status?.latest_result?.run_id === activeRun?.run_id)} verifyingFix={experienceBusy} onVerifyFix={verifyOfficialFix} />
  }
  if (shutdownRequested) return <Result status="success" title="界鉴正在安全退出" subTitle="服务、Worker 和受控浏览器清理完成后，可以关闭此页面；下次启动会自动检查异常中断记录。" />
  return <Layout className="app-shell">
    <DesktopProcessNavigation route={route} steps={status?.steps ?? null} onNavigate={navigateTo} />
    <Layout className="product-main">
      <MobileProcessNavigation route={route} steps={status?.steps ?? null} onNavigate={navigateTo} />
      <AppHeader projects={projects} selected={selected} activeTask={readiness?.active_tasks[0]} profiles={llmProfiles} aiSettings={aiSettings} profilesFailed={llmLoadFailed} settingsFailed={aiSettingsFailed} systemStatus={systemStatus} onSelectProject={choose} onConnectNew={() => navigate('/application')} onRemoveCurrent={() => setRemoveConfirmOpen(true)} onNavigate={navigate} onOpenAI={() => setSettingsOpen(true)} onRequestShutdown={requestShutdown} />
      <Layout.Content className="content"><div className="content-frame"><JudgeGuideBar status={status} experience={experience} preparingIdentities={experienceBusy} onPrepareIdentities={() => { void prepareOfficialIdentities() }} />{error && <ErrorRecovery error={error} onRetry={retryCurrentPage} onNavigate={(path) => { clearError(); navigate(normalizeRoute(path)) }} onClose={clearError} />}{content()}</div></Layout.Content>
    </Layout>
    <NotificationCenter items={notifications} onDismiss={dismissNotification} onNavigate={(path, key) => { dismissNotification(key); clearError(); navigate(path) }} />
    <Modal
      open={removeConfirmOpen}
      title="移除当前应用？"
      okText="确认移除"
      cancelText="取消"
      okButtonProps={{ danger: true, loading: removeBusy }}
      onCancel={() => setRemoveConfirmOpen(false)}
      onOk={() => { void removeCurrentProject() }}
    >
      界鉴会从普通应用列表中移除当前应用，并清理当前测试账号的安全凭据；不会删除应用源码、检查结果和历史记录。再次接入同一目录时会恢复原来的应用历史，并要求重新准备当前凭据。
    </Modal>
    <Modal
      open={shutdownConfirmOpen}
      title="退出界鉴？"
      okText="安全退出"
      cancelText="继续使用"
      cancelButtonProps={{ id: 'shutdown-cancel-button' }}
      afterOpenChange={(open) => { if (open) document.getElementById('shutdown-cancel-button')?.focus() }}
      onCancel={() => setShutdownConfirmOpen(false)}
      focusTriggerAfterClose
      onOk={async () => {
        try {
          await systemApi.shutdown()
          setShutdownConfirmOpen(false)
          setShutdownRequested(true)
        } catch (shutdownError) {
          notifyError(shutdownError as ApiError)
        }
      }}
    >
      界鉴会先停止服务、Worker 和受控浏览器，并保留可恢复的任务记录。
    </Modal>
    <LLMSettingsDrawer open={settingsOpen} profiles={llmProfiles} aiSettings={aiSettings} onClose={() => setSettingsOpen(false)} onChanged={systemState.setProfiles} onSettingsChanged={setAiSettings} onError={notifyError} />
  </Layout>
}
