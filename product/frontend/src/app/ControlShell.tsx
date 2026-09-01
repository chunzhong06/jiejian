/* 产品工作台壳：集中处理任务导航、项目恢复、状态展示和错误恢复。 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Layout, Modal, Result } from 'antd'
import { HashRouter, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/http'
import { experienceApi, type OfficialExperienceDto } from '../api/experience'
import { mcpAccessApi, type MCPAccessView } from '../api/mcp'
import { projectsApi, type ProjectDto } from '../api/projects'
import { systemApi } from '../api/system'
import { ErrorRecovery } from '../components/ErrorRecovery'
import { DesktopModuleNavigation, MobileModuleNavigation } from '../components/ModuleNavigation'
import { AccessPage } from '../features/access/AccessPage'
import { TestIdentityPage } from '../features/identities/TestIdentityPage'
import { CheckHistoryPage } from '../features/checks/CheckHistoryPage'
import { PermissionCheckPage } from '../features/checks/PermissionCheckPage'
import { CheckResultsPage } from '../features/checks/CheckResultsPage'
import { VerificationPage } from '../features/checks/VerificationPage'
import { ChangesPage } from '../features/changes/ChangesPage'
import { PreparationPage } from '../features/preparation/PreparationPage'
import { RecordingPage } from '../features/recording/RecordingPage'
import { PresentationMode } from '../features/presentation/PresentationMode'
import { ModelServicePage } from '../features/settings/ModelServicePage'
import LLMSettingsDrawer from '../features/settings/LLMSettingsDrawer'
import { RuntimePage } from '../features/system/RuntimePage'
import { TestingPage } from '../features/testing/TestingPage'
import { ToolsPage } from '../features/tools/ToolsPage'
import { WorkbenchPage } from '../features/workspace/WorkbenchPage'
import { aiStatusLabel, AppHeader } from './AppHeader'
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
  const [presentationOpen, setPresentationOpen] = useState(false)
  const [presentationReturnRoute, setPresentationReturnRoute] = useState<AppRoute>('/workspace')
  const [mcpStatus, setMcpStatus] = useState<MCPAccessView | null>(null)
  const [mcpStatusFailed, setMcpStatusFailed] = useState(false)
  const updateNotifications = useCallback((updater: (items: NotificationItem[]) => NotificationItem[]) => setNotifications(updater), [])
  // 工作区加载失败会阻断整个控制面；页面内操作失败只进入通知，避免同一错误重复覆盖页面。
  const showBlockingError = useCallback((nextError: ApiError) => setError(nextError), [])
  const notifyError = useCallback((nextError: ApiError) => {
    setNotifications((items) => enqueueNotification(items, nextError, Date.now()))
  }, [])
  const updateMcpStatus = useCallback((next: MCPAccessView) => {
    setMcpStatus(next)
    setMcpStatusFailed(false)
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
    if (state !== 'CREDENTIAL_READY' && state !== 'AUTHENTICATED') return
    let active = true
    // 客户端在壳层首次读取之后才发出请求时，短轮询负责把真实连接事实同步到顶部；连接成立即停止。
    const timer = window.setInterval(() => {
      void mcpAccessApi.status().then((value) => {
        if (active) updateMcpStatus(value)
      }).catch(() => {
        if (active) setMcpStatusFailed(true)
      })
    }, 2_000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [mcpStatus?.connection_state, updateMcpStatus])

  const choose = (project: ProjectDto) => { workspace.selectProject(project); navigate('/workspace') }
  const connectForAccess = (project: ProjectDto) => { workspace.selectProject(project); clearError() }
  const refreshRuns = useCallback(async () => {
    await workspace.refreshCurrent()
  }, [workspace.refreshCurrent])
  const retryCurrentPage = () => { clearError(); setRetryEpoch((epoch) => epoch + 1); void workspace.refreshProjects(); void workspace.refreshCurrent() }
  const requestShutdown = () => setShutdownConfirmOpen(true)
  const removeCurrentProject = async () => {
    if (!selected) return
    const removedActiveExperience = experience?.active === true && experience.project_id === selected.project_id
    setRemoveBusy(true)
    try {
      await projectsApi.remove(selected.project_id)
      setRemoveConfirmOpen(false)
      await workspace.refreshProjects()
      if (removedActiveExperience) {
        experienceApi.status().then(setExperience).catch((statusError) => notifyError(statusError as ApiError))
      }
      navigate('/workspace')
    } catch (removeError) {
      notifyError(removeError as ApiError)
    } finally {
      setRemoveBusy(false)
    }
  }
  const activeOfficialProject = experience?.active === true && experience.project_id === selected?.project_id
  const scenarioRuns = useMemo(() => {
    const scenarioChangedAt = experience?.scenario_changed_at_us
    if (!activeOfficialProject || typeof scenarioChangedAt !== 'number') return runs
    return runs.filter((run) => {
      const createdAt = run.created_at_us ?? run.created_at
      return typeof createdAt === 'number' && createdAt >= scenarioChangedAt
    })
  }, [activeOfficialProject, experience?.scenario_changed_at_us, runs])
  const activeRun = useMemo(() => scenarioRuns[0], [scenarioRuns])
  const statusLatestResult = status?.latest_result
  const currentLatestResult = !activeOfficialProject
    ? statusLatestResult ?? null
    : statusLatestResult && statusLatestResult.run_id === activeRun?.run_id
      ? statusLatestResult
      : null
  const repairReadyToVerify = status?.repair?.status === 'READY_TO_VERIFY'
  const currentCheckChangeId = repairReadyToVerify
    ? status?.repair?.tasks.find((task) => task.status === 'READY_TO_VERIFY')?.linked_change_id ?? undefined
    : (
      status?.revalidation?.status === 'READY'
        ? status.revalidation.change_id ?? undefined
        : undefined
    )
  const startOfficialExperience = async () => {
    setExperienceBusy(true)
    try {
      const started = await experienceApi.start()
      setExperience(started)
      const currentProjects = await workspace.refreshProjects()
      const project = currentProjects.find((item) => item.project_id === started.project_id)
      if (project) {
        workspace.selectProject(project)
        // 启动返回的新项目不能等待下一轮 effect 再恢复，否则真实浏览器会短暂丢失样例状态区。
        await workspace.refreshCurrent(project)
      }
      navigate('/workspace')
      return true
    } catch (experienceError) {
      notifyError(experienceError as ApiError)
      return false
    } finally {
      setExperienceBusy(false)
    }
  }
  const stopOfficialExperience = async () => {
    setExperienceBusy(true)
    try {
      setPresentationOpen(false)
      setExperience(await experienceApi.stop())
      // 后端会把一次性样例 Project 一并归档；重新读取应用列表，避免前端保留失效目录。
      await workspace.refreshProjects()
      navigate('/workspace')
    } catch (experienceError) {
      notifyError(experienceError as ApiError)
    } finally {
      setExperienceBusy(false)
    }
  }
  const prepareOfficialScenario = async () => {
    setExperienceBusy(true)
    try {
      setExperience(await experienceApi.prepare())
      await workspace.refreshCurrent()
    } catch (experienceError) {
      notifyError(experienceError as ApiError)
    } finally {
      setExperienceBusy(false)
    }
  }
  const switchOfficialVersion = async (version: 'VULNERABLE' | 'EVIDENCE_LIMITED' | 'FIXED', sourceRunId?: string) => {
    setExperienceBusy(true)
    try {
      setExperience(await experienceApi.switchVersion(version, sourceRunId))
      await workspace.refreshCurrent()
      // 版本切换后回到唯一主控工作台；变化与测试仍是可以自由进入的辅助模块。
      navigate('/workspace')
    } catch (experienceError) {
      notifyError(experienceError as ApiError)
    } finally {
      setExperienceBusy(false)
    }
  }
  const continuePreparation = async () => {
    if (!selected?.project_id) {
      navigate('/application')
      return
    }
    const snapshot = await workspace.refreshCurrent()
    if (!snapshot) return
    const preparation = snapshot.readiness?.preparation
    if (!preparation) {
      navigate('/application')
      return
    }
    if (preparation.ready) {
      navigate('/validation')
      return
    }
    navigate(normalizeRoute(preparation.next_path ?? '/preparation'))
  }
  const prepareCurrentProject = async () => {
    if (!selected?.project_id) return
    try {
      await projectsApi.prepareSafe(selected.project_id)
      await workspace.refreshCurrent()
    } catch (preparationError) {
      notifyError(preparationError as ApiError)
    }
  }
  useEffect(() => {
    if (location.pathname !== route) navigate(route, { replace: true })
  }, [location.pathname, navigate, route])
  useEffect(() => {
    if (route !== '/validation' || repairReadyToVerify || !status?.revalidation) return
    if (activeOfficialProject && !activeRun) return
    if (['NO_CHANGE', 'READY'].includes(status.revalidation.status)) return
    if (status.revalidation.next_path && status.revalidation.next_path !== '/validation') {
      navigate(status.revalidation.next_path, { replace: true })
    }
  }, [activeOfficialProject, activeRun, navigate, repairReadyToVerify, route, status?.revalidation])
  useEffect(() => {
    if (
      presentationOpen
      && (!experience?.active || !selected?.project_id || experience.project_id !== selected.project_id)
    ) setPresentationOpen(false)
  }, [experience?.active, experience?.project_id, presentationOpen, selected?.project_id])
  useEffect(() => {
    if (
      !selected?.project_id
      || !['/tests', '/preparation', '/results', '/verification', '/history'].includes(route)
    ) return
    // 准备事实与 Run 都可能在其他页面或进程形成，返回汇总页时重新读取权威工作区状态。
    void refreshRuns()
  }, [refreshRuns, route, selected?.project_id])

  const navigateTo = (path: AppRoute) => navigate(path)
  const enterPresentation = () => {
    if (!experience?.active || experience.project_id !== selected?.project_id) return
    setPresentationReturnRoute(route)
    setPresentationOpen(true)
  }
  const leavePresentation = () => {
    setPresentationOpen(false)
    navigate(presentationReturnRoute)
  }
  const content = () => {
    if (route === '/workspace') return <WorkbenchPage selected={selected} readiness={readiness} status={status} runs={runs} systemStatus={systemStatus} experience={experience} experienceBusy={experienceBusy} onStartExperience={startOfficialExperience} onPrepareExperience={() => { void prepareOfficialScenario() }} onRunExperience={() => navigate('/validation')} onSwitchExperience={(version, sourceRunId) => { void switchOfficialVersion(version, sourceRunId) }} onStopExperience={stopOfficialExperience} onEnterPresentation={enterPresentation} onNavigate={(path) => navigate(path)} onError={notifyError} />
    if (route === '/tools') return <ToolsPage projects={projects} onError={notifyError} onStatusChange={updateMcpStatus} />
    if (route === '/application') return <AccessPage selected={selected} endpointStatus={readiness?.endpoint_status} officialSampleAvailable={experience?.available === true} officialSampleBusy={experienceBusy} onStartOfficialSample={startOfficialExperience} onConnected={connectForAccess} onUnderstandingChanged={() => { void workspace.refreshCurrent() }} onBack={() => navigate('/workspace')} onContinue={() => navigate('/permissions')} />
    if (route === '/settings/models') return <ModelServicePage profiles={llmProfiles} onManage={() => setSettingsOpen(true)} />
    if (route === '/settings/system') return <RuntimePage status={systemStatus} profiles={llmProfiles} failed={llmLoadFailed} />
    if (!selected) return <MissingApplication onNavigate={() => navigate('/application')} />
    if (route === '/changes') return <ChangesPage project={selected} status={status} onError={notifyError} onNavigate={(path) => navigate(normalizeRoute(path))} />
    if (route === '/identities') return <TestIdentityPage key={`identities-${selected.project_id}-${retryEpoch}`} project={selected} onError={notifyError} onBack={() => navigate('/permissions')} onStateChanged={workspace.refreshCurrent} onContinuePreparation={continuePreparation} />
    if (route === '/flows') return <RecordingPage key={`recording-${retryEpoch}`} project={selected} onError={notifyError} onBack={() => navigate('/permissions')} onStateChanged={workspace.refreshCurrent} onContinuePreparation={continuePreparation} />
    if (route === '/permissions') return <PermissionCheckPage mode="permissions" key={`permissions-${retryEpoch}`} project={selected} runs={scenarioRuns} onRefresh={refreshRuns} onError={notifyError} onResolved={() => resolveRouteErrors(['/permissions'])} onNavigate={(path) => navigate(normalizeRoute(path))} onBack={() => navigate('/workspace')} onContinuePreparation={continuePreparation} />
    if (route === '/tests') return status && readiness ? <TestingPage status={status} readiness={readiness} runs={scenarioRuns} latestResult={currentLatestResult} onNavigate={(path) => navigate(path)} /> : <MissingApplication onNavigate={() => navigate('/application')} />
    if (route === '/preparation') return readiness ? <PreparationPage readiness={readiness} onPrepareSafe={prepareCurrentProject} onNavigate={(path) => navigate(normalizeRoute(path))} /> : <MissingApplication onNavigate={() => navigate('/application')} />
    if (route === '/validation') {
      if (!status) return <Result status="info" title="正在确认当前检查状态" subTitle="界鉴会先核对代码变化、权限规则和测试准备，再开放验证运行。" />
      if (status.repair && !['NONE', 'READY_TO_VERIFY', 'VERIFIED'].includes(status.repair.status)) {
        return <Result status="info" title={status.repair.next_label ?? '当前修复尚未就绪'} subTitle="请先完成当前修复任务，再开始独立复验。" />
      }
      if (!repairReadyToVerify && !(activeOfficialProject && !activeRun) && status.revalidation && !['NO_CHANGE', 'READY'].includes(status.revalidation.status)) {
        return <Result status="info" title={status.revalidation.summary} subTitle="当前前置事项完成后，才能开始这次检查。" />
      }
      return <PermissionCheckPage mode="validation" key={`validation-${retryEpoch}-${experience?.scenario_changed_at_us ?? currentCheckChangeId ?? 'baseline'}`} project={selected} runs={scenarioRuns} changeId={currentCheckChangeId} onRefresh={refreshRuns} onError={notifyError} onResolved={() => resolveRouteErrors(['/validation'])} onNavigate={(path) => navigate(normalizeRoute(path))} onBack={() => navigate('/tests')} onResult={() => navigate('/results')} />
    }
    if (route === '/history') return <CheckHistoryPage projectId={selected.project_id} onError={notifyError} onBack={() => navigate('/results')} />
    if (route === '/verification') return <VerificationPage key={`verification-${retryEpoch}`} run={activeRun} onError={notifyError} onBack={() => navigate('/results')} onHistory={() => navigate('/history')} />
    return <CheckResultsPage key={`results-${retryEpoch}`} run={activeRun} onError={notifyError} onBack={() => navigate('/tests')} onHistory={() => navigate('/history')} onVerification={() => navigate('/verification')} onNavigate={(path) => navigate(normalizeRoute(path))} repair={status?.repair} inconclusiveRecovery={status?.inconclusive_recovery} />
  }
  if (shutdownRequested) return <Result status="success" title="界鉴正在安全退出" subTitle="服务、Worker 和受控浏览器清理完成后，可以关闭此页面；下次启动会自动检查异常中断记录。" />
  if (presentationOpen && experience?.active && selected && experience.project_id === selected.project_id) return <PresentationMode
    experience={experience}
    projectName={selected.name?.trim() || experience.display_name}
    runs={scenarioRuns}
    onExit={leavePresentation}
    onOpenProductRoute={(path) => { setPresentationOpen(false); navigate(path) }}
  />
  return <Layout className="app-shell">
    <DesktopModuleNavigation route={route} areas={status?.areas ?? null} aiLabel={assistantStatus} onNavigate={navigateTo} onOpenAI={() => setSettingsOpen(true)} onRequestShutdown={requestShutdown} />
    <Layout className="product-main">
      <MobileModuleNavigation route={route} areas={status?.areas ?? null} aiLabel={assistantStatus} onNavigate={navigateTo} onOpenAI={() => setSettingsOpen(true)} onRequestShutdown={requestShutdown} />
      <AppHeader projects={projects} selected={selected} activeTask={readiness?.active_tasks[0]} mcpStatus={mcpStatus} mcpStatusFailed={mcpStatusFailed} systemStatus={systemStatus} onSelectProject={choose} onConnectNew={() => navigate('/application')} onRemoveCurrent={() => setRemoveConfirmOpen(true)} onNavigate={navigate} />
      <Layout.Content className="content"><div className="content-frame">{error && <ErrorRecovery error={error} onRetry={retryCurrentPage} onNavigate={(path) => { clearError(); navigate(normalizeRoute(path)) }} onClose={clearError} />}{content()}</div></Layout.Content>
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
