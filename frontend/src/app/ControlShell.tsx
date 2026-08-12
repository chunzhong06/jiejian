/* =============================================================================
 * 前端控制壳
 *
 * 定位
 *   六个用户阶段、HashRouter 与本地恢复状态之间的页面组合边界
 *
 * 职责
 *   装配能力页面｜恢复当前 Project/Run｜统一显示 API 错误与阶段导航
 *
 * 调用链
 *   main.tsx → ControlShell → feature pages / API clients
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Layout, Menu, Result, Steps, Tag, Typography } from 'antd'
import { AppstoreOutlined, CheckCircleOutlined, FileSearchOutlined, PlayCircleOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { HashRouter, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/http'
import { projectsApi } from '../api/projects'
import { runsApi } from '../api/runs'
import { llmApi, LLMProfile } from '../api/llm'
import { systemApi, SystemStatus } from '../api/system'
import { AccessPage } from '../features/access/AccessPage'
import { ContractPage } from '../features/contracts/ContractPage'
import { RecordingPage } from '../features/recording/RecordingPage'
import { ReportPage } from '../features/results/ReportPage'
import { RunPage } from '../features/runs/RunPage'
import { VerifyPage } from '../features/verification/VerifyPage'
import LLMSettingsDrawer from '../features/settings/LLMSettingsDrawer'
import '../styles.css'

type Item = Record<string, any>
export const remembered = {
  project: 'jiejian.project',
  resource: 'jiejian.resource',
  cursor: 'jiejian.cursor',
}
const phases = [
  { key: 'access', label: '接入', icon: <AppstoreOutlined /> },
  { key: 'recording', label: '录制', icon: <PlayCircleOutlined /> },
  { key: 'contract', label: '建约', icon: <SafetyCertificateOutlined /> },
  { key: 'run', label: '测试', icon: <CheckCircleOutlined /> },
  { key: 'verify', label: '验证', icon: <FileSearchOutlined /> },
  { key: 'report', label: '报告', icon: <FileSearchOutlined /> },
]

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

function remember(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value))
}

function recalled<T>(key: string): T | null {
  try {
    return JSON.parse(localStorage.getItem(key) ?? 'null') as T
  } catch {
    return null
  }
}

export default function ControlShell() {
  return <HashRouter><ControlShellContent /></HashRouter>
}

function ControlShellContent() {
  const location = useLocation()
  const navigate = useNavigate()
  const routePhase = phases.some((item) => `/${item.key}` === location.pathname)
    ? location.pathname.slice(1)
    : 'access'
  const [projects, setProjects] = useState<Item[]>([])
  const [selected, setSelected] = useState<Item | null>(null)
  const [runs, setRuns] = useState<Item[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(false)
  const [llmProfiles, setLlmProfiles] = useState<LLMProfile[]>([])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [llmLoadFailed, setLlmLoadFailed] = useState(false)
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({ api: 'unknown', worker: 'unknown', browser: 'unknown' })
  const refresh = async () => {
    try {
      const current = await projectsApi.projects()
      setProjects(current)
      const recalledProject = recalled<Item>(remembered.project)
      const authoritative = current.find((item) => item.project_id === recalledProject?.project_id)
      if (authoritative) setSelected(authoritative)
      else {
        setSelected(null)
        localStorage.removeItem(remembered.project)
      }
      setError(null)
    } catch (e) {
      setError(e as ApiError)
    }
  }
  const choose = (project: Item) => {
    setSelected(project)
    remember(remembered.project, project)
    navigate('/contract')
  }
  const refreshRuns = async () => {
    if (selected?.project_id) {
      try {
        setRuns(await runsApi.runs(selected.project_id))
      } catch (e) {
        setError(e as ApiError)
      }
    }
  }
  useEffect(() => { void refresh() }, [])
  useEffect(() => {
    void llmApi.profiles().then((profiles) => { setLlmProfiles(profiles); setLlmLoadFailed(false) }).catch(() => setLlmLoadFailed(true))
  }, [])
  const refreshSystemStatus = () => {
    void systemApi.status().then(setSystemStatus).catch(() => setSystemStatus({ api: 'unknown', worker: 'unknown', browser: 'unknown' }))
  }
  useEffect(() => {
    refreshSystemStatus()
    const onFocus = () => refreshSystemStatus()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [])
  useEffect(() => { void refreshRuns() }, [selected?.project_id])
  useEffect(() => {
    if (location.pathname !== `/${routePhase}`) {
      navigate('/access', { replace: true })
    }
  }, [location.pathname, navigate, routePhase])
  const activeRun = useMemo(() => runs[0], [runs])
  const register = async ({ path }: { path: string }) => {
    setLoading(true)
    try {
      choose(await projectsApi.registerProject(path))
      await refresh()
    } catch (e) {
      setError(e as ApiError)
    } finally {
      setLoading(false)
    }
  }
  const content = () => {
    if (routePhase === 'access') return <AccessPage projects={projects} selected={selected} runs={runs} onSelect={choose} onContinue={() => navigate('/contract')} onRegister={register} loading={loading} />
    if (!selected) return <Result status="info" title="请先在接入阶段选择项目" />
    if (routePhase === 'contract') return <ContractPage project={selected} profiles={llmProfiles} onError={setError} />
    if (routePhase === 'recording') return <RecordingPage project={selected} onError={setError} />
    if (routePhase === 'run') return <RunPage project={selected} runs={runs} onRefresh={refreshRuns} onError={setError} />
    if (routePhase === 'verify') return <VerifyPage run={activeRun} onError={setError} />
    return <ReportPage run={activeRun} onError={setError} />
  }
  return (
    <Layout className="app-shell">
      <Layout.Sider breakpoint="lg" collapsedWidth="0">
        <div className="brand">
          界鉴<span>安全意图差分验证与交付门禁</span>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[routePhase]}
          items={phases.map((item) => ({
            ...item,
            onClick: () => navigate(`/${item.key}`),
          }))}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header className="topbar">
          <Typography.Title className="topbar-title" level={3}>控制面</Typography.Title>
          <Button className="topbar-settings" type="link" onClick={() => setSettingsOpen(true)}>模型服务</Button>
          <div className="status-cluster">
            {([['API', systemStatus.api, { available: '可用', unknown: '未知' }], ['Worker', systemStatus.worker, { running: '运行中', stopped: '已停止', unknown: '未知' }], ['浏览器', systemStatus.browser, { available: '可用', unavailable: '不可用', unknown: '未知' }]] as const).map(([name, value, labels]) => { const item = statusTag(value, labels); return <Tag key={name} color={item.color}>{name} · {item.label}</Tag> })}
            {(() => { const value = llmStatus(llmProfiles, llmLoadFailed); const item = statusTag(value, { testing: '正在测试', available: '可用', unavailable: '不可用', configured: '已配置', offline: '离线', unknown: '未知' }); return <Tag color={item.color}>LLM · {item.label}</Tag> })()}
          </div>
        </Layout.Header>
        <Layout.Content className="content">
          <Steps
            current={Math.max(phases.findIndex((item) => item.key === routePhase), 0)}
            items={phases.map(({ label }) => ({ title: label }))}
            className="phase-steps"
            responsive={false}
          />
          {error && (
            <Alert
              closable
              showIcon
              type="error"
              message={`${error.code}: ${error.message}`}
              description={error.traceId ? `trace_id: ${error.traceId}` : undefined}
              onClose={() => setError(null)}
            />
          )}
          {content()}
        </Layout.Content>
      </Layout>
      <LLMSettingsDrawer open={settingsOpen} profiles={llmProfiles} onClose={() => setSettingsOpen(false)} onChanged={setLlmProfiles} onError={setError} />
    </Layout>
  )
}
