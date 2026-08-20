/* 产品工作台壳：集中处理任务导航、项目恢复、状态展示和错误恢复。 */

import { useEffect, useMemo, useState } from 'react'
import { Button, Layout, Menu, Result, Tag, Typography } from 'antd'
import { AppstoreOutlined, CloudServerOutlined, FileSearchOutlined, HistoryOutlined, PlayCircleOutlined, SettingOutlined } from '@ant-design/icons'
import { HashRouter, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/http'
import { projectsApi, type ProjectDto } from '../api/projects'
import { runsApi, type RunDto } from '../api/runs'
import { llmApi, LLMProfile } from '../api/llm'
import { systemApi, SystemStatus } from '../api/system'
import { onboardingApi } from '../api/onboarding'
import { ErrorRecovery } from '../components/ErrorRecovery'
import { AccessPage } from '../features/access/AccessPage'
import { PermissionRulesPage } from '../features/permissions/PermissionRulesPage'
import { CheckHistoryPage } from '../features/checks/CheckHistoryPage'
import { CheckResultsPage } from '../features/checks/CheckResultsPage'
import { StartCheckPage } from '../features/checks/StartCheckPage'
import { RecordingPage } from '../features/recording/RecordingPage'
import { ModelServicePage } from '../features/settings/ModelServicePage'
import LLMSettingsDrawer from '../features/settings/LLMSettingsDrawer'
import { RuntimePage } from '../features/system/RuntimePage'
import { WorkbenchPage } from '../features/workspace/WorkbenchPage'
import { navigationGroups, normalizeRoute, AppRoute } from './presentation'
import { browserState } from './browserState'
import '../styles.css'

function statusTag(value: string, labels: Record<string, string>) {
  const color = value === 'available' || value === 'running' ? 'green' : value === 'unavailable' || value === 'stopped' ? 'red' : value === 'configured' ? 'blue' : value === 'testing' ? 'gold' : 'default'
  return { color, label: labels[value] ?? '未知' }
}

export function llmStatus(profiles: LLMProfile[], failed: boolean) {
  if (failed) return 'unknown'
  if (profiles.some((item) => item.enabled && item.connection_status === 'testing')) return 'testing'
  if (profiles.some((item) => item.enabled && item.secret_configured && item.connection_status === 'available')) return 'available'
  if (profiles.some((item) => item.enabled && item.secret_configured && item.connection_status === 'unavailable')) return 'unavailable'
  if (profiles.some((item) => item.enabled && item.secret_configured)) return 'configured'
  return 'offline'
}

function MissingApplication({ onNavigate }: { onNavigate: () => void }) {
  return <Result status="info" title="先选择要检查的应用" subTitle="选择应用后才能查看这里的内容。" extra={<Button type="primary" onClick={onNavigate}>去应用接入</Button>} />
}

export default function ControlShell() { return <HashRouter><ControlShellContent /></HashRouter> }

function ControlShellContent() {
  const location = useLocation()
  const navigate = useNavigate()
  const route = normalizeRoute(location.pathname)
  const reportView = route === '/checks/results' && location.search === '?view=report'
  const [projects, setProjects] = useState<ProjectDto[]>([])
  const [selected, setSelected] = useState<ProjectDto | null>(null)
  const [runs, setRuns] = useState<RunDto[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(false)
  const [llmProfiles, setLlmProfiles] = useState<LLMProfile[]>([])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [llmLoadFailed, setLlmLoadFailed] = useState(false)
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({ api: 'unknown', worker: 'unknown', browser: 'unknown' })
  const [retryEpoch, setRetryEpoch] = useState(0)
  const [demoData, setDemoData] = useState(false)

  const refresh = async () => {
    try {
    const current = await projectsApi.projects()
      setProjects(current)
      const recalledProject = browserState.readProject()
      const authoritative = current.find((item) => item.project_id === recalledProject?.project_id)
      if (authoritative) setSelected(authoritative)
      else { setSelected(null); browserState.clearProject() }
      setError(null)
    } catch (e) { setError(e as ApiError) }
  }
  const choose = (project: ProjectDto) => { setSelected(project); setDemoData(false); browserState.writeProject(project); navigate('/apps/rules') }
  const onboardingSubmitted = async (result: { project_id: string; run_id: string; job_id: string; demo_data?: boolean }) => {
    setLoading(true); setDemoData(Boolean(result.demo_data))
    try {
      const current = await projectsApi.projects()
      setProjects(current)
      const project = current.find((item) => item.project_id === result.project_id) ?? await projectsApi.project(result.project_id)
      setSelected(project); browserState.writeProject(project); setRuns(await runsApi.runs(result.project_id)); navigate('/checks/start'); setError(null)
    } catch (e) { setError(e as ApiError) } finally { setLoading(false) }
  }
  const refreshRuns = async () => {
    if (!selected?.project_id) return
    try { setRuns(await runsApi.runs(selected.project_id)) } catch (e) { setError(e as ApiError) }
  }
  const retryCurrentPage = () => { setError(null); setRetryEpoch((epoch) => epoch + 1); void refresh(); void refreshRuns() }
  useEffect(() => { void refresh() }, [])
  useEffect(() => { void llmApi.profiles().then((profiles) => { setLlmProfiles(profiles); setLlmLoadFailed(false) }).catch(() => setLlmLoadFailed(true)) }, [])
  const refreshSystemStatus = () => { void systemApi.status().then(setSystemStatus).catch(() => setSystemStatus({ api: 'unknown', worker: 'unknown', browser: 'unknown' })) }
  useEffect(() => { refreshSystemStatus(); const onFocus = () => refreshSystemStatus(); window.addEventListener('focus', onFocus); return () => window.removeEventListener('focus', onFocus) }, [])
  useEffect(() => { void refreshRuns() }, [selected?.project_id])
  useEffect(() => { if (!selected?.project_id) return; void onboardingApi.demoStatus().then((status) => { if (status.project_id === selected.project_id && status.demo_data) setDemoData(true) }).catch(() => undefined) }, [selected?.project_id])
  useEffect(() => {
    if (location.pathname === '/report') { navigate({ pathname: '/checks/results', search: '?view=report' }, { replace: true }); return }
    if (location.pathname !== route) navigate(route, { replace: true })
  }, [location.pathname, navigate, route])

  const activeRun = useMemo(() => runs[0], [runs])
  const register = async ({ path }: { path: string }) => {
    setLoading(true)
    try { choose(await projectsApi.registerProject(path)); await refresh() } catch (e) { setError(e as ApiError) } finally { setLoading(false) }
  }
  const content = () => {
    if (route === '/workspace') return <WorkbenchPage selected={selected} runs={runs} systemStatus={systemStatus} profiles={llmProfiles} llmLoadFailed={llmLoadFailed} onNavigate={(path) => navigate(path)} onError={setError} />
    if (route === '/apps/access') return <AccessPage projects={projects} selected={selected} runs={runs} onSelect={choose} onContinue={() => navigate('/apps/rules')} onRegister={register} onOnboardingSubmitted={onboardingSubmitted} loading={loading} />
    if (route === '/advanced/models') return <ModelServicePage profiles={llmProfiles} onManage={() => setSettingsOpen(true)} />
    if (route === '/advanced/system') return <RuntimePage status={systemStatus} profiles={llmProfiles} failed={llmLoadFailed} />
    if (!selected) return <MissingApplication onNavigate={() => navigate('/apps/access')} />
    if (route === '/apps/rules') return <PermissionRulesPage key={`rules-${retryEpoch}`} project={selected} profiles={llmProfiles} onError={setError} onNext={() => navigate('/checks/start')} />
    if (route === '/checks/start') return <StartCheckPage key={`start-${retryEpoch}`} project={selected} runs={runs} onRefresh={refreshRuns} onError={setError} onNext={() => navigate('/checks/results')} />
    if (route === '/checks/history') return <CheckHistoryPage runs={runs} onError={setError} />
    if (route === '/advanced/recording') return <RecordingPage key={`recording-${retryEpoch}`} project={selected} onError={setError} onNext={() => navigate('/apps/rules')} />
    return <CheckResultsPage key={`results-${retryEpoch}`} run={activeRun} onError={setError} onNext={() => navigate('/checks/start')} initialView={reportView ? 'report' : 'results'} />
  }
  const menuItems = [
    { key: '/workspace', icon: <AppstoreOutlined />, label: '工作台' },
    ...navigationGroups.map((group) => ({ key: group.key, icon: group.key === 'apps' ? <SettingOutlined /> : group.key === 'checks' ? <FileSearchOutlined /> : <CloudServerOutlined />, label: group.label, children: group.items.map((item) => ({ key: item.key, label: item.label, icon: item.key === '/checks/history' ? <HistoryOutlined /> : item.key === '/advanced/recording' ? <PlayCircleOutlined /> : undefined })) })),
  ]
  const service = statusTag(systemStatus.api, { available: '可用', unknown: '未知' })
  const execution = statusTag(systemStatus.worker, { running: '运行中', stopped: '已停止', unknown: '未知' })
  const browser = statusTag(systemStatus.browser, { available: '可用', unavailable: '不可用', unknown: '未知' })
  const model = statusTag(llmStatus(llmProfiles, llmLoadFailed), { testing: '检查中', available: '可用', unavailable: '不可用', configured: '已配置', offline: '未配置', unknown: '未知' })
  return <Layout className="app-shell">
    <Layout.Sider breakpoint="lg" collapsedWidth="0"><div className="brand">界鉴<span>安全意图一致性验证</span></div><Menu theme="dark" mode="inline" defaultOpenKeys={['apps', 'checks', 'advanced']} selectedKeys={[route]} items={menuItems} onClick={({ key }) => { if (String(key).startsWith('/')) navigate(String(key)) }} /></Layout.Sider>
    <Layout><Layout.Header className="topbar"><Typography.Text className="topbar-context">{selected ? String(selected.name ?? '当前应用') : '尚未选择应用'}</Typography.Text><Button className="topbar-settings" type="link" onClick={() => setSettingsOpen(true)}>模型服务</Button><div className="status-cluster"><Tag color={service.color}>服务 · {service.label}</Tag><Tag color={execution.color}>执行 · {execution.label}</Tag><Tag color={browser.color}>浏览器 · {browser.label}</Tag><Tag color={model.color}>模型 · {model.label}</Tag></div></Layout.Header>
      <Layout.Content className="content">{error && <ErrorRecovery error={error} onRetry={retryCurrentPage} onBackAccess={() => { setError(null); navigate('/apps/access') }} onClose={() => setError(null)} />}{demoData && route !== '/apps/access' && <div className="demo-data-banner">演示数据，不代表真实项目</div>}{content()}</Layout.Content>
    </Layout>
    <LLMSettingsDrawer open={settingsOpen} profiles={llmProfiles} onClose={() => setSettingsOpen(false)} onChanged={setLlmProfiles} onError={setError} />
  </Layout>
}
