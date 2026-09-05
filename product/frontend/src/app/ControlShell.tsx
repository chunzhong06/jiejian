/* 当前产品壳：只接入动作级 Workspace、应用接入、业务边界和明确不可用区域。 */

import { useCallback, useEffect, useState } from 'react'
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
import { BusinessBoundaryPage } from '../features/boundaries/BusinessBoundaryPage'
import LLMSettingsDrawer from '../features/settings/LLMSettingsDrawer'
import { RuntimePage } from '../features/system/RuntimePage'
import { ToolsPage } from '../features/tools/ToolsPage'
import { WorkbenchPage } from '../features/workspace/WorkbenchPage'
import { aiStatusLabel, AppHeader } from './AppHeader'
import { NotificationCenter, enqueueNotification, useNotificationExpiry, type NotificationItem } from './NotificationCenter'
import { normalizeRoute, type AppRoute } from './presentation'
import { useProjectWorkspace } from './useProjectWorkspace'
import { useSystemStatus } from './useSystemStatus'
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
  const { projects, selected, workspace } = workspaceState
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

  useEffect(() => {
    if (location.pathname === '/settings/models') {
      setSettingsOpen(true)
      navigate('/workspace', { replace: true })
      return
    }
    if (location.pathname !== route) navigate(route, { replace: true })
  }, [location.pathname, navigate, route])

  const choose = (project: ProjectDto) => { workspaceState.selectProject(project); navigate('/workspace') }
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
    navigate(normalizeRoute(path))
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

  const content = () => {
    if (route === '/workspace') return <WorkbenchPage selected={selected} workspace={workspace} systemStatus={systemStatus} experience={experience} onNavigate={(path) => navigate(path)} />
    if (route === '/tools') return <ToolsPage projects={projects} onError={notifyError} onStatusChange={updateMcpStatus} />
    if (route === '/application') return <AccessPage selected={selected} endpointStatus={workspace?.connection.endpoint_status} officialSampleAvailable={false} onConnected={connectForAccess} onUnderstandingChanged={() => { void workspaceState.refreshCurrentWorkspace() }} onBack={() => navigate('/workspace')} onContinue={() => navigate('/permissions')} />
    if (route === '/settings/system') return <RuntimePage status={systemStatus} profiles={llmProfiles} failed={llmLoadFailed} />
    if (!selected) return <MissingApplication onNavigate={() => navigate('/application')} />
    if (route === '/permissions') return <BusinessBoundaryPage key={`permissions-${selected.project_id}-${retryEpoch}`} project={selected} onError={notifyError} onStateChanged={workspaceState.refreshCurrentWorkspace} onBack={() => navigate('/workspace')} />
    if (route === '/changes') return <CurrentUnavailableArea title="变化与修复当前暂不可用" description="当前尚不支持代码变化分析、修复与复验。可返回工作台查看当前待办。" onBack={() => navigate('/workspace')} />
    if (route === '/tests') return <CurrentUnavailableArea title="当前不可检查" description="可维护业务权限和实现映射；当前尚不支持准备测试材料或运行权限检查。" onBack={() => navigate('/workspace')} />
    return <CurrentUnavailableArea title="此历史入口当前不可用" description="该页面属于尚未接回的 Recording、Run、Result 或修复主链。" onBack={() => navigate('/workspace')} />
  }

  if (shutdownRequested) return <Result status="success" title="界鉴正在安全退出" subTitle="服务清理完成后，可以关闭此页面。" />
  return <Layout className="app-shell">
    <DesktopModuleNavigation route={route} areas={workspace?.areas ?? null} onNavigate={(path: AppRoute) => navigate(path)} />
    <Layout className="product-main">
      <MobileModuleNavigation route={route} areas={workspace?.areas ?? null} onNavigate={(path: AppRoute) => navigate(path)} />
      <AppHeader projects={projects} selected={selected} mcpStatus={mcpStatus} mcpStatusFailed={mcpStatusFailed} systemStatus={systemStatus} onSelectProject={choose} onConnectNew={() => navigate('/application')} onRemoveCurrent={() => setRemoveConfirmOpen(true)} onNavigate={navigate} aiLabel={assistantStatus} onOpenAI={() => setSettingsOpen(true)} onRequestShutdown={() => setShutdownConfirmOpen(true)} />
      <Layout.Content className="content"><div className="content-frame">{error && <ErrorRecovery error={error} onRetry={retryCurrentPage} onNavigate={(path) => { clearError(); navigateRecoveryTarget(path) }} onClose={clearError} />}{content()}</div></Layout.Content>
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
  </Layout>
}
