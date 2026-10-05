/* 全局顶部栏：呈现当前应用、活动任务和结构化系统工具入口。 */

import { Button, Dropdown, Layout, Space } from 'antd'
import { useEffect, useState } from 'react'
import { ApiOutlined, BgColorsOutlined, LogoutOutlined, SettingOutlined, RobotOutlined, SearchOutlined, AppstoreOutlined } from '@ant-design/icons'
import type { LLMProfile, AIAssistanceSettings } from '../../api/assistance/llm'
import type { MCPAccessView } from '../../api/system/mcp'
import type { ProjectDto } from '../../api/applications/projects'
import type { SystemStatus } from '../../api/system/system'
import { ApplicationSwitcher } from '../navigation/ApplicationSwitcher'
import { useThemeMode, type ThemeMode, type MotionMode, type DensityMode } from '../theme/ThemeContext'
import { EntrySearch } from '../navigation/EntrySearch'

export function aiStatusLabel(
  profiles: LLMProfile[],
  settings: AIAssistanceSettings,
  profilesFailed: boolean,
  settingsFailed: boolean,
) {
  if (profilesFailed || settingsFailed) return 'AI辅助 · 状态未知'
  if (!settings.enabled) return 'AI辅助 · 未开启'
  if (!settings.default_profile_name) return 'AI辅助 · 待配置'
  const profile = profiles.find((item) => item.profile_name === settings.default_profile_name)
  if (!profile) return 'AI辅助 · 待配置'
  if (profile.model) return `AI辅助 · ${profile.model}`
  return 'AI辅助 · 已配置'
}

export function systemStatusLabel(status: SystemStatus) {
  if (status.api === 'unknown') return '状态未知'
  return status.api === 'available'
    && (status.worker === 'running' || status.worker === 'unavailable')
    && status.browser === 'available'
    ? '系统正常'
    : '系统需处理'
}

export function mcpStatusLabel(status: MCPAccessView | null, failed: boolean) {
  if (failed) return 'Coding Agent · 状态未知'
  if (!status) return 'Coding Agent · 正在读取'
  const state = status.connection_state
    ?? (!status.paired ? 'DISABLED' : !status.accepting_connections ? 'PAUSED' : status.client_connected ? 'CONNECTED' : 'CREDENTIAL_READY')
  if (state === 'DISABLED') return 'Coding Agent · 未准备'
  if (state === 'CREDENTIAL_READY') return 'Coding Agent · 等待连接'
  if (state === 'AUTHENTICATED') return 'Coding Agent · 正在确认连接'
  if (state === 'CREDENTIAL_REJECTED') return 'Coding Agent · 凭据需更新'
  if (state === 'CONNECTED') return `Coding Agent · ${status.client_name?.trim() || '已连接'}`
  return 'Coding Agent · 已暂停'
}

type AppHeaderProps = {
  projects: ProjectDto[]
  selected: ProjectDto | null
  mcpStatus: MCPAccessView | null
  mcpStatusFailed: boolean
  systemStatus: SystemStatus
  onSelectProject: (project: ProjectDto) => void
  onConnectNew: () => void
  onNavigate: (path: string) => void
  aiLabel: string
  onOpenAI: () => void
  onRequestShutdown: () => void
}

export function AppHeader({
  projects,
  selected,
  mcpStatus,
  mcpStatusFailed,
  systemStatus,
  onSelectProject,
  onConnectNew,
  onNavigate,
  aiLabel,
  onOpenAI,
  onRequestShutdown,
}: AppHeaderProps) {
  const { mode, setMode, motion, setMotion, density, setDensity } = useThemeMode()
  const [menuOpen, setMenuOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  useEffect(() => {
    const search = (event: KeyboardEvent) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setSearchOpen(value => !value) } }
    window.addEventListener('keydown', search)
    return () => window.removeEventListener('keydown', search)
  }, [])
  // 主题或视口变化后关闭旧浮层；再次打开时由组件按当前布局定位。
  useEffect(() => { setMenuOpen(false) }, [mode])
  useEffect(() => {
    const close = () => setMenuOpen(false)
    window.addEventListener('resize', close)
    return () => window.removeEventListener('resize', close)
  }, [])
  const themeLabels: Record<ThemeMode, string> = { system: '跟随系统', light: '亮色', dark: '暗色' }
  const mcpLabel = mcpStatusLabel(mcpStatus, mcpStatusFailed)
  const mcpConnected = mcpStatus?.connection_state === 'CONNECTED'
  const compactMcpLabel = mcpConnected ? `${mcpStatus?.client_name?.trim() || '开发客户端'} · 已连接` : mcpLabel.replace(/^Coding Agent/, '开发工具')
  return <><Layout.Header className="topbar">
    <div className="topbar-left">
      <button className="product-brand" aria-label="界鉴总览" onClick={() => onNavigate('/workspace')}><svg width="27" height="27" viewBox="0 0 28 28" fill="none" aria-hidden="true"><path d="M17 4H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V11" stroke="currentColor" strokeWidth="3" strokeLinejoin="round"/><path d="m19 3 7 7-7 5-5-7 5-5Z" fill="currentColor"/></svg><strong>界鉴</strong></button>
      <ApplicationSwitcher projects={projects} selected={selected} onSelect={onSelectProject} onConnectNew={onConnectNew} />

    </div>
    <Space className="topbar-tools" size="small">
      <Button type="text" icon={<SearchOutlined />} aria-label="查找入口，Ctrl K" onClick={() => setSearchOpen(true)}><span>查找入口</span><kbd>Ctrl K</kbd></Button>
      <Button className="topbar-agent-entry" type="text" icon={<ApiOutlined />} aria-label={`${mcpLabel}，打开开发工具连接`} onClick={() => onNavigate('/tools')}><span>{compactMcpLabel}</span><i className={`topbar-status-dot${mcpConnected ? ' is-connected' : ''}`} aria-hidden="true" /></Button>
      <Dropdown trigger={['click']} placement="bottomRight" menu={{ triggerSubMenuAction: 'click', selectable: true, selectedKeys: [`theme:${mode}`, `motion:${motion}`, `density:${density}`], items: [
        { key: 'theme', label: `主题 · ${themeLabels[mode]}`, children: [{key:'theme:system',label:'跟随系统'},{key:'theme:light',label:'亮色'},{key:'theme:dark',label:'暗色'}] },
        { key: 'motion', label: '动效', children: [{key:'motion:full',label:'完整动效'},{key:'motion:soft',label:'减少动效'},{key:'motion:off',label:'关闭动效'}] },
        { key: 'density', label: '密度', children: [{key:'density:comfortable',label:'舒适'},{key:'density:compact',label:'紧凑'}] },
      ], onClick: ({key}) => { const [kind,value] = key.split(':'); if(kind==='theme')setMode(value as ThemeMode); if(kind==='motion')setMotion(value as MotionMode); if(kind==='density')setDensity(value as DensityMode) } }}><Button type="text" icon={<BgColorsOutlined />} aria-label="显示偏好">显示</Button></Dropdown>
      <Dropdown
        open={menuOpen}
        onOpenChange={setMenuOpen}
        destroyOnHidden
        placement="bottomRight"
        trigger={['click']}
        menu={{
          triggerSubMenuAction: 'click',
          items: [
            { key: 'system', icon: <span className="system-state-icon" aria-hidden="true"><i className={`system-state-dot${systemStatusLabel(systemStatus) === '系统正常' ? ' is-ready' : ''}`} /></span>, label: systemStatusLabel(systemStatus) },
            { key: 'application', icon: <AppstoreOutlined />, label: '应用与环境' },
            { key: 'ai', icon: <RobotOutlined />, label: `界鉴 AI 辅助 · ${aiLabel.replace(/^AI辅助 · /, '')}` },
            { type: 'divider' },
            { key: 'shutdown', danger: true, icon: <LogoutOutlined />, label: '退出界鉴' },
          ],
            onClick: ({ key }) => {
              setMenuOpen(false)
            if (key === 'ai') onOpenAI()
            else if (key === 'application') onNavigate('/environment')
            else if (key === 'system') onNavigate('/settings/system')
            else if (key === 'shutdown') onRequestShutdown()
            else if (key.startsWith('theme:')) setMode(key.slice('theme:'.length) as ThemeMode)
          },
        }}
      >
        <Button type="text" icon={<SettingOutlined />} aria-label="设置与更多">设置</Button>
      </Dropdown>
    </Space>
  </Layout.Header><EntrySearch open={searchOpen} onClose={() => setSearchOpen(false)} onNavigate={onNavigate} /></>
}
