/* 产品工作台壳：集中处理任务导航、项目恢复、状态展示和错误恢复。 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Layout, Menu, Modal, Result } from 'antd'
import { AppstoreOutlined, FileSearchOutlined, HistoryOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { HashRouter, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/http'
import { projectsApi, type ProjectDto } from '../api/projects'
import { systemApi } from '../api/system'
import { ErrorRecovery } from '../components/ErrorRecovery'
import { AccessPage } from '../features/access/AccessPage'
import { TestIdentityPage } from '../features/identities/TestIdentityPage'
import { PermissionRulesPage } from '../features/permissions/PermissionRulesPage'
import { CheckHistoryPage } from '../features/checks/CheckHistoryPage'
import { CheckResultsPage } from '../features/checks/CheckResultsPage'
import { StartCheckPage } from '../features/checks/StartCheckPage'
import { RecordingPage } from '../features/recording/RecordingPage'
import { ModelServicePage } from '../features/settings/ModelServicePage'
import LLMSettingsDrawer from '../features/settings/LLMSettingsDrawer'
import { RuntimePage } from '../features/system/RuntimePage'
import { WorkbenchPage } from '../features/workspace/WorkbenchPage'
import { AppHeader } from './AppHeader'
import { NotificationCenter, enqueueNotification, useNotificationExpiry, type NotificationItem } from './NotificationCenter'
import { navigationGroups, normalizeRoute } from './presentation'
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
  const reportView = route === '/checks/results' && location.search === '?view=report'
  const [error, setError] = useState<ApiError | null>(null)
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [loading, setLoading] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [retryEpoch, setRetryEpoch] = useState(0)
  const [shutdownConfirmOpen, setShutdownConfirmOpen] = useState(false)
  const [shutdownRequested, setShutdownRequested] = useState(false)
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
  const { projects, selected, readiness, runs } = workspace
  const { profiles: llmProfiles, profilesFailed: llmLoadFailed, aiSettings, setAiSettings, aiSettingsFailed, status: systemStatus } = systemState

  const choose = (project: ProjectDto) => { workspace.selectProject(project); navigate('/workspace') }
  const connectForAccess = (project: ProjectDto) => { workspace.selectProject(project); clearError() }
  const refreshRuns = workspace.refreshCurrent
  const retryCurrentPage = () => { clearError(); setRetryEpoch((epoch) => epoch + 1); void workspace.refreshProjects(); void workspace.refreshCurrent() }
  const requestShutdown = () => setShutdownConfirmOpen(true)
  useEffect(() => {
    if (location.pathname !== route) navigate(route, { replace: true })
  }, [location.pathname, navigate, route])

  const activeRun = useMemo(() => runs[0], [runs])
  const register = async ({ path }: { path: string }) => {
    setLoading(true)
    try { choose(await projectsApi.registerProject(path)); await workspace.refreshProjects() } catch (e) { notifyError(e as ApiError) } finally { setLoading(false) }
  }
  const content = () => {
    if (route === '/workspace') return <WorkbenchPage selected={selected} readiness={readiness} runs={runs} systemStatus={systemStatus} profiles={llmProfiles} llmLoadFailed={llmLoadFailed} onNavigate={(path) => navigate(path)} />
    if (route === '/apps/access') return <AccessPage projects={projects} selected={selected} runs={runs} onSelect={choose} onConnected={connectForAccess} onUnderstandingChanged={() => { void workspace.refreshCurrent() }} onContinue={() => navigate('/apps/identities')} onRegister={register} loading={loading} />
    if (route === '/settings/models') return <ModelServicePage profiles={llmProfiles} onManage={() => setSettingsOpen(true)} />
    if (route === '/settings/system') return <RuntimePage status={systemStatus} profiles={llmProfiles} failed={llmLoadFailed} />
    if (!selected) return <MissingApplication onNavigate={() => navigate('/apps/access')} />
    if (route === '/apps/rules') return <PermissionRulesPage key={`rules-${retryEpoch}`} project={selected} onError={notifyError} onResolved={() => resolveRouteErrors(['/apps/rules', '/checks/start'])} onNext={() => navigate('/checks/start')} />
    if (route === '/apps/identities') return <TestIdentityPage key={`identities-${selected.project_id}-${retryEpoch}`} project={selected} onError={notifyError} onNext={() => navigate('/apps/flows')} />
    if (route === '/checks/start') return <StartCheckPage key={`start-${retryEpoch}`} project={selected} runs={runs} onRefresh={refreshRuns} onError={notifyError} onResolved={() => resolveRouteErrors(['/checks/start', '/apps/rules'])} onPrepare={(path) => navigate(path)} onNext={() => navigate('/checks/results')} />
    if (route === '/checks/history') return <CheckHistoryPage projectId={selected.project_id} onError={notifyError} />
    if (route === '/apps/flows') return <RecordingPage key={`recording-${retryEpoch}`} project={selected} onError={notifyError} onNext={() => navigate('/apps/rules')} />
    return <CheckResultsPage key={`results-${retryEpoch}`} run={activeRun} onError={notifyError} onNext={() => navigate('/checks/start')} onNavigate={(path) => navigate(path)} initialView={reportView ? 'report' : 'results'} />
  }
  const menuItems = [
    { key: '/workspace', icon: <AppstoreOutlined />, label: '工作台' },
    ...navigationGroups.map((group) => ({ key: group.key, icon: group.key === 'apps' ? <AppstoreOutlined /> : <FileSearchOutlined />, label: group.label, children: group.items.map((item) => ({ key: item.key, label: item.label, icon: item.key === '/checks/history' ? <HistoryOutlined /> : item.key === '/apps/flows' ? <PlayCircleOutlined /> : undefined })) })),
  ]
  if (shutdownRequested) return <Result status="success" title="界鉴正在安全退出" subTitle="服务、Worker 和受控浏览器清理完成后，可以关闭此页面；下次启动会自动检查异常中断记录。" />
  return <Layout className="app-shell">
    <Layout.Sider breakpoint="lg" collapsedWidth="0"><div className="brand">界鉴<span>安全意图一致性验证</span></div><Menu theme="dark" mode="inline" defaultOpenKeys={['apps', 'checks']} selectedKeys={[route]} items={menuItems} onClick={({ key }) => { if (String(key).startsWith('/')) navigate(String(key)) }} /></Layout.Sider>
    <Layout><AppHeader projectName={selected ? (selected.name ?? '') : undefined} activeTask={readiness?.active_tasks[0]} profiles={llmProfiles} aiSettings={aiSettings} profilesFailed={llmLoadFailed} settingsFailed={aiSettingsFailed} systemStatus={systemStatus} onNavigate={navigate} onOpenAI={() => setSettingsOpen(true)} onRequestShutdown={requestShutdown} />
      <Layout.Content className="content">{error && <ErrorRecovery error={error} onRetry={retryCurrentPage} onNavigate={(path) => { clearError(); navigate(path) }} onClose={clearError} />}{content()}</Layout.Content>
    </Layout>
    <NotificationCenter items={notifications} onDismiss={dismissNotification} onNavigate={(path, key) => { dismissNotification(key); clearError(); navigate(path) }} />
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
